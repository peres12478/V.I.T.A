"""Barrido de continuidad de tinta de fechas (sin OCR ni formato esperado).

Comprueba bandas transversales de baja presencia de tinta comparadas con trazos
vigorosos a izquierda y derecha. Usa la mascara del inspector y la imagen BGR
original. Las lineas virtuales NO exigen letras en coordenadas fijas.

Si existe una discontinuidad compatible con una perdida de impresion, se devuelve
una alerta de REVISION (sin voto BIEN). Una ausencia sin referencia de contenido
no es por si sola prueba de que hubiera debido imprimirse un caracter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class Continuidad:
    sospechosa: bool
    confirmada: bool
    indice: float
    mascara: np.ndarray
    franjas: Tuple[Tuple[int, int, int, int], ...]
    lineas: int
    coincidencias: int
    motivo: str = ""


def _filas(ink: np.ndarray, altura_letra: float) -> list[tuple[int, int]]:
    """Segmenta renglones mediante proyeccion Y, sin imponer su cantidad."""
    h, w = ink.shape
    counts = np.sum(ink, axis=1).astype(np.float32)
    active = np.uint8(counts > max(3, round(w * 0.007)))
    k = max(3, min(7, int(round(altura_letra * .09))))
    active = cv2.morphologyEx(active[:, None], cv2.MORPH_CLOSE,
                              np.ones((k, 1), np.uint8))[:, 0]
    intervals: list[tuple[int, int]] = []
    start = None
    for y, present in enumerate(list(active) + [0]):
        if present and start is None:
            start = y
        if not present and start is not None:
            if y - start >= max(8, int(altura_letra * .40)):
                intervals.append((start, y))
            start = None
    # Si dos renglones casi se tocan, su proyeccion puede conectarlos.
    # Solo separar por un valle claro y si la region supera dos alturas
    # tipicas de trazo (estimadas desde los componentes, nunca caracteres OCR).
    result: list[tuple[int, int]] = []
    for ya, yb in intervals:
        length = yb - ya
        if length < 1.8 * altura_letra:
            result.append((ya, yb))
            continue
        ylo = ya + round(.28 * length)
        yhi = ya + round(.72 * length)
        smooth = cv2.GaussianBlur(counts[:, None], (1, 0),
                                  sigmaX=0, sigmaY=max(2., altura_letra*.14))[:, 0]
        valley = int(ylo + np.argmin(smooth[ylo:yhi + 1]))
        left = float(np.max(smooth[ya:valley])) if valley > ya else 0.
        right = float(np.max(smooth[valley + 1:yb])) if valley + 1 < yb else 0.
        if (valley - ya > altura_letra*.54 and yb - valley > altura_letra*.54
                and smooth[valley] < .64 * min(left, right)):
            result.extend([(ya, valley), (valley + 1, yb)])
        else:
            result.append((ya, yb))
    return result


def _altura_referencia(ink: np.ndarray) -> float:
    h, w = ink.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n < 2:
        return float(max(9, .22 * h))
    a = stats[1:, cv2.CC_STAT_AREA]
    hh = stats[1:, cv2.CC_STAT_HEIGHT]
    ww = stats[1:, cv2.CC_STAT_WIDTH]
    valid = (a >= 8) & (a < h*w*.08) & (hh >= 6) & (hh < h*.59) & (ww >= 2)
    values = hh[valid]
    if values.size < 3:
        return float(max(9, min(60, h * .22)))
    return float(np.clip(np.percentile(values, 75), 9, min(110, h*.75)))


def _candidatos(ink: np.ndarray, fila: tuple[int, int], glyph: float
                ) -> list[tuple[int, int, int, int, float]]:
    """Bandas largas donde falta tinta, respaldadas por tinta a ambos lados."""
    ya, yb = fila
    h, w = ink.shape
    columna = ink[ya:yb].sum(axis=0).astype(np.float32)
    nonzero = np.flatnonzero(columna)
    if nonzero.size < max(28, round(w*.025)):
        return []
    xmin = int(np.percentile(nonzero, 1))
    xmax = int(np.percentile(nonzero, 99))
    if xmax - xmin < max(glyph*4., w*.22):
        return []
    # Una ventana amplia no confunde espacios finos entre caracteres con
    # desaparicion de una FRANJA completa del texto.
    window = max(9, int(round(.58*glyph)))
    perfil = np.convolve(columna, np.ones(window, np.float32)/window,
                         mode='same')
    ref = float(np.percentile(perfil[xmin:xmax+1], 65))
    if ref < 1.5:
        return []
    low = perfil < max(.65, .23*ref)
    margin = max(window, int(.55*glyph))
    low[:xmin+margin] = False
    low[xmax-margin:] = False
    candidates: list[tuple[int,int,int,int,float]] = []
    a = None
    for x, zero in enumerate(list(low) + [False]):
        if zero and a is None:
            a = x
        if not zero and a is not None:
            b = x
            width = b - a
            if width < max(.82*glyph, window*.95):
                a = None
                continue
            if width > max(.48*(xmax-xmin), glyph*8.5):
                a = None
                continue
            # Comprobar que es realmente INTERIOR, con trazos suficientes a
            # ambos lados en un radio proporcional a la tipografia.
            reach = max(2*window, round(3.6*glyph))
            left = perfil[max(xmin, a-reach):a]
            right = perfil[b:min(xmax+1, b+reach)]
            if left.size and right.size and max(left) > .80*ref and max(right) > .80*ref:
                # Severidad relativa a grosor de la geometria, no a un
                # numero esperado de digitos, palabras o renglones.
                severity = min(1., width/max(glyph*2.5, 1.))
                candidates.append((a,ya,b,yb,severity))
            a = None
    return candidates


def detectar_barrido_continuidad(imagen_bgr: np.ndarray,
                                 mascara_tinta: np.ndarray) -> Continuidad:
    if (imagen_bgr is None or mascara_tinta is None
            or imagen_bgr.size == 0):
        return Continuidad(False, False, 0., np.zeros((0,0),np.uint8), (), 0, 0)
    h0, w0 = imagen_bgr.shape[:2]
    blank = np.zeros((h0,w0),np.uint8)
    if (mascara_tinta.shape[:2] != (h0,w0) or min(h0,w0) < 30
            or h0*w0 < 1800):
        return Continuidad(False, False, 0., blank, (), 0, 0)
    rotated = h0 > w0
    source = cv2.rotate(imagen_bgr, cv2.ROTATE_90_CLOCKWISE) if rotated else imagen_bgr
    ink = cv2.rotate(mascara_tinta, cv2.ROTATE_90_CLOCKWISE) if rotated else mascara_tinta
    ink = np.uint8(ink > 0)
    h, w = ink.shape
    if ink.sum() < max(60, .004 * h*w):
        return Continuidad(False, False, 0., blank, (), 0, 0)
    glyph = _altura_referencia(ink)
    lineas = _filas(ink, glyph)
    candidates = []
    for ln in lineas:
        candidates.extend(_candidatos(ink, ln, glyph))
    if not candidates:
        return Continuidad(False, False, 0., blank, (), len(lineas), 0)
    # Coincidencia entre dos renglones INDEPENDIENTES. Evita condenar
    # un espacio normal dentro de una sola fila de texto.
    matches = set()
    for i, (a,ya,b,yb,si) in enumerate(candidates):
        for j in range(i+1, len(candidates)):
            c,yc,d,yd,sj = candidates[j]
            if not (yb <= yc or yd <= ya):
                continue
            overlap = max(0,min(b,d)-max(a,c))
            if overlap >= max(.55*glyph, min(b-a,d-c)*.26):
                matches.update((i,j))
    strong = len(matches) >= 2
    # Medir primero si hay restos DEBILES en la imagen original.
    # Un espacio normal puede ser ancho y no es una anomalia de impresion.
    lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB)
    lum = lab[:,:,0].astype(np.float32)
    sigma = float(np.clip(.18*glyph, 3, 13))
    bg = cv2.GaussianBlur(lum, (0,0), sigmaX=sigma)
    contrast = np.maximum(bg-lum,0.)
    typical = float(np.percentile(contrast[ink > 0], 60)) if ink.any() else 0.
    threshold = max(3.0, .11*typical)
    ghost_fracs = []
    for a,ya,b,yb,si in candidates:
        observed = contrast[ya:yb,a:b]
        ghost_fracs.append(float(np.mean((observed > threshold) &
                          (observed < max(8.,typical*.55)))))
    # Se usan dos comprobaciones complementarias: restos de tinta tenue,
    # o una ausencia grande respecto al resto del mismo renglon.
    # Esta ultima solo causa REVISAR, jamas MAL sin corroboracion adicional.
    flagged_idx = []
    for i,c in enumerate(candidates):
        a,ya,b,yb,_ = c
        run = b-a
        row_ink = np.flatnonzero(ink[ya:yb].sum(axis=0))
        span = (float(np.percentile(row_ink,99)-np.percentile(row_ink,1))
                if row_ink.size else 0.)
        # Un hueco muy largo y totalmente limpio dentro de una misma fila
        # sigue siendo AMBIGUO: no se puede asegurar que falten caracteres.
        # Solo impide aprobar sin más evidencia cuando el hueco es grande
        # frente al resto de la linea, pero no ocupa media region de texto.
        vacio_inusual = (run > 2.8*glyph and span > 5*glyph and
                         run < .46*span and run < .36*w)
        if i in matches or (ghost_fracs[i] > .085 and
                            run >= max(1.6*glyph, .12*w)) or vacio_inusual:
            flagged_idx.append(i)
    if not flagged_idx:
        return Continuidad(False, False, 0., blank, (), len(lineas), 0)
    flagged = [candidates[i] for i in flagged_idx]
    mask = np.zeros_like(ink)
    for i in flagged_idx:
        a,ya,b,yb,si = candidates[i]
        observed = contrast[ya:yb,a:b]
        # Estas son las dos lineas verticales virtuales que delimitan
        # la region baja en tinta. Son MARCAS DE DEPURACION, no una suposicion
        # sobre el contenido o la posicion de caracteres.
        cv2.line(mask,(a,ya),(a,yb-1),255,1)
        cv2.line(mask,(b-1,ya),(b-1,yb-1),255,1)
        ghost = np.uint8((observed>threshold) &
                         (observed<max(8.,typical*.55))) * 255
        if ghost.shape[0] and ghost.shape[1]:
            mask[ya:yb,a:b] = cv2.bitwise_or(mask[ya:yb,a:b], ghost)
    # Evitar que la cámara convierta una sombra sin contornos en defecto:
    # el doble valle es una sospecha; MAL solo con huellas tenues localizadas
    # de densidad intermedia, no con cualquier variacion de contraste.
    confirmed = bool(strong and sum(.075 < ghost_fracs[i] < .22 for i in matches)>=2)
    indice = float(max(c[4] for c in flagged))
    if rotated:
        mask = cv2.rotate(mask,cv2.ROTATE_90_COUNTERCLOCKWISE)
        boxes = tuple((ya, w-b, yb, w-a) for a,ya,b,yb,_ in flagged)
    else:
        boxes = tuple((a,ya,b,yb) for a,ya,b,yb,_ in flagged)
    return Continuidad(True, confirmed, round(indice,3), mask, boxes,
                       len(lineas), len(matches),
                       ('Ausencia de tinta alineada en varios renglones; '
                        'hay restos debiles compatibles con impresion parcialmente borrada'
                        if confirmed else
                        'Franja de tinta anormalmente escasa entre trazos; '
                        'requiere corroboracion, sin suponer caracteres esperados'))

"""Auditoria de islas de tinta incompleta sobre la mascara REAL del inspector.

Complementa el barrido de continuidad: busca zonas interiores con grandes
caidas de densidad y restos de trazos fragmentados. NO cuenta caracteres,
ni requiere filas/formato fijos. La mascara por si sola NO prueba que
haya habido un caracter ausente: solo puede impedir un voto BIEN.
"""
from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class AuditoriaMascara:
    sospecha: bool
    indice: float
    mascara: np.ndarray
    regiones: int
    motivo: str = ''


def auditar_mascara_tinta(mascara_tinta: np.ndarray) -> AuditoriaMascara:
    if mascara_tinta is None or mascara_tinta.size == 0:
        return AuditoriaMascara(False, 0., np.zeros((0, 0), np.uint8), 0)
    h0, w0 = mascara_tinta.shape[:2]
    salida = np.zeros((h0, w0), dtype=np.uint8)
    if min(h0, w0) < 30 or h0 * w0 < 1800:
        return AuditoriaMascara(False, 0., salida, 0)
    rotada = h0 > w0
    mascara = (cv2.rotate(mascara_tinta, cv2.ROTATE_90_CLOCKWISE)
               if rotada else mascara_tinta)
    tinta = np.uint8(mascara > 0)
    h, w = tinta.shape
    if int(tinta.sum()) < 80:
        return AuditoriaMascara(False, 0., salida, 0)
    n, etiquetas, stats, centros = cv2.connectedComponentsWithStats(tinta, 8)
    comps = []
    reglas_externas = []
    for j in range(1, n):
        x, y, cw, ch, area = map(int, stats[j])
        if area < 5:
            continue
        # Separar reglas horizontales aisladas de la tipografia cuando el
        # recorte incluye el borde de una etiqueta. Una raya ENTRE letras
        # que las conecta no queda excluida por este criterio.
        if cw > .50 * w and ch < max(5, .11 * h):
            reglas_externas.append((j, x, y, cw, ch))
            continue
        comps.append((j, x, y, cw, ch, area))
    if len(comps) < 6:
        return AuditoriaMascara(False, 0., salida, 0)
    # Una linea recta aislada puede pertenecer al borde del empaque o a una
    # etiqueta. No se interpreta como tinta mala; invalida el recorte como
    # representacion exclusiva de la fecha para evitar falsos BIEN.
    cy_principales = np.array([c[2]+c[4]*.5 for c in comps if c[5] >= 20], dtype=float)
    altos_ref = [c[4] for c in comps if c[4] >= 8 and c[4] < .6*h]
    altura_ref = float(np.percentile(altos_ref,70)) if altos_ref else 12.
    for j, x, y, cw, ch in reglas_externas:
        cy = y+ch*.5
        if (cy_principales.size >= 4 and
                np.min(np.abs(cy_principales-cy)) >= max(6., altura_ref*.46)):
            marcas = np.zeros_like(tinta)
            marcas[etiquetas==j] = 255
            if rotada:
                marcas=cv2.rotate(marcas,cv2.ROTATE_90_COUNTERCLOCKWISE)
            return AuditoriaMascara(True, 1., marcas, 1,
                'Recorte contiene una linea larga aislada ajena a los trazos; '
                'verificar el borde de YOLO antes de aprobar')
    alturas = np.array([c[4] for c in comps if c[4] >= 6 and c[4] <= .65*h],
                       dtype=np.float32)
    if len(alturas) < 3:
        return AuditoriaMascara(False, 0., salida, 0)
    glyph = float(np.clip(np.percentile(alturas, 75), 10, min(125, h*.72)))
    letras = [c for c in comps if c[4] >= glyph*.65 and c[5] >= 12]
    if len(letras) < 5:
        return AuditoriaMascara(False, 0., salida, 0)
    area_ref = float(np.median([c[5] for c in letras]))
    nucleos = [c for c in letras if c[5] >= max(16., area_ref*.36)]
    # Puntos y signos pequenos aislados NO bastan para sospecha: se piden
    # varios fragmentos dentro de una franja de tinta anormalmente escasa.
    fragmentos = [c for c in comps if (
        c[4] < glyph*.68 and c[3] < glyph*.82 and
        c[5] < max(20., area_ref*.82))]
    if len(nucleos) < 5 or len(fragmentos) < 3:
        return AuditoriaMascara(False, 0., salida, 0)

    xleft = min(c[1] for c in nucleos)
    xright = max(c[1]+c[3] for c in nucleos)
    span = xright-xleft
    if span < max(w*.38, glyph*5.5):
        return AuditoriaMascara(False, 0., salida, 0)

    # Densidad de tinta principal, sin inventar letras ni comparar con una
    # cadena esperada. El grosor de las ventanas sigue la escala de tinta.
    banda = max(12, int(round(glyph*2.7)))
    paso = max(4, int(round(glyph*.20)))
    alcance = max(round(glyph*2.), round(banda*.85))
    zonas = []
    for a in range(xleft + int(.10*span), xright - banda - int(.07*span)+1, paso):
        b = a+banda
        left = [c for c in nucleos if (c[1]+c[3] >= a-alcance and c[1]+c[3] <= a+glyph*.2)]
        right = [c for c in nucleos if (c[1] <= b+alcance and c[1] >= b-glyph*.2)]
        if not left or not right:
            continue
        frag = [c for c in fragmentos if a <= c[1]+c[3]*.5 <= b]
        if len(frag) < 3:
            continue
        frag_x = sorted(c[1]+c[3]*.5 for c in frag)
        if frag_x[-1]-frag_x[0] < .56 * glyph:
            continue
        # Si hay texto fuerte ocupando la ventana, los fragmentos pequenos
        # pueden ser simplemente puntuacion valida.
        tinta_centro = float(np.mean(tinta[:,a:b]))
        ref = max(float(np.mean(tinta[:, max(xleft,a-alcance):a])),
                  float(np.mean(tinta[:,b:min(xright,b+alcance)])), 1.e-5)
        propor = tinta_centro / ref
        if propor >= .48:
            continue
        # Filtrar cuando un solo signo grande divide la franja: comprobar
        # que el numero de nucleos que la atraviesan sea muy bajo.
        core_occupancy = sum(1 for c in nucleos if c[1] < b-.2*glyph and c[1]+c[3] > a+.2*glyph)
        if core_occupancy > 1:
            continue
        score = (1-min(1.,propor)) * min(1.,len(frag)/5)
        zonas.append((score,a,b,frag))
    if not zonas:
        return AuditoriaMascara(False, 0., salida, 0)
    # Seleccionar la region mas explicativa, sin pintar todo el empaque.
    zonas.sort(key=lambda v:v[0],reverse=True)
    _,a,b,frag = zonas[0]
    vis = np.zeros((h,w),dtype=np.uint8)
    for j,x,y,cw,ch,area in frag:
        vis[etiquetas==j] = 255
    # Dos guias virtuales muestran la zona de perdida, no dibujan tinta.
    ys = [c[2] for c in nucleos]+[c[2]+c[4] for c in nucleos]
    ya = max(0, int(np.percentile(ys, 5)))
    yb = min(h-1, int(np.percentile(ys, 95)))
    cv2.line(vis,(a,ya),(a,yb),255,1)
    cv2.line(vis,(b-1,ya),(b-1,yb),255,1)
    if rotada:
        vis=cv2.rotate(vis,cv2.ROTATE_90_COUNTERCLOCKWISE)
    return AuditoriaMascara(True,round(float(zonas[0][0]),3),vis,1,
        'Mascara con franja interior de tinta escasa y restos fragmentados; '
        'comparar con fotograma original antes de aprobar')

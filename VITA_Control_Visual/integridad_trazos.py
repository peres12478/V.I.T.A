"""Indicador conservador de zonas con tinta debilitada dentro del texto.

No reconoce caracteres, no exige un formato y nunca interpreta un hueco
intencional como prueba de un caracter faltante. Un debilitamiento relevante
crea REVISAR (no voto BUENA); MAL requiere evidencia distinta corroborada.
El resultado debe calibrarse con fotos originales y etiquetas humanas.
"""
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass(frozen=True)
class Integridad:
    posible_debilitamiento: bool
    indice: float
    mascara: np.ndarray
    motivo: str = ''


def detectar_debilitamiento(imagen_bgr: np.ndarray, mascara_tinta: np.ndarray,
                           polaridad: str = 'oscura') -> Integridad:
    if imagen_bgr is None or mascara_tinta is None or imagen_bgr.size == 0:
        return Integridad(False, 0., np.zeros((0, 0), np.uint8))
    h0, w0 = imagen_bgr.shape[:2]
    salida = np.zeros((h0, w0), dtype=np.uint8)
    if min(h0, w0) < 36 or h0 * w0 < 2600 or mascara_tinta.shape[:2] != (h0, w0):
        return Integridad(False, 0., salida)
    rotar = h0 > w0
    im = cv2.rotate(imagen_bgr, cv2.ROTATE_90_CLOCKWISE) if rotar else imagen_bgr
    ink = cv2.rotate(mascara_tinta, cv2.ROTATE_90_CLOCKWISE) if rotar else mascara_tinta
    ink = np.uint8(ink > 0)
    h, w = ink.shape
    if np.count_nonzero(ink) < max(50, h * w * 0.006):
        return Integridad(False, 0., salida)
    # Trabajar en luminancia normalizada localmente, usando tinta de la fecha.
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)
    l = lab[:, :, 0].astype(np.float32)
    sigma = max(4., min(18., min(h, w) / 8.))
    bg = cv2.GaussianBlur(l, (0, 0), sigmaX=sigma)
    if polaridad == 'clara':
        signal = np.maximum(l-bg, 0.)
    elif polaridad == 'color':
        ab = lab[:, :, 1:].astype(np.float32)
        bgab = cv2.GaussianBlur(ab, (0,0), sigmaX=sigma)
        signal = np.sqrt(np.sum((ab-bgab)**2, axis=2))
    else:
        signal = np.maximum(bg-l, 0.)
    # Buscar renglones de tinta geométricamente; no se pide número de renglones.
    ys, xs = np.where(ink > 0)
    xmin, xmax = int(np.percentile(xs, 1)), int(np.percentile(xs, 99))
    if xmax - xmin < max(90, w * .30):
        return Integridad(False, 0., salida)
    ink_roi = ink[:, xmin:xmax+1]
    perfil = np.sum(ink_roi, axis=1)
    activo = (perfil > max(3, int(.012 * (xmax-xmin+1)))).astype(np.uint8)
    activo = cv2.morphologyEx(activo[:,None], cv2.MORPH_CLOSE, np.ones((3,1),np.uint8))[:,0]
    lineas = []
    ini = None
    for y, v in enumerate(list(activo) + [0]):
        if v and ini is None:
            ini = y
        if not v and ini is not None:
            if y-ini >= max(8, int(h*.035)):
                lineas.append((ini, y))
            ini = None
    sospecha = np.zeros_like(ink)
    mejor = 0.
    for ya, yb in lineas:
        alto = yb-ya
        # Las ventanas son relativas al alto de los trazos, no a un numero
        # esperado de caracteres o una longitud fija de fecha.
        ancho_bloque = int(np.clip(round(alto*.65), 10, 70))
        paso = max(5, ancho_bloque//2)
        valores=[]
        pos=[]
        fuertes=[]
        suaves=[]
        # Solo el interior del renglón: los bordes no permiten comparación.
        for x in range(xmin, xmax-ancho_bloque+2, paso):
            trozo = signal[ya:yb,x:x+ancho_bloque]
            trozo_ink = ink[ya:yb,x:x+ancho_bloque] > 0
            n = int(trozo_ink.sum())
            q95 = float(np.percentile(trozo,95))
            if n < max(3, int(trozo.size*.012)):
                valores.append(0.);fuertes.append(False);suaves.append(q95);pos.append(x);continue
            med = float(np.median(trozo[trozo_ink]))
            valores.append(med)
            fuertes.append(True)
            suaves.append(q95)
            pos.append(x)
        if len(valores) < 10:
            continue
        val = np.array(valores, dtype=np.float32)
        use = np.array(fuertes, dtype=bool)
        if np.count_nonzero(use) < 7:
            continue
        base = float(np.median(val[use]))
        if base < 5.: continue
        # Zonas contiguas debiles dentro del mismo renglon. Requerimos
        # contraste fuerte ANTES y DESPUES de la franja, sin exigir la forma
        # ni la cantidad de caracteres que componen la fecha.
        suave = np.array(suaves, dtype=np.float32)
        # Puede haber tinta tan tenue que ya no supere el umbral binario.
        # La comprobamos en el ORIGINAL sin elevar artificialmente el contraste;
        # una zona enteramente en blanco no ofrece evidencia y se ignora.
        ghost = (~use) & (suave > max(9., .10*base)) & (suave < .43*base)
        sospechoso = (use & (val < .43 * base)) | ghost
        medida = np.where(ghost, suave, val)
        idx = np.where(sospechoso)[0]
        if len(idx) == 0:
            continue
        grupos = np.split(idx, np.where(np.diff(idx) > 2)[0] + 1)
        for grupo in grupos:
            if grupo.size < 2:
                continue
            primero, ultimo = int(grupo[0]), int(grupo[-1])
            if primero < 3 or ultimo > len(val) - 4:
                continue
            # Buscar zonas de referencia de alta tinta a ambos lados, no
            # solamente en los 3 o 4 bloques mas cercanos.
            antes = val[max(0, primero-16):primero]
            despues = val[ultimo+1:min(len(val), ultimo+17)]
            if not (np.any(antes > .85*base) and np.any(despues > .85*base)):
                continue
            extension = (pos[ultimo]+ancho_bloque-pos[primero]) / max(1., xmax-xmin)
            if extension < .055 or extension > .48:
                continue
            debiles = medida[grupo]
            ratio = float((base-np.median(debiles))/max(1.,base))
            if ratio <= .57:
                continue
            mejor = max(mejor, ratio)
            # Marcar solo pixeles que realmente estan asociados a tinta en
            # esa region, nunca un rectangulo entero de fondo del empaque.
            for i in grupo:
                a, b = pos[i], pos[i]+ancho_bloque
                nucleo = ink[ya:yb,a:b]*255
                if ghost[i]:
                    # Solo la huella tenue, no los pixeles de fondo.
                    nucleo = np.uint8((signal[ya:yb,a:b] > max(8., .11*base)))*255
                sospecha[ya:yb,a:b] |= nucleo
    detectado = mejor >= .57 and np.count_nonzero(sospecha) >= 6
    if not detectado:
        sospecha[:]=0
    if rotar:
        sospecha = cv2.rotate(sospecha, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return Integridad(detectado, round(mejor,3) if detectado else 0., sospecha,
                      ('Trazos de contraste anormalmente debil frente a tramos vecinos; '
                       'comparar con otra toma') if detectado else '')

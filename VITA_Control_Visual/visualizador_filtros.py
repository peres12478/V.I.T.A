"""Paneles de inspeccion para la interfaz Nutreo.

Solo VISUALIZA resultados; no clasifica ni modifica votos o imagenes de
entrada. Mascaras de tinta y zonas sospechosas proceden del inspector real.
Las vistas de luminancia, fondo y diferencia muestran transformaciones del
preprocesamiento; la diferencia L es una VISTA AUXILIAR, no implica que la
segmentacion sea exclusivamente en grises (se admite tinta cromatica).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Mapping

import cv2
import numpy as np


def _bgr(imagen: np.ndarray) -> np.ndarray:
    if imagen.ndim == 2:
        return cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR)
    return imagen.copy()


def crear_vistas_filtros(recorte_bgr: np.ndarray, resultado) -> Mapping[str, np.ndarray]:
    """Devuelve seis imagenes BGR para panel de etapas, sin alterar al inspector."""
    if recorte_bgr is None or recorte_bgr.size == 0:
        raise ValueError('Se necesita un recorte valido de la fecha')
    original = _bgr(recorte_bgr)
    h, w = original.shape[:2]
    lab = cv2.cvtColor(original, cv2.COLOR_BGR2LAB)
    lum = lab[:, :, 0]
    sigma = max(3., min(15., min(h, w) / 10.))
    fondo = cv2.GaussianBlur(lum.astype(np.float32), (0, 0), sigmaX=sigma)
    # Vista explicativa: puede haber segmentacion basada en diferencia cromatica.
    diferencia = np.abs(lum.astype(np.float32) - fondo)
    escala = float(np.percentile(diferencia, 99.5))
    mapa_diferencia = np.uint8(np.clip(diferencia * (180. / max(escala, 4.)), 0, 255))
    mascara = getattr(resultado, 'mascara_tinta', None)
    if mascara is None or mascara.shape[:2] != (h, w):
        mascara = np.zeros((h, w), dtype=np.uint8)
    sospechosa = getattr(resultado, 'mascara_sospechosa', None)
    if sospechosa is None or sospechosa.shape[:2] != (h, w):
        sospechosa = np.zeros((h, w), dtype=np.uint8)

    evidencia = original.copy()
    peligro = sospechosa > 0
    if np.any(peligro):
        naranja = np.zeros_like(original)
        naranja[:, :] = (0, 133, 255)
        capa = cv2.addWeighted(original, 0.48, naranja, 0.52, 0)
        evidencia[peligro] = capa[peligro]
    return OrderedDict([
        ('01  Fecha detectada', original),
        ('02  Luminosidad LAB', cv2.cvtColor(lum, cv2.COLOR_GRAY2BGR)),
        ('03  Fondo estimado', cv2.cvtColor(np.uint8(np.clip(fondo, 0, 255)), cv2.COLOR_GRAY2BGR)),
        ('04  Contraste local (apoyo)', cv2.cvtColor(mapa_diferencia, cv2.COLOR_GRAY2BGR)),
        ('05  Tinta segmentada (real)', cv2.cvtColor(mascara, cv2.COLOR_GRAY2BGR)),
        ('06  Zonas sospechosas (real)', evidencia),
    ])

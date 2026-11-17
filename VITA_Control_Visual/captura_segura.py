"""Proteccion del flujo de camara, adaptada de VITA v0.1.

No evalua la fecha ni el empaque. Evita inferir sobre cuadros ausentes,
negros, uniformes o exactamente repetidos por una camara congelada.
Solo dependencias OpenCV + NumPy. No utiliza OCR ni OpenVINO.

La deteccion de congelamiento exige frames IDENTICOS durante un numero
configurable de lecturas y, cuando se configura, durante un tiempo minimo.
Esto evita falsos congelamientos con camaras virtuales / Wi-Fi. No se considera que un objeto quieto sea un defecto.
"""
from __future__ import annotations

from dataclasses import dataclass
import zlib
import time
import cv2
import numpy as np


@dataclass(frozen=True)
class EstadoCaptura:
    util: bool
    motivo: str = 'ok'
    repeticiones: int = 0
    brillo: float = 0.0
    desviacion: float = 0.0


def evaluar_escena(frame: np.ndarray | None) -> EstadoCaptura:
    """Comprobacion de fuente: no confundir falta de señal con defecto de tinta."""
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return EstadoCaptura(False, 'sin imagen')
    if frame.ndim == 2:
        gris = frame
    elif frame.ndim == 3 and frame.shape[2] in (3, 4):
        modo = cv2.COLOR_BGR2GRAY if frame.shape[2] == 3 else cv2.COLOR_BGRA2GRAY
        gris = cv2.cvtColor(frame, modo)
    else:
        return EstadoCaptura(False, 'formato de imagen no admitido')
    mini = cv2.resize(gris, (160, 120), interpolation=cv2.INTER_AREA)
    media = float(mini.mean())
    desviacion = float(mini.std())
    fraccion_negra = float(np.mean(mini < 25))
    if media < 18 and fraccion_negra > .85:
        return EstadoCaptura(False, 'camara negra, bloqueada o sin senal', 0, media, desviacion)
    if desviacion < 2.0:
        return EstadoCaptura(False, 'cuadro casi uniforme o pantalla de espera', 0, media, desviacion)
    return EstadoCaptura(True, 'ok', 0, media, desviacion)


class GuardiaCaptura:
    """Detecta datos sin señal y cuadros exactamente congelados en secuencia."""
    def __init__(self, repeticiones_congelado: int = 45, segundos_congelado: float = 0.0):
        if repeticiones_congelado < 2:
            raise ValueError('repeticiones_congelado debe ser >= 2')
        if segundos_congelado < 0:
            raise ValueError('segundos_congelado no puede ser negativo')
        self.limite = repeticiones_congelado
        self.segundos_congelado = float(segundos_congelado)
        self.firma_previa: int | None = None
        self.repetidos = 0
        self.inicio_repetidos: float | None = None

    def revisar(self, frame: np.ndarray | None, instante: float | None = None) -> EstadoCaptura:
        estado = evaluar_escena(frame)
        if not estado.util:
            self.firma_previa = None
            self.repetidos = 0
            self.inicio_repetidos = None
            return estado
        # CRC del fotograma completo: descarta UNICAMENTE imagenes identicas.
        # Un thumbnail muy pequeno podria confundir dos capturas distintas
        # de una fecha con trazos finos, precisamente lo que queremos evitar.
        firma = zlib.crc32(memoryview(np.ascontiguousarray(frame)))
        ahora = time.monotonic() if instante is None else float(instante)
        if firma == self.firma_previa:
            self.repetidos += 1
            if self.inicio_repetidos is None:
                self.inicio_repetidos = ahora
        else:
            self.repetidos = 0
            self.inicio_repetidos = None
        self.firma_previa = firma
        # Con Wi-Fi, leer la misma imagen decenas de veces en 0.2 s es normal.
        # Exigir tambien tiempo real para diagnosticar camara congelada.
        duracion = (ahora - self.inicio_repetidos) if self.inicio_repetidos is not None else 0.
        if self.repetidos >= self.limite and duracion >= self.segundos_congelado:
            return EstadoCaptura(False, 'flujo de camara congelado: cuadros identicos',
                                 self.repetidos, estado.brillo, estado.desviacion)
        return EstadoCaptura(True, 'ok', self.repetidos, estado.brillo, estado.desviacion)


def diagnostico_movimiento_roi(roi: np.ndarray | None) -> dict[str, float]:
    """Medidas de VITA: Sobel/Tenengrad y anisotropia, solo DIAGNOSTICO.

    No se convierten en rechazo automatico. Tipografias delgadas, inclinadas
    o formatos variables pueden tener anisotropia alta sin estar movidos.
    """
    if roi is None or not isinstance(roi, np.ndarray) or roi.size == 0:
        return {'gradiente_tenengrad': 0.0, 'anisotropia_gradiente': 0.0}
    gris = roi if roi.ndim == 2 else cv2.cvtColor(roi[:, :, :3], cv2.COLOR_BGR2GRAY)
    g = gris.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    ex, ey = float(np.mean(np.abs(gx))), float(np.mean(np.abs(gy)))
    return {'gradiente_tenengrad': float(np.mean(gx*gx + gy*gy)),
            'anisotropia_gradiente': abs(ex-ey)/max(ex+ey, 1e-6)}


def backends_camara(sistema: str, preferido: str = 'auto') -> list[tuple[str,int]]:
    """Prioriza la seleccion del usuario y conserva respaldos en Windows."""
    if preferido not in ('auto', 'dshow', 'msmf'):
        raise ValueError('Backend: auto, dshow o msmf')
    if sistema != 'win32':
        return [('auto', cv2.CAP_ANY)]
    orden = (['dshow','msmf','auto'] if preferido == 'auto'
             else [preferido] + [v for v in ('dshow','msmf','auto') if v != preferido])
    puertos = {'dshow':cv2.CAP_DSHOW,'msmf':cv2.CAP_MSMF,'auto':cv2.CAP_ANY}
    return [(k,puertos[k]) for k in orden]

"""Captura de baja latencia sin servidor ni cola acumulativa de fotogramas.

El hilo de lectura vacia el buffer del dispositivo continuamente; YOLO recibe
la ULTIMA imagen completa disponible, nunca una cola de imagenes viejas.
No se inventan fotogramas ni se reutiliza una imagen como voto nuevo.
"""
from __future__ import annotations
import threading
import time

class CapturaReciente:
    def __init__(self, captura, pausa_minima=0.008):
        self.captura = captura
        self.pausa_minima = max(0., float(pausa_minima))
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._ultimo = None
        self._secuencia = 0
        self._fallos = 0
        self._capturados = 0
        self._instante = 0.
        self._hilo = threading.Thread(target=self._leer, name='VITA-Captura-Reciente', daemon=True)
        self._hilo.start()

    def _leer(self):
        try:
            while not self._stop.is_set():
                comienzo = time.monotonic()
                try:
                    ok, imagen = self.captura.read()
                except (Exception,) as exc:
                    with self._cv:
                        self._fallos += 1
                        self._cv.notify_all()
                    # No encadenar excepciones por fallo de dispositivo.
                    if self._stop.wait(.06):
                        break
                    continue
                ahora = time.monotonic()
                with self._cv:
                    if ok and imagen is not None and imagen.size:
                        self._ultimo = imagen
                        self._instante = ahora
                        self._secuencia += 1
                        self._capturados += 1
                        self._fallos = 0
                    else:
                        self._fallos += 1
                    self._cv.notify_all()
                falta = self.pausa_minima - (time.monotonic()-comienzo)
                if falta > 0:
                    self._stop.wait(falta)
        finally:
            with self._cv:
                self._cv.notify_all()

    def esperar_nuevo(self, anterior=0, timeout=.4):
        """Devuelve (secuencia, fotograma, tiempo) o None si no llego nuevo."""
        limite = time.monotonic() + max(0., timeout)
        with self._cv:
            while self._secuencia <= anterior and not self._stop.is_set():
                resta = limite - time.monotonic()
                if resta <= 0:
                    return None
                self._cv.wait(resta)
            if self._secuencia <= anterior:
                return None
            return self._secuencia, self._ultimo, self._instante

    def estadisticas(self, anterior=0):
        with self._cv:
            return {'recibidos': self._capturados,
                    'sin_procesar': max(0, self._secuencia-int(anterior)-1),
                    'fallos': self._fallos,
                    'ultimo_t': self._instante}

    def cerrar(self):
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        self._hilo.join(timeout=.8)
        # Hay controladores OpenCV que bloquean read() hasta liberar la camara.
        if self._hilo.is_alive():
            self.captura.release()
            self._hilo.join(timeout=.8)

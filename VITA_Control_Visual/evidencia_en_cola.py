"""Escritura asincrona fiable de evidencias sin bloquear YOLO + OpenCV.

La cola tiene limite de memoria; ante disco lento, se espera en vez de
perder una muestra. cerrar() vacia y sincroniza todas las evidencias.
"""
from __future__ import annotations
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

from evidencia_inspeccion import registrar_evidencia


class EvidenciasEnCola:
    def __init__(self, max_pendientes=80):
        self.pendientes = queue.Queue(maxsize=max_pendientes)
        self.errores = []
        self._cerrada = False
        self._hilo = threading.Thread(target=self._escribir, name='VITA-Guardado-Evidencias', daemon=True)
        self._hilo.start()

    def agregar(self, carpeta, producto, muestra, recorte, resultado):
        if self._cerrada:
            raise RuntimeError('La cola de evidencias ya se cerro.')
        # Retener una copia independiente del proximo fotograma y sus mascaras.
        dato = SimpleNamespace(
            estado=resultado.estado, motivo=resultado.motivo,
            metricas=dict(resultado.metricas or {}),
            mascara_tinta=None if resultado.mascara_tinta is None else resultado.mascara_tinta.copy(),
            mascara_sospechosa=None if resultado.mascara_sospechosa is None else resultado.mascara_sospechosa.copy(),
        )
        self.pendientes.put((Path(carpeta), producto, muestra, recorte.copy(), dato))

    def _escribir(self):
        while True:
            item = self.pendientes.get()
            try:
                if item is None:
                    return
                registrar_evidencia(*item)
            except (Exception,) as exc:
                self.errores.append(str(exc))
            finally:
                self.pendientes.task_done()

    def cerrar(self):
        if self._cerrada:
            return
        self._cerrada = True
        self.pendientes.put(None)
        self.pendientes.join()
        self._hilo.join(timeout=5)

"""Prueba el trabajador REAL con lector de video y detector simulados.

Comprueba que un flujo congelado o negro no pueda sumar 7 votos.
"""
from __future__ import annotations
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interfaz_nutreo import Configuracion, Trabajador
from calidad_impresion import Resultado


class FakeTensor:
    def __init__(self, arr): self.arr=np.array(arr)
    def cpu(self): return self
    def numpy(self): return self.arr
class FakeBox:
    def __init__(self, box): self.xyxy=[FakeTensor(box)]
class FakePred:
    def __init__(self, box): self.boxes=[FakeBox(box)]
class FakeDetector:
    def predict(self, frame, conf, verbose=False):
        return [FakePred((40,45,260,120))]
class FakeInspector:
    def analizar(self, crop):
        h,w=crop.shape[:2]
        return Resultado('BIEN','Prueba de calidad',90.,{},[],
                         np.zeros((h,w),np.uint8),np.zeros((h,w),np.uint8),'oscura')
class FakeCapture:
    def __init__(self, frames): self.frames=list(frames); self.closed=False
    def isOpened(self): return True
    def get(self, what): return 10.
    def set(self, what, value): return True
    def read(self):
        if not self.frames: return False,None
        return True,self.frames.pop(0).copy()
    def release(self): self.closed=True


class TestIntegracionGuardiaCamara(unittest.TestCase):
    @staticmethod
    def escena():
        f=np.full((180,350,3),205,np.uint8)
        cv2.putText(f,'LOTE 0426',(44,100),cv2.FONT_HERSHEY_SIMPLEX,1,(12,12,12),2)
        return f

    def ejecutar(self, frames):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            cfg=Configuracion(video=tmp/'simulado.mp4', fotos=7,
                              min_buenas=5, intervalo_ms=0,
                              control_visibilidad=False,
                              guardar_evidencia=False, mostrar_etapas=False,
                              registro=tmp/'eventos.csv')
            captura=FakeCapture(frames)
            fotos=queue.Queue(maxsize=2)
            eventos=queue.Queue()
            hilo=Trabajador(cfg,threading.Event(),fotos,eventos)
            with patch('interfaz_nutreo.cargar_yolo',return_value=FakeDetector()), \
                 patch('interfaz_nutreo.InspectorCalidadRobusto',return_value=FakeInspector()), \
                 patch('interfaz_nutreo.cv2.VideoCapture',return_value=captura):
                hilo.run()
            lista=[]
            while not eventos.empty(): lista.append(eventos.get_nowait())
            return [e for tipo,e in lista if tipo=='resultado'],lista,captura.closed

    def test_video_repetido_no_conduce_a_pasa(self):
        f=self.escena()
        recibidos,info,closed=self.ejecutar([f]*30)
        self.assertTrue(closed)
        self.assertEqual(len(recibidos),1)
        self.assertEqual(recibidos[0].estado,'MAL')
        self.assertEqual(recibidos[0].buenas,1)
        self.assertEqual(recibidos[0].total,1)

    def test_video_totalmente_negro_no_genera_producto(self):
        recibidos,info,closed=self.ejecutar([np.zeros((180,350,3),np.uint8)]*10)
        self.assertTrue(closed)
        self.assertEqual(recibidos,[])

    def test_video_con_capturas_nuevas_puede_aprobar(self):
        f=self.escena()
        diferentes=[]
        for j in range(7):
            uno=f.copy()
            cv2.rectangle(uno,(0,0),(20,20),(20+j*22,220,210),-1)
            diferentes.append(uno)
        recibidos,info,closed=self.ejecutar(diferentes)
        self.assertEqual(len(recibidos),1)
        self.assertEqual(recibidos[0].estado,'BIEN')
        self.assertEqual(recibidos[0].buenas,7)

if __name__ == '__main__':unittest.main()

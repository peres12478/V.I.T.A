"""Prueba real del flujo falso-YOLO -> recorte -> analisis -> 7 votos -> evento."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
import cv2
import numpy as np

from calidad_impresion import InspectorCalidad
from iniciar_calidad import inspeccionar, dibujar_banda, RegistroEventos
from seguimiento_banda import SeguimientoBanda, Observacion
from tempfile import TemporaryDirectory
import csv


class MatrizFalsa:
    def __init__(self, value):
        self.value=np.array(value, dtype=np.int32)
    def cpu(self):
        return self
    def numpy(self):
        return self.value

class CajaFalsa:
    def __init__(self, value):
        self.xyxy=[MatrizFalsa(value)]

class PrediccionFalsa:
    def __init__(self, cajas):
        self.boxes=[CajaFalsa(c) for c in cajas]

class ModeloFalso:
    def __init__(self):
        self.cajas=[]
        self.llamadas=0
    def predict(self,frame,conf,verbose):
        self.llamadas+=1
        return [PrediccionFalsa(self.cajas)]

class TestFlujoBanda(unittest.TestCase):
    def test_varias_fotos_mismo_producto_una_decision_csv(self):
        inspector=InspectorCalidad()
        seguidor=SeguimientoBanda(min_buenas=1, objetivo=7,min_validas=3)
        detector=ModeloFalso()
        eventos=[]
        for i in range(8):
            frame=np.full((230,690,3),(210,190,130),np.uint8)
            x=25+8*i
            cv2.putText(frame,'VEN 12/2028',(x+10,116),cv2.FONT_HERSHEY_SIMPLEX,
                        .74,(22,22,22),2,cv2.LINE_AA)
            detector.cajas=[(x,60,x+260,140)]
            img,res,mask=inspeccionar(frame,detector,inspector,.45,dibujar=False)
            self.assertEqual(res[0][0].estado,'BIEN')
            observado=[Observacion(caja,r.estado,r.motivo) for r,caja in res]
            salida=seguidor.actualizar(observado,i*.1,i+1)
            eventos+=salida.eventos
            pantalla=dibujar_banda(frame,salida,seguidor,res,i*.1,7.0)
            self.assertEqual(pantalla.shape,frame.shape)
        self.assertEqual(detector.llamadas,8)
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual((eventos[0].buenas,eventos[0].malas),(7,0))
        self.assertEqual([p.id for p in seguidor.pistas.values()],[1])
        with TemporaryDirectory() as d:
            path=Path(d)/'registro.csv'
            logger=RegistroEventos(path)
            logger.guardar(eventos[0]);logger.close()
            with path.open('r',encoding='utf-8-sig',newline='') as f:
                lineas=list(csv.DictReader(f))
            self.assertEqual(len(lineas),1)
            self.assertEqual(lineas[0]['decision'],'BIEN')
            self.assertEqual(lineas[0]['votos_validos'],'7')


if __name__=='__main__':
    unittest.main()

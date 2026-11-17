"""Ejemplo defectuoso: YOLO simulado -> recorte -> 7 capturas -> NO PASA."""
import unittest
import cv2
import numpy as np
from pathlib import Path
from interfaz_nutreo import Configuracion, ProcesadorNutreo
from inspeccion_robusta import InspectorCalidadRobusto
from pruebas.test_integracion_banda import ModeloFalso

DIR=Path(__file__).resolve().parent/'muestras_calibracion'

class TestIntegracionConDefectoReal(unittest.TestCase):
    def test_una_fecha_corrida_no_se_aprueba_ni_renueva_id(self):
        fecha=cv2.imread(str(DIR/'defecto_confirmado_11550.png'))
        self.assertIsNotNone(fecha)
        h,w=fecha.shape[:2]
        frame=np.full((h+240,w+360,3),(220,205,190),np.uint8)
        x,y=180,120
        frame[y:y+h,x:x+w]=fecha
        detector=ModeloFalso()
        detector.cajas=[(x,y,x+w,y+h)]
        cfg=Configuracion(fotos=7,min_buenas=5,control_visibilidad=True,
                          confirmaciones_fecha=3,intervalo_ms=75,
                          recorte_borde=.12,mostrar_etapas=True)
        engine=ProcesadorNutreo(cfg,detector,InspectorCalidadRobusto())
        resultados=[];identificadores=[]
        for i in range(13):
            vista,eventos=engine.procesar(frame,i*.1)
            resultados.extend(eventos)
            identificadores.append(vista.producto)
        self.assertEqual(len(resultados),1)
        self.assertEqual(resultados[0].estado,'MAL',resultados[0].motivo)
        self.assertEqual(resultados[0].malas,7)
        self.assertEqual(resultados[0].buenas,0)
        self.assertEqual(vista.estado,'NO PASA')
        self.assertEqual(set(identificadores),{1})
        self.assertGreater(vista.metricas.get('indice_arrastre_interno',0.), .25)

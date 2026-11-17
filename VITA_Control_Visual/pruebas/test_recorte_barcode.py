"""Pruebas del ROI interior: no analizar el codigo de barras adyacente."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import cv2
from calidad_impresion import Resultado
from iniciar_calidad import caja_recorte, inspeccionar
from interfaz_nutreo import Configuracion, ProcesadorNutreo


class TensorFalso:
    def __init__(self, caja): self.caja = np.asarray(caja)
    def cpu(self): return self
    def numpy(self): return self.caja

class BoxFalsa:
    def __init__(self, caja): self.xyxy = [TensorFalso(caja)]

class DetectorFalso:
    def __init__(self, caja): self.caja = caja
    def predict(self, frame, conf, verbose=False):
        pred = type('Pred', (), {})()
        pred.boxes = [BoxFalsa(self.caja)]
        return [pred]

class InspectorTest:
    """El resultado cambia SOLO si el recorte todavia incluye rayas externas."""
    def __init__(self): self.crops=[]
    def analizar(self, crop):
        self.crops.append(crop.copy())
        # Los barcode artificiales son lineas intensas en banda superior.
        oscuro = np.mean(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)[:8] < 50)
        estado='MAL' if oscuro > .20 else 'BIEN'
        h,w=crop.shape[:2]
        mascara=np.zeros((h,w),np.uint8)
        return Resultado(estado,'Prueba de contaminacion de barcode',75.,{},[],mascara,mascara,'oscura')


class TestRecorteBarcode(unittest.TestCase):
    def test_horizontal_se_acorta_altura_no_longitud(self):
        box = caja_recorte(50, 50, 450, 250, (360,600,3), recorte_borde=.15)
        # Se conservan los extremos de fecha y se suprimen 30 px de arriba/abajo.
        self.assertEqual(box, (42,80,458,220))

    def test_vertical_se_acorta_anchura_no_longitud(self):
        box = caja_recorte(50, 50, 250, 450, (600,400,3), recorte_borde=.15)
        self.assertEqual(box, (80,42,220,458))

    def test_recuadro_pequeno_no_se_recorta_demasiado(self):
        x1,y1,x2,y2 = caja_recorte(10,10,160,39,(90,200,3),recorte_borde=.30)
        self.assertGreaterEqual(y2-y1,25)

    def test_porcentaje_cero_no_corta_caracteres(self):
        x1,y1,x2,y2 = caja_recorte(10,20,210,120,(150,230,3),recorte_borde=0)
        self.assertEqual((y1,y2),(20,120))

    def test_porcentaje_invalido(self):
        with self.assertRaises(ValueError):
            caja_recorte(0,0,100,100,(120,120,3),recorte_borde=.5)

    def test_barcode_excluido_antes_de_inspeccion(self):
        frame=np.full((260,600,3), (230,200,190),np.uint8)
        # Barra ajena a la fecha en los primeros 15% del recuadro de YOLO.
        for y in (54,57,60,63):
            cv2.line(frame,(50,y),(550,y),(10,10,10),2)
        cv2.putText(frame,'VEN. 2026',(100,145),cv2.FONT_HERSHEY_SIMPLEX,1.,(20,20,20),2)
        detector=DetectorFalso((50,50,550,210))
        inspect=InspectorTest()
        _, datos, _=inspeccionar(frame,detector,inspect,.45,dibujar=False,recorte_borde=.15)
        self.assertEqual(datos[0][0].estado,'BIEN')
        self.assertEqual(datos[0][1][1],74)
        self.assertEqual(inspect.crops[-1].shape[0],112)

    def test_gui_reutiliza_roi_real_y_conserva_votacion(self):
        frame=np.full((260,600,3), (230,200,190),np.uint8)
        for y in (54,57,60,63):
            cv2.line(frame,(50,y),(550,y),(10,10,10),2)
        cv2.putText(frame,'VENCE',(180,155),cv2.FONT_HERSHEY_SIMPLEX,1.,(10,10,10),2)
        insp=InspectorTest()
        procesador=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=2,intervalo_ms=0,
                                      recorte_borde=.15, mostrar_etapas=True),
                                      DetectorFalso((50,50,550,210)),insp)
        view0, e0=procesador.procesar(frame,0)
        view1, e1=procesador.procesar(frame,.1)
        self.assertEqual(e0,[])
        self.assertEqual(len(e1),1)
        self.assertEqual(e1[0].estado,'BIEN')
        self.assertEqual((e1[0].buenas,e1[0].malas),(2,0))
        self.assertEqual(view1.estado,'PASA')
        self.assertEqual(view1.filtro_paneles['01  Fecha detectada'].shape,
                         insp.crops[-1].shape)
        pista=next(iter(procesador.tracker.pistas.values()))
        self.assertEqual(pista.caja,(40,74,560,186))
        self.assertEqual(len(procesador.tracker.pistas),1)


if __name__=='__main__':
    unittest.main()

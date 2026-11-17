"""Pruebas deterministas del filtro basico (no son una validacion industrial)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
import cv2
import numpy as np
from calidad_impresion import InspectorCalidad

BASE=Path(__file__).resolve().parents[1]


def render(texto, fondo=(210,190,130), tinta=(33,28,25)):
    imagen=np.full((150,550,3),fondo,np.uint8)
    cv2.putText(imagen,texto,(15,86),cv2.FONT_HERSHEY_SIMPLEX,.94,tinta,2,cv2.LINE_AA)
    return imagen


class TestInspector(unittest.TestCase):
    def setUp(self):
        self.insp=InspectorCalidad()

    def test_sin_formato_de_fecha(self):
        for texto in ('VEN: 11/26','2027-09-16','AB 567 A 06:35','07.01.28'):
            with self.subTest(texto=texto):
                r=self.insp.analizar(render(texto))
                self.assertNotEqual(r.estado,'MAL')
                self.assertGreater(r.metricas['fraccion_tinta'],.01)

    def test_integracion_en_mismo_fotograma(self):
        from iniciar_calidad import inspeccionar
        import torch
        class Caja:
            xyxy=[torch.tensor([120,20,350,115],dtype=torch.float32)]
        class Pred:
            boxes=[Caja()]
        class DetectorFalso:
            llamadas=0
            def predict(self,frame,conf,verbose):
                self.llamadas+=1
                return [Pred()]
        detector=DetectorFalso()
        frame=render('09/26')
        overlay,resultados,mascara=inspeccionar(frame,detector,self.insp,.5)
        self.assertEqual(detector.llamadas,1)
        self.assertEqual(len(resultados),1)
        self.assertIn(resultados[0][0].estado,('BIEN','MAL','REVISAR'))
        self.assertEqual(overlay.shape,frame.shape)

    def test_tinta_clara_sobre_oscuro(self):
        r=InspectorCalidad('clara').analizar(render('Ven: 12/28',(70,50,105),(240,240,230)))
        self.assertNotEqual(r.estado,'MAL')

    def test_colores_de_empaque_y_tinta(self):
        for fondo,tinta in [
            ((230,230,230),(10,10,10)),
            ((180,110,50),(15,15,15)),
            ((30,50,75),(244,244,244)),
            ((45,55,180),(245,245,245)),
            ((130,145,50),(150,75,160))]:
            with self.subTest(fondo=fondo,tinta=tinta):
                r=self.insp.analizar(render('VEN 24/11/26',fondo,tinta))
                self.assertNotEqual(r.estado,'MAL')

    def test_mancha_concentrada(self):
        im=render('L:6967 V:24/09/26')
        cv2.circle(im,(260,75),17,(33,28,25),-1)
        r=self.insp.analizar(im)
        self.assertEqual(r.estado,'MAL')

    def test_vacio_no_se_aprueba(self):
        im=np.full((150,550,3),(205,180,120),np.uint8)
        self.assertEqual(self.insp.analizar(im).estado,'REVISAR')

    def test_ejemplo_con_arrastre(self):
        im=cv2.imread(str(BASE/'imagenes_prueba/1995.jpg'))
        r=self.insp.analizar(im[447:1020,360:523])
        self.assertEqual(r.estado,'MAL')
        self.assertGreater(r.metricas['indice_barrido'],.20)

    def test_ejemplo_con_reflejos(self):
        im=cv2.imread(str(BASE/'imagenes_prueba/1757.jpg'))
        r=self.insp.analizar(im[558:940,458:565])
        self.assertNotEqual(r.estado,'MAL')

if __name__=='__main__':unittest.main()

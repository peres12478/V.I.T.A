"""Pruebas del filtro de captura (no certifican defectos industriales)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

from inspeccion_robusta import InspectorCalidadRobusto, diagnosticar_captura
from seguimiento_banda import SeguimientoBanda, Observacion
from pruebas.test_calidad import render


class TestCapturaRobusta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filtro = InspectorCalidadRobusto()

    def test_conserva_una_impresion_sana(self):
        r = self.filtro.analizar(render('EXP 15-08-29'))
        self.assertEqual(r.estado, 'BIEN')
        self.assertEqual(r.metricas['camara_captura_no_evaluable'], 0.)

    def test_tinta_clara_y_diferencia_cromatica(self):
        for fondo, tinta in [
            ((70,50,105),(240,240,230)),
            ((130,145,50),(150,75,160)),
        ]:
            with self.subTest(fondo=fondo,tinta=tinta):
                r = self.filtro.analizar(render('V 12/2028',fondo,tinta))
                self.assertNotEqual(r.estado,'MAL')
                self.assertGreater(r.metricas['fraccion_tinta'], 0.01)

    def test_captura_sin_contraste_no_aprueba(self):
        buena = render('VEN 12/27')
        tenue = cv2.addWeighted(buena,.07,np.full_like(buena,200),.93,0)
        r = self.filtro.analizar(tenue)
        self.assertEqual(r.estado,'REVISAR')
        self.assertIn('CAPTURA NO EVALUABLE',r.motivo)

    def test_ruido_elevado_no_es_defecto_automatico(self):
        img = render('V 12/2028')
        noise = np.random.default_rng(4).normal(0,25,img.shape)
        img = np.uint8(np.clip(img.astype(float)+noise,0,255))
        r = self.filtro.analizar(img)
        self.assertEqual(r.estado,'REVISAR')
        self.assertIn('ruido',r.motivo)

    def test_desenfoque_fuerte_no_se_vota_como_buena(self):
        img = cv2.GaussianBlur(render('VEN 12/28'),(0,0),2.5)
        r = self.filtro.analizar(img)
        self.assertEqual(r.estado,'REVISAR')
        self.assertIn('detalle fino',r.motivo)

    def test_mancha_fuerte_en_captura_clara_se_conserva(self):
        im=render('L:6967 V:24/09/26')
        cv2.circle(im,(260,75),17,(33,28,25),-1)
        r=self.filtro.analizar(im)
        self.assertEqual(r.estado,'MAL')
        self.assertEqual(r.metricas['segunda_pasada'],1.)
        self.assertGreater(r.metricas['concordancia_mascaras'], .7)

    def test_fecha_real_marca_extensa(self):
        path=Path(__file__).resolve().parents[1]/'imagenes_prueba/1995.jpg'
        img=cv2.imread(str(path))[447:1020,360:523]
        self.assertEqual(self.filtro.analizar(img).estado,'MAL')

    def test_tinta_a_un_pixel_es_resolucion_insuficiente(self):
        img = np.full((80,250,3),180,np.uint8)
        cv2.putText(img,'V 12/2028',(6,44),cv2.FONT_HERSHEY_SIMPLEX,.45,
                    (25,25,25),1,cv2.LINE_AA)
        r = self.filtro.analizar(img)
        self.assertEqual(r.estado,'REVISAR')
        self.assertIn('demasiado finos',r.motivo)

    def test_desacuerdo_segunda_pasada_no_condena(self):
        from calidad_impresion import Resultado
        class DosInspectores:
            def __init__(self): self.n=0
            def analizar(self, im):
                self.n+=1
                m=np.ones(im.shape[:2],dtype=np.uint8)*255
                est='MAL' if self.n==1 else 'BIEN'
                return Resultado(est,'simulado',50.,{'snr_contraste':3.,'grosor_medio':4.,
                                  'fraccion_tinta':.12},mascara_tinta=m)
        filtro=InspectorCalidadRobusto()
        filtro.inspector=DosInspectores()
        r=filtro.analizar(render('Ven 12/2028'))
        self.assertEqual(r.estado,'REVISAR')
        self.assertEqual(r.metricas['segunda_pasada'],1.)
        self.assertIn('inestable',r.motivo)

    def test_flujo_robusto_7_fotos_por_producto(self):
        from iniciar_calidad import inspeccionar
        class Caja:
            def __init__(self,box):
                self.xyxy=[self]
                self.box=np.array(box, dtype=np.int32)
            def cpu(self): return self
            def numpy(self): return self.box
        class Pred:
            def __init__(self,box): self.boxes=[Caja(box)]
        class Detector:
            def __init__(self): self.box=None
            def predict(self,frame,conf,verbose): return [Pred(self.box)]
        detector=Detector()
        banda=SeguimientoBanda(min_buenas=1, objetivo=7,min_validas=3)
        eventos=[]
        for i in range(7):
            frame=np.full((230,650,3),(210,190,130),np.uint8)
            x=20+6*i
            cv2.putText(frame,'V 12/2028',(x+10,115),
                        cv2.FONT_HERSHEY_SIMPLEX,.8,(30,20,15),2,cv2.LINE_AA)
            detector.box=(x,60,x+240,142)
            _,datos,_=inspeccionar(frame,detector,self.filtro,.45,dibujar=False)
            self.assertEqual(len(datos),1)
            result, caja = datos[0]
            self.assertEqual(result.estado,'BIEN')
            nuevo=banda.actualizar([Observacion(caja,result.estado,result.motivo)],i*.1,i+1)
            eventos.extend(nuevo.eventos)
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual((eventos[0].buenas,eventos[0].malas),(7,0))

    def test_la_camra_incierta_no_da_voto_pero_banda_decide(self):
        r=self.filtro.analizar(np.full((150,400,3),128,np.uint8))
        self.assertEqual(r.estado,'REVISAR')
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2)
        estados=['REVISAR','BIEN','BIEN']
        events=[]
        for i,est in enumerate(estados):
            res=b.actualizar([Observacion((10+i*4,30,150+i*4,110),est)],i*.1,i+1)
            events+=res.eventos
        self.assertEqual(len(events), 1)
        ev=events[0]
        self.assertEqual(b.cerrar(.6,4), [])
        self.assertEqual(ev.estado,'BIEN')
        self.assertEqual((ev.buenas,ev.ambiguas),(2,1))


if __name__=='__main__':
    unittest.main()

"""Regresiones del filtro de fuentes importado de ideas de VITA.

No usa OCR ni OpenVINO, no requiere camara fisica ni best.pt.
"""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from captura_segura import evaluar_escena, GuardiaCaptura, backends_camara, diagnostico_movimiento_roi
from seguimiento_banda import SeguimientoBanda, Observacion


class TestCapturaProtegida(unittest.TestCase):
    def setUp(self):
        self.frame=np.full((180,360,3),180,np.uint8)
        cv2.putText(self.frame,'FECHA 12/26',(20,90),cv2.FONT_HERSHEY_SIMPLEX,1,(30,30,30),2)

    def test_descarta_falta_de_senal(self):
        self.assertFalse(evaluar_escena(None).util)
        self.assertFalse(evaluar_escena(np.zeros((180,360,3),np.uint8)).util)
        self.assertFalse(evaluar_escena(np.full((180,360,3),255,np.uint8)).util)
        self.assertTrue(evaluar_escena(self.frame).util)

    def test_no_cuenta_frames_exactamente_repetidos(self):
        guardia=GuardiaCaptura(repeticiones_congelado=4)
        estados=[guardia.revisar(self.frame) for _ in range(6)]
        self.assertTrue(estados[0].util)
        self.assertEqual(estados[0].repeticiones,0)
        self.assertTrue(estados[1].util)
        self.assertEqual(estados[1].repeticiones,1)
        self.assertFalse(estados[4].util)
        self.assertIn('congelado',estados[4].motivo)
        movida=np.roll(self.frame,5,axis=1)
        recuperada=guardia.revisar(movida)
        self.assertTrue(recuperada.util)
        self.assertEqual(recuperada.repeticiones,0)

    def test_controladores_y_resolucion_diagnostica(self):
        self.assertEqual([a for a,_ in backends_camara('win32','msmf')],['msmf','dshow','auto'])
        self.assertEqual([a for a,_ in backends_camara('win32','auto')],['dshow','msmf','auto'])
        self.assertEqual(backends_camara('linux','msmf')[0][0],'auto')
        with self.assertRaises(ValueError):
            backends_camara('win32','incorrecto')

    def test_diagnostico_no_asume_formato(self):
        r=diagnostico_movimiento_roi(self.frame)
        self.assertGreater(r['gradiente_tenengrad'],0)
        self.assertGreaterEqual(r['anisotropia_gradiente'],0)
        self.assertLessEqual(r['anisotropia_gradiente'],1)
        self.assertEqual(diagnostico_movimiento_roi(None)['gradiente_tenengrad'],0)

    def test_falla_de_camara_no_aprueba_votos_previos(self):
        t=SeguimientoBanda(objetivo=50,min_buenas=5,intervalo_s=0)
        for i in range(8):
            t.actualizar([Observacion((10,20,150,90),'BIEN')],i*.1,i+1)
        e=t.invalidar_por_falla_camara(1.1,10)
        self.assertEqual(len(e),1)
        self.assertEqual(e[0].estado,'MAL')
        self.assertEqual(e[0].buenas,8)
        self.assertEqual(e[0].cierre,'falla_camara')
        self.assertIn('INTERRUMPIDA',e[0].motivo)
        self.assertEqual(t.pistas,{})
        self.assertEqual(t.cerrar(1.2,11),[])

    def test_falla_no_emite_duplicado_de_producto_ya_finalizado(self):
        t=SeguimientoBanda(objetivo=5,min_buenas=5,intervalo_s=0)
        hechos=[]
        for i in range(5):
            hechos.extend(t.actualizar([Observacion((10,20,150,90),'BIEN')],i*.1,i+1).eventos)
        self.assertEqual(len(hechos),1)
        self.assertEqual(hechos[0].estado,'BIEN')
        self.assertEqual(t.invalidar_por_falla_camara(1.1,10),[])

if __name__=='__main__': unittest.main()

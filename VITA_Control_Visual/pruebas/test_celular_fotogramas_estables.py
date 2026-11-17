"""Regresion del parpadeo con camara virtual de celular."""
from pathlib import Path
import sys
import unittest
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from captura_segura import GuardiaCaptura
from interfaz_nutreo import VistaCuadro, vista_sin_nuevo_fotograma


class TestVideoCelular(unittest.TestCase):
    def setUp(self):
        self.frame=np.full((150,320,3),210,np.uint8)
        cv2.putText(self.frame,'FECHA 10-2026',(20,72),cv2.FONT_HERSHEY_SIMPLEX,1,(35,35,35),2)

    def test_wifi_repetidos_rapidos_no_es_congelamiento(self):
        g=GuardiaCaptura(repeticiones_congelado=4,segundos_congelado=2.5)
        self.assertTrue(g.revisar(self.frame,instante=0.0).util)
        for i in range(1,100):
            estado=g.revisar(self.frame,instante=i*.01)
            self.assertTrue(estado.util, 'No marcar congelado en menos de un segundo')
            self.assertEqual(estado.repeticiones,i)
        self.assertFalse(g.revisar(self.frame,instante=2.7).util)
        nueva=self.frame.copy()
        nueva[0,0]=[1,2,3]
        recuperado=g.revisar(nueva,instante=2.8)
        self.assertTrue(recuperado.util)
        self.assertEqual(recuperado.repeticiones,0)

    def test_espera_conserva_recuadro_estado_y_ultimo_voto(self):
        dibujada=self.frame.copy()
        cv2.rectangle(dibujada,(4,4),(300,142),(40,190,130),1)
        cv2.rectangle(dibujada,(35,35),(280,110),(255,190,40),2)
        vista=VistaCuadro(dibujada,10.0,estado='EVALUANDO PRODUCTO',producto=7,
                          buenas=12,malas=0, muestreos=15, ultima_muestra='BUENA',
                          etapas_version=(7,15),
                          filtro_paneles={'etapa05':self.frame.copy()})
        pausa=vista_sin_nuevo_fotograma(vista,self.frame,11.0,'fotograma repetido')
        self.assertEqual(pausa.estado,'EVALUANDO PRODUCTO')
        self.assertEqual(pausa.producto,7)
        self.assertEqual(pausa.buenas,12)
        self.assertEqual(pausa.muestreos,15)
        self.assertEqual(pausa.ultima_muestra,'BUENA')
        self.assertEqual(pausa.etapas_version,(7,15))
        self.assertEqual(pausa.fotograma[100,35].tolist(),dibujada[100,35].tolist())
        self.assertIsNot(pausa.fotograma, dibujada)
        self.assertIn('NO se suman votos',pausa.aviso)
        self.assertNotIn('CAPTURA NO UTIL',pausa.ultima_muestra)

    def test_fallo_prolongado_no_sugiere_aprobacion(self):
        pausa=vista_sin_nuevo_fotograma(None,self.frame,9.,'sin imagen',interrupcion=True)
        self.assertEqual(pausa.estado,'CAMARA SIN SENAL')
        self.assertNotEqual(pausa.ultima_muestra,'BUENA')
        self.assertIn('Sin evaluacion',pausa.motivo)

if __name__=='__main__': unittest.main()

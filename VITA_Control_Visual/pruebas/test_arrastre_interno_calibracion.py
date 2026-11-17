"""Regresion con un defecto señalado por el usuario y controles visuales.

Estas comprobaciones de software no miden precision ni sustituyen etiquetas
humanas independientes de buena/mala impresion en banda.
"""
import unittest
from pathlib import Path
import cv2
import numpy as np
from calidad_impresion import InspectorCalidad
from inspeccion_robusta import InspectorCalidadRobusto
from deteccion_arrastre_interno import detectar_arrastre_interno
from visualizador_filtros import crear_vistas_filtros
from iniciar_calidad import caja_recorte

DIR=Path(__file__).parent/'muestras_calibracion'

def cargar(nombre):
    im=cv2.imread(str(DIR/nombre))
    assert im is not None,nombre
    return im

class TestArrastreInterno(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspector=InspectorCalidadRobusto()

    def test_reproduce_fallo_real_reportado(self):
        im=cargar('defecto_confirmado_11550.png')
        resultado=self.inspector.analizar(im)
        self.assertEqual(resultado.estado,'MAL',resultado.motivo)
        self.assertIn('Arrastre lineal',resultado.motivo)
        self.assertGreater(resultado.metricas['indice_arrastre_interno'], .3)
        self.assertGreater(np.count_nonzero(resultado.mascara_sospechosa), 40)

    def test_defecto_con_recorte_del_12_por_ciento(self):
        # El recorte automatico opera antes de evaluar, no solo en el dibujo.
        im=cargar('defecto_confirmado_11550.png')
        h,w=im.shape[:2]
        box=caja_recorte(0,0,w,h,im.shape,recorte_borde=.12)
        rec=im[box[1]:box[3],box[0]:box[2]]
        self.assertEqual(self.inspector.analizar(rec).estado,'MAL')

    def test_sigue_detectando_vertical(self):
        im=cargar('defecto_confirmado_11550.png')
        vert=cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE)
        self.assertEqual(self.inspector.analizar(vert).estado,'MAL')

    def test_defecto_zip_distintas_fotos(self):
        for nombre in ('defecto_similar_164304.png','defecto_similar_164308.png'):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.inspector.analizar(cargar(nombre)).estado,'MAL')

    def test_recorte_12_conserva_falta_en_segunda_foto(self):
        im=cargar('defecto_similar_164308.png')
        h=im.shape[0]
        rec=im[round(.12*h):round(.88*h)]
        self.assertEqual(self.inspector.analizar(rec).estado,'MAL')

    def test_no_inventa_defecto_en_comparacion(self):
        r=self.inspector.analizar(cargar('comparacion_sin_arrastre_visible_161708.png'))
        self.assertEqual(r.estado,'BIEN')
        self.assertEqual(r.metricas['indice_arrastre_interno'],0.)

    def test_sombra_barcode_y_lineas_impresas(self):
        for nombre in ('sintetica_sin_defecto.png','sintetica_sombra.png',
                       'sintetica_barcode.png','sintetica_lineas_originales.png'):
            with self.subTest(nombre=nombre):
                r=self.inspector.analizar(cargar(nombre))
                self.assertNotEqual(r.estado,'MAL',r.motivo)
                self.assertEqual(r.metricas['indice_arrastre_interno'],0.)

    def test_smear_sintetico(self):
        r=self.inspector.analizar(cargar('sintetica_arrastre.png'))
        self.assertEqual(r.estado,'MAL')

    def test_marcado_etapa_06_coincide_con_motivo(self):
        im=cargar('defecto_confirmado_11550.png')
        r=self.inspector.analizar(im)
        vistas=crear_vistas_filtros(im,r)
        self.assertIn('06  Zonas sospechosas (real)',vistas)
        self.assertIn('05  Tinta segmentada (real)',vistas)
        self.assertGreater(np.count_nonzero(r.mascara_sospechosa),50)
        self.assertGreater(r.metricas['pixeles_sospechosos'],50)

if __name__=='__main__':unittest.main()

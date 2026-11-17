"""Regresiones: el empaque no es la fecha. No valida formatos ni numero de letras."""
from pathlib import Path
import sys
import unittest
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calidad_impresion import InspectorCalidad
from inspeccion_robusta import InspectorCalidadRobusto
from visualizador_filtros import crear_vistas_filtros
from pruebas.test_calidad import render


class TestFocoExclusivoTinta(unittest.TestCase):
    def setUp(self):
        self.inspector = InspectorCalidad()
        self.base = render('EXP 15-08-29')

    def test_banda_oscura_ajena_en_borde(self):
        imagen = self.base.copy()
        cv2.rectangle(imagen, (0, 110), (549, 121), (20, 15, 15), -1)
        resultado = self.inspector.analizar(imagen)
        self.assertEqual(resultado.estado, 'BIEN', resultado.motivo)
        self.assertGreaterEqual(resultado.metricas['bandas_externas_ignoradas'], 1)
        self.assertLessEqual(resultado.metricas['indice_barrido'], .02)
        self.assertEqual(np.count_nonzero(resultado.mascara_sospechosa), 0)

    def test_banda_oscura_ajena_sin_tocar_extremo(self):
        imagen = self.base.copy()
        cv2.rectangle(imagen, (25, 110), (520, 116), (20, 15, 15), -1)
        resultado = self.inspector.analizar(imagen)
        self.assertEqual(resultado.estado, 'BIEN', resultado.motivo)
        self.assertGreaterEqual(resultado.metricas['bandas_externas_ignoradas'], 1)

    def test_banda_tenue_no_hace_votar_mal(self):
        imagen = self.base.copy()
        cv2.rectangle(imagen, (0, 106), (549, 114), (196, 176, 118), -1)
        resultado = self.inspector.analizar(imagen)
        self.assertEqual(resultado.estado, 'BIEN', resultado.motivo)
        self.assertEqual(np.count_nonzero(resultado.mascara_sospechosa), 0)

    def test_fecha_vertical_con_banda_lateral(self):
        imagen = cv2.rotate(self.base, cv2.ROTATE_90_CLOCKWISE)
        cv2.rectangle(imagen, (112, 15), (126, 535), (20, 15, 15), -1)
        resultado = self.inspector.analizar(imagen)
        self.assertEqual(resultado.estado, 'BIEN', resultado.motivo)
        self.assertGreaterEqual(resultado.metricas['bandas_externas_ignoradas'], 1)

    def test_mancha_sobre_tinta_sigue_siendo_defecto(self):
        imagen = render('L:6967 V:24/09/26')
        cv2.circle(imagen, (260,75), 17, (33, 28, 25), -1)
        r = self.inspector.analizar(imagen)
        self.assertEqual(r.estado, 'MAL')
        self.assertGreater(np.count_nonzero(r.mascara_sospechosa), 0)
        visual = crear_vistas_filtros(imagen, r)
        self.assertIn('06  Zonas sospechosas (real)', visual)

    def test_arrastre_sobre_fecha_se_sigue_detectando(self):
        im = cv2.imread(str(Path(__file__).resolve().parents[1] /
                            'imagenes_prueba' / '1995.jpg'))
        r = self.inspector.analizar(im[447:1020, 360:523])
        self.assertEqual(r.estado, 'MAL')
        self.assertGreater(r.metricas['indice_barrido'], .20)
        self.assertLessEqual(r.metricas['radio_busqueda_tinta_px'], 7.)

    def test_ambiguedad_explicita_indicador(self):
        im = cv2.imread(str(Path(__file__).resolve().parents[1] /
                            'imagenes_prueba' / '1757.jpg'))
        r = self.inspector.analizar(im[558:940,458:565])
        # El inspector SOLO evalua estructura de tinta: la camara confirma
        # si hay detalle suficiente, de lo contrario REVISAR por captura.
        self.assertEqual(r.estado, 'BIEN')
        self.assertIn('Aviso:', r.motivo)
        self.assertNotIn('Trazos ambiguos', r.motivo)
        self.assertLessEqual(np.count_nonzero(r.mascara_sospechosa), 10)
        robusto = InspectorCalidadRobusto().analizar(im[558:940,458:565])
        self.assertEqual(robusto.estado, 'REVISAR')
        self.assertIn('CAPTURA NO EVALUABLE', robusto.motivo)

    def test_variable_texto_y_color(self):
        for texto, fondo, tinta in [
            ('LOT', (230,230,230), (10,10,10)),
            ('V:12/28', (55,50,40), (238,238,225)),
            ('2028-11-09 00:17', (195,130,80), (25,15,15)),
            ('9/7/26', (90,145,140), (150,75,160)),
        ]:
            with self.subTest(texto=texto):
                r = self.inspector.analizar(render(texto, fondo, tinta))
                self.assertNotEqual(r.estado, 'MAL')

    def test_no_se_reprocesa_una_toma_buena_sin_alertas_de_camara(self):
        robusto = InspectorCalidadRobusto()
        r = robusto.analizar(render('EXP 15-08-29'))
        self.assertEqual(r.estado, 'BIEN')
        self.assertEqual(r.metricas['segunda_pasada'], 0.)

    def test_foto_borrosa_no_es_defecto_de_tinta_por_defecto(self):
        robusto = InspectorCalidadRobusto()
        im = cv2.GaussianBlur(self.base, (0,0), 2.5)
        r = robusto.analizar(im)
        self.assertEqual(r.estado, 'REVISAR')
        self.assertIn('CAPTURA NO EVALUABLE', r.motivo)


if __name__ == '__main__':
    unittest.main()

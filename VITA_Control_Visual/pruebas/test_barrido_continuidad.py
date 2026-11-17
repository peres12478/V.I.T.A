"""Pruebas del barrido adaptativo, sin OCR ni caracteres obligatorios."""
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calidad_impresion import InspectorCalidad
from inspeccion_robusta import InspectorCalidadRobusto
from barrido_continuidad import detectar_barrido_continuidad
from seguimiento_banda import SeguimientoBanda, Observacion

HERE = Path(__file__).resolve().parent


def imagen(path):
    im = cv2.imread(str(HERE / path))
    if im is None:
        raise AssertionError(f'No se pudo leer {path}')
    return im


class TestBarridoContinuidad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inspector = InspectorCalidadRobusto()

    def test_foto_real_muy_borrada_no_aprueba(self):
        im=imagen('fecha_11682_centro.png')
        r=self.inspector.analizar(im)
        self.assertEqual(r.estado,'MAL')
        self.assertIn('BARRIDO',r.motivo)
        self.assertGreater(r.metricas['coincidencias_continuidad'],0)
        self.assertGreater(np.count_nonzero(r.mascara_sospechosa),0)

    def test_recorte_estrecho_no_se_cuenta_como_bueno(self):
        im=imagen('fecha_11682_estrecha.png')
        r=self.inspector.analizar(im)
        self.assertIn(r.estado,('MAL','REVISAR'))
        self.assertGreater(r.metricas['indice_continuidad_tinta'],0.)

    def test_fecha_sintetica_sana_no_se_marca(self):
        r=self.inspector.analizar(imagen('barrido_normal.png'))
        self.assertEqual(r.estado,'BIEN')
        self.assertEqual(r.metricas['indice_continuidad_tinta'],0.)

    def test_espacios_intencionales_no_exigen_caracteres(self):
        r=self.inspector.analizar(imagen('barrido_spaces.png'))
        self.assertEqual(r.estado,'BIEN')
        self.assertEqual(r.metricas['indice_continuidad_tinta'],0.)

    def test_desvanecido_sintetico_no_aprueba_sin_prueba(self):
        from test_regresion_errores_11669_11670 import fecha_sintetica
        r=self.inspector.analizar(fecha_sintetica(.75))
        self.assertEqual(r.estado,'REVISAR')
        self.assertGreater(r.metricas['indice_continuidad_tinta'],0.)

    def test_hueco_sin_restos_no_se_declara_bueno(self):
        # Ausencia limpia de tinta = evidencia ambigua, NO crear caracteres
        # imaginarios ni afirmar un defecto sin referencia del formato.
        r=self.inspector.analizar(imagen('barrido_erased.png'))
        self.assertEqual(r.estado,'REVISAR')
        self.assertEqual(r.metricas['continuidad_confirmada'],0.)

    def test_tinta_extremadamente_tenue_no_es_buena(self):
        r=self.inspector.analizar(imagen('barrido_faded.png'))
        self.assertEqual(r.estado,'REVISAR')

    def test_fecha_buena_real_original_se_mantiene(self):
        r=self.inspector.analizar(imagen('casos_reales/161708_comparacion.png'))
        self.assertEqual(r.estado,'BIEN')

    def test_arrastre_interno_sigue_siendomal(self):
        r=self.inspector.analizar(imagen('casos_reales/11550_arrastre.png'))
        self.assertEqual(r.estado,'MAL')

    def test_mascara_de_gui_marca_las_guias_no_la_foto_completa(self):
        from visualizador_filtros import crear_vistas_filtros
        im=imagen('fecha_11682_centro.png')
        r=self.inspector.analizar(im)
        vistas=crear_vistas_filtros(im,r)
        self.assertEqual(set(vistas.keys()),{
            '01  Fecha detectada','02  Luminosidad LAB','03  Fondo estimado',
            '04  Contraste local (apoyo)','05  Tinta segmentada (real)',
            '06  Zonas sospechosas (real)'})
        self.assertEqual(vistas['05  Tinta segmentada (real)'].shape,im.shape)
        self.assertFalse(np.array_equal(vistas['06  Zonas sospechosas (real)'],im))
        self.assertEqual(r.mascara_sospechosa.shape[:2],im.shape[:2])

    def test_al_girar_recorte_no_desaparece_alerta(self):
        im=imagen('fecha_11682_centro.png')
        rotated=cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE)
        r=self.inspector.analizar(rotated)
        self.assertNotEqual(r.estado,'BIEN')
        self.assertGreater(r.metricas['indice_continuidad_tinta'],0)

    def test_seguimiento_no_convierte_sospecha_en_buena(self):
        s=SeguimientoBanda(objetivo=7,min_buenas=5,intervalo_s=0.)
        r=self.inspector.analizar(imagen('fecha_11682_centro.png'))
        eventos=[]
        for i in range(7):
            eventos+=s.actualizar([Observacion((30,40,280,90),r.estado)],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual(eventos[0].buenas,0)

    def test_41_buenas_de_50_sigue_aprobando_al_salir(self):
        s=SeguimientoBanda(objetivo=50,min_buenas=5,intervalo_s=0,
                          max_ausencia_s=.65,max_sin_ver=3)
        for i in range(41):
            s.actualizar([Observacion((30,40,280,90),'BIEN')],i*.1,i+1)
        eventos=[]
        for i,t in enumerate((4.15,4.48,4.95),start=42):
            eventos+=s.actualizar([],t,i).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')


if __name__=='__main__':
    unittest.main()

"""Regresiones sobre mascara 05 y captura original, sin OCR/OpenVINO.

Las mascaras extraidas de fotos de la PANTALLA son referencias diagnosticas:
NO equivalen a fotogramas originales del sensor, ni a predicciones de YOLO.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auditoria_mascara import auditar_mascara_tinta
from evidencia_inspeccion import registrar_evidencia
from inspeccion_robusta import InspectorCalidadRobusto
from calidad_impresion import InspectorCalidad
from seguimiento_banda import SeguimientoBanda, Observacion

ROOT = Path(__file__).parent


def imagen(archivo):
    x=cv2.imread(str(ROOT / archivo))
    if x is None:raise AssertionError(f'No se encontro muestra {archivo}')
    return x


class TestAuditoriaMascara(unittest.TestCase):
    def test_captura_historial_46_buenas_mascara_borrada_es_sospechosa(self):
        mascara=cv2.imread(str(ROOT/'casos_reportados/11709_mascara_extraida.png'), 0)
        a=auditar_mascara_tinta(mascara)
        self.assertTrue(a.sospecha)
        self.assertGreater(a.indice, .50)
        self.assertGreater(np.count_nonzero(a.mascara), 0)

    def test_mascara_con_linea_externa_no_aprueba_el_recorte(self):
        mascara=cv2.imread(str(ROOT/'casos_reportados/11713_mascara_extraida.png'), 0)
        a=auditar_mascara_tinta(mascara)
        self.assertTrue(a.sospecha)
        self.assertIn('linea larga',a.motivo)

    def test_espacios_normales_no_producen_falso_defecto(self):
        r=InspectorCalidad().analizar(imagen('barrido_spaces.png'))
        self.assertFalse(auditar_mascara_tinta(r.mascara_tinta).sospecha)
        self.assertEqual(InspectorCalidadRobusto().analizar(imagen('barrido_spaces.png')).estado,'BIEN')

    def test_fecha_sana_simulada_se_conserva(self):
        r=InspectorCalidadRobusto().analizar(imagen('barrido_normal.png'))
        self.assertEqual(r.estado,'BIEN')
        self.assertEqual(r.metricas['indice_auditoria_mascara'],0.)

    def test_fecha_borrada_original_sigue_rechazandose(self):
        r=InspectorCalidadRobusto().analizar(imagen('fecha_11682_centro.png'))
        self.assertEqual(r.estado,'MAL')
        self.assertGreater(np.count_nonzero(r.mascara_sospechosa), 0)

    def test_recorte_estrecho_no_aprueba_por_error(self):
        r=InspectorCalidadRobusto().analizar(imagen('fecha_11682_estrecha.png'))
        self.assertNotEqual(r.estado,'BIEN')

    def test_incertidumbre_no_se_convierte_en_voto_bueno(self):
        estado='REVISAR'
        s=SeguimientoBanda(objetivo=7,min_buenas=5,intervalo_s=0.)
        eventos=[]
        for i in range(7):
            eventos+=s.actualizar([Observacion((20,30,300,130),estado)],i*.2,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual(eventos[0].buenas,0)

    def test_evidencia_guarda_voto_y_05_06(self):
        im=imagen('barrido_normal.png')
        r=InspectorCalidadRobusto().analizar(im)
        with TemporaryDirectory() as d:
            f=registrar_evidencia(Path(d),4,1,im,r)
            self.assertTrue(f.is_file())
            self.assertTrue((f.parent/'foto_001_05_tinta.png').exists())
            self.assertTrue((f.parent/'foto_001_06_sospechas.png').exists())
            lines=(f.parent/'diagnostico.jsonl').read_text(encoding='utf8').splitlines()
            self.assertEqual(len(lines),1)
            data=json.loads(lines[0])
            self.assertEqual(data['estado'],r.estado)
            self.assertEqual(data['captura'],1)
            self.assertIn('indice_auditoria_mascara',data['metricas'])

if __name__=='__main__':unittest.main()

"""Regresiones de los problemas de votacion e impresion incompleta.

No se usa OCR ni se presupone el numero de caracteres o lineas.
"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from calidad_impresion import InspectorCalidad
from inspeccion_robusta import InspectorCalidadRobusto
from seguimiento_banda import SeguimientoBanda, Observacion


def fecha_sintetica(debilitamiento=0.):
    im = np.full((145,600,3), (220,190,150),dtype=np.uint8)
    cv2.putText(im,'L:690150 304 07:52',(24,62),cv2.FONT_HERSHEY_SIMPLEX,
                1.25,(30,35,40),3,cv2.LINE_AA)
    cv2.putText(im,'Ven.:29/10/26',(24,119),cv2.FONT_HERSHEY_SIMPLEX,
                1.25,(30,35,40),3,cv2.LINE_AA)
    if debilitamiento:
        a,b=145,265
        im[:,a:b]=np.uint8(im[:,a:b].astype(np.float32)*(1-debilitamiento)+
                           np.array((220,190,150),dtype=np.float32)*debilitamiento)
    return im


class TestErroresReportados(unittest.TestCase):
    def test_41_buenas_de_50_y_cero_malas_pasa_al_salir(self):
        s=SeguimientoBanda(objetivo=50,min_buenas=5,intervalo_s=0,
                          bloqueo_unico=True,max_ausencia_s=.65,max_sin_ver=3)
        eventos=[]
        for i in range(41):
            eventos += s.actualizar([Observacion((40,50,320,90),'BIEN')],i*.1,i+1).eventos
        self.assertEqual(eventos,[])
        # Se aleja de camara sin completar la cifra maxima configurada.
        for i,t in enumerate((4.15,4.48,4.95),start=42):
            eventos += s.actualizar([],t,i).eventos
        self.assertEqual(len(eventos),1)
        e=eventos[0]
        self.assertEqual(e.estado,'BIEN')
        self.assertEqual((e.buenas,e.malas,e.total),(41,0,41))
        self.assertIn('MAYORIA BUENA',e.motivo)
        self.assertEqual(s.proximo_id,2)

    def test_una_buena_no_aprueba_aunque_no_haya_malas(self):
        s=SeguimientoBanda(objetivo=50,min_buenas=5,intervalo_s=0)
        s.actualizar([Observacion((50,50,300,100),'BIEN')],0,1)
        e=s.cerrar(2.,3)[0]
        self.assertEqual(e.estado,'MAL')
        self.assertIn('BUENAS INSUFICIENTES',e.motivo)

    def test_original_aprobaba_trazos_muy_debilitados(self):
        imagen=fecha_sintetica(.75)
        r=InspectorCalidad().analizar(imagen)
        # Reproduce la clase de falso positivo que motivó este control.
        self.assertEqual(r.estado,'BIEN')
        nuevo=InspectorCalidadRobusto().analizar(imagen)
        self.assertEqual(nuevo.estado,'REVISAR')
        self.assertIn('IMPRESION INCOMPLETA',nuevo.motivo)
        self.assertGreater(nuevo.metricas['indice_debilitamiento_local'],.57)
        self.assertGreater(np.count_nonzero(nuevo.mascara_sospechosa),0)

    def test_fecha_normal_no_es_rechazada_por_nuevo_filtro(self):
        nuevo=InspectorCalidadRobusto().analizar(fecha_sintetica(0.))
        self.assertEqual(nuevo.estado,'BIEN')
        self.assertEqual(nuevo.metricas['indice_debilitamiento_local'],0.)

    def test_impresion_debil_no_suma_votos_buenos(self):
        inspector=InspectorCalidadRobusto()
        estado=inspector.analizar(fecha_sintetica(.85)).estado
        self.assertEqual(estado,'REVISAR')
        s=SeguimientoBanda(objetivo=7,min_buenas=5,intervalo_s=0)
        eventos=[]
        for i in range(7):
            eventos += s.actualizar([Observacion((30,40,280,90),estado)],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual((eventos[0].buenas,eventos[0].malas,eventos[0].ambiguas),(0,0,7))
        self.assertIn('SIN VOTOS EVALUABLES',eventos[0].motivo)

    def test_arrastre_interno_real_sigue_detectado(self):
        base=Path(__file__).resolve().parent/'casos_reales'/'11550_arrastre.png'
        im=cv2.imread(str(base))
        self.assertIsNotNone(im)
        r=InspectorCalidadRobusto().analizar(im)
        self.assertEqual(r.estado,'MAL')
        self.assertIn('Arrastre lineal',r.motivo)

    def test_comparacion_real_sin_arrastre_se_mantiene_bien(self):
        base=Path(__file__).resolve().parent/'casos_reales'/'161708_comparacion.png'
        im=cv2.imread(str(base))
        self.assertIsNotNone(im)
        self.assertEqual(InspectorCalidadRobusto().analizar(im).estado,'BIEN')

    def test_captura_del_monitor_no_debe_generar_buena_automatica(self):
        # Esto es SOLO una foto de pantalla; NO equivale al frame BGR original.
        base=Path(__file__).resolve().parent/'casos_reales'/'11669_captura_pantalla.png'
        im=cv2.imread(str(base))
        self.assertIsNotNone(im)
        self.assertEqual(InspectorCalidadRobusto().analizar(im).estado,'REVISAR')


if __name__ == '__main__':
    unittest.main()

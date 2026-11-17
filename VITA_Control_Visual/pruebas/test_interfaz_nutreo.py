"""Pruebas de la GUI sin ventana, camara fisica ni Ultralytics."""
import tempfile
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from calidad_impresion import Resultado
from interfaz_nutreo import Configuracion, ProcesadorNutreo, RegistroEventos
from visualizador_filtros import crear_vistas_filtros


class FakeTensor:
    def __init__(self, data): self.data = np.array(data)
    def cpu(self): return self
    def numpy(self): return self.data


class FakeBox:
    def __init__(self, b): self.xyxy = [FakeTensor(b)]


class FakePred:
    def __init__(self, boxes): self.boxes = [FakeBox(b) for b in boxes]


class FakeDetector:
    def __init__(self, boxes): self.boxes = boxes
    def predict(self, frame, conf, verbose=False): return [FakePred(self.boxes)]


class FakeInspector:
    def __init__(self, estados):
        self.estados = estados
        self.i = 0
    def analizar(self, crop):
        h, w = crop.shape[:2]
        estado = self.estados[min(self.i, len(self.estados)-1)]
        self.i += 1
        mask = np.zeros((h,w),np.uint8)
        cv2.rectangle(mask, (3,3), (18,13), 255, -1)
        suspect = np.zeros_like(mask)
        cv2.line(suspect, (5,4), (10,6), 255, 1)
        return Resultado(estado, 'Diagnostico de prueba', 65.,
                        {'camara_contraste_luz': 80., 'camara_ruido_relativo': .012,
                         'segunda_pasada': 1.}, [], mask, suspect, 'oscura')


class TestInterfazNutreo(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((180,360,3), 210, np.uint8)
        cv2.putText(self.frame, 'VENCE 11/26', (45,90), cv2.FONT_HERSHEY_SIMPLEX,
                    .8,(35,35,35),2,cv2.LINE_AA)
        self.box = [34, 55, 265, 110]

    def make_engine(self, states, opts=None, registro=None):
        return ProcesadorNutreo(opts or Configuracion(min_buenas=1, control_visibilidad=False, fotos=7,intervalo_ms=0),
                                FakeDetector([self.box]), FakeInspector(states), registro)

    def test_esperando_si_no_fecha(self):
        p = ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, ), FakeDetector([]), FakeInspector(['BIEN']))
        vista, eventos = p.procesar(self.frame, 0.)
        self.assertEqual(vista.estado, 'ESPERANDO PRODUCTO')
        self.assertEqual(vista.regiones, 0)
        self.assertEqual(vista.filtro_paneles, {})
        self.assertEqual(eventos, [])

    def test_mayoria_buena_y_un_solo_evento(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'salida.csv'
            log = RegistroEventos(path)
            p = self.make_engine(['BIEN','MAL','BIEN','BIEN','MAL','BIEN','BIEN','BIEN'], registro=log)
            recibidos=[]
            for n in range(12):
                vista, eventos = p.procesar(self.frame, n*.1)
                recibidos.extend(eventos)
            log.close()
            self.assertEqual(len(recibidos), 1)
            self.assertEqual(recibidos[0].estado, 'BIEN')
            self.assertEqual(recibidos[0].buenas, 5)
            self.assertEqual(recibidos[0].malas, 2)
            self.assertEqual(vista.estado, 'PASA')
            self.assertEqual(len(path.read_text(encoding='utf-8-sig').splitlines()),2)

    def test_mayoria_mala_es_no_pasa(self):
        estados=['MAL','BIEN','MAL','MAL','BIEN','MAL','MAL']
        p = self.make_engine(estados)
        for n in range(7):
            v, ev = p.procesar(self.frame,n*.1)
        self.assertEqual(v.estado,'NO PASA')
        self.assertEqual(ev[0].estado,'MAL')

    def test_dudosas_no_votan_y_se_muestra_motivo(self):
        p=self.make_engine(['REVISAR','BIEN','BIEN','REVISAR','MAL','BIEN','MAL','BIEN','BIEN'])
        for n in range(9):
            vista, ev=p.procesar(self.frame,n*.1)
        self.assertEqual(vista.estado,'PASA')
        self.assertEqual(vista.ambiguas,2)
        self.assertEqual(vista.validas,5)
        self.assertEqual(vista.muestreos,7)
        self.assertEqual(vista.ultima_muestra,'DECISION FINAL')

    def test_historico_cambio_a_esperando(self):
        detector=FakeDetector([self.box])
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=2,min_fotos=2,intervalo_ms=0),
                          detector,FakeInspector(['MAL']))
        p.procesar(self.frame,0)
        v, ev=p.procesar(self.frame,.1)
        self.assertEqual(v.estado,'NO PASA')
        detector.boxes=[]
        v,_=p.procesar(self.frame,.3)
        self.assertEqual(v.estado,'NO PASA') # Mensaje visible brevemente
        p.procesar(self.frame,.5)
        p.procesar(self.frame,.8)
        v,_=p.procesar(self.frame,2.6)
        self.assertEqual(v.estado,'ESPERANDO PRODUCTO')

    def test_paneles_reflejan_mascaras_de_inspector(self):
        r=FakeInspector(['MAL']).analizar(self.frame)
        p=crear_vistas_filtros(self.frame,r)
        self.assertEqual(len(p),6)
        self.assertTrue(all(i.shape==self.frame.shape for i in p.values()))
        self.assertTrue(np.array_equal(p['05  Tinta segmentada (real)'][:,:,0],r.mascara_tinta))
        # Overlay solo modifica pixeles sospechosos.
        self.assertTrue(np.array_equal(p['06  Zonas sospechosas (real)'][0,0],self.frame[0,0]))
        self.assertTrue(np.any(np.any(p['06  Zonas sospechosas (real)'] != self.frame, axis=2) & (r.mascara_sospechosa > 0)))

    def test_cada_producto_tiene_seguimiento_independiente(self):
        # Dos cajas activas de la misma imagen y dos votos por cada una.
        detector=FakeDetector([[10,30,130,100],[190,30,315,100]])
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=2,min_fotos=2,intervalo_ms=0,bloqueo_unico=False),
                          detector,FakeInspector(['BIEN','MAL','BIEN','MAL']))
        recibidos=[]
        for n in range(2):
            _,e=p.procesar(self.frame,n*.2)
            recibidos += e
        self.assertEqual(len(recibidos),2)
        self.assertNotEqual(recibidos[0].id,recibidos[1].id)
        self.assertEqual({ev.estado for ev in recibidos},{'BIEN','MAL'})

if __name__ == '__main__': unittest.main()

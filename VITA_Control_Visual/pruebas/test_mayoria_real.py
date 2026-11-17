"""Pruebas de la anterior politica de mayoria, configurada explicitamente para compatibilidad."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from seguimiento_banda import Observacion, SeguimientoBanda
from interfaz_nutreo import Configuracion, ProcesadorNutreo
from calidad_impresion import Resultado


def observar(sistema, estados, distancia=.11):
    """Un recuadro desplazandose a velocidad moderada a lo largo de la banda."""
    eventos=[]
    for i, estado in enumerate(estados):
        salida=sistema.actualizar([Observacion((20+i*3,40,180+i*3,95), estado)],i*distancia,i+1)
        eventos+=salida.eventos
        assert salida.asignaciones[0][0]==1, 'No se debe abrir un ID nuevo'
    return eventos

class _Tensor:
    def __init__(self, d): self.d=np.array(d)
    def cpu(self): return self
    def numpy(self): return self.d
class _Caja:
    def __init__(self, caja): self.xyxy=[_Tensor(caja)]
class _Pred:
    def __init__(self, cajas): self.boxes=[_Caja(c) for c in cajas]
class _Modelo:
    def __init__(self, cajas): self.boxes=cajas
    def predict(self, frame, conf, verbose=False): return [_Pred(self.boxes)]
class _Inspector:
    def __init__(self, estados): self.estados=iter(estados)
    def analizar(self, crop):
        estado=next(self.estados, 'REVISAR')
        h,w=crop.shape[:2]
        return Resultado(estado, f'Evaluacion {estado}', 30., {}, [],
                         np.zeros((h,w),dtype=np.uint8),
                         np.zeros((h,w),dtype=np.uint8),'oscura')

class TestMayoriaReal(unittest.TestCase):
    def test_trece_buenas_dos_malas_quince_inciertas_aprueba(self):
        estados=['BIEN']*13+['MAL']*2+['REVISAR']*15
        b=SeguimientoBanda(min_buenas=1, objetivo=30, min_validas=20, proporcion_minima=.75,
                           bloqueo_unico=True, intervalo_s=.075)
        eventos=observar(b,estados)
        self.assertEqual(len(eventos),1)
        e=eventos[0]
        self.assertEqual(e.estado,'BIEN')
        self.assertEqual((e.buenas,e.malas,e.ambiguas,e.total),(13,2,15,30))
        self.assertIn('MAYORIA BUENA',e.motivo)
        self.assertIn('AVISO DE CONFIABILIDAD',e.motivo)
        self.assertEqual(b.pistas[1].estado_final,'BIEN')
        self.assertEqual(b.proximo_id,2)

    def test_31_capturas_fraccion_inferior_no_rechaza_mayoria_buena(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=31, min_validas=29, proporcion_minima=.95,
                           bloqueo_unico=True)
        ev=observar(b,['REVISAR']*16+['MAL']*2+['BIEN']*13)
        self.assertEqual(len(ev),1)
        self.assertEqual((ev[0].buenas,ev[0].malas,ev[0].ambiguas),(13,2,16))
        self.assertEqual(ev[0].estado,'BIEN')

    def test_mayoria_mala_sin_umbral_fijo(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=30,bloqueo_unico=True)
        ev=observar(b,['BIEN']*12+['MAL']*13+['REVISAR']*5)
        self.assertEqual(len(ev),1)
        self.assertEqual(ev[0].estado,'MAL')
        self.assertIn('MAYORIA MALA',ev[0].motivo)

    def test_empate_no_pasa_preventivo(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        ev=observar(b,['MAL']*3+['BIEN']*3+['REVISAR'])
        self.assertEqual(len(ev),1)
        self.assertEqual(ev[0].estado,'MAL')
        self.assertIn('EMPATE',ev[0].motivo)

    def test_todas_inciertas_no_pasa_sin_fingir_malas(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        ev=observar(b,['REVISAR']*7)
        self.assertEqual(len(ev),1)
        self.assertEqual(ev[0].estado,'MAL')
        self.assertEqual(ev[0].malas,0)
        self.assertEqual(ev[0].ambiguas,7)
        self.assertIn('SIN VOTOS EVALUABLES',ev[0].motivo)

    def test_una_buena_y_seis_inciertas_rechaza_con_nuevo_minimo(self):
        b=SeguimientoBanda(objetivo=7, min_validas=3, proporcion_minima=.5)
        ev=observar(b,['REVISAR']*6+['BIEN'])
        self.assertEqual(ev[0].estado,'MAL')
        self.assertIn('BUENAS INSUFICIENTES',ev[0].motivo)
        self.assertIn('AVISO DE CONFIABILIDAD',ev[0].motivo)

    def test_salir_antes_de_siete_aprueba_si_hay_votos_suficientes(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7, bloqueo_unico=True,
                           max_ausencia_s=.6,max_sin_ver=3)
        eventos=observar(b,['REVISAR','BIEN','MAL','BIEN'])
        self.assertEqual(eventos,[])
        for n,t in enumerate([.5,.75,1.1],start=5):
            eventos+=b.actualizar([],t,n).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertIn('MAYORIA BUENA',eventos[0].motivo)
        self.assertEqual(eventos[0].total,4)

    def test_ui_muestra_30_capturas_no_15_votos(self):
        frame=np.full((160,320,3),220,np.uint8)
        detector=_Modelo([[35,40,245,102]])
        estados=['REVISAR']*15+['MAL']*2+['BIEN']*13
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=30,intervalo_ms=0,mostrar_etapas=False),
                          detector,_Inspector(estados))
        eventos=[]
        for i in range(38):
            vista,e=p.procesar(frame,i*.1)
            eventos+=e
        self.assertEqual(len(eventos),1)
        self.assertEqual(vista.estado,'PASA')
        self.assertEqual(vista.muestreos,30)
        self.assertEqual(vista.validas,15)
        self.assertEqual((vista.buenas,vista.malas,vista.ambiguas),(13,2,15))
        self.assertEqual(vista.producto,1)

    def test_intervalo_igual_para_inciertas_y_buenas(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7,intervalo_s=.10,bloqueo_unico=True)
        entradas=['REVISAR','BIEN','REVISAR','MAL','BIEN','REVISAR','BIEN']
        eventos=[]
        for i,estado in enumerate(entradas):
            # Dos frames del mismo tipo justo despues de cada muestra no suman otra.
            eventos+=b.actualizar([Observacion((10,20,120,66),estado)],i*.11,i*2+1).eventos
            eventos+=b.actualizar([Observacion((10,20,120,66),'REVISAR')],i*.11+.005,i*2+2).eventos
        self.assertEqual(len(eventos),1)
        e=eventos[0]
        self.assertEqual(e.total,7)
        self.assertEqual((e.buenas,e.malas,e.ambiguas),(3,1,3))
        self.assertEqual(e.estado,'BIEN')

if __name__=='__main__': unittest.main()

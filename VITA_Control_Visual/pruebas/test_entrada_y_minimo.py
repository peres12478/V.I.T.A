"""Regresion: no aprobar recortes parciales ni por solo 1 voto favorable."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
from seguimiento_banda import SeguimientoBanda, Observacion
from interfaz_nutreo import Configuracion, ProcesadorNutreo
from calidad_impresion import Resultado


class _T:
    def __init__(self,data):self.data=np.array(data)
    def cpu(self): return self
    def numpy(self):return self.data
class _B:
    def __init__(self,box):self.xyxy=[_T(box)]
class _P:
    def __init__(self,boxes):self.boxes=[_B(x) for x in boxes]
class Modelo:
    def __init__(self,boxes):self.boxes=boxes
    def predict(self,frame,conf,verbose=False):return [_P(self.boxes)]
class Inspector:
    def __init__(self,estados):self.estados=list(estados);self.llamadas=0
    def analizar(self,recorte):
        i=self.llamadas;self.llamadas+=1
        estado=self.estados[i] if i<len(self.estados) else 'REVISAR'
        h,w=recorte.shape[:2]
        return Resultado(estado,'Muestra controlada',80.,{},[],
                         np.zeros((h,w),np.uint8),np.zeros((h,w),np.uint8),'oscura')


class PruebaControlEntrada(unittest.TestCase):
    def test_entrada_fuera_de_zona_no_ejecuta_inspector(self):
        frame=np.full((180,360,3),200,np.uint8)
        detector=Modelo([[0,40,95,85]])
        inspector=Inspector(['BIEN']*9)
        proc=ProcesadorNutreo(Configuracion(fotos=7, min_buenas=5,
                      zona_segura_pct=8,confirmaciones_fecha=3,intervalo_ms=0,
                      mostrar_etapas=False),detector,inspector)
        for n in range(8):
            v,ev=proc.procesar(frame,n*.1)
        self.assertEqual(inspector.llamadas,0)
        self.assertEqual(v.estado,'ESPERANDO FECHA COMPLETA')
        self.assertEqual(v.muestreos,0)
        self.assertEqual(ev,[])
        self.assertEqual(v.producto,1)
        self.assertEqual(proc.tracker.proximo_id,2)

    def test_se_requieren_tres_detecciones_estables_sin_parar_la_banda(self):
        frame=np.full((180,360,3),200,np.uint8)
        detector=Modelo([[0,40,125,90]])
        inspector=Inspector(['BIEN']*8)
        proc=ProcesadorNutreo(Configuracion(fotos=7,min_buenas=5,
                      zona_segura_pct=8,confirmaciones_fecha=3,
                      intervalo_ms=0,mostrar_etapas=False),detector,inspector)
        for n in range(2):proc.procesar(frame,n*.1)
        self.assertEqual(inspector.llamadas,0)
        # La fecha entra por la izquierda. Puede avanzar en la banda;
        # lo que debe estabilizarse es su TAMANO, no su posicion.
        for i,x in enumerate((40,51,62),start=2):
            detector.boxes=[[x,40,x+125,90]]
            vista,ev=proc.procesar(frame,i*.1)
            if i<4:self.assertEqual(vista.muestreos,0)
        self.assertEqual(inspector.llamadas,1)
        self.assertEqual(vista.estado,'EVALUANDO PRODUCTO')
        self.assertEqual(vista.producto,1)
        self.assertEqual(vista.muestreos,1)
        self.assertEqual(ev,[])

    def test_salto_de_tamano_reinicia_confirmaciones(self):
        b=SeguimientoBanda(objetivo=7,min_buenas=5,control_visibilidad=True,
                           intervalo_s=0,confirmaciones=3,margen_seguro=.08)
        for i,box in enumerate(((40,40,165,90),(40,40,165,90),(40,40,105,90),
                                (40,40,105,90),(40,40,105,90)),start=1):
            b.actualizar([Observacion(box,'BIEN')],i*.1,i,forma_frame=(180,360,3))
        # Cambio de escala brusco: el contador vuelve a 1 y toma muestra
        # solamente en la tercera deteccion del segundo tamano.
        self.assertEqual(b.pistas[1].muestreos,1)

    def test_una_buena_y_seis_inciertas_no_pasa(self):
        b=SeguimientoBanda(objetivo=7,intervalo_s=0)
        eventos=[]
        for i,estado in enumerate(['BIEN']+['REVISAR']*6):
            eventos+=b.actualizar([Observacion((30,30,200,80),estado)],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertIn('BUENAS INSUFICIENTES',eventos[0].motivo)
        self.assertEqual((eventos[0].buenas,eventos[0].malas,eventos[0].ambiguas),(1,0,6))

    def test_cinco_buenas_una_mala_una_incierta_pasa(self):
        b=SeguimientoBanda(objetivo=7,intervalo_s=0)
        eventos=[]
        for i,est in enumerate(['BIEN']*5+['MAL','REVISAR']):
            eventos+=b.actualizar([Observacion((30,30,200,80),est)],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual((eventos[0].buenas,eventos[0].malas,eventos[0].ambiguas),(5,1,1))

    def test_cuatro_buenas_y_cero_malas_no_pasa(self):
        b=SeguimientoBanda(objetivo=7,intervalo_s=0)
        eventos=[]
        for i,est in enumerate(['BIEN']*4+['REVISAR']*3):
            eventos+=b.actualizar([Observacion((30,30,200,80),est)],i*.1,i+1).eventos
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual(eventos[0].malas,0)
        self.assertIn('BUENAS INSUFICIENTES',eventos[0].motivo)

    def test_cinco_buenas_pero_seis_malas_no_pasa(self):
        b=SeguimientoBanda(objetivo=11,intervalo_s=0)
        eventos=[]
        for i,est in enumerate(['BIEN']*5+['MAL']*6):
            eventos+=b.actualizar([Observacion((30,30,200,80),est)],i*.1,i+1).eventos
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertIn('MAYORIA MALA',eventos[0].motivo)

    def test_cinco_buenas_en_seis_de_siete_aprueba_al_salir(self):
        b=SeguimientoBanda(objetivo=7,intervalo_s=0)
        eventos=[]
        for i,est in enumerate(['BIEN']*5+['REVISAR']):
            eventos+=b.actualizar([Observacion((30,30,200,80),est)],i*.1,i+1).eventos
        self.assertEqual(eventos,[])
        self.assertIsNone(b.pistas[1].estado_final)
        eventos=b.cerrar(1.,7)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertIn('MAYORIA BUENA',eventos[0].motivo)

    def test_siete_buenas_dan_un_resultado_y_mantienen_id(self):
        frame=np.full((180,360,3),200,np.uint8)
        detector=Modelo([[35,55,250,105]])
        inspector=Inspector(['BIEN']*20)
        proc=ProcesadorNutreo(Configuracion(fotos=7,min_buenas=5,
            intervalo_ms=0,mostrar_etapas=False),detector,inspector)
        eventos=[]
        for i in range(16):
            v,ev=proc.procesar(frame,i*.1)
            eventos+=ev
        self.assertEqual(len(eventos),1)
        self.assertEqual(v.estado,'PASA')
        self.assertEqual(v.muestreos,7)
        self.assertEqual(v.producto,1)
        self.assertEqual(inspector.llamadas,7)

    def test_interrupcion_yolo_pausa_capturas_y_conserva_id(self):
        frame=np.full((180,360,3),200,np.uint8)
        detector=Modelo([[35,55,250,105]])
        inspector=Inspector(['BIEN']*20)
        proc=ProcesadorNutreo(Configuracion(fotos=7,min_buenas=5,
            intervalo_ms=0,mostrar_etapas=False),detector,inspector)
        for n in range(4):v,_=proc.procesar(frame,n*.1)
        self.assertEqual(v.muestreos,2)
        detector.boxes=[]
        v,_=proc.procesar(frame,.45)
        self.assertEqual(v.producto,1)
        self.assertEqual(v.muestreos,2)
        self.assertEqual(v.estado,'EVALUANDO PRODUCTO')
        detector.boxes=[[35,55,250,105]]
        for i in range(2):v,_=proc.procesar(frame,.55+i*.1)
        self.assertEqual(v.muestreos,2)
        v,_=proc.procesar(frame,.75)
        self.assertEqual(v.muestreos,3)

    def test_fuera_zona_salida_pausa_tomas_no_crea_id(self):
        frame=np.full((180,360,3),200,np.uint8)
        detector=Modelo([[35,55,250,105]])
        inspector=Inspector(['BIEN']*20)
        proc=ProcesadorNutreo(Configuracion(fotos=7,min_buenas=5,
            intervalo_ms=0,mostrar_etapas=False),detector,inspector)
        for i in range(4):v,_=proc.procesar(frame,i*.1)
        self.assertEqual(v.muestreos,2)
        # Pasando por la derecha, su caja esta cerca de salida; sigue
        # siendo el mismo ID, pero se suspenden capturas fuera de la zona.
        detector.boxes=[[110,55,350,105]]
        v,_=proc.procesar(frame,.5)
        self.assertEqual(v.producto,1)
        self.assertEqual(v.muestreos,2)
        self.assertEqual(inspector.llamadas,2)

if __name__=='__main__':unittest.main()

"""Regresiones reportadas por operario: recuadro fijo hasta salida y dudas sin rafagas."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import cv2
from seguimiento_banda import Observacion, SeguimientoBanda
from interfaz_nutreo import Configuracion, ProcesadorNutreo
from calidad_impresion import Resultado


def ob(estado, x=40, y=35, ancho=110, alto=42):
    return Observacion((x,y,x+ancho,y+alto),estado,'simulado')


class _Tensor:
    def __init__(self, datos): self.datos=np.array(datos)
    def cpu(self): return self
    def numpy(self): return self.datos

class _Caja:
    def __init__(self, box): self.xyxy=[_Tensor(box)]

class _Pred:
    def __init__(self, boxes): self.boxes=[_Caja(b) for b in boxes]

class _Modelo:
    def __init__(self, boxes): self.boxes=boxes
    def predict(self,frame,conf,verbose=False): return [_Pred(self.boxes)]

class _Inspector:
    def __init__(self, estados):
        self.estados=estados
        self.i=0
    def analizar(self,crop):
        estado=self.estados[min(self.i,len(self.estados)-1)]
        self.i+=1
        h,w=crop.shape[:2]
        return Resultado(estado, f'Muestra {estado}', 70.,
                         {'camara_contraste_luz':60.,'camara_ruido_relativo':.01},
                         [],np.zeros((h,w),np.uint8),np.zeros((h,w),np.uint8),'oscura')

class BloqueoYControlDeDudas(unittest.TestCase):
    def test_bloqueo_mantiene_id_tras_objetivo_con_recuadro_presente(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7,intervalo_s=.07,bloqueo_unico=True)
        eventos=[]
        for i in range(100):
            estado='BIEN' if i<7 else 'REVISAR'
            res=b.actualizar([ob(estado,x=40+i)],i*.12,i+1)
            eventos+=res.eventos
            self.assertEqual(res.asignaciones[0][0],1)
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].cierre,'objetivo')
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual(b.pistas[1].validas,7)
        self.assertEqual(b.pistas[1].ambiguas,0)
        self.assertEqual(b.pistas[1].muestreos,7)
        self.assertEqual(b.proximo_id,2)

    def test_una_lectura_lenta_no_crea_producto(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,intervalo_s=0,max_ausencia_s=.6,
                          max_sin_ver=3,bloqueo_unico=True)
        r=[]
        for i,t in enumerate([0., .9, 1.9, 3.5]):
            x=[30,100,180,250][i]
            res=b.actualizar([ob('BIEN',x=x)],t,i+1)
            r += res.eventos
            self.assertEqual(res.asignaciones[0][0],1)
        self.assertEqual(len(r),1)
        self.assertEqual(b.proximo_id,2)

    def test_perdida_corta_yolo_persiste_recuadro_y_estado(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=2,min_validas=2,bloqueo_unico=True)
        b.actualizar([ob('BIEN')],0.,1)
        b.actualizar([ob('BIEN',x=45)],.1,2)
        self.assertEqual(b.pistas[1].estado_final,'BIEN')
        for i,t in enumerate([.21,.40],start=3):
            res=b.actualizar([],t,i)
            self.assertEqual(res.eventos,[])
            self.assertEqual(set(b.pistas),{1})
            self.assertTrue(b.pistas[1].caja_mostrada)
        res=b.actualizar([ob('REVISAR',x=60)],.5,5)
        self.assertEqual(res.asignaciones[0][0],1)
        self.assertEqual(b.pistas[1].estado_final,'BIEN')

    def test_nuevo_id_solo_tras_hueco_confirmado(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=2,min_validas=2,bloqueo_unico=True,
                          max_ausencia_s=.6,max_sin_ver=3)
        b.actualizar([ob('MAL')],0.,1)
        b.actualizar([ob('MAL')],.1,2)
        b.actualizar([],.3,3)
        b.actualizar([],.5,4)
        b.actualizar([],.8,5)
        self.assertFalse(b.pistas)
        res=b.actualizar([ob('BIEN')],.9,6)
        self.assertEqual(res.asignaciones[0][0],2)

    def test_dudas_respetan_la_misma_cadencia_y_tope_total(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7,bloqueo_unico=True,
                          intervalo_s=.075,intervalo_dudosa_s=.45,max_dudosas=3,
                          max_muestras=80)
        eventos=[]
        for i in range(45):
            # 10 ms entre frames: ninguna categoria debe contarse a 100 FPS.
            salida=b.actualizar([ob('REVISAR')],i*.01,i+1)
            eventos.extend(salida.eventos)
            p=b.pistas[1]
            self.assertLessEqual(p.muestreos,7)
            self.assertEqual(p.validas,0)
        p=b.pistas[1]
        self.assertEqual(p.ambiguas,6)
        self.assertEqual(p.muestreos,6)
        self.assertEqual(eventos,[])
        salida=b.actualizar([ob('REVISAR')],.50,46)
        eventos+=salida.eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].ambiguas,7)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual(eventos[0].total,7)

    def test_dudas_ocupan_capturas_pero_no_votan(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7,bloqueo_unico=True,
                          intervalo_s=.07, intervalo_dudosa_s=.45, max_dudosas=3,
                          max_muestras=80)
        secuencia=['REVISAR','BIEN','REVISAR','BIEN','BIEN','MAL','BIEN']
        eventos=[]
        for i,estado in enumerate(secuencia+['MAL']*10):
            eventos+=b.actualizar([ob(estado)],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual((eventos[0].buenas,eventos[0].malas),(4,1))
        self.assertEqual(eventos[0].ambiguas,2)
        self.assertEqual(eventos[0].total,7)
        self.assertEqual(b.pistas[1].estado_final,'BIEN')

    def test_incertidumbre_persistente_termina_sin_simular_defecto(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7,min_validas=3,max_muestras=12,
                          bloqueo_unico=True,intervalo_s=.07,max_dudosas=2)
        resultados=[]
        for i in range(23):
            resultados+=b.actualizar([ob('REVISAR')],i*.1,i+1).eventos
        self.assertEqual(len(resultados),1)
        self.assertEqual(resultados[0].estado,'MAL')
        self.assertIn('SIN VOTOS EVALUABLES',resultados[0].motivo)
        self.assertEqual(resultados[0].malas,0)
        self.assertEqual(resultados[0].ambiguas,7)
        self.assertEqual(resultados[0].total,7)
        self.assertEqual(b.proximo_id,2)

    def test_duplicados_yolo_no_son_otro_producto(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,bloqueo_unico=True,intervalo_s=0)
        for i in range(8):
            estado=b.actualizar([ob('BIEN',x=20),ob('MAL',x=300)],.1*i,i+1)
            self.assertEqual(len(estado.asignaciones),1)
            self.assertEqual(estado.indices,[0])
            self.assertEqual(estado.asignaciones[0][0],1)
        self.assertEqual(b.proximo_id,2)

    def test_gui_recuadro_y_decision_permanecen_al_terminar_siete(self):
        frame=np.full((170,300,3),160,np.uint8)
        modelo=_Modelo([[25,45,230,105]])
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=7,intervalo_ms=0,mostrar_etapas=False),
                          modelo,_Inspector(['BIEN']*7+['REVISAR']*40))
        eventos=[]
        for i in range(45):
            vista,ev=p.procesar(frame,i*.1)
            eventos+=ev
            if i>=6:
                self.assertEqual(vista.estado,'PASA')
                self.assertEqual(vista.producto,1)
                self.assertEqual(vista.ultima_muestra,'DECISION FINAL')
                self.assertEqual(vista.ambiguas,0)
        self.assertEqual(len(eventos),1)

    def test_gui_recuadro_persiste_fallo_corto_yolo(self):
        frame=np.full((170,300,3),160,np.uint8)
        modelo=_Modelo([[25,45,230,105]])
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=2,min_fotos=2,intervalo_ms=0,
                                          mostrar_etapas=False),modelo,_Inspector(['BIEN']))
        p.procesar(frame,0)
        p.procesar(frame,.1)
        modelo.boxes=[]
        v,e=p.procesar(frame,.2)
        self.assertEqual(v.estado,'PASA')
        self.assertEqual(v.producto,1)
        self.assertTrue(v.aviso)
        self.assertEqual(len(e),0)
        modelo.boxes=[[28,47,233,109]]
        v,e=p.procesar(frame,.3)
        self.assertEqual(v.estado,'PASA')
        self.assertEqual(v.producto,1)
        self.assertEqual(len(e),0)

    def test_gui_filtros_se_congelan_con_la_decision(self):
        frame=np.full((180,360,3),200,np.uint8)
        cv2.putText(frame,'VENCE 11/27',(55,87),cv2.FONT_HERSHEY_SIMPLEX,
                    .8,(10,10,10),2,cv2.LINE_AA)
        modelo=_Modelo([[40,40,290,110]])
        p=ProcesadorNutreo(Configuracion(min_buenas=1, control_visibilidad=False, fotos=2,min_fotos=2,intervalo_ms=0),
                          modelo,_Inspector(['BIEN','BIEN','REVISAR']))
        p.procesar(frame,0)
        v,_=p.procesar(frame,.1)
        self.assertEqual(v.estado,'PASA')
        prev={k:img.copy() for k,img in v.filtro_paneles.items()}
        self.assertEqual(len(prev),6)
        for i in range(20):
            v,ev=p.procesar(frame,.2+i*.1)
            self.assertEqual(v.estado,'PASA')
            self.assertEqual(ev,[])
            for key in prev:
                self.assertTrue(np.array_equal(prev[key],v.filtro_paneles[key]))

if __name__=='__main__':
    unittest.main()

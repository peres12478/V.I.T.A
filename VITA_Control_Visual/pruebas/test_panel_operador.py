"""Pruebas del modo nativo y trazabilidad, sin servidor ni modelo real."""
from __future__ import annotations
import inspect
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import panel_operador
from panel_operador import ControlOperador, buscar_camaras
from historial_operador import (clasificar,cargar_historial,filtrar_historial,
                                 estadisticas,sanitizar_meta,exportar_csv,COLUMNAS_EXPORT)
from interfaz_nutreo import Configuracion
from seguimiento_banda import EventoFinal
from iniciar_calidad import RegistroEventos


class TestHistorialNativo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.sesion='sesion_20261112_153000_101010'
        (self.folder / (self.sesion+'.json')).write_text(json.dumps({
            'linea':'Línea 1','turno':'Tarde','lote':'LOTE-7','referencia':'Producto X'
        }),encoding='utf-8')
        reg=RegistroEventos(self.folder / (self.sesion+'.csv'))
        reg.guardar(EventoFinal(1,'BIEN','MAYORIA BUENA',6,0,1,0,7,0.5,10,'objetivo'))
        reg.guardar(EventoFinal(2,'MAL','SIN VOTOS EVALUABLES: NO PASA preventivo; defecto no confirmado',0,0,7,0,7,.9,50,'desaparecio'))
        reg.guardar(EventoFinal(3,'MAL','MAYORIA MALA: 5 malas > 1 buenas',1,5,1,0,7,1.,70,'objetivo'))
        reg.close()

    def tearDown(self): self.tmp.cleanup()

    def test_historial_persistente_y_categorias(self):
        r=cargar_historial(self.folder)
        self.assertEqual(len(r),3)
        por_id={i['producto_id']:i for i in r}
        self.assertEqual(por_id['1']['resultado'],'PASA')
        self.assertEqual(por_id['2']['tipo'],'sin_evidencia')
        self.assertEqual(por_id['3']['tipo'],'no_pasa')
        c=estadisticas(r)
        self.assertEqual((c['total'],c['pasa'],c['no_pasa'],c['sin_evidencia']),(3,1,2,1))

    def test_busqueda_y_filtros(self):
        r=cargar_historial(self.folder)
        self.assertEqual(len(filtrar_historial(r, resultado='PASA')),1)
        self.assertEqual(len(filtrar_historial(r, buscar='Línea 1')),3)
        self.assertEqual(len(filtrar_historial(r, buscar='tarde')),3)
        self.assertFalse(filtrar_historial(r, buscar='lote-7'))
        self.assertEqual(len(filtrar_historial(r, tipo='sin_evidencia')),1)
        self.assertFalse(filtrar_historial(r,hasta='2020-01-01'))

    def test_exporta_excel_sin_formula_inyectada(self):
        r=cargar_historial(self.folder)
        r[0]['linea']='=2+2'
        r[0]['lote']='NO EXPORTAR'
        r[0]['motivo']='EXPLICACION CONFIDENCIAL'
        texto=exportar_csv(r)
        self.assertTrue(texto.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b"'=2+2",texto)
        self.assertNotIn(b'NO EXPORTAR',texto)
        self.assertNotIn(b'EXPLICACION CONFIDENCIAL',texto)
        filas=list(csv.reader(io.StringIO(texto.decode('utf-8-sig'))))
        self.assertEqual(filas[0],list(COLUMNAS_EXPORT))
        self.assertEqual(filas[0], ['Producto','Resultado','Buenas','Malas',
                                    'Inciertas','Línea','Turno'])
        self.assertEqual(len(filas),4)
        self.assertEqual(filas[1][0],r[0]['producto_id'])
        self.assertEqual(filas[1][1],r[0]['resultado'])
        self.assertEqual(filas[1][2],str(r[0]['buenas']))
        self.assertEqual(filas[1][3],str(r[0]['malas']))
        self.assertEqual(filas[1][4],str(r[0]['inciertas']))
        self.assertEqual(filas[1][5],"'=2+2")
        self.assertEqual(filas[1][6],r[0]['turno'])

    def test_metadatos_sin_caracteres_de_control(self):
        r=sanitizar_meta({'linea':'A\nB','turno':'c'*200,
                          'lote':'ANTERIOR','referencia':'ANTERIOR'})
        self.assertEqual(r['linea'],'AB')
        self.assertEqual(len(r['turno']),48)
        self.assertEqual(set(r),{'linea','turno'})


class TrabajadorFalso(threading.Thread):
    """Simula la misma interfaz del trabajador, con registros reales."""
    def __init__(self, cfg, stop, fotos, eventos):
        super().__init__(daemon=True)
        self.config=cfg;self.stop=stop;self.fotos=fotos;self.eventos=eventos

    def run(self):
        self.eventos.put(('info','Fuente activa (simulada). Esperando producto.'))
        reg=RegistroEventos(self.config.registro)
        evento=EventoFinal(1,'BIEN','MAYORIA BUENA',5,0,0,0,5,1.,3,'objetivo')
        reg.guardar(evento)
        reg.close()
        self.eventos.put(('resultado',evento))
        self.eventos.put(('rendimiento',{'fps_analisis':12.,'ms_proceso':83.,'omitidos':1}))
        self.stop.wait(.12)
        self.eventos.put(('detenido','Fin'))


class TestPanelDeEscritorio(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.ctl=ControlOperador(Configuracion(fotos=50,min_buenas=5),self.folder)

    def tearDown(self):
        self.ctl.cerrar()
        if self.ctl.worker: self.ctl.worker.join(timeout=2)
        self.tmp.cleanup()

    def test_usa_el_mismo_trabajador_y_todos_sus_filtros(self):
        with patch('panel_operador.Trabajador',TrabajadorFalso):
            ok,sesion=self.ctl.iniciar({'linea':'L1','turno':'Noche','lote':'antiguo'},camara=1,backend='msmf',resolucion='1280x720')
            self.assertTrue(ok)
            self.assertEqual(self.ctl.worker.config.camara,1)
            self.assertEqual(self.ctl.worker.config.camara_backend,'msmf')
            self.assertTrue(self.ctl.worker.config.captura_reciente)
            self.assertTrue(self.ctl.worker.config.evidencia_asincrona)
            self.assertTrue(self.ctl.worker.config.guardar_evidencia)
            self.assertEqual(self.ctl.worker.config.fotos,50)
            self.assertIs(self.ctl.worker.config.video,None)
            self.assertIn('sesion_',sesion)
            meta=json.loads((self.folder/(sesion+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(meta,{'linea':'L1','turno':'Noche'})
            self.ctl.worker.join(timeout=2)
            self.ctl.consultar()
            self.assertEqual(self.ctl.fase,'detenido')
            self.assertEqual(self.ctl.resumen['pasa'],1)
            self.assertEqual(self.ctl.eventos_sesion[0]['finalizacion'],'objetivo')
            self.assertEqual(len(cargar_historial(self.folder)),1)
            self.assertAlmostEqual(self.ctl.rendimiento['fps_analisis'],12.)

    def test_impide_duplicar_sesiones_y_cambia_camara_antes_inicio(self):
        with patch('panel_operador.Trabajador',TrabajadorFalso):
            ok,_=self.ctl.iniciar({},camara=3)
            self.assertTrue(ok)
            ok,mensaje=self.ctl.iniciar({},camara=4)
            self.assertFalse(ok)
            self.assertIn('activa',mensaje)
            self.ctl.detener()

    def test_no_crea_servidor_ni_solicita_puerto(self):
        source=inspect.getsource(panel_operador)
        for prohibido in ('BaseHTTPRequestHandler','ThreadingHTTPServer','serve_forever','cv2.imencode','webbrowser.open'):
            self.assertNotIn(prohibido, source)

    def test_historial_gui_sin_hora_ni_explicacion(self):
        # Una verificacion rapida de cabeceras y valores vinculados a la tabla.
        source=inspect.getsource(panel_operador.VitaOperadorGUI._construir)
        self.assertIn("cols=('producto','estado','buenas','malas','inciertas','linea','turno')",source)
        self.assertNotIn("('LOTE'",source)
        self.assertNotIn("('REFERENCIA'",source)
        self.assertNotIn("'Explicacion'",source)
        self.assertNotIn("'Hora'",source)

    def test_validacion_camara(self):
        ok,_=self.ctl.iniciar({},camara=-1)
        self.assertFalse(ok)
        ok,_=self.ctl.iniciar({},camara=2,backend='noexiste')
        self.assertFalse(ok)

    def test_detectar_camaras_durante_sondeo_no_inicia_motor(self):
        class Cam:
            def __init__(self,i): self.i=i;self.suelta=False
            def isOpened(self): return self.i==1
            def release(self):self.suelta=True
        with patch('panel_operador.cv2.VideoCapture',side_effect=lambda i,b:Cam(i)):
            self.assertEqual(buscar_camaras('auto',max_indice=2),[1])


if __name__=='__main__': unittest.main()

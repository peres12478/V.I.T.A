"""V.I.T.A. - Aplicacion nativa para el equipo de planta (SIN HTTP ni navegador).

Ejecutar: python panel_operador.py

El operador selecciona la camara en la ventana. El MISMO Trabajador de
interfaz_nutreo.py ejecuta YOLO, el inspector OpenCV completo, seguimiento,
votacion, evidencias e historial. La UI solo presenta resultados del motor.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from interfaz_nutreo import Configuracion, Trabajador, VistaCuadro
from historial_operador import (cargar_historial, clasificar, estadisticas,
                                 filtrar_historial, exportar_csv, sanitizar_meta)

BASE = Path(__file__).resolve().parent
HISTORIAL = BASE / 'registros_operador'
MARCA = BASE / 'assets' / 'vita_logo_referencia.png'

# Colores basados en la referencia V.I.T.A. facilitada por el usuario.
FONDO = '#EDF3F3'
BLANCO = '#FFFFFF'
MARINO = '#113B43'
MARINO_OSCURO = '#092A32'
TURQUESA = '#147581'
MENTA = '#C7EB7D'
TEXTO = '#18343C'
GRIS = '#607780'
BORDE = '#CFDEDD'
VERDE = '#177850'
ROJO = '#B63E4C'
AMBAR = '#98650C'


class ControlOperador:
    """Administracion nativa de sesion, sin codificacion JPEG ni red.

    Trabajador es compartido con el centro tecnico. Esta clase no crea
    inspectores ni tiene condiciones especiales para modificar votos.
    """

    def __init__(self, plantilla: Configuracion | None = None,
                 carpeta_historial: Path = HISTORIAL):
        self.plantilla = plantilla or Configuracion(
            fotos=50, min_fotos=3, min_buenas=5, intervalo_ms=180., conf=.45,
            guardar_evidencia=True, evidencia_asincrona=True,
            captura_reciente=True, mostrar_etapas=False,
        )
        self.carpeta = Path(carpeta_historial)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.cola_fotos: queue.Queue = queue.Queue(maxsize=2)
        self.cola_eventos: queue.Queue = queue.Queue()
        self.worker: Trabajador | None = None
        self.stop_flag = threading.Event()
        self.fase = 'detenido'
        self.info = 'Elige la camara y comienza una sesion.'
        self.error = ''
        self.sesion = ''
        self.meta = sanitizar_meta({})
        self.ultima_vista: VistaCuadro | None = None
        self.ultimo_resultado: dict | None = None
        self.eventos_sesion: list[dict] = []
        self.rendimiento: dict = {}
        self._t_inicio = 0.
        self._pendientes_nuevos: list[dict] = []

    def iniciar(self, meta: dict, *, camara: int, backend: str = 'auto',
                resolucion: str = '1280x720', video: Path | None = None) -> tuple[bool, str]:
        if self.worker is not None and self.worker.is_alive():
            return False, 'Ya existe una inspeccion activa.'
        if self.fase in ('cargando', 'activo', 'deteniendo'):
            return False, 'Espera a que termine la inspeccion anterior.'
        if camara < 0 or camara > 32:
            return False, 'Indice de camara fuera de rango.'
        if backend not in ('auto', 'msmf', 'dshow'):
            return False, 'Controlador de camara no valido.'
        if resolucion not in ('Automatica', '1280x720', '1920x1080'):
            return False, 'Resolucion no valida.'
        if video is not None and not Path(video).is_file():
            return False, 'No existe el video de prueba.'
        self.meta = sanitizar_meta(meta)
        sesion = 'sesion_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        try:
            with (self.carpeta / f'{sesion}.json').open('x', encoding='utf-8') as fd:
                json.dump(self.meta, fd, ensure_ascii=False, indent=2)
        except OSError as exc:
            return False, f'No se pudo crear la sesion: {exc}'
        config = replace(
            self.plantilla, camara=camara, camara_backend=backend,
            resolucion_camara=resolucion, video=video,
            registro=self.carpeta / f'{sesion}.csv',
            ruta_evidencia=BASE / 'evidencias_operador' / sesion,
            captura_reciente=(video is None), evidencia_asincrona=True,
            guardar_evidencia=True, mostrar_etapas=False,
        )
        self.cola_fotos = queue.Queue(maxsize=2)
        self.cola_eventos = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = Trabajador(config, self.stop_flag,
                                self.cola_fotos, self.cola_eventos)
        self.sesion = sesion
        self.fase = 'cargando'
        self.info = 'Cargando modelo YOLO y preparando camara...'
        self.error = ''
        self.ultima_vista = None
        self.ultimo_resultado = None
        self.eventos_sesion = []
        self.rendimiento = {}
        self._pendientes_nuevos = []
        self._t_inicio = time.monotonic()
        self.worker.start()
        return True, sesion

    def detener(self):
        if self.worker is None or not self.worker.is_alive():
            return False
        self.fase = 'deteniendo'
        self.info = 'Cerrando el producto pendiente y guardando evidencias...'
        self.stop_flag.set()
        return True

    def consultar(self):
        """Invocar solo en el hilo Tk. No realiza analisis ni I/O de imagen."""
        self._pendientes_nuevos = []
        for _ in range(500):
            try:
                tipo, dato = self.cola_eventos.get_nowait()
            except queue.Empty:
                break
            if tipo == 'resultado':
                registro = {
                    'fecha_hora': datetime.now().isoformat(timespec='seconds'),
                    'sesion': self.sesion, **self.meta,
                    'producto_id': str(dato.id),
                    'resultado': 'PASA' if dato.estado == 'BIEN' else 'NO PASA',
                    'tipo': clasificar(dato.estado, dato.motivo),
                    'motivo': dato.motivo,
                    'buenas': dato.buenas, 'malas': dato.malas,
                    'inciertas': dato.ambiguas + dato.desenfocadas,
                    'fotos_totales': dato.total,
                    'votos_validos': dato.buenas + dato.malas,
                    'finalizacion': dato.cierre,
                }
                self.ultimo_resultado = registro
                self.eventos_sesion.append(registro)
                self._pendientes_nuevos.append(registro)
            elif tipo == 'info':
                self.info = str(dato)
                if 'Fuente activa' in str(dato) and self.fase == 'cargando':
                    self.fase = 'activo'
            elif tipo == 'error':
                self.error = str(dato)
                self.info = 'Error de equipo: ' + self.error
                self.fase = 'error'
            elif tipo == 'detenido':
                if self.fase != 'error':
                    self.fase = 'detenido'
                    self.info = 'Sesion finalizada. Puedes iniciar otra.'
            elif tipo == 'rendimiento':
                self.rendimiento = dict(dato)
        ultima = None
        # La cola no puede acumular retraso visual: solo se dibuja el mas reciente.
        while True:
            try:
                ultima = self.cola_fotos.get_nowait()
            except queue.Empty:
                break
        if ultima is not None:
            self.ultima_vista = ultima
        return list(self._pendientes_nuevos)

    @property
    def activo(self):
        return bool(self.worker is not None and self.worker.is_alive())

    @property
    def resumen(self):
        return estadisticas(self.eventos_sesion)

    def cerrar(self):
        self.stop_flag.set()


def buscar_camaras(backend='auto', max_indice=5, cancelar=None) -> list[int]:
    """Enumeracion opcional y separada: nunca toca la camara activa del motor."""
    from captura_segura import backends_camara
    indices = []
    for indice in range(max_indice + 1):
        if cancelar is not None and cancelar.is_set():
            break
        for _, api in backends_camara(sys.platform, backend):
            cap = None
            try:
                cap = cv2.VideoCapture(indice, api)
                if cap.isOpened():
                    indices.append(indice)
                    break
            except (cv2.error, OSError):
                pass
            finally:
                if cap is not None:
                    cap.release()
    return indices


class VitaOperadorGUI:
    FUENTE = 'Segoe UI' if sys.platform == 'win32' else 'DejaVu Sans'

    def __init__(self, root: tk.Tk, indice_inicial: int = 0,
                 control: ControlOperador | None = None):
        self.root = root
        self.root.title('V.I.T.A. | Panel de inspeccion para Nutreo')
        ancho = root.winfo_screenwidth()
        alto = root.winfo_screenheight()
        root.geometry(f'{min(1380,max(980,ancho-60))}x{min(930,max(700,alto-45))}')
        root.minsize(960, 700)
        root.configure(bg=FONDO)
        root.protocol('WM_DELETE_WINDOW', self.cerrar)
        self.control = control or ControlOperador()
        self.indice = tk.StringVar(value=str(indice_inicial))
        self.backend = tk.StringVar(value='auto')
        self.resolucion = tk.StringVar(value='1280x720')
        self.linea = tk.StringVar()
        self.turno = tk.StringVar()
        self.filtro_estado = tk.StringVar(value='Todos')
        self.busqueda = tk.StringVar()
        self.sesion_info = tk.StringVar(value='Sin sesion activa')
        self._image = None
        self._logo = None
        self._vista_id = None
        self._ultimo_dibujo = 0.
        self._scan_activo = False
        self._scan_resultados: queue.Queue = queue.Queue(maxsize=1)
        self._ultimo_numero_eventos = -1
        self._cerrando = False
        self._filas_historial = []
        self._montar_estilos()
        self._construir()
        self._refrescar_historial()
        self.root.after(55, self._actualizar)

    def _montar_estilos(self):
        st = ttk.Style(self.root)
        if 'clam' in st.theme_names():
            st.theme_use('clam')
        st.configure('VITA.TNotebook', background=FONDO, borderwidth=0)
        st.configure('VITA.TNotebook.Tab', background='#DFEDE9', foreground=MARINO,
                     padding=(16,8), font=(self.FUENTE,10,'bold'))
        st.map('VITA.TNotebook.Tab', background=[('selected',BLANCO)],
               foreground=[('selected',TURQUESA)])
        st.configure('VITA.TCombobox', fieldbackground=BLANCO, background=BLANCO,
                     foreground=TEXTO, bordercolor=BORDE, padding=6)
        st.map('VITA.TCombobox', fieldbackground=[('readonly',BLANCO)],
               foreground=[('readonly',TEXTO)])
        st.configure('VITA.Treeview', background=BLANCO, fieldbackground=BLANCO,
                     foreground=TEXTO, rowheight=31, borderwidth=0,
                     font=(self.FUENTE, 10))
        st.configure('VITA.Treeview.Heading', background='#D9E8E5',
                     foreground=MARINO, relief='flat', font=(self.FUENTE, 10, 'bold'))
        st.map('VITA.Treeview', background=[('selected','#BEDDDC')],
               foreground=[('selected',MARINO)])

    def _text(self, parent, value='', size=11, color=TEXTO, bold=False, **kw):
        return tk.Label(parent, text=value, bg=parent.cget('bg'), fg=color,
                        font=(self.FUENTE,size,'bold' if bold else 'normal'), **kw)

    def _card(self, parent, bg=BLANCO, **kw):
        return tk.Frame(parent, bg=bg, highlightbackground=BORDE,
                        highlightthickness=1, **kw)

    def _button(self, parent, txt, command, bg=TURQUESA, fg=BLANCO, **kw):
        return tk.Button(parent, text=txt, command=command,
                         bg=bg, fg=fg, activebackground=MARINO,
                         activeforeground=BLANCO, cursor='hand2',
                         borderwidth=0, padx=16, pady=9,
                         font=(self.FUENTE,10,'bold'), **kw)

    def _entry(self, parent, var, width=15):
        return tk.Entry(parent, textvariable=var, width=width,
                        bg=BLANCO, fg=TEXTO, insertbackground=TEXTO,
                        relief='solid', bd=1, highlightthickness=1,
                        highlightbackground=BORDE, highlightcolor=TURQUESA,
                        font=(self.FUENTE,11))

    def _construir(self):
        cab = tk.Frame(self.root, bg=BLANCO, height=92)
        cab.pack(fill='x')
        cab.pack_propagate(False)
        marca = tk.Frame(cab, bg=BLANCO)
        marca.pack(side='left', padx=(24,14), pady=13)
        if MARCA.is_file():
            try:
                logo = Image.open(MARCA).convert('RGB')
                logo.thumbnail((237,62), Image.Resampling.LANCZOS)
                self._logo = ImageTk.PhotoImage(logo, master=self.root)
                tk.Label(marca, image=self._logo, bg=BLANCO).pack()
            except (OSError, ValueError):
                self._text(marca,'V.I.T.A.',26,MARINO,True).pack()
        else:
            self._text(marca,'V.I.T.A.',26,MARINO,True).pack()
        titulo = tk.Frame(cab, bg=BLANCO)
        titulo.pack(side='left', pady=21)
        self._text(titulo, 'INSPECCION VISUAL DE IMPRESION', 13, MARINO, True,
                   anchor='w').pack(anchor='w')
        self._text(titulo, 'Panel del personal de planta', 10, GRIS, anchor='w').pack(anchor='w')
        badge = tk.Frame(cab,bg=BLANCO)
        badge.pack(side='right',padx=30)
        self._text(badge,'DESARROLLADO PARA',9,GRIS,True).pack(anchor='e')
        self._text(badge,'Nutreo',18,MARINO,True).pack(anchor='e')

        contenido = tk.Frame(self.root,bg=FONDO)
        contenido.pack(fill='both',expand=True,padx=22,pady=(16,12))
        barra = self._card(contenido)
        barra.pack(fill='x',pady=(0,12))
        fila = tk.Frame(barra,bg=BLANCO)
        fila.pack(fill='x',padx=14,pady=(12,8))
        self._text(fila,'CAMARA',9,GRIS,True).pack(side='left',padx=(0,8))
        self.combo_camara = ttk.Combobox(fila,textvariable=self.indice, width=5,
                                         values=[str(i) for i in range(7)],
                                         style='VITA.TCombobox')
        self.combo_camara.pack(side='left')
        self.boton_buscar = self._button(fila,'Buscar',self.buscar, bg='#DCEDE7',fg=MARINO)
        self.boton_buscar.pack(side='left',padx=(7,20))
        self._text(fila,'CONTROLADOR',9,GRIS,True).pack(side='left',padx=(0,7))
        self.combo_backend = ttk.Combobox(fila,textvariable=self.backend, width=8,
                                         state='readonly',values=('auto','msmf','dshow'),
                                         style='VITA.TCombobox')
        self.combo_backend.pack(side='left')
        self._text(fila,'RESOLUCION',9,GRIS,True).pack(side='left',padx=(22,7))
        self.combo_resolucion = ttk.Combobox(fila,textvariable=self.resolucion,width=12,
                                            state='readonly',
                                            values=('Automatica','1280x720','1920x1080'),
                                            style='VITA.TCombobox')
        self.combo_resolucion.pack(side='left')
        self.btn_start = self._button(fila,'INICIAR',self.iniciar,bg=MENTA,fg=MARINO)
        self.btn_start.pack(side='right',padx=(10,0))
        self.btn_stop = self._button(fila,'DETENER',self.detener,bg='#F2CAD0',fg=ROJO)
        self.btn_stop.pack(side='right')
        self.btn_stop.configure(state='disabled')

        datos = tk.Frame(barra,bg=BLANCO)
        datos.pack(fill='x',padx=14,pady=(0,12))
        for etiqueta,var in [('LINEA',self.linea),('TURNO',self.turno)]:
            item = tk.Frame(datos,bg=BLANCO)
            item.pack(side='left',padx=(0,18))
            self._text(item,etiqueta,9,GRIS,True).pack(anchor='w',pady=(0,3))
            campo=self._entry(item,var,width=16)
            campo.pack(anchor='w',ipady=3)
            if not hasattr(self,'_meta_entries'): self._meta_entries=[]
            self._meta_entries.append(campo)
        self._text(datos,'Línea y turno se guardan con cada inspección.',10,GRIS).pack(side='left',padx=(8,0),pady=(22,0))

        self.tabs=ttk.Notebook(contenido,style='VITA.TNotebook')
        self.tabs.pack(fill='both',expand=True)
        tab_directo=tk.Frame(self.tabs,bg=FONDO)
        tab_historial=tk.Frame(self.tabs,bg=FONDO)
        self.tabs.add(tab_directo,text='  INSPECCION EN VIVO  ')
        self.tabs.add(tab_historial,text='  HISTORIAL Y EXPORTACION  ')
        centro = tk.Frame(tab_directo,bg=FONDO)
        centro.pack(fill='both',expand=True,pady=(10,0))
        izquierda = self._card(centro)
        izquierda.pack(side='left',fill='both',expand=True,padx=(0,12))
        top_cam = tk.Frame(izquierda,bg=BLANCO)
        top_cam.pack(fill='x',padx=15,pady=(12,10))
        self._text(top_cam,'CAMARA EN VIVO',12,MARINO,True).pack(side='left')
        self.txt_senal = self._text(top_cam,'SIN INICIAR',10,GRIS,True)
        self.txt_senal.pack(side='right')
        self.img_camara = tk.Label(izquierda,text='Selecciona una camara y pulsa INICIAR',
                                    bg=MARINO_OSCURO, fg='#A7C6C6',
                                    font=(self.FUENTE,15), compound='center')
        self.img_camara.pack(fill='both',expand=True,padx=14,pady=(0,10))
        pie_cam = tk.Frame(izquierda,bg=BLANCO)
        pie_cam.pack(fill='x',padx=14,pady=(0,12))
        self.lbl_cam_info=self._text(pie_cam,'Imagen y analisis del motor completo de V.I.T.A.',9,GRIS)
        self.lbl_cam_info.pack(side='left')
        self.lbl_fps=self._text(pie_cam,'',9,GRIS)
        self.lbl_fps.pack(side='right')

        derecha = tk.Frame(centro,bg=FONDO,width=390)
        derecha.pack(side='right',fill='y')
        derecha.pack_propagate(False)
        estado = self._card(derecha)
        estado.pack(fill='x',pady=(0,10))
        self._text(estado,'ESTADO DE INSPECCION',10,MARINO,True).pack(pady=(14,5))
        self.lbl_estado=tk.Label(estado,text='SIN INICIAR',bg='#DDE8E6',fg=MARINO,
                                  font=(self.FUENTE,17,'bold'),pady=13,wraplength=348)
        self.lbl_estado.pack(fill='x',padx=12)
        self.lbl_producto=self._text(estado,'Producto: --',11,MARINO,True)
        self.lbl_producto.pack(anchor='w',padx=16,pady=(12,4))
        self.lbl_votos=self._text(estado,'Buenas 0   |   Malas 0   |   Inciertas 0',10,GRIS)
        self.lbl_votos.pack(anchor='w',padx=16,pady=(0,5))
        self.lbl_muestra=self._text(estado,'Ultima muestra: --',10,MARINO)
        self.lbl_muestra.pack(anchor='w',padx=16,pady=(0,6))
        self.lbl_motivo=self._text(estado,'Esperando inicio.',10,GRIS,
                                    wraplength=345,justify='left',anchor='w')
        self.lbl_motivo.pack(fill='x',padx=16,pady=(0,14))

        ultimo = self._card(derecha)
        ultimo.pack(fill='x',pady=(0,10))
        self._text(ultimo,'ULTIMO PRODUCTO FINALIZADO',10,MARINO,True).pack(anchor='w',padx=14,pady=(12,8))
        self.lbl_ultimo=self._text(ultimo,'Aun no hay decisiones.',11,GRIS,
                                    wraplength=345,justify='left')
        self.lbl_ultimo.pack(anchor='w',padx=14,pady=(0,14))

        cifras = self._card(derecha)
        cifras.pack(fill='x',pady=(0,10))
        self._text(cifras,'RESUMEN DE LA SESION',10,MARINO,True).pack(anchor='w',padx=14,pady=(12,8))
        self.lbl_cifras=self._text(cifras,'0 inspeccionados  |  0 PASA  |  0 NO PASA',11,TEXTO,True)
        self.lbl_cifras.pack(anchor='w',padx=14,pady=(0,7))
        self.lbl_preventivos=self._text(cifras,'Sin evidencia suficiente: 0',10,GRIS)
        self.lbl_preventivos.pack(anchor='w',padx=14,pady=(0,12))

        self.lbl_info=self._text(derecha,'Sin inspeccion activa.',10,GRIS,
                                  wraplength=360,justify='left')
        self.lbl_info.pack(fill='x',pady=(2,0))

        inferior=self._card(tab_historial)
        inferior.pack(fill='both',expand=True,pady=(10,0))
        cab_hist=tk.Frame(inferior,bg=BLANCO)
        cab_hist.pack(fill='x',padx=12,pady=(10,5))
        self._text(cab_hist,'HISTORIAL DE INSPECCIONES',11,MARINO,True).pack(side='left')
        self.btn_export=self._button(cab_hist,'Exportar CSV',self.exportar,bg=TURQUESA)
        self.btn_export.pack(side='right')
        self.btn_refresh=self._button(cab_hist,'Actualizar',self._refrescar_historial,
                                      bg='#DCEDE7',fg=MARINO)
        self.btn_refresh.pack(side='right',padx=(0,8))
        self.search=self._entry(cab_hist,self.busqueda,18)
        self.search.pack(side='right',padx=(0,8),ipady=5)
        self.search.bind('<Return>',lambda _:self._refrescar_historial())
        self.estado_filtro=ttk.Combobox(cab_hist,textvariable=self.filtro_estado,width=13,
                                        state='readonly',
                                        values=('Todos','PASA','NO PASA','Preventivo'),
                                        style='VITA.TCombobox')
        self.estado_filtro.pack(side='right',padx=(0,8))
        self.estado_filtro.bind('<<ComboboxSelected>>',lambda _:self._refrescar_historial())
        frame_tabla=tk.Frame(inferior,bg=BLANCO)
        frame_tabla.pack(fill='both',expand=True,padx=12,pady=(0,10))
        cols=('producto','estado','buenas','malas','inciertas','linea','turno')
        self.tabla=ttk.Treeview(frame_tabla,columns=cols,show='headings',height=12,
                                 style='VITA.Treeview')
        nombres=('Producto','Resultado','Buenas','Malas','Inciertas','Línea','Turno')
        anchos=(105,125,85,80,90,160,155)
        for key,nom,ancho in zip(cols,nombres,anchos):
            self.tabla.heading(key,text=nom)
            self.tabla.column(key,width=ancho,anchor='center',stretch=True)
        self.tabla.tag_configure('pasa',foreground=VERDE)
        self.tabla.tag_configure('no_pasa',foreground=ROJO)
        self.tabla.pack(side='left',fill='both',expand=True)
        barra=tk.Scrollbar(frame_tabla,orient='vertical',command=self.tabla.yview)
        barra.pack(side='right',fill='y')
        self.tabla.configure(yscrollcommand=barra.set)

    def buscar(self):
        if self.control.activo or self._scan_activo:
            return
        self._scan_activo=True
        self.boton_buscar.configure(state='disabled',text='Buscando...')
        self.btn_start.configure(state='disabled')
        backend=self.backend.get()
        def tarea():
            encontrado=buscar_camaras(backend,max_indice=5)
            self._scan_resultados.put(encontrado)
        threading.Thread(target=tarea,name='VITA-Buscar-Camaras',daemon=True).start()

    def _fin_busqueda(self,encontradas):
        self._scan_activo=False
        self.boton_buscar.configure(state='normal',text='Buscar')
        if not self.control.activo:
            self.btn_start.configure(state='normal')
        actual=self.indice.get()
        valores=sorted({str(i) for i in encontradas} | {actual})
        self.combo_camara.configure(values=valores)
        if encontradas:
            self.lbl_info.configure(text='Camaras encontradas: '+', '.join(str(i) for i in encontradas))
        else:
            self.lbl_info.configure(text='No se detectaron camaras en el sondeo. Prueba otro controlador o escribe un indice.')

    def iniciar(self):
        try:
            indice=int(self.indice.get().strip())
        except ValueError:
            messagebox.showerror('Camara','Elige o escribe un numero de camara valido.')
            return
        ok,mensaje=self.control.iniciar({
            'linea':self.linea.get(),'turno':self.turno.get(),
        },camara=indice,backend=self.backend.get(),resolucion=self.resolucion.get())
        if not ok:
            messagebox.showerror('V.I.T.A. - Inicio',mensaje)
            return
        self.sesion_info.set(mensaje)
        self._vista_id=None
        self._ultima_vista_mostrada=None
        self._ultimo_numero_eventos=-1
        self._image=None
        self.img_camara.configure(image='',text='Cargando el modelo y la camara...')
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self.boton_buscar.configure(state='disabled')
        for control in (self.combo_camara,self.combo_backend,self.combo_resolucion):
            control.configure(state='disabled')
        for campo in self._meta_entries:
            campo.configure(state='disabled')

    def detener(self):
        if self.control.detener():
            self.btn_stop.configure(state='disabled')

    def _imagen(self, fotograma):
        # La GUI nunca hace YOLO ni crea JPEG. Solo convierte el ultimo BGR.
        ancho=self.img_camara.winfo_width()-16
        alto=self.img_camara.winfo_height()-16
        if ancho < 80 or alto < 80:
            return
        h,w=fotograma.shape[:2]
        escala=min(ancho/w,alto/h)
        objetivo=(max(1,int(w*escala)),max(1,int(h*escala)))
        # INTER_AREA evita cargar frames grandes innecesariamente.
        img=cv2.resize(fotograma,objetivo,
                       interpolation=cv2.INTER_AREA if escala<1 else cv2.INTER_LINEAR)
        img=cv2.cvtColor(img,cv2.COLOR_BGR2RGB)
        self._image=ImageTk.PhotoImage(Image.fromarray(img),master=self.root)
        self.img_camara.configure(image=self._image,text='')

    def _dibujar(self,v: VistaCuadro):
        # Limitar solo las conversiones de la interfaz, no el analisis ni votos.
        ahora=time.monotonic()
        if (v is not self._vista_id) and ahora-self._ultimo_dibujo>=1/15:
            self._imagen(v.fotograma)
            self._vista_id=v
            self._ultimo_dibujo=ahora
        estado=v.estado
        colores={
            'PASA':(VERDE,'#D9F4E5'),
            'NO PASA':(ROJO,'#F9E2E6'),
            'CAMARA SIN SENAL':(ROJO,'#F9E2E6'),
            'EVALUANDO PRODUCTO':(AMBAR,'#FFF0CD'),
            'ESPERANDO FECHA COMPLETA':(MARINO,'#E4EFF6'),
            'ESPERANDO PRODUCTO':(MARINO,'#E4EFF6'),
            'CAMARA EN ESPERA':(AMBAR,'#FFF0CD'),
        }
        fg,bg=colores.get(estado,(MARINO,'#E4EFF6'))
        self.lbl_estado.configure(text=estado,bg=bg,fg=fg)
        self.lbl_producto.configure(text=f'Producto: {v.producto if v.producto is not None else "--"} '
                                         f' | Capturas: {v.muestreos}/{v.objetivo}')
        self.lbl_votos.configure(text=f'Buenas {v.buenas}   |   Malas {v.malas}   |   Inciertas {v.ambiguas+v.desenfocadas}')
        self.lbl_muestra.configure(text=f'Ultima muestra: {v.ultima_muestra}')
        self.lbl_motivo.configure(text=v.motivo or 'Inspeccion en curso.')
        self.txt_senal.configure(text=('PAUSA DE VIDEO' if v.aviso else 'CAMARA ACTIVA'),
                                  fg=AMBAR if v.aviso else VERDE)

    def _refrescar_historial(self):
        self._filas_historial=cargar_historial(self.control.carpeta)
        filtro=self.filtro_estado.get()
        rows=filtrar_historial(self._filas_historial,
                              resultado=filtro if filtro in ('PASA','NO PASA') else '',
                              tipo='sin_evidencia' if filtro=='Preventivo' else '',
                              buscar=self.busqueda.get())
        for item in self.tabla.get_children(): self.tabla.delete(item)
        for r in rows[:160]:
            self.tabla.insert('', 'end',values=(r['producto_id'],r['resultado'],
                              r['buenas'],r['malas'],r['inciertas'],
                              r.get('linea', ''),r.get('turno', '')),
                              tags=('pasa' if r['resultado']=='PASA' else 'no_pasa',))

    def exportar(self):
        filas=filtrar_historial(cargar_historial(self.control.carpeta),
                               resultado=self.filtro_estado.get() if self.filtro_estado.get() in ('PASA','NO PASA') else '',
                               tipo='sin_evidencia' if self.filtro_estado.get()=='Preventivo' else '',
                               buscar=self.busqueda.get())
        if not filas:
            messagebox.showinfo('V.I.T.A.','No hay registros para exportar con ese filtro.')
            return
        archivo=filedialog.asksaveasfilename(defaultextension='.csv',
                            filetypes=[('Archivo CSV','*.csv')],
                            initialfile='VITA_historial.csv')
        if archivo:
            try:
                Path(archivo).write_bytes(exportar_csv(filas))
            except OSError as exc:
                messagebox.showerror('Exportacion',str(exc))
            else:
                self.lbl_info.configure(text=f'Historial exportado: {Path(archivo).name}')

    def _actualizar(self):
        try:
            encontradas=self._scan_resultados.get_nowait()
        except queue.Empty:
            pass
        else:
            if not self._cerrando:
                self._fin_busqueda(encontradas)
        nuevos=self.control.consultar()
        for evento in nuevos:
            self._refrescar_historial()
            tipo='PREVENTIVO' if evento['tipo']=='sin_evidencia' else evento['resultado']
            self.lbl_ultimo.configure(text=f"Producto {evento['producto_id']}  |  {tipo}\n"
                              f"{evento['buenas']} buenas, {evento['malas']} malas\n"
                              f"{evento['motivo']}",
                              fg=VERDE if evento['resultado']=='PASA' else ROJO)
        if self._ultimo_numero_eventos != len(self.control.eventos_sesion):
            res=self.control.resumen
            self.lbl_cifras.configure(text=f"{res['total']} inspeccionados  |  {res['pasa']} PASA  |  {res['no_pasa']} NO PASA")
            self.lbl_preventivos.configure(text=f"Sin evidencia suficiente: {res['sin_evidencia']}")
            self._ultimo_numero_eventos=len(self.control.eventos_sesion)
        self.lbl_info.configure(text=self.control.info)
        v=self.control.ultima_vista
        if v is not None and v is not getattr(self,'_ultima_vista_mostrada',None):
            self._dibujar(v)
            self._ultima_vista_mostrada=v
        perf=self.control.rendimiento
        if perf:
            self.lbl_fps.configure(text=f"Analisis: {perf.get('fps_analisis',0):.1f} fps | {perf.get('ms_proceso',0):.0f} ms | omitidos: {perf.get('omitidos',0)}")
        if self.control.fase=='error':
            self.lbl_estado.configure(text='ERROR DE CAMARA',bg='#F9E2E6',fg=ROJO)
        if self.control.fase=='cargando':
            self.lbl_estado.configure(text='PREPARANDO EQUIPO',bg='#E4EFF6',fg=MARINO)
        if self.control.fase in ('detenido','error'):
            self.btn_start.configure(state='normal')
            self.btn_stop.configure(state='disabled')
            for widget in (self.combo_camara,self.combo_backend,self.combo_resolucion):
                widget.configure(state='normal' if widget is self.combo_camara else 'readonly')
            if not self._scan_activo:
                self.boton_buscar.configure(state='normal')
            for campo in self._meta_entries:
                campo.configure(state='normal')
        if self._cerrando:
            if not self.control.activo:
                self.root.destroy()
                return
        self.root.after(70,self._actualizar)

    def cerrar(self):
        self.control.cerrar()
        self._cerrando=True
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='disabled')
        self.lbl_info.configure(text='Cerrando V.I.T.A. y guardando historial...')
        if not self.control.activo:
            self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description='V.I.T.A. - panel NATIVO, sin servidor local')
    parser.add_argument('--camara',type=int,default=0,
                        help='indice inicial sugerido; tambien se elige en la interfaz')
    args=parser.parse_args()
    root=tk.Tk()
    VitaOperadorGUI(root,indice_inicial=args.camara)
    root.mainloop()

if __name__=='__main__':
    main()

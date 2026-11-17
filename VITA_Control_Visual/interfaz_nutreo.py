"""NUTREO | Interfaz visual independiente para inspeccion de banda.

Ejecutar desde esta misma carpeta:
    python interfaz_nutreo.py

No sustituye iniciar_calidad.py ni modifica los detectores/umbrales.
Usa el modelo YOLO, el inspector robusto y el seguimiento temporal EXISTENTES.
La interfaz dibuja visualizaciones y muestra eventos reales del motor.

Estados visibles al operador:
    ESPERANDO PRODUCTO -> EVALUANDO PRODUCTO -> PASA / NO PASA.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

from iniciar_calidad import RegistroEventos, cargar_yolo, detectar_cajas, ROOT
from inspeccion_robusta import InspectorCalidadRobusto
from evidencia_inspeccion import registrar_evidencia
from evidencia_en_cola import EvidenciasEnCola
from camara_buffer import CapturaReciente
from captura_segura import GuardiaCaptura, backends_camara, diagnostico_movimiento_roi
from seguimiento_banda import EventoFinal, Observacion, SeguimientoBanda
from visualizador_filtros import crear_vistas_filtros

BG = '#0A1320'
PANEL = '#111E2D'
PANEL2 = '#17283A'
LINE = '#26394C'
TEXT = '#F1F6FB'
MUTED = '#91A6BA'
BLUE = '#58BAFF'
GREEN = '#32D6A0'
RED = '#FF707F'
YELLOW = '#FFCA68'
DEFAULT_CSV = ROOT / 'registros_gui.csv'


@dataclass(frozen=True)
class Configuracion:
    camara: int = 0
    camara_backend: str = "auto"
    resolucion_camara: str = "Automatica"
    video: Optional[Path] = None
    fotos: int = 7
    min_fotos: int = 3
    min_buenas: int = 5
    zona_segura_pct: float = 8.
    confirmaciones_fecha: int = 3
    control_visibilidad: bool = True
    intervalo_ms: float = 180.
    conf: float = 0.45
    recorte_borde: float = .12  # cada lado del eje corto de YOLO
    pesos: Path = ROOT / 'best.pt'
    registro: Path = DEFAULT_CSV
    mostrar_etapas: bool = True
    guardar_evidencia: bool = True  # registrar recortes/motivos de cada voto
    evidencia_asincrona: bool = False  # panel operativo: escritura fuera del hilo YOLO
    captura_reciente: bool = False  # panel operativo: nunca analizar buffers atrasados
    ruta_evidencia: Path = ROOT / 'evidencias_inspeccion'
    bloqueo_unico: bool = True            # un producto en la zona de inspeccion
    ausencia_ms: float = 650.             # tiempo minimo sin recuadro YOLO
    cuadros_ausentes: int = 3             # ademas, 3 cuadros vacios consecutivos
    intervalo_dudosa_ms: float = 450.     # argumento antiguo, no altera frecuencia
    max_dudosas: int = 3                  # argumento antiguo por compatibilidad


@dataclass
class VistaCuadro:
    """Instantanea de solo lectura para actualizar Tk en el hilo principal."""
    fotograma: np.ndarray
    instante: float
    estado: str = 'ESPERANDO PRODUCTO'
    producto: Optional[int] = None
    buenas: int = 0
    malas: int = 0
    ambiguas: int = 0
    desenfocadas: int = 0
    validas: int = 0
    muestreos: int = 0
    objetivo: int = 7
    min_buenas: int = 5
    max_dudosas: int = 3  # compatibilidad
    motivo: str = 'No se ha detectado ninguna fecha.'
    ultima_muestra: str = 'SIN FECHA'
    metricas: dict = field(default_factory=dict)
    filtro_paneles: dict = field(default_factory=dict)
    etapas_version: tuple[int, int] | None = None
    regiones: int = 0
    tiempo_ms: float = 0.
    segunda_pasada: bool = False
    aviso: str = ''


def vista_sin_nuevo_fotograma(ultima: VistaCuadro | None,
                             frame: np.ndarray, instante: float,
                             motivo: str, interrupcion: bool = False) -> VistaCuadro:
    """Mantiene los recuadros, voto y filtros previos durante pausas de Wi-Fi.

    No se invoca YOLO, no se altera el seguimiento, no se suma ningun voto.
    El video retenido se identifica explicitamente; no se presenta como LIVE.
    """
    if ultima is None:
        base = VistaCuadro(frame.copy(), instante,
                          estado='CAMARA EN ESPERA',
                          ultima_muestra='SIN NUEVA MUESTRA',
                          motivo='Esperando un fotograma util de la camara.')
    else:
        # Crucial: el overlay YA CONTIENE ZONA SEGURA y el ultimo recuadro.
        # Antes se remplazaba por frame.copy() y ambas marcas parpadeaban.
        base = replace(ultima, instante=instante,
                       fotograma=ultima.fotograma.copy())
    if interrupcion:
        base.estado = 'CAMARA SIN SENAL'
        base.motivo = 'Captura interrumpida. Sin evaluacion ni aprobacion nuevas.'
    base.aviso = 'Video en espera / sin fotograma nuevo: ' + motivo + '. NO se suman votos.'
    cv2.putText(base.fotograma,
                'VIDEO EN ESPERA - SIN NUEVO VOTO', (12, 27),
                cv2.FONT_HERSHEY_SIMPLEX, .57, (0, 165, 255), 2, cv2.LINE_AA)
    return base


class ProcesadorNutreo:
    """Motor independiente de Tk, con un unico ID mientras el recuadro persista."""

    def __init__(self, config: Configuracion, modelo, inspector, registro=None):
        self.config = config
        self.modelo = modelo
        self.inspector = inspector
        self.registro = registro
        self.tracker = SeguimientoBanda(
            objetivo=config.fotos, min_validas=min(config.min_fotos, config.fotos),
            intervalo_s=config.intervalo_ms / 1000.,
            max_ausencia_s=config.ausencia_ms / 1000.,
            max_sin_ver=config.cuadros_ausentes,
            proporcion_minima=.50, max_muestras=config.fotos,
            bloqueo_unico=config.bloqueo_unico,
            intervalo_dudosa_s=config.intervalo_dudosa_ms / 1000.,
            max_dudosas=config.max_dudosas,
            min_buenas=config.min_buenas, control_visibilidad=config.control_visibilidad,
            margen_seguro=config.zona_segura_pct/100.,
            confirmaciones=config.confirmaciones_fecha,
        )
        self.ultimo_evento: Optional[EventoFinal] = None
        self.instante_evento: float = -1e9
        self.n_cuadro = 0
        # Unicamente las capturas admitidas actualizan paneles y metricas.
        self._ultimas_vistas: dict = {}
        self._guardador = (EvidenciasEnCola() if config.guardar_evidencia and
                           config.evidencia_asincrona else None)
        # Evitar que dos sesiones reutilicen producto_0001 y sobrescriban
        # pruebas de una inspeccion anterior.
        self.ruta_evidencia_sesion = (config.ruta_evidencia /
            ('sesion_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))

    def procesar(self, frame: np.ndarray, instante: float):
        self.n_cuadro += 1
        inicio = time.perf_counter()
        cajas = detectar_cajas(frame, self.modelo, self.config.conf,
                              recorte_borde=self.config.recorte_borde)
        obs = [Observacion(caja, 'REVISAR', 'Esperando fecha completa') for caja in cajas]
        resultados_muestreados = {}
        def evaluar(pista, observacion, indice):
            x1,y1,x2,y2 = observacion.caja
            roi = frame[y1:y2, x1:x2]
            resultado = self.inspector.analizar(roi)
            # Metricas de VITA, solo como informacion tecnica de captura.
            # NO producen un voto MALA ni fuerzan formatos de fecha.
            resultado.metricas.update(diagnostico_movimiento_roi(roi))
            resultados_muestreados[indice] = (resultado, observacion.caja)
            return Observacion(observacion.caja, resultado.estado, resultado.motivo)
        actualizado = self.tracker.actualizar(obs, instante, self.n_cuadro,
                                              forma_frame=frame.shape, evaluar=evaluar)
        for ev in actualizado.eventos:
            self.ultimo_evento = ev
            self.instante_evento = instante
            if self.registro is not None:
                self.registro.guardar(ev)

        # Los indices impiden que un recuadro duplicado de YOLO mezcle la
        # imagen del segundo resultado con el ID del primero.
        pares = [(resultados_muestreados[i], pista)
                 for i, (_, pista) in zip(actualizado.indices, actualizado.asignaciones)
                 if i in resultados_muestreados]
        muestras_ids = {id_ for id_, _, _, _ in actualizado.muestras}
        for (resultado, caja), p in pares:
            if p.id not in muestras_ids:
                continue
            # Guardar el fotograma ORIGINAL que causo cada voto. El detalle
            # ampliado de la interfaz es una instantanea y puede no coincidir
            # con todos los votos que acumulo ese producto.
            if self.config.guardar_evidencia:
                x1, y1, x2, y2 = caja
                try:
                    if self._guardador is not None:
                        self._guardador.agregar(self.ruta_evidencia_sesion, p.id,
                                               p.muestreos, frame[y1:y2, x1:x2], resultado)
                    else:
                        registrar_evidencia(self.ruta_evidencia_sesion, p.id,
                                            p.muestreos, frame[y1:y2, x1:x2], resultado)
                except (OSError, ValueError, cv2.error) as exc:
                    # No abortar inspeccion por error de disco; documentar
                    # que la evidencia de ESTA captura no se pudo guardar.
                    resultado.metricas['evidencia_error'] = 1.0
                    print('NUTREO | Error guardando evidencia:', exc, flush=True)
            anterior = self._ultimas_vistas.get(p.id, {})
            nuevo = {
                'metricas': dict(resultado.metricas),
                'segunda': bool(resultado.metricas.get('segunda_pasada', 0.)),
                'motivo': resultado.motivo,
                'paneles': anterior.get('paneles', {}),
            }
            if self.config.mostrar_etapas:
                x1, y1, x2, y2 = caja
                nuevo['paneles'] = crear_vistas_filtros(frame[y1:y2, x1:x2], resultado)
            self._ultimas_vistas[p.id] = nuevo
        for id_ in list(self._ultimas_vistas):
            if id_ not in self.tracker.pistas:
                del self._ultimas_vistas[id_]

        overlay = frame.copy()
        if self.config.control_visibilidad:
            alto, ancho = overlay.shape[:2]
            margen = self.config.zona_segura_pct/100.
            xa, ya = int(ancho*margen), int(alto*margen)
            xb, yb = int(ancho*(1.-margen)), int(alto*(1.-margen))
            cv2.rectangle(overlay,(xa,ya),(xb,yb),(195,115,60),1)
            cv2.putText(overlay,'ZONA SEGURA',(xa+5,max(14,ya+17)),
                        cv2.FONT_HERSHEY_SIMPLEX,.45,(195,115,60),1,cv2.LINE_AA)
        for p in self.tracker.pistas.values():
            # La caja persiste durante fallos transitorios de YOLO; se marca
            # explicitamente que la deteccion no esta confirmada en este frame.
            x1, y1, x2, y2 = p.caja_mostrada
            visto = p.ultimo_cuadro == self.n_cuadro
            if p.estado_final is None:
                color = (245, 185, 55)
                estado_caja = ('ESPERANDO FECHA COMPLETA' if self.config.control_visibilidad and p.muestreos == 0 and not p.visibilidad.habilitada else 'EVALUANDO')
            else:
                color = (137, 209, 38) if p.estado_final == 'BIEN' else (127, 112, 255)
                estado_caja = 'PASA' if p.estado_final == 'BIEN' else 'NO PASA'
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2 if visto else 1)
            estado_caja += '' if visto else ' | YOLO INTERMITENTE'
            etiqueta = f'ID {p.id} | {estado_caja}'
            cv2.putText(overlay, etiqueta, (x1, max(19, y1-7)),
                        cv2.FONT_HERSHEY_SIMPLEX, .53, color, 2, cv2.LINE_AA)

        vista = VistaCuadro(overlay, instante, objetivo=self.config.fotos,
                           min_buenas=self.config.min_buenas,
                           max_dudosas=self.config.max_dudosas,
                           regiones=len(actualizado.asignaciones))
        # Elegir un producto real (no necesariamente detectado en ESTE cuadro),
        # para que ni el recuadro ni su decision parpadeen por YOLO intermitente.
        activos = list(self.tracker.pistas.values())
        p = max(activos, key=lambda q: (q.ultimo_cuadro, q.validas), default=None)
        if p is not None:
            ultimo = self._ultimas_vistas.get(p.id, {})
            vista.producto = p.id
            vista.buenas = p.buenas
            vista.malas = p.malas
            vista.ambiguas = p.ambiguas
            vista.desenfocadas = p.desenfocadas
            vista.validas = p.validas
            vista.muestreos = p.muestreos
            vista.metricas = dict(ultimo.get('metricas', {}))
            vista.segunda_pasada = bool(ultimo.get('segunda', False))
            vista.filtro_paneles = ultimo.get('paneles', {})
            vista.etapas_version = (p.id, p.muestreos)
            vista.ultima_muestra = {'BIEN': 'BUENA', 'MAL': 'MALA',
                                    'REVISAR': 'NO EVALUABLE',
                                    'SIN FOTO': 'CAPTURANDO'}.get(p.ultima_muestra, p.ultima_muestra)
            if p.estado_final is None:
                if self.config.control_visibilidad and p.muestreos == 0 and not p.visibilidad.habilitada:
                    vista.estado = 'ESPERANDO FECHA COMPLETA'
                    vista.motivo = p.visibilidad.motivo
                else:
                    vista.estado = 'EVALUANDO PRODUCTO'
                    vista.motivo = (p.visibilidad.motivo if not p.visibilidad.habilitada
                                    else ultimo.get('motivo', 'Fecha completa. Tomando capturas.'))
            else:
                vista.estado = 'PASA' if p.estado_final == 'BIEN' else 'NO PASA'
                vista.motivo = p.motivo_final
                vista.ultima_muestra = 'DECISION FINAL'
            if p.faltas > 0:
                vista.aviso = ('Recuadro conservado: YOLO no lo detecto en este cuadro. '
                              'Esperando salida confirmada.')
            elif self.config.control_visibilidad and p.estado_final is None and not p.visibilidad.habilitada:
                vista.aviso = ('Aun no se suman votos: ' + p.visibilidad.motivo)
            elif p.estado_final is not None:
                vista.aviso = ('Resultado bloqueado para este producto. '
                              'Se habilitara otro cuando salga la fecha.')
            elif any(p.id == id_ and estado == 'REVISAR'
                     for id_, _, estado, _ in actualizado.muestras):
                vista.aviso = 'Muestra incierta registrada (no es voto). Se buscara una toma clara.'
            elif p.dudosas_ignoradas > 0:
                vista.aviso = ('Capturas inciertas repetidas ignoradas; '
                              'no incrementan el contador de dudas.')
        elif self.ultimo_evento is not None and instante - self.instante_evento <= 1.8:
            ev = self.ultimo_evento
            vista.estado = 'PASA' if ev.estado == 'BIEN' else 'NO PASA'
            vista.producto = ev.id
            vista.buenas = ev.buenas
            vista.malas = ev.malas
            vista.ambiguas = ev.ambiguas
            vista.desenfocadas = ev.desenfocadas
            vista.validas = ev.validas
            vista.muestreos = ev.total
            vista.motivo = ev.motivo
            vista.ultima_muestra = 'DECISION FINAL'
        else:
            vista.estado = 'ESPERANDO PRODUCTO'
            vista.motivo = 'Esperando que YOLO detecte una fecha delante de la camara.'
            vista.ultima_muestra = 'SIN FECHA'
        vista.tiempo_ms = (time.perf_counter() - inicio) * 1000.
        return vista, actualizado.eventos

    def cerrar_evidencias(self):
        if self._guardador is not None:
            self._guardador.cerrar()
            return list(self._guardador.errores)
        return []

    def cancelar_por_falla_camara(self, instante: float):
        """No aprobar productos pendientes cuando se perdio la camara."""
        eventos = self.tracker.invalidar_por_falla_camara(instante, self.n_cuadro)
        for ev in eventos:
            self.ultimo_evento = ev
            self.instante_evento = instante
            if self.registro is not None:
                self.registro.guardar(ev)
        self._ultimas_vistas.clear()
        return eventos

    def finalizar(self, instante: float):
        eventos = self.tracker.cerrar(instante, self.n_cuadro)
        for ev in eventos:
            if self.registro is not None:
                self.registro.guardar(ev)
        return eventos


class Trabajador(threading.Thread):
    """Toda la captura, YOLO y OpenCV ocurren fuera del hilo de interfaz."""

    def __init__(self, config: Configuracion, stop: threading.Event,
                 cola_fotos: queue.Queue, cola_eventos: queue.Queue):
        super().__init__(name='NutreoCamara', daemon=True)
        self.config = config
        self.stop_flag = stop
        self.cola_fotos = cola_fotos
        self.cola_eventos = cola_eventos

    def _publicar_foto(self, vista):
        try:
            self.cola_fotos.put_nowait(vista)
        except queue.Full:
            try:
                self.cola_fotos.get_nowait()
            except queue.Empty:
                pass
            try:
                self.cola_fotos.put_nowait(vista)
            except queue.Full:
                pass

    def run(self):
        capture = None
        registro = None
        proceso = None
        lector_reciente = None
        ultimo_t = 0.
        try:
            self.cola_eventos.put(('info', 'Cargando best.pt y preparando el inspector...'))
            modelo = cargar_yolo(self.config.pesos)
            if self.stop_flag.is_set():
                return
            inspector = InspectorCalidadRobusto()
            if self.config.video is not None:
                capture = cv2.VideoCapture(str(self.config.video), cv2.CAP_ANY)
                backend_nombre = 'archivo de video'
            else:
                # Seleccion de API inspirada en VITA. MSMF puede funcionar
                # mejor con camaras de celular; DSHOW es el respaldo habitual.
                for nombre, backend in backends_camara(sys.platform, self.config.camara_backend):
                    cam = cv2.VideoCapture(self.config.camara, backend)
                    if cam.isOpened():
                        capture, backend_nombre = cam, nombre
                        break
                    cam.release()
            if capture is None or not capture.isOpened():
                raise RuntimeError('No fue posible abrir la camara o el video. Verifica la fuente y sus permisos.')
            if self.config.video is None and self.config.resolucion_camara != 'Automatica':
                ancho, alto = (int(v) for v in self.config.resolucion_camara.split('x'))
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not np.isfinite(fps) or fps <= 1:
                fps = 30.
            if self.config.video is None and self.config.captura_reciente:
                lector_reciente = CapturaReciente(capture)
            registro = RegistroEventos(self.config.registro)
            proceso = ProcesadorNutreo(self.config, modelo, inspector, registro)
            self.cola_eventos.put(('info', f'Fuente activa ({backend_nombre}). Esperando producto.'))
            guardia = GuardiaCaptura(repeticiones_congelado=45, segundos_congelado=2.5)
            numero = 0
            errores_lectura = 0
            ultimo_aviso = -1e12
            ultima_vista = None
            falla_grave = False
            desde_invalido = None
            ultima_publicacion_pausa = -1e12
            ultimo_fotograma_nuevo = time.monotonic()
            secuencia_recibida = 0
            ultima_llegada = time.monotonic()
            ultimo_reporte = time.monotonic()
            procesados_intervalo = 0
            while not self.stop_flag.is_set():
                if lector_reciente is not None:
                    nuevo = lector_reciente.esperar_nuevo(secuencia_recibida, timeout=.35)
                    if nuevo is None:
                        # La interfaz sigue receptiva, pero el tracker no puede
                        # aprobar con un fotograma viejo durante un corte de Wi-Fi.
                        if time.monotonic()-ultima_llegada > 2.5 and not falla_grave:
                            for ev in proceso.cancelar_por_falla_camara(time.monotonic()):
                                self.cola_eventos.put(('resultado', ev))
                            falla_grave = True
                            self.cola_eventos.put(('info', 'Camara sin fotogramas nuevos; inspeccion interrumpida.'))
                        if time.monotonic()-ultima_llegada > 9.:
                            self.cola_eventos.put(('error', 'La camara dejo de enviar imagenes.'))
                            break
                        continue
                    secuencia_recibida, frame, instante_captura = nuevo
                    ultima_llegada = time.monotonic()
                    ok = True
                else:
                    ok, frame = capture.read()
                if not ok or frame is None:
                    if self.config.video is not None:
                        self.cola_eventos.put(('info', 'Fin del archivo de video.'))
                        break
                    errores_lectura += 1
                    if errores_lectura >= 30:
                        falla_grave = True
                        self.cola_eventos.put(('error', 'Camara sin cuadros: no se emitiran aprobaciones pendientes.'))
                        break
                    time.sleep(.04)
                    continue
                errores_lectura = 0
                numero += 1
                # Video: tiempo por fotograma, no por velocidad de decodificacion.
                t = ((numero - 1) / fps if self.config.video is not None
                     else (instante_captura if lector_reciente is not None else time.monotonic()))
                ultimo_t = t
                estado_camara = guardia.revisar(frame)
                # Una camara de celular por Wi-Fi repite fotogramas entre
                # actualizaciones. No son defectos ni una nueva evaluacion.
                duplicado = estado_camara.util and estado_camara.repeticiones > 0
                if not estado_camara.util or duplicado:
                    motivo = ('fotograma repetido (enlace de celular o escena quieta)'
                              if duplicado else estado_camara.motivo)
                    grave = not estado_camara.util
                    if grave:
                        if desde_invalido is None:
                            desde_invalido = time.monotonic()
                        if time.monotonic() - desde_invalido > 2.0 and not falla_grave:
                            # Fallo prolongado: cerrar preventivamente un
                            # producto pendiente, NUNCA aprobarlo.
                            for ev in proceso.cancelar_por_falla_camara(t):
                                self.cola_eventos.put(('resultado', ev))
                            falla_grave = True
                    else:
                        desde_invalido = None
                    # No sustituir el overlay con un frame sin recuadro.
                    # Solo actualizar la pantalla de vez en cuando durante
                    # una pausa visible; asi no oscila CAPTURA NO UTIL / BIEN.
                    pausa_visible = (time.monotonic() - ultimo_fotograma_nuevo >= 0.8)
                    ahora = time.monotonic()
                    if (ultima_vista is None or grave or pausa_visible) and (
                            ahora - ultima_publicacion_pausa >= 0.65):
                        vista = vista_sin_nuevo_fotograma(
                            ultima_vista, frame, t, motivo,
                            interrupcion=falla_grave)
                        self._publicar_foto(vista)
                        ultima_publicacion_pausa = ahora
                    if grave and ahora - ultimo_aviso > 2.0:
                        self.cola_eventos.put(('info', 'Camara: ' + motivo + '. Sin nuevos votos.'))
                        ultimo_aviso = ahora
                    if self.config.video is None:
                        time.sleep(0.03)  # Evita leer el mismo frame a cientos de FPS.
                    continue
                desde_invalido = None
                falla_grave = False
                ultimo_fotograma_nuevo = time.monotonic()
                vista, eventos = proceso.procesar(frame, t)
                procesados_intervalo += 1
                ahora_diag = time.monotonic()
                if lector_reciente is not None and ahora_diag - ultimo_reporte >= 2.:
                    stats_camara = lector_reciente.estadisticas(secuencia_recibida)
                    self.cola_eventos.put(('rendimiento', {
                        'fps_analisis': round(procesados_intervalo / max(.01, ahora_diag-ultimo_reporte), 1),
                        'ms_proceso': round(vista.tiempo_ms, 1),
                        'leidos': stats_camara['recibidos'],
                        'omitidos': max(0, stats_camara['recibidos']-numero),
                    }))
                    procesados_intervalo = 0
                    ultimo_reporte = ahora_diag
                ultima_vista = vista
                self._publicar_foto(vista)
                for ev in eventos:
                    self.cola_eventos.put(('resultado', ev))
            if falla_grave and proceso is not None:
                for ev in proceso.cancelar_por_falla_camara(ultimo_t):
                    self.cola_eventos.put(('resultado', ev))
        except Exception as exc:
            # Excepcion del detector o de la camara: no aprobar un producto
            # pendiente mediante el cierre normal despues de un fallo.
            if proceso is not None:
                try:
                    for ev in proceso.cancelar_por_falla_camara(ultimo_t):
                        self.cola_eventos.put(('resultado', ev))
                except Exception as error_cierre:
                    self.cola_eventos.put(('error', f'Error invalidando captura: {error_cierre}'))
            self.cola_eventos.put(('error', str(exc)))
        finally:
            if proceso is not None:
                try:
                    for ev in proceso.finalizar(ultimo_t):
                        self.cola_eventos.put(('resultado', ev))
                except Exception as exc:
                    self.cola_eventos.put(('error', f'Error cerrando seguimiento: {exc}'))
            if proceso is not None:
                for error_evidencia in proceso.cerrar_evidencias():
                    self.cola_eventos.put(('info', 'No se pudo guardar una evidencia: ' + error_evidencia))
            if registro is not None:
                registro.close()
            if lector_reciente is not None:
                lector_reciente.cerrar()
            if capture is not None:
                capture.release()
            self.cola_eventos.put(('detenido', 'Proceso detenido.'))


class NutreoGUI:
    FONT = 'Segoe UI' if sys.platform == 'win32' else 'DejaVu Sans'

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('V.I.T.A. | Centro tecnico de inspeccion visual')
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f'{min(1440, max(960, screen_w-60))}x{min(940, max(650, screen_h-85))}')
        self.root.minsize(960, 630)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.cerrar)
        self._stop = threading.Event()
        self._worker: Optional[Trabajador] = None
        self._cola_fotos: queue.Queue = queue.Queue(maxsize=2)
        self._cola_eventos: queue.Queue = queue.Queue()
        self._ultima_vista: Optional[VistaCuadro] = None
        self._images = {}
        self._vistas_ultimo = {}
        self._ultimo_render_etapas = None
        self._hist_count = 0
        self._conectado = False
        self._last_draw = 0.
        self._state_time = 0.
        self._last_state = None
        self._cerrando = False
        self._crear_estilos()
        self._construir()
        self._limpiar_etapas()
        self._dibujar_estado('ESPERANDO PRODUCTO', 'Inicia la camara para inspeccionar fechas.')
        self.root.after(45, self._actualizar)

    def _crear_estilos(self):
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Nutreo.Horizontal.TProgressbar', troughcolor=LINE,
                        background=BLUE, darkcolor=BLUE, lightcolor=BLUE,
                        bordercolor=LINE, thickness=16)
        style.configure('Nutreo.Treeview', background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=27, borderwidth=0,
                        font=(self.FONT, 9))
        style.configure('Nutreo.Treeview.Heading', background=PANEL2,
                        foreground=TEXT, font=(self.FONT, 9, 'bold'), relief='flat')
        style.map('Nutreo.Treeview', background=[('selected', '#265177')])

    def _texto(self, parent, valor='', tamaño=11, color=TEXT, negrita=False, **kwargs):
        return tk.Label(parent, text=valor, bg=parent.cget('bg'), fg=color,
                        font=(self.FONT, tamaño, 'bold' if negrita else 'normal'), **kwargs)

    def _panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, highlightbackground=LINE,
                        highlightcolor=LINE, highlightthickness=1, **kwargs)

    def _control_entry(self, parent, variable, ancho):
        return tk.Entry(parent, textvariable=variable, width=ancho, bg=PANEL2,
                        fg=TEXT, insertbackground=TEXT, highlightthickness=1,
                        highlightbackground=LINE, highlightcolor=BLUE,
                        relief='flat', font=(self.FONT, 10))

    def _btn(self, parent, texto, comando, fondo, activo=None):
        return tk.Button(parent, text=texto, command=comando, bg=fondo,
                         activebackground=activo or fondo, fg=BG,
                         activeforeground=BG, bd=0, cursor='hand2', padx=15,
                         pady=9, font=(self.FONT, 10, 'bold'))

    def _construir(self):
        root = self.root
        top = tk.Frame(root, bg=BG, padx=20, pady=13)
        top.pack(side='top', fill='x')
        self._texto(top, 'V.I.T.A.', 22, BLUE, True).pack(side='left')
        self._texto(top, '  /  CONTROL VISUAL DE IMPRESION', 13, TEXT, True).pack(side='left', pady=7)
        self._texto(top, 'Vision artificial  ·  Inspeccion en tiempo real',
                    10, MUTED).pack(side='right', pady=8)

        settings = self._panel(root)
        settings.pack(fill='x', padx=20, pady=(0, 12))
        form = tk.Frame(settings, bg=PANEL, padx=12, pady=10)
        form.pack(fill='x')
        self.fuente = tk.StringVar(value='camara')
        self.indice = tk.StringVar(value='0')
        self.camara_backend = tk.StringVar(value='auto')
        self.resolucion_camara = tk.StringVar(value='Automatica')
        self.fotos = tk.StringVar(value='7')
        self.min_buenas = tk.StringVar(value='5')
        self.zona_segura = tk.StringVar(value='8')
        self.confirmaciones = tk.StringVar(value='3')
        self.intervalo = tk.StringVar(value='180')
        self.confianza = tk.StringVar(value='0.45')
        self.recorte_borde = tk.StringVar(value='12')
        self.ausencia = tk.StringVar(value='650')
        self.video = tk.StringVar(value='')
        self.guardar_evidencia = tk.BooleanVar(value=True)
        tk.Radiobutton(form, text='Camara', variable=self.fuente, value='camara',
                       bg=PANEL, fg=TEXT, selectcolor=PANEL2,
                       activebackground=PANEL, activeforeground=TEXT,
                       font=(self.FONT, 10)).pack(side='left')
        self._control_entry(form, self.indice, 3).pack(side='left', padx=(3, 15), ipady=7)
        tk.Radiobutton(form, text='Video de prueba', variable=self.fuente, value='video',
                       bg=PANEL, fg=TEXT, selectcolor=PANEL2,
                       activebackground=PANEL, activeforeground=TEXT,
                       font=(self.FONT, 10)).pack(side='left')
        self._btn(form, 'Elegir video', self._elegir_video, '#B6C9DA').pack(side='left', padx=(5, 18))
        self._texto(form, 'Max. fotos', 9, MUTED).pack(side='left')
        self._control_entry(form, self.fotos, 3).pack(side='left', padx=(6, 15), ipady=7)
        self._texto(form, 'Intervalo ms', 9, MUTED).pack(side='left')
        self._control_entry(form, self.intervalo, 4).pack(side='left', padx=(6, 15), ipady=7)
        self._texto(form, 'YOLO conf.', 9, MUTED).pack(side='left')
        self._control_entry(form, self.confianza, 4).pack(side='left', padx=(6, 14), ipady=7)
        self.boton_inicio = self._btn(form, 'INICIAR', self.iniciar, GREEN)
        self.boton_inicio.pack(side='right', padx=(8, 0))
        self.boton_stop = self._btn(form, 'DETENER', self.detener, RED)
        self.boton_stop.pack(side='right')
        self.boton_stop.configure(state='disabled')

        # Los tres parametros permiten adaptarse a la velocidad real de la
        # banda sin editar codigo: no liberamos un ID por completar 7 fotos.
        extra = tk.Frame(settings, bg=PANEL, padx=13, pady=7)
        extra.pack(fill='x')
        self._texto(extra, 'RECUADRO DEL MISMO PRODUCTO', 9, GREEN, True).pack(side='left', padx=(0, 12))
        self._texto(extra, 'Salida sin YOLO (ms)', 9, MUTED).pack(side='left')
        self._control_entry(extra, self.ausencia, 5).pack(side='left', padx=(6, 12), ipady=5)
        self._texto(extra, 'Reducir alto (%)', 9, MUTED).pack(side='left')
        self._control_entry(extra, self.recorte_borde, 3).pack(side='left', padx=(6, 12), ipady=5)
        self._texto(extra, 'Solo area interior de la fecha (evita etiqueta)',
                    9, BLUE, True).pack(side='left', padx=(4, 10))
        reglas = tk.Frame(settings, bg=PANEL, padx=13, pady=7)
        reglas.pack(fill='x')
        self._texto(reglas, 'CONTROL DE ENTRADA Y APROBACION', 9, GREEN, True).pack(side='left', padx=(0, 14))
        self._texto(reglas, 'Min. buenas', 9, MUTED).pack(side='left')
        self._control_entry(reglas, self.min_buenas, 3).pack(side='left', padx=(5, 14), ipady=5)
        self._texto(reglas, 'Margen zona (%)', 9, MUTED).pack(side='left')
        self._control_entry(reglas, self.zona_segura, 4).pack(side='left', padx=(5, 14), ipady=5)
        self._texto(reglas, 'Confirmaciones', 9, MUTED).pack(side='left')
        self._control_entry(reglas, self.confirmaciones, 3).pack(side='left', padx=(5, 12), ipady=5)
        tk.Checkbutton(reglas, text='Guardar pruebas 05/06 de cada voto',
                       variable=self.guardar_evidencia, bg=PANEL, fg=TEXT,
                       activebackground=PANEL, activeforeground=TEXT,
                       selectcolor=PANEL2, font=(self.FONT, 9)).pack(side='left', padx=(14, 0))

        opciones_camara = tk.Frame(settings, bg=PANEL, padx=13, pady=6)
        opciones_camara.pack(fill='x')
        self._texto(opciones_camara, 'CAMARA USB / CELULAR', 9, BLUE, True).pack(side='left', padx=(0, 13))
        self._texto(opciones_camara, 'Controlador', 9, MUTED).pack(side='left')
        ttk.Combobox(opciones_camara, textvariable=self.camara_backend,
                     values=('auto', 'msmf', 'dshow'), state='readonly', width=8).pack(
                         side='left', padx=(6, 15))
        self._texto(opciones_camara, 'Resolucion solicitada', 9, MUTED).pack(side='left')
        ttk.Combobox(opciones_camara, textvariable=self.resolucion_camara,
                     values=('Automatica', '1280x720', '1920x1080'),
                     state='readonly', width=12).pack(side='left', padx=(6, 15))
        self._texto(opciones_camara, 'Sin senal o imagen congelada = SIN VOTO',
                    9, YELLOW).pack(side='left')

        # Zona central desplazable: los filtros y el historial siguen siendo
        # visibles en portatiles de 1366x768 y otras pantallas pequenas.
        contenedor_scroll = tk.Frame(root, bg=BG)
        contenedor_scroll.pack(fill='both', expand=True)
        self.scroll = tk.Canvas(contenedor_scroll, bg=BG, bd=0, highlightthickness=0)
        barra_scroll = ttk.Scrollbar(contenedor_scroll, orient='vertical', command=self.scroll.yview)
        barra_scroll.pack(side='right', fill='y')
        self.scroll.pack(side='left', fill='both', expand=True)
        self.scroll.configure(yscrollcommand=barra_scroll.set)
        body = tk.Frame(self.scroll, bg=BG)
        window_body = self.scroll.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _e: self.scroll.configure(scrollregion=self.scroll.bbox('all')))
        self.scroll.bind('<Configure>', lambda e: self.scroll.itemconfigure(window_body, width=e.width))
        self.scroll.bind_all('<MouseWheel>', lambda e: self.scroll.yview_scroll(int(-e.delta/120), 'units'))
        self.scroll.bind_all('<Button-4>', lambda _e: self.scroll.yview_scroll(-1, 'units'))
        self.scroll.bind_all('<Button-5>', lambda _e: self.scroll.yview_scroll(1, 'units'))

        center = tk.Frame(body, bg=BG, height=450)
        center.pack(fill='x', padx=20)
        center.grid_propagate(False)
        center.grid_columnconfigure(0, weight=8)
        center.grid_columnconfigure(1, weight=5)
        center.grid_rowconfigure(0, weight=1)

        cam = self._panel(center)
        cam.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        cam.grid_rowconfigure(1, weight=1)
        cam.grid_columnconfigure(0, weight=1)
        bar = tk.Frame(cam, bg=PANEL)
        bar.grid(row=0, column=0, sticky='ew', padx=14, pady=12)
        self._texto(bar, 'CAMARA EN VIVO', 12, TEXT, True).pack(side='left')
        self._texto(bar, 'YOLO delimita la fecha; solo la tinta se evalua',
                    9, MUTED).pack(side='right')
        self.imagen_camara = tk.Label(cam, bg='#050B12', fg=MUTED,
                                      text='Sin imagen: pulsa INICIAR',
                                      font=(self.FONT, 14))
        self.imagen_camara.grid(row=1, column=0, sticky='nsew', padx=13, pady=(0, 13))

        status = self._panel(center)
        status.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        status.grid_columnconfigure(0, weight=1)
        self._texto(status, 'ESTADO DE INSPECCION', 11, MUTED, True).pack(
            fill='x', padx=18, pady=(15, 7))
        self.banda_estado = tk.Frame(status, bg=PANEL2, height=86)
        self.banda_estado.pack(fill='x', padx=14)
        self.banda_estado.pack_propagate(False)
        self.label_estado = tk.Label(self.banda_estado, text='ESPERANDO PRODUCTO',
                                     bg=PANEL2, fg=BLUE, font=(self.FONT, 21, 'bold'))
        self.label_estado.pack(expand=True)
        self.label_id = self._texto(status, 'Producto: --', 11, TEXT, True)
        self.label_id.pack(anchor='w', padx=18, pady=(13, 5))
        self.barra = ttk.Progressbar(status, style='Nutreo.Horizontal.TProgressbar',
                                     orient='horizontal', mode='determinate', maximum=7)
        self.barra.pack(fill='x', padx=18, pady=(2, 5))
        self.label_avance = self._texto(status, '0 de 7 capturas totales', 10, MUTED)
        self.label_avance.pack(anchor='w', padx=18)
        votos = tk.Frame(status, bg=PANEL)
        votos.pack(fill='x', padx=18, pady=(12, 8))
        votos.grid_columnconfigure((0, 1, 2), weight=1)
        self.label_buenas = self._texto(votos, '0 BUENAS', 11, GREEN, True)
        self.label_buenas.grid(row=0, column=0, sticky='w')
        self.label_malas = self._texto(votos, '0 MALAS', 11, RED, True)
        self.label_malas.grid(row=0, column=1, sticky='w')
        self.label_dudas = self._texto(votos, '0 DUDOSAS', 10, YELLOW, True)
        self.label_dudas.grid(row=0, column=2, sticky='w')
        self.label_balance = self._texto(status, 'BALANCE: 0 buenas / 0 malas',
                                        10, BLUE, True)
        self.label_balance.pack(anchor='w', padx=18, pady=(0, 5))
        self._texto(status, 'ULTIMA MUESTRA ADMITIDA', 9, MUTED, True).pack(
            anchor='w', padx=18, pady=(5, 0))
        self.label_ultima = self._texto(status, 'SIN FECHA', 13, BLUE, True)
        self.label_ultima.pack(anchor='w', padx=18, pady=(3, 6))
        self._texto(status, 'EXPLICACION DEL ANALISIS', 9, MUTED, True).pack(
            anchor='w', padx=18, pady=(3, 0))
        self.motivo = tk.Label(status, text='Esperando producto...', bg=PANEL,
                               fg=TEXT, justify='left', anchor='nw', wraplength=380,
                               font=(self.FONT, 10))
        self.motivo.pack(fill='x', padx=18, pady=(5, 8))
        self.label_metricas = tk.Label(status, text='Contraste: --   Ruido: --\n'
                                 'Verificacion secundaria: --', bg=PANEL, fg=MUTED,
                                 justify='left', anchor='nw', wraplength=390,
                                 font=(self.FONT, 9))
        self.label_metricas.pack(fill='x', padx=18, pady=(3, 10))
        self.alerta = tk.Label(status, text='', bg=PANEL, fg=YELLOW,
                               justify='left', anchor='nw', wraplength=370,
                               font=(self.FONT, 9))
        self.alerta.pack(fill='x', padx=18, pady=(0, 12))

        title_filters = tk.Frame(body, bg=BG)
        title_filters.pack(fill='x', padx=20, pady=(12, 6))
        self._texto(title_filters, 'COMO SE EVALUA LA FECHA', 12, TEXT, True).pack(side='left')
        self._texto(title_filters, 'Haz clic en una imagen para ampliarla · mascaras reales en pasos 5 y 6',
                    9, MUTED).pack(side='right')

        flow = tk.Frame(body, bg=BG, height=170)
        flow.pack(fill='x', padx=20)
        flow.grid_propagate(False)
        flow.grid_rowconfigure(0, weight=1)
        self.miniaturas = {}
        nombres = ['01  Fecha detectada', '02  Luminosidad LAB', '03  Fondo estimado',
                   '04  Contraste local (apoyo)', '05  Tinta segmentada (real)',
                   '06  Zonas sospechosas (real)']
        subtitulos = ['Recorte interior de fecha', 'Canal L, sin eliminar el color',
                      'Correccion de iluminacion', 'Vista auxiliar de diferencias',
                      'Mascara del inspector', 'Solo indicios proximos a trazos']
        for n, (nombre, info) in enumerate(zip(nombres, subtitulos)):
            flow.grid_columnconfigure(n, weight=1, uniform='filtros')
            tile = self._panel(flow)
            tile.grid(row=0, column=n, sticky='nsew', padx=(0 if n == 0 else 4,
                                                         0 if n == 5 else 4))
            self._texto(tile, nombre, 9, TEXT, True).pack(pady=(10, 4), padx=6)
            img = tk.Label(tile, bg='#07111C', fg=MUTED, text='Sin fecha',
                           height=6, width=15, font=(self.FONT, 9))
            img.pack(fill='both', expand=True, padx=7, pady=3)
            img.configure(cursor='hand2')
            img.bind('<Button-1>', lambda _ev, etapa=nombre: self._abrir_etapa(etapa))
            self._texto(tile, info, 8, MUTED).pack(padx=5, pady=(3, 10))
            self.miniaturas[nombre] = img

        history_title = tk.Frame(body, bg=BG)
        history_title.pack(fill='x', padx=20, pady=(12, 5))
        self._texto(history_title, 'REGISTRO DE PRODUCTOS', 12, TEXT, True).pack(side='left')
        self.label_registro = self._texto(history_title, f'CSV: {DEFAULT_CSV.name}', 9, MUTED)
        self.label_registro.pack(side='right')
        hist = self._panel(body)
        hist.pack(fill='both', expand=False, padx=20, pady=(0, 12))
        cols = ('hora', 'producto', 'decision', 'buenas', 'malas', 'inciertas', 'motivo')
        self.tabla = ttk.Treeview(hist, columns=cols, show='headings', height=5,
                                  style='Nutreo.Treeview')
        headers = ['Hora', 'Producto', 'Resultado', 'Buenas', 'Malas', 'Inciertas', 'Motivo']
        for key, nombre in zip(cols, headers):
            self.tabla.heading(key, text=nombre)
            self.tabla.column(key, width=75 if key != 'motivo' else 350,
                              minwidth=55, stretch=(key == 'motivo'))
        self.tabla.column('producto', width=85)
        self.tabla.column('decision', width=110)
        self.tabla.tag_configure('pasa', foreground=GREEN)
        self.tabla.tag_configure('no_pasa', foreground=RED)
        self.tabla.pack(fill='both', expand=True, padx=8, pady=8)

        foot = tk.Frame(body, bg=BG, padx=20, pady=10)
        foot.pack(fill='x')
        self.texto_pie = self._texto(foot, 'Sin conexion. La inspeccion es experimental; validar con la banda real.',
                                    9, MUTED)
        self.texto_pie.pack(side='left')
        self._texto(foot, 'Sin OCR ni validacion del formato de la fecha',
                    9, MUTED).pack(side='right')

    def _elegir_video(self):
        path = filedialog.askopenfilename(
            title='Abrir video de prueba',
            filetypes=[('Videos', '*.mp4 *.avi *.mov *.mkv'), ('Todos los archivos', '*.*')],
        )
        if path:
            self.video.set(path)
            self.fuente.set('video')
            self.texto_pie.configure(text=f'Video seleccionado: {Path(path).name}')

    def _obtener_config(self) -> Configuracion:
        cam = int(self.indice.get())
        backend_camara = self.camara_backend.get()
        resolucion_camara = self.resolucion_camara.get()
        if backend_camara not in ('auto', 'msmf', 'dshow'):
            raise ValueError('Controlador invalido: auto, msmf o dshow')
        if resolucion_camara not in ('Automatica', '1280x720', '1920x1080'):
            raise ValueError('Resolucion de camara no admitida')
        fotos = int(self.fotos.get())
        min_buenas = int(self.min_buenas.get())
        zona_segura = float(self.zona_segura.get())
        confirmaciones = int(self.confirmaciones.get())
        intervalo = float(self.intervalo.get())
        conf = float(self.confianza.get())
        ausencia = float(self.ausencia.get())
        recorte_pct = float(self.recorte_borde.get())
        if cam < 0 or not 5 <= fotos <= 50 or not 5 <= min_buenas <= fotos or intervalo < 0 or not 0 < conf <= 1:
            raise ValueError('Fotos debe ser 5-50, minimo buenas entre 5 y fotos, camara >=0 y conf 0-1.')
        if not 0 <= zona_segura < 40 or not 1 <= confirmaciones <= 20:
            raise ValueError('Margen seguro entre 0 y 39%; confirmaciones de 1 a 20.')
        if not 100 <= ausencia <= 5000:
            raise ValueError('Salida sin YOLO: 100-5000 ms.')
        if not 0 <= recorte_pct <= 30:
            raise ValueError('Reducir alto: porcentaje entre 0 y 30.')
        video = None
        if self.fuente.get() == 'video':
            video = Path(self.video.get())
            if not video.is_file():
                raise ValueError('Selecciona un video de prueba existente.')
        return Configuracion(camara=cam, camara_backend=backend_camara,
                              resolucion_camara=resolucion_camara,
                              video=video, fotos=fotos,
                              min_fotos=min(3, fotos), min_buenas=min_buenas,
                              zona_segura_pct=zona_segura, confirmaciones_fecha=confirmaciones,
                              intervalo_ms=intervalo,
                              conf=conf, ausencia_ms=ausencia,
                              recorte_borde=recorte_pct/100.,
                              guardar_evidencia=bool(self.guardar_evidencia.get()))

    def iniciar(self):
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            cfg = self._obtener_config()
        except (ValueError, TypeError) as exc:
            messagebox.showerror('Configuracion', str(exc))
            return
        self._cola_fotos = queue.Queue(maxsize=2)
        self._cola_eventos = queue.Queue()
        self._stop = threading.Event()
        self._worker = Trabajador(cfg, self._stop, self._cola_fotos, self._cola_eventos)
        self.boton_inicio.configure(state='disabled')
        self.boton_stop.configure(state='normal')
        self._dibujar_estado('ESPERANDO PRODUCTO', 'Cargando modelo y conectando fuente de imagen...')
        self.texto_pie.configure(text='Conectando a YOLO y a la camara...')
        self.label_registro.configure(text=f'CSV: {cfg.registro.name}')
        self._worker.start()

    def detener(self):
        self._stop.set()
        self.boton_stop.configure(state='disabled')
        self.texto_pie.configure(text='Deteniendo captura y cerrando las inspecciones pendientes...')

    def cerrar(self):
        self._stop.set()
        # Esperar al finally del motor para conservar el CSV y liberar la camara.
        if self._worker is not None and self._worker.is_alive():
            if not self._cerrando:
                self._cerrando = True
                self.texto_pie.configure(text='Cerrando inspecciones y liberando camara...')
                self.boton_inicio.configure(state='disabled')
                self.boton_stop.configure(state='disabled')
            self.root.after(120, self.cerrar)
            return
        self.root.destroy()

    def _dibujar_estado(self, estado: str, motivo: str):
        palette = {'CAMARA EN ESPERA': (YELLOW, '#42351F'),
                   'CAMARA SIN SENAL': (RED, '#49262C'),
                   'ESPERANDO PRODUCTO': (BLUE, '#193247'),
                   'ESPERANDO FECHA COMPLETA': (BLUE, '#193247'),
                   'EVALUANDO PRODUCTO': (YELLOW, '#42351F'),
                   'PASA': (GREEN, '#163E35'),
                   'NO PASA': (RED, '#49262C')}
        color, fondo = palette.get(estado, (BLUE, PANEL2))
        self.banda_estado.configure(bg=fondo)
        self.label_estado.configure(text=estado, fg=color, bg=fondo,
            font=(self.FONT, 16 if estado == 'ESPERANDO FECHA COMPLETA' else 21,'bold'))
        self.motivo.configure(text=motivo)

    def _mostrar_bgr(self, widget, image_bgr, key: str, maxsize):
        if image_bgr is None or image_bgr.size == 0:
            return
        w, h = maxsize
        w = max(40, int(w)); h = max(40, int(h))
        ih, iw = image_bgr.shape[:2]
        factor = min(w / iw, h / ih)
        nw = max(1, int(iw * factor)); nh = max(1, int(ih * factor))
        thumb = cv2.resize(image_bgr, (nw, nh), interpolation=(cv2.INTER_AREA if factor < 1 else cv2.INTER_NEAREST))
        rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(image=Image.fromarray(rgb), master=self.root)
        self._images[key] = photo
        widget.configure(image=photo, text='')

    def _abrir_etapa(self, nombre):
        imagen = self._vistas_ultimo.get(nombre)
        if imagen is None:
            return
        detalles = {
            '01': 'Recorte detectado por YOLO en el fotograma actual. Es la imagen base que entra al inspector.',
            '02': 'Canal L de LAB: permite estudiar la luz. El sistema tambien analiza informacion de color.',
            '03': 'Suavizado gaussiano que estima cambios lentos de iluminacion y color del fondo.',
            '04': 'Diferencia de luminosidad local, solo ilustrativa. La tinta puede segmentarse por contraste cromatico.',
            '05': 'Mascara binaria de tinta producida por el inspector REAL de este recorte.',
            '06': 'Naranja = zonas sospechosas del inspector. Las LINEAS VERTICALES FINAS son guias del barrido de continuidad: delimitan franjas con poca tinta, NO caracteres obligatorios.',
        }
        numero = nombre[:2]
        ventana = tk.Toplevel(self.root)
        ventana.title(f'V.I.T.A. | Detalle: {nombre}')
        ventana.configure(bg=BG)
        ventana.geometry('960x520')
        ventana.minsize(540, 340)
        self._texto(ventana, nombre, 18, TEXT, True).pack(pady=(18, 9))
        explicacion = tk.Label(ventana, text=detalles.get(numero, ''),
                               bg=BG, fg=MUTED, justify='center', wraplength=880,
                               font=(self.FONT, 10))
        explicacion.pack(padx=16, pady=(0, 12))
        lienzo = tk.Label(ventana, bg='#040910')
        lienzo.pack(fill='both', expand=True, padx=16, pady=(0, 16))
        foto = imagen.copy()  # instantanea: no cambia mientras se examina
        def refrescar(_event=None):
            if not ventana.winfo_exists():
                return
            w = lienzo.winfo_width() - 20
            h = lienzo.winfo_height() - 20
            if w >= 60 and h >= 40:
                self._mostrar_bgr(lienzo, foto, f'detalle-{id(ventana)}', (w,h))
        ventana.bind('<Configure>', refrescar)
        ventana.after(100, refrescar)

    def _limpiar_etapas(self):
        self._vistas_ultimo = {}
        self._ultimo_render_etapas = None
        for key, tile in self.miniaturas.items():
            tile.configure(image='', text='Sin fecha')
            self._images.pop(key, None)

    def _renderizar(self, vista: VistaCuadro):
        self._ultima_vista = vista
        w = self.imagen_camara.winfo_width() - 18
        h = self.imagen_camara.winfo_height() - 18
        if w < 100 or h < 100:
            w, h = 700, 390
        self._mostrar_bgr(self.imagen_camara, vista.fotograma, 'camara', (w, h))
        self._dibujar_estado(vista.estado, vista.motivo)
        self.label_id.configure(text=('Producto: ' + str(vista.producto)) if vista.producto else 'Producto: --')
        self.barra.configure(maximum=vista.objetivo, value=min(vista.muestreos, vista.objetivo))
        self.label_avance.configure(text=(
            f'{vista.muestreos}/{vista.objetivo} capturas (limite maximo, no minimo) '
            f'({vista.validas} evaluables; minimo {vista.min_buenas} buenas)'))
        self.label_buenas.configure(text=f'{vista.buenas} BUENAS')
        self.label_malas.configure(text=f'{vista.malas} MALAS')
        self.label_dudas.configure(text=f'{vista.ambiguas + vista.desenfocadas} INCIERTAS')
        if vista.buenas + vista.malas == 0:
            balance = 'BALANCE: SIN VOTOS EVALUABLES'
            color_balance = YELLOW
        elif vista.buenas > vista.malas:
            fase = 'FINAL' if vista.estado in ('PASA','NO PASA') else 'PROVISIONAL'
            balance = (f'{fase}: {vista.buenas} buenas > {vista.malas} malas; '
                       f'minimo para PASA: {vista.min_buenas}')
            color_balance = GREEN if vista.estado == 'PASA' else BLUE
        elif vista.malas > vista.buenas:
            balance = f'BALANCE PROVISIONAL: {vista.malas} malas > {vista.buenas} buenas'
            color_balance = RED
        else:
            balance = f'BALANCE: EMPATE {vista.buenas} / {vista.malas}'
            color_balance = YELLOW
        if vista.estado in ('PASA', 'NO PASA'):
            balance = balance.replace('PROVISIONAL', 'FINAL')
        if vista.buenas < vista.min_buenas:
            faltan = vista.min_buenas - vista.buenas
            balance = (f'AUN NO APRUEBA: faltan {faltan} votos BUENA '
                       f'(minimo {vista.min_buenas})') if vista.estado not in ('PASA','NO PASA') else (
                       f'FINAL: NO PASA. {vista.buenas}/{vista.min_buenas} votos BUENA')
            color_balance = YELLOW if vista.estado not in ('PASA','NO PASA') else RED
        elif vista.estado == 'NO PASA':
            color_balance = RED
        self.label_balance.configure(text=balance, fg=color_balance)
        self.label_ultima.configure(text=vista.ultima_muestra,
                                    fg=(GREEN if vista.ultima_muestra == 'BUENA' else
                                        RED if vista.ultima_muestra == 'MALA' else
                                        YELLOW if vista.ultima_muestra == 'NO EVALUABLE' else BLUE))
        m = vista.metricas
        if m:
            s2 = 'SI' if vista.segunda_pasada else 'NO'
            conc = m.get('concordancia_mascaras', -1.)
            acord = f'  |  Acuerdo: {conc:.2f}' if conc >= 0 else ''
            texto = (
                f"CAMARA: contraste {m.get('camara_contraste_luz', 0):.1f} "
                f"| ruido {m.get('camara_ruido_relativo', 0):.3f}\n"
                f"TINTA: SNR {m.get('snr_contraste', 0):.1f} "
                f"| barrido cercano {m.get('indice_barrido', 0):.2f} "
                f"| halo cercano {m.get('indice_halo', 0):.2f}\n"
                f"ARRASTRE INTERNO: {m.get('indice_arrastre_interno', 0):.2f} "
                f"| crestas: {int(m.get('bandas_arrastre_interno', 0))} "
                f"| debilidad local: {m.get('indice_debilitamiento_local', 0):.2f}\n"
                f"BARRIDO DE TINTA: {m.get('indice_continuidad_tinta', 0):.2f} "
                f"| franjas: {int(m.get('franjas_continuidad_tinta', 0))} "
                f"| coincide: {int(m.get('coincidencias_continuidad', 0))}\n"
                f"AUDITORIA MASCARA 05: {m.get('indice_auditoria_mascara', 0):.2f} "
                f"| regiones: {int(m.get('regiones_auditoria_mascara', 0))}\n"
                f"ZONAS: {int(m.get('pixeles_sospechosos', 0))} px "
                f"| bandas externas ignoradas {int(m.get('bandas_externas_ignoradas', 0))} "
                f"| radio {m.get('radio_busqueda_tinta_px', 0):.0f} px\n"
                f"Segunda pasada: {s2}{acord} | {vista.tiempo_ms:.0f} ms/fotograma"
            )
        else:
            texto = 'Camara: -- | Tinta: -- | Zonas: --\nSegunda pasada: --'
        self.label_metricas.configure(text=texto)
        self.alerta.configure(text=vista.aviso)
        if vista.filtro_paneles:
            # NO convertir a PhotoImage seis veces en cada fotograma: solo
            # cuando el tracker acepta una nueva muestra del producto.
            nueva = (vista.etapas_version is None or
                     vista.etapas_version != self._ultimo_render_etapas)
            if nueva:
                self._vistas_ultimo = dict(vista.filtro_paneles)
                for key, im in vista.filtro_paneles.items():
                    tile = self.miniaturas.get(key)
                    if tile is not None:
                        width = tile.winfo_width() - 12
                        height = min(105, max(64, tile.winfo_height() - 8))
                        if width < 50: width = 174
                        self._mostrar_bgr(tile, im, key, (width, height))
                self._ultimo_render_etapas = vista.etapas_version
        elif vista.estado in ('ESPERANDO PRODUCTO', 'ESPERANDO FECHA COMPLETA'):
            if self._vistas_ultimo:
                self._limpiar_etapas()

    def _agregar_evento(self, ev: EventoFinal):
        hora = datetime.now().strftime('%H:%M:%S')
        estado = 'PASA' if ev.estado == 'BIEN' else 'NO PASA'
        tag = 'pasa' if ev.estado == 'BIEN' else 'no_pasa'
        self.tabla.insert('', 0, values=(hora, ev.id, estado, ev.buenas,
                          ev.malas, ev.ambiguas + ev.desenfocadas, ev.motivo), tags=(tag,))
        self._hist_count += 1
        if self._hist_count > 100:
            items = self.tabla.get_children()
            if items:
                self.tabla.delete(items[-1])
        self.texto_pie.configure(text=f'Producto {ev.id} -> {estado}. Registrado en CSV.')

    def _actualizar(self):
        # Actualizar siempre en el hilo principal de Tk; el trabajo pesado esta
        # en la hebra. Eventos no se descartan aunque el video vaya mas rapido.
        try:
            while True:
                tipo, dato = self._cola_eventos.get_nowait()
                if tipo == 'resultado':
                    self._agregar_evento(dato)
                elif tipo == 'info':
                    self.texto_pie.configure(text=dato)
                elif tipo == 'error':
                    self.texto_pie.configure(text=f'ERROR: {dato}')
                    messagebox.showerror('V.I.T.A. - Error', dato)
                elif tipo == 'detenido':
                    self.boton_inicio.configure(state='normal')
                    self.boton_stop.configure(state='disabled')
        except queue.Empty:
            pass
        ultimo = None
        try:
            while True:
                ultimo = self._cola_fotos.get_nowait()
        except queue.Empty:
            pass
        if ultimo is not None:
            self._renderizar(ultimo)
        self.root.after(45, self._actualizar)


def main():
    parser = argparse.ArgumentParser(description='V.I.T.A.: centro tecnico de inspeccion')
    parser.add_argument('--camara', type=int, default=0)
    args = parser.parse_args()
    root = tk.Tk()
    gui = NutreoGUI(root)
    gui.indice.set(str(args.camara))
    root.mainloop()


if __name__ == '__main__':
    main()

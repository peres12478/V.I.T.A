"""Nutreo: YOLO + inspeccion fisica de tinta + mayoria temporal por producto.

CAMARA / VIDEO -> MODO BANDA: fecha individual = BIEN/MAL/REVISAR, pero la
DECISION FINAL POR PRODUCTO solo puede ser BIEN o MAL.

Ejemplos:
  python iniciar_calidad.py --camara 0 --fotos 7
  python iniciar_calidad.py --video ensayo.mp4 --sin-ventana --registro ensayo.csv
  python iniciar_calidad.py --imagen imagenes_prueba/1995.jpg --roi 360 447 523 1020

La foto aislada es SOLO diagnostico, no una decision mayoritaria.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from calidad_impresion import InspectorCalidad, dibujar_resultado
from inspeccion_robusta import InspectorCalidadRobusto
from seguimiento_banda import Observacion, SeguimientoBanda, EventoFinal

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def cargar_yolo(pesos):
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError('Falta ultralytics. Ejecuta: python -m pip install -r requirements.txt') from exc
    if not Path(pesos).is_file():
        raise RuntimeError(f'No existe el archivo de pesos de YOLO: {pesos}')
    return YOLO(str(pesos))


def caja_recorte(x1, y1, x2, y2, shape, margen=.02, recorte_borde=.12):
    """ROI interior para inspeccionar la FECHA y evitar bordes del empaque.

    Antes la deteccion se expandia 6% en ambos ejes e incorporaba etiquetas,
    bordes y franjas vecinas del codigo de barras. Ahora:
    - En el eje LARGO se conserva una expansion pequena (2%) para no cortar
      el inicio o fin de la fecha.
    - En el eje CORTO se quita 12% por cada lado por defecto. Para fechas
      horizontales equivale a reducir altura; para verticales, anchura.
    - El area realmente procesada coincide con el recuadro mostrado.

    No usa OCR ni numeros de caracteres. El ajuste es configurable; si el
    detector ya marca un rectangulo muy ajustado, usar recorte_borde=0.
    """
    if not 0. <= recorte_borde <= .30:
        raise ValueError('recorte_borde debe estar entre 0 y 0.30')
    if not 0. <= margen <= .15:
        raise ValueError('margen debe estar entre 0 y 0.15')
    alto, ancho = shape[:2]
    x1, x2 = sorted((float(x1), float(x2)))
    y1, y2 = sorted((float(y1), float(y2)))
    base_w = max(0., x2-x1)
    base_h = max(0., y2-y1)
    if base_w < 2 or base_h < 2:
        return (0, 0, 0, 0)
    eje_corto = min(base_w, base_h)
    # Proteger recortes pequenos: nunca acortarlos por debajo de 25 px.
    fraccion = min(recorte_borde, max(0., (eje_corto-25.)/(2.*eje_corto)))
    corte = eje_corto * fraccion
    if base_w >= base_h:
        ax, bx = x1-base_w*margen, x2+base_w*margen
        ay, by = y1+corte, y2-corte
    else:
        ax, bx = x1+corte, x2-corte
        ay, by = y1-base_h*margen, y2+base_h*margen
    ax, ay = max(0, int(round(ax))), max(0, int(round(ay)))
    bx, by = min(ancho, int(round(bx))), min(alto, int(round(by)))
    if bx <= ax or by <= ay:
        return (0, 0, 0, 0)
    return ax, ay, bx, by


def detectar_cajas(frame, modelo, conf, roi=None, recorte_borde=.12):
    """YOLO primero. No evalua tinta; devuelve solo zonas de la fecha."""
    if roi is not None:
        boxes = [roi]
    else:
        pred = modelo.predict(frame, conf=conf, verbose=False)[0]
        boxes = [tuple(map(int, b.xyxy[0].cpu().numpy())) for b in pred.boxes]
    cajas = [caja_recorte(*box, frame.shape, recorte_borde=recorte_borde)
             for box in boxes]
    return [c for c in cajas if c[2] > c[0] and c[3] > c[1]]


def inspeccionar(frame, modelo, inspector, conf, roi=None, mostrar_mascara=False,
                 dibujar=True, recorte_borde=.12):
    """Para pruebas y modo foto, se conserva la API original (3 resultados).

    Cuando dibujar=False, la pantalla final la produce seguimiento_banda.
    Se inspeccionan regiones con coordenadas de ESTE fotograma; no quedan
    guardadas para aplicar a fotogramas posteriores.
    """
    annotated = frame.copy()
    cajas = detectar_cajas(frame, modelo, conf, roi, recorte_borde)
    resultados = []
    muestra = None
    for x1, y1, x2, y2 in cajas:
        crop = frame[y1:y2, x1:x2]
        r = inspector.analizar(crop)
        resultados.append((r, (x1,y1,x2,y2)))
        if dibujar:
            dibujar_resultado(annotated, (x1,y1,x2,y2), r)
        if mostrar_mascara and r.mascara_tinta is not None:
            a = cv2.cvtColor(r.mascara_tinta, cv2.COLOR_GRAY2BGR)
            if r.mascara_sospechosa is not None:
                a[r.mascara_sospechosa > 0] = (0, 165, 255)
            muestra = a
    if dibujar:
        if not resultados:
            texto = 'SIN FECHA DETECTADA'
            color = (0, 180, 255)
        else:
            estados = [r.estado for r, _ in resultados]
            estado = 'MAL' if 'MAL' in estados else 'REVISAR' if 'REVISAR' in estados else 'BIEN'
            texto = f'CALIDAD: {estado} | {len(resultados)} region(es)'
            color = {'MAL': (10,10,240), 'REVISAR': (0,175,255), 'BIEN': (10,170,55)}[estado]
        cv2.rectangle(annotated, (0,0), (min(annotated.shape[1],780),42), (10,14,22), -1)
        cv2.putText(annotated, texto, (12,29), cv2.FONT_HERSHEY_SIMPLEX, .75, color, 2, cv2.LINE_AA)
        if resultados:
            peor = next((r for r,_ in resultados if r.estado == 'MAL'),
                        next((r for r,_ in resultados if r.estado == 'REVISAR'), resultados[0][0]))
            cv2.rectangle(annotated, (0,42), (min(annotated.shape[1],990),75), (10,14,22), -1)
            cv2.putText(annotated, peor.motivo[:100], (12,65),
                        cv2.FONT_HERSHEY_SIMPLEX,.48,(235,235,235),1,cv2.LINE_AA)
    return annotated, resultados, muestra


class RegistroEventos:
    """Una fila por producto; no se guardan fotogramas salvo solicitud."""
    FIELDS = ('fecha_hora', 'producto_id', 'decision', 'motivo', 'buenas', 'malas',
              'ambiguas', 'desenfocadas', 'fotos_totales', 'votos_validos',
              'segundo_video_o_camara', 'fotograma', 'finalizacion')

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists() and self.path.stat().st_size > 0
        self.file = self.path.open('a', newline='', encoding='utf-8-sig' if not existed else 'utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELDS)
        if not existed:
            self.writer.writeheader()
            self.file.flush()

    def guardar(self, ev: EventoFinal):
        self.writer.writerow({
            'fecha_hora': datetime.now().isoformat(timespec='seconds'),
            'producto_id': ev.id,
            'decision': ev.estado,
            'motivo': ev.motivo,
            'buenas': ev.buenas,
            'malas': ev.malas,
            'ambiguas': ev.ambiguas,
            'desenfocadas': ev.desenfocadas,
            'fotos_totales': ev.total,
            'votos_validos': ev.validas,
            'segundo_video_o_camara': f'{ev.instante:.3f}',
            'fotograma': ev.cuadro,
            'finalizacion': ev.cierre,
        })
        self.file.flush()

    def close(self):
        self.file.close()


def nitidez_recorte(crop) -> float:
    if crop.size == 0:
        return 0.
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dibujar_banda(frame, estado, tracker: SeguimientoBanda, resultados, t,
                  tiempo_proceso_ms: float):
    """Dibujo persistente de pista aunque YOLO falle durante un breve intervalo."""
    img=frame.copy()
    altura,ancho=img.shape[:2]
    if tracker.control_visibilidad:
        m=tracker.margen_seguro
        cv2.rectangle(img,(int(ancho*m),int(altura*m)),
                      (int(ancho*(1-m)),int(altura*(1-m))),(195,115,60),1)
    recientes=list(tracker.pistas.values())
    for p in recientes:
        x1,y1,x2,y2=p.caja_mostrada
        if p.estado_final is None:
            txt=(f'ID {p.id} | ESPERANDO FECHA COMPLETA' if tracker.control_visibilidad and p.muestreos == 0 and not p.visibilidad.habilitada else f'ID {p.id} | ANALIZANDO {p.muestreos}/{tracker.objetivo} | B{p.buenas} M{p.malas} I{p.ambiguas+p.desenfocadas}')
            color=(0,190,245)
        else:
            txt=f'ID {p.id} | {p.estado_final} (BLOQUEADO HASTA SALIR)'
            color=(35,190,65) if p.estado_final=='BIEN' else (30,30,245)
        if p.ultimo_cuadro != estado_cuadro(estado,p):
            # En la zona de seguimiento, no hay nueva caja YOLO en este frame.
            txt+=' | YOLO INTERMITENTE'
        cv2.rectangle(img,(x1,y1),(x2,y2),color,2)
        bx=max(0,x1)
        by=max(0,y1-25)
        cv2.rectangle(img,(bx,by),(min(ancho-1,bx+min(ancho,len(txt)*9+12)),max(1,y1)),
                      (15,18,26),-1)
        cv2.putText(img,txt[:85],(bx+3,max(16,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,
                    .46,color,1,cv2.LINE_AA)
    finalizados=[p for p in recientes if p.estado_final is not None]
    actual=finalizados[0] if finalizados else None
    if actual is not None:
        texto=f'PRODUCTO {actual.id}: {actual.estado_final}'
        color=(35,190,65) if actual.estado_final=='BIEN' else (25,30,245)
    elif recientes:
        p=max(recientes,key=lambda p:p.validas)
        texto=(f'PRODUCTO {p.id}: ESPERANDO FECHA COMPLETA' if tracker.control_visibilidad and p.muestreos == 0 and not p.visibilidad.habilitada else f'PRODUCTO {p.id}: ANALIZANDO {p.muestreos}/{tracker.objetivo} (B{p.buenas} vs M{p.malas}; minimo {tracker.min_buenas} buenas)')
        color=(0,190,245)
    elif tracker.ultimo_evento is not None and t-tracker.ultimo_evento.instante<1.8:
        ev=tracker.ultimo_evento
        texto=f'ULTIMO PRODUCTO {ev.id}: {ev.estado}'
        color=(35,190,65) if ev.estado=='BIEN' else (25,30,245)
    else:
        texto='ESPERANDO PRODUCTO EN LA BANDA'
        color=(190,190,190)
    cv2.rectangle(img,(0,0),(ancho,min(55,altura)),(10,14,22),-1)
    cv2.putText(img,texto[:65],(12,min(37,altura-7)),cv2.FONT_HERSHEY_SIMPLEX,
                min(.76,ancho/max(500,len(texto)*16)),color,2,cv2.LINE_AA)
    if altura>155 and any(r.motivo.startswith('CAPTURA NO EVALUABLE') for r,_ in resultados):
        cv2.rectangle(img,(0,altura-59),(min(ancho,720),altura-29),(10,14,22),-1)
        cv2.putText(img,'CAMARA: toma no evaluable; no suma voto. Mejorar enfoque/luz.',
                    (10,altura-37),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,190,245),1,cv2.LINE_AA)
    if altura>95:
        cv2.rectangle(img,(0,altura-29),(min(ancho,610),altura),(10,14,22),-1)
        cv2.putText(img,f'Inspeccion {tiempo_proceso_ms:.0f} ms/frame | Q salir | S foto | R reiniciar ID',
                    (10,altura-9),cv2.FONT_HERSHEY_SIMPLEX,.43,(225,225,225),1,cv2.LINE_AA)
    return img


def estado_cuadro(estado, pista):
    """Consulta si la pista fue observada en ESTE cuadro (no un cuadro anterior)."""
    return pista.ultimo_cuadro if any(id_==pista.id for id_,_ in estado.asignaciones) else -1


def main():
    parser = argparse.ArgumentParser(description='Nutreo | Inspeccion temporal de tinta con votacion por producto')
    fuente = parser.add_mutually_exclusive_group()
    fuente.add_argument('--imagen',type=Path,help='Solo diagnostico de foto (NO votacion temporal)')
    fuente.add_argument('--video',type=Path,help='Analizar video de la banda')
    fuente.add_argument('--camara',type=int,default=0,help='Indice de camara (por defecto 0)')
    parser.add_argument('--pesos',type=Path,default=ROOT/'best.pt')
    parser.add_argument('--conf',type=float,default=.45,help='Confianza minima YOLO')
    parser.add_argument('--recorte-borde',type=float,default=12.,
                        help='Acortar cada borde del eje corto del recuadro YOLO, en %% (0-30; defecto 15)')
    parser.add_argument('--roi',type=int,nargs=4,metavar=('X1','Y1','X2','Y2'),help='ROI manual; SOLO diagnostico recomendable')
    parser.add_argument('--polaridad',choices=['automatica','oscura','clara','color'],default='automatica')
    parser.add_argument('--modelo-calidad',type=Path,help='Clasificador entrenado localmente (opcional)')
    parser.add_argument('--filtros',choices=['robusto','original'],default='robusto',
                        help='robusto: verifica calidad de camara y consistencia; original: algoritmo anterior')
    parser.add_argument('--salida',type=Path,help='Imagen resultante para --imagen')
    parser.add_argument('--mostrar-mascara',action='store_true')
    parser.add_argument('--sin-ventana',action='store_true',help='Ejecuta sin cv2.imshow (foto o video)')
    parser.add_argument('--salida-video',type=Path,help='Guarda video anotado (.avi o .mp4), opcional')
    # Parametros temporales; cada fotograma llama al inspector UNA VEZ.
    parser.add_argument('--fotos',type=int,default=7,help='Capturas TOTALES por producto, incluyendo inciertas (7)')
    parser.add_argument('--min-buenas',type=int,default=5,help='Minimo de votos BUENA para PASA (5), ademas de superar MALAS')
    parser.add_argument('--zona-segura-pct',type=float,default=8.,help='Margen de seguridad de los cuatro bordes (8%%)')
    parser.add_argument('--confirmaciones-fecha',type=int,default=3,help='Detecciones estables antes de evaluar (3)')
    parser.add_argument('--min-fotos',type=int,default=3,help='Solo advertencia de poca evidencia; NO altera la mayoria (3)')
    parser.add_argument('--intervalo-ms',type=float,default=75,help='Separacion minima entre muestras del MISMO producto (75 ms)')
    parser.add_argument('--ausencia-ms',type=float,default=650,help='Hueco minimo sin YOLO para liberar el ID (600 ms)')
    parser.add_argument('--max-sin-ver',type=int,default=3,help='Fotogramas vacios seguidos requeridos, ademas del tiempo (3)')
    parser.add_argument('--max-muestras',type=int,default=None,help='Compatibilidad anterior; limite real es --fotos')
    parser.add_argument('--max-dudosas',type=int,default=3,help='Compatibilidad anterior; inciertas ahora tienen misma cadencia que otras')
    parser.add_argument('--intervalo-dudosa-ms',type=float,default=450,
                        help='Compatibilidad anterior; se aplica --intervalo-ms a todas las capturas')
    parser.add_argument('--multiples-productos',action='store_true',
                        help='Desactiva bloqueo de un solo producto; requiere separacion y tracking fiable')
    parser.add_argument('--min-fraccion',type=float,default=.50,help='Solo genera aviso de baja evidencia; NO altera la mayoria (0.50)')
    parser.add_argument('--min-nitidez',type=float,default=0,
                        help='Umbral varianza laplaciana para ignorar desenfoque; 0 desactiva hasta calibrar')
    parser.add_argument('--registro',type=Path,default=Path.cwd()/'registros_banda.csv',
                        help='CSV que guarda UNA fila por producto')
    parser.add_argument('--guardar-muestras',action='store_true',
                        help='Guarda todos los recortes muestreados para auditoria (ocupa disco)')
    args = parser.parse_args()
    if not 0 <= args.recorte_borde <= 30:
        parser.error('--recorte-borde debe estar entre 0 y 30')
    if not 5 <= args.fotos <= 50 or not 5 <= args.min_buenas <= args.fotos:
        parser.error('--fotos debe ser >= 5 y --min-buenas no mayor que --fotos')
    if not 0 <= args.zona_segura_pct < 40 or args.confirmaciones_fecha < 1:
        parser.error('Zona segura o confirmaciones invalidas')
    clase_inspector = InspectorCalidadRobusto if args.filtros == 'robusto' else InspectorCalidad
    inspector = clase_inspector(args.polaridad, str(args.modelo_calidad) if args.modelo_calidad else None)
    modelo = None if args.roi else cargar_yolo(args.pesos)

    if args.imagen is not None:
        frame = cv2.imread(str(args.imagen))
        if frame is None:
            raise SystemExit(f'No se pudo abrir: {args.imagen}')
        img, res, mask = inspeccionar(frame, modelo, inspector, args.conf, args.roi,args.mostrar_mascara,
                                        recorte_borde=args.recorte_borde/100.)
        print('DIAGNOSTICO DE FOTO AISLADA; para votacion use --camara o --video:')
        for r, box in res:
            print(f'ROI {box}: {r.estado} | {r.motivo} | {r.metricas}')
        if not res:
            print('SIN FECHA DETECTADA')
        if args.salida:
            args.salida.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.salida),img)
            print('Imagen guardada en:',args.salida)
        if not args.sin_ventana:
            cv2.imshow('Nutreo | Diagnostico de una foto',img)
            if mask is not None: cv2.imshow('Tinta segmentada',mask)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    if args.roi is not None:
        print('ADVERTENCIA: --roi fija no distingue productos sucesivos. Usa YOLO o reinicia con R.')
    seguidor = SeguimientoBanda(
        objetivo=args.fotos, min_validas=min(args.min_fotos,args.fotos),
        intervalo_s=args.intervalo_ms/1000., max_ausencia_s=args.ausencia_ms/1000.,
        max_sin_ver=args.max_sin_ver, proporcion_minima=args.min_fraccion,
        max_muestras=args.max_muestras, min_nitidez=args.min_nitidez,
        bloqueo_unico=not args.multiples_productos,
        max_dudosas=args.max_dudosas, intervalo_dudosa_s=args.intervalo_dudosa_ms/1000.,
        min_buenas=args.min_buenas, control_visibilidad=True,
        margen_seguro=args.zona_segura_pct/100., confirmaciones=args.confirmaciones_fecha,
    )
    cap = cv2.VideoCapture(str(args.video) if args.video else args.camara,
                           cv2.CAP_DSHOW if sys.platform=='win32' and args.video is None else cv2.CAP_ANY)
    if not cap.isOpened() and args.video is None and sys.platform=='win32':
        cap.release()
        cap = cv2.VideoCapture(args.camara,cv2.CAP_ANY)
    if not cap.isOpened():
        raise SystemExit('No se pudo abrir camara/video. Cierra otras aplicaciones que la utilicen.')
    cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps < 1:
        fps = 30.
    registro = RegistroEventos(args.registro)
    writer = None
    if args.salida_video:
        dest = args.salida_video
        dest.parent.mkdir(parents=True,exist_ok=True)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w < 1 or h < 1:
            print('ADVERTENCIA: el video no informa dimensiones, se omitira grabacion anotada')
        else:
            codec = 'mp4v' if dest.suffix.lower() == '.mp4' else 'MJPG'
            writer = cv2.VideoWriter(str(dest),cv2.VideoWriter_fourcc(*codec),fps,(w,h))
            if not writer.isOpened():
                raise RuntimeError('No se pudo abrir el archivo de salida de video')
    print(f'BANDA ACTIVA: {args.fotos} fotos, minimo {args.min_buenas} buenas para PASA y buenas > malas.')
    print(f'ZONA SEGURA: margen {args.zona_segura_pct:g}%%; {args.confirmaciones_fecha} detecciones estables antes de votar.')
    print(f'Filtros: {args.filtros} | Vista normal en COLOR. La mascara es opcional con --mostrar-mascara.')
    print(f'ROI FECHA: eje corto -{args.recorte_borde:g}%% por lado; area reducida antes del analisis.')
    print(f'BLOQUEO: {args.max_sin_ver} cuadros ausentes + {args.ausencia_ms:g} ms; modo unico: {not args.multiples_productos}.')
    print('VOTACION: completar fotos y reunir >=5 buenas y buenas > malas; inciertas no votan.')
    print('Pantalla: ANALIZANDO hasta emitir decision binaria. Q salir; S captura; R cerrar/reiniciar pistas.')
    print('CSV:',registro.path)
    cuadro = 0
    ultimo_t = 0.
    def procesar_eventos(eventos):
        for ev in eventos:
            registro.guardar(ev)
            print(f'PRODUCTO {ev.id} => {ev.estado} | {ev.buenas} buenas, '
                  f'{ev.malas} malas, {ev.ambiguas} ambiguas, {ev.desenfocadas} borrosas, '
                  f'{ev.dudosas_ignoradas} dudosas repetidas ignoradas '
                  f'| {ev.motivo} | {ev.cierre}',flush=True)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cuadro += 1
            # Videos leidos mas rapido que tiempo real requieren tiempo por fotograma,
            # no time.perf_counter() (de otro modo no se separan las muestras).
            t = (cuadro - 1) / fps if args.video is not None else time.monotonic()
            ultimo_t = t
            tiempo_inicio = time.perf_counter()
            cajas = detectar_cajas(frame,modelo,args.conf,args.roi,
                                    recorte_borde=args.recorte_borde/100.)
            observaciones = [Observacion(c, 'REVISAR', 'Aguardando fecha completa') for c in cajas]
            evaluados = {}
            mascara = None
            def evaluar(p, ob, indice):
                x1,y1,x2,y2 = ob.caja
                crop = frame[y1:y2,x1:x2]
                resultado = inspector.analizar(crop)
                nitidez = nitidez_recorte(crop) if args.min_nitidez > 0 else None
                evaluados[indice] = resultado
                return Observacion(ob.caja, resultado.estado, resultado.motivo, nitidez)
            estado = seguidor.actualizar(observaciones,t,cuadro,
                                         forma_frame=frame.shape,evaluar=evaluar)
            res = [(evaluados[i], cajas[i]) for i in sorted(evaluados)]
            if args.mostrar_mascara and res:
                resultado = res[-1][0]
                if resultado.mascara_tinta is not None:
                    mascara = cv2.cvtColor(resultado.mascara_tinta, cv2.COLOR_GRAY2BGR)
                    if resultado.mascara_sospechosa is not None:
                        mascara[resultado.mascara_sospechosa > 0] = (0,165,255)
            procesar_eventos(estado.eventos)
            if args.guardar_muestras:
                for id_,n,origen,caja in estado.muestras:
                    x1,y1,x2,y2 = caja
                    folder = Path.cwd()/'muestras_banda'/f'producto_{id_:05d}'
                    folder.mkdir(parents=True,exist_ok=True)
                    cv2.imwrite(str(folder/f'{n:02d}_{origen}.png'),frame[y1:y2,x1:x2])
            dt_ms = (time.perf_counter()-tiempo_inicio)*1000.
            img = dibujar_banda(frame,estado,seguidor,res,t,dt_ms)
            if writer is not None:
                writer.write(img)
            if not args.sin_ventana:
                cv2.imshow('Nutreo | Control de calidad BANDA',img)
                if args.mostrar_mascara and mascara is not None:
                    cv2.imshow('Tinta segmentada',mascara)
                tecla = cv2.waitKey(1) & 0xff
                if tecla in (ord('q'),27):
                    break
                if tecla == ord('s'):
                    path = Path.cwd()/f'captura_banda_{time.strftime("%Y%m%d_%H%M%S")}.jpg'
                    cv2.imwrite(str(path),img)
                    print('Captura guardada:',path)
                if tecla == ord('r'):
                    procesar_eventos(seguidor.cerrar(t,cuadro))
                    print('Pistas reiniciadas; lista para nuevo producto.')
    finally:
        procesar_eventos(seguidor.cerrar(ultimo_t,cuadro))
        registro.close()
        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

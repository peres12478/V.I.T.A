"""Revisa posibles fuentes (incluidas camaras virtuales de celular) sin abrir YOLO.

Uso: python diagnosticar_camaras.py --backend msmf --max-indice 5
"""
from __future__ import annotations
import argparse
import sys
import time
import cv2
from captura_segura import backends_camara, GuardiaCaptura


def probar_camara(indice: int, backend: int, segundos: float, resolucion: str):
    cap = cv2.VideoCapture(indice, backend)
    if not cap.isOpened():
        cap.release()
        return None
    if resolucion != 'Automatica':
        ancho,alto=(int(x) for x in resolucion.split('x'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    guardia = GuardiaCaptura(repeticiones_congelado=45, segundos_congelado=2.5)
    inicio = time.monotonic()
    frames = 0
    utiles = 0
    repetidos = 0
    invalidos = 0
    max_pausa_s = 0.
    ultimo_unico = inicio
    motivos = {}
    forma = None
    try:
        while time.monotonic()-inicio < segundos:
            ok,frame=cap.read()
            if not ok or frame is None:
                time.sleep(.02)
                continue
            frames += 1
            forma=frame.shape
            estado=guardia.revisar(frame)
            if estado.util and estado.repeticiones == 0:
                utiles += 1
                ultimo_unico = time.monotonic()
            elif estado.util:
                repetidos += 1
                max_pausa_s = max(max_pausa_s, time.monotonic()-ultimo_unico)
                time.sleep(.02)
            else:
                invalidos += 1
                motivos[estado.motivo] = motivos.get(estado.motivo,0)+1
                max_pausa_s = max(max_pausa_s, time.monotonic()-ultimo_unico)
                time.sleep(.02)
        duracion = max(.01, time.monotonic()-inicio)
        return {'indice':indice, 'resolucion':(f'{forma[1]}x{forma[0]}' if forma else 'sin frames'),
                'lecturas':frames, 'nuevos':utiles, 'repetidos':repetidos, 'invalidos':invalidos,
                'fps_lectura':round(frames/duracion,1), 'fps_nuevos':round(utiles/duracion,1),
                'pausa_maxima_s':round(max_pausa_s,2), 'motivos':motivos}
    finally:
        cap.release()


def main():
    parser=argparse.ArgumentParser(description='Diagnostico de camaras Nutreo sin YOLO')
    parser.add_argument('--backend',choices=('auto','msmf','dshow'),default='auto')
    parser.add_argument('--max-indice',type=int,default=5)
    parser.add_argument('--indice',type=int,default=None,help='Probar una sola camara, ej. 1')
    parser.add_argument('--segundos',type=float,default=1.5)
    parser.add_argument('--resolucion',choices=('Automatica','1280x720','1920x1080'),default='Automatica')
    args=parser.parse_args()
    if args.max_indice<1 or not 0.1<=args.segundos<=30:
        parser.error('max-indice >=1 y 0.1 <= segundos <= 30')
    indices = [args.indice] if args.indice is not None else range(args.max_indice)
    for indice in indices:
        for nombre,backend in backends_camara(sys.platform,args.backend):
            info=probar_camara(indice,backend,args.segundos,args.resolucion)
            if info is not None:
                print(f'Camara {indice} ({nombre}): {info}',flush=True)
                break
    print('Diagnostico: fps_nuevos es la tasa REAL de imagenes distintas. Mueve el celular/empaque durante la prueba.',flush=True)
    print('Si hay muchos repetidos: baja a 1280x720 o prueba --backend msmf / dshow; comprueba Wi-Fi o USB.',flush=True)

if __name__=='__main__':
    main()

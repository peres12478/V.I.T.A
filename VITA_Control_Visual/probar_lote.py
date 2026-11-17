"""Evaluacion de fotos SIN formato de fecha; no etiqueta automaticamente datos.

python probar_lote.py --carpeta imagenes_prueba --salida resultados_lote
"""
from pathlib import Path
import argparse
import csv
import cv2
from iniciar_calidad import cargar_yolo,inspeccionar,ROOT
from calidad_impresion import InspectorCalidad
from inspeccion_robusta import InspectorCalidadRobusto


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--carpeta',type=Path,default=ROOT/'imagenes_prueba')
    p.add_argument('--salida',type=Path,default=ROOT/'resultados_lote')
    p.add_argument('--pesos',type=Path,default=ROOT/'best.pt')
    p.add_argument('--conf',type=float,default=.45)
    p.add_argument('--filtros',choices=['robusto','original'],default='robusto')
    a=p.parse_args()
    detector=cargar_yolo(a.pesos)
    inspector=(InspectorCalidadRobusto() if a.filtros=='robusto' else InspectorCalidad())
    a.salida.mkdir(exist_ok=True,parents=True)
    registros=[]
    fotos=sorted(p for p in a.carpeta.rglob('*') if p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp'))
    for i,p in enumerate(fotos,1):
        im=cv2.imread(str(p))
        if im is None:continue
        overlay,results,mask=inspeccionar(im,detector,inspector,a.conf)
        cv2.imwrite(str(a.salida/(p.stem+'_analisis.jpg')),overlay)
        if not results:
            registros.append({'foto':p.name,'estado':'SIN_FECHA','motivo':'YOLO no localizo fecha'})
            print(f'{i}/{len(fotos)} {p.name}: SIN_FECHA')
            continue
        for n,(r,(x1,y1,x2,y2)) in enumerate(results):
            registros.append({'foto':p.name,'estado':r.estado,'motivo':r.motivo,'roi':f'{x1},{y1},{x2},{y2}',**r.metricas})
            print(f'{i}/{len(fotos)} {p.name}, roi {n}: {r.estado} ({r.motivo})')
    if registros:
        cols=list(dict.fromkeys(k for row in registros for k in row))
        with open(a.salida/'reporte.csv','w',encoding='utf-8-sig',newline='') as fp:
            writer=csv.DictWriter(fp,fieldnames=cols)
            writer.writeheader();writer.writerows(registros)
    print('Resultados:',a.salida)
    print('IMPORTANTE: los estados no son etiquetas humanas de entrenamiento.')

if __name__=='__main__':main()

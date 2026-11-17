"""Pruebas de recortes de fecha SIN YOLO ni camara.

Solo acepta regiones YA recortadas a la fecha. NO ejecutar sobre fotografias
completas de empaques, pues los codigos de barras/textos ajenos sesgarian el
inspector. Las muestras incluidas no son una evaluacion de precision industrial.
"""
from pathlib import Path
import argparse
import csv
import cv2
from inspeccion_robusta import InspectorCalidadRobusto
from visualizador_filtros import crear_vistas_filtros

BASE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description='Verificar inspeccion sobre recortes de fechas')
    parser.add_argument('--carpeta',type=Path,default=BASE/'pruebas'/'muestras_calibracion',
                        help='Carpeta con RECORTES DE FECHAS (no fotos completas)')
    parser.add_argument('--salida',type=Path,default=BASE/'salida_calibracion',
                        help='Carpeta donde guardar mascaras, alertas y CSV')
    args=parser.parse_args()
    carpeta=args.carpeta.resolve();salida=args.salida.resolve()
    if not carpeta.is_dir():parser.error(f'No existe: {carpeta}')
    salida.mkdir(parents=True,exist_ok=True)
    inspector=InspectorCalidadRobusto()
    resultados=[]
    for img_path in sorted(carpeta.iterdir()):
        if img_path.suffix.lower() not in {'.png','.jpg','.jpeg','.bmp','.tiff'}:
            continue
        im=cv2.imread(str(img_path))
        if im is None:
            print('NO SE PUDO LEER',img_path)
            continue
        r=inspector.analizar(im)
        datos={'imagen':img_path.name,'estado':r.estado,'motivo':r.motivo,
               'indice_arrastre_interno':round(r.metricas.get('indice_arrastre_interno',0.),3),
               'longitud_relativa':round(r.metricas.get('longitud_arrastre_interno',0.),3),
               'superposicion_relativa':round(r.metricas.get('superposicion_arrastre_interno',0.),3),
               'crestas':int(r.metricas.get('bandas_arrastre_interno',0)),
               'pixeles_sospechosos':int(r.metricas.get('pixeles_sospechosos',0)),
               'segunda_pasada':int(r.metricas.get('segunda_pasada',0)),
               'captura_no_evaluable':int(r.metricas.get('camara_captura_no_evaluable',0))}
        resultados.append(datos)
        vistas=crear_vistas_filtros(im,r)
        pref=salida/img_path.stem
        cv2.imwrite(str(pref)+'_05_tinta.png',vistas['05  Tinta segmentada (real)'])
        cv2.imwrite(str(pref)+'_06_sospechas.jpg',vistas['06  Zonas sospechosas (real)'])
        print(f"{img_path.name:46s} {r.estado:8s} arrastre={datos['indice_arrastre_interno']:.3f}  {r.motivo}")
    if resultados:
        with (salida/'informe_recortes.csv').open('w',newline='',encoding='utf-8-sig') as archivo:
            writer=csv.DictWriter(archivo,fieldnames=list(resultados[0]))
            writer.writeheader();writer.writerows(resultados)
        print(f'CSV guardado: {salida / "informe_recortes.csv"}')
    else:
        print('No hay imagenes compatibles.')

if __name__ == '__main__':main()

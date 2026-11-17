"""Comprobar deteccion de borrados en mascaras y recortes originales.

Uso: python verificar_etapa05.py
No requiere YOLO ni camara. Las capturas de pantalla se usan SOLO como
referencia visual, NO equivalen a los fotogramas BGR originales.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from auditoria_mascara import auditar_mascara_tinta
from inspeccion_robusta import InspectorCalidadRobusto

BASE=Path(__file__).resolve().parent
DESTINO=BASE/'salida_auditoria_05'


def dibujar(mascara:np.ndarray, sospecha:np.ndarray, ancho:int=640)->np.ndarray:
    m=np.uint8(mascara>0)*255
    out=cv2.cvtColor(m,cv2.COLOR_GRAY2BGR)
    if sospecha is not None and sospecha.shape == m.shape:
        out[sospecha>0]=(0,155,255)
    esc=min(ancho/max(m.shape[1],1),4.)
    return cv2.resize(out,(int(m.shape[1]*esc),int(m.shape[0]*esc)),interpolation=cv2.INTER_NEAREST)


def main():
    DESTINO.mkdir(parents=True,exist_ok=True)
    inspeccion=InspectorCalidadRobusto()
    entradas=[
        ('11709_mascara_de_pantalla','pruebas/casos_reportados/11709_mascara_extraida.png',True),
        ('11713_mascara_de_pantalla','pruebas/casos_reportados/11713_mascara_extraida.png',True),
        ('11682_recorte_original','pruebas/fecha_11682_centro.png',False),
        ('normal','pruebas/barrido_normal.png',False),
        ('espacios_normales','pruebas/barrido_spaces.png',False),
    ]
    for nombre,ruta,es_mascara in entradas:
        imagen=cv2.imread(str(BASE/ruta))
        if imagen is None:
            raise FileNotFoundError(ruta)
        if es_mascara:
            mascara=imagen[:,:,0]
            a=auditar_mascara_tinta(mascara)
            estado='REVISAR' if a.sospecha else 'SIN INDICIO'
            alerta=a.mascara
            motivo=a.motivo
        else:
            resultado=inspeccion.analizar(imagen)
            estado=resultado.estado
            mascara=resultado.mascara_tinta
            alerta=resultado.mascara_sospechosa
            motivo=resultado.motivo
        salida=dibujar(mascara,alerta)
        output=DESTINO/(nombre+'_05_06.png')
        cv2.imwrite(str(output),salida)
        print(nombre,'=>',estado,'|',motivo,'|',output)
    print('\nNota: las mascaras fotografiadas de un monitor solo comprueban la'
          ' auditoria geometrica. Para medir precision se necesitan frames'
          ' originales BGR y etiquetas humanas por producto.')

if __name__=='__main__':main()

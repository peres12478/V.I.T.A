"""Ejecuta el barrido de continuidad sobre recortes de muestra, sin YOLO/camara.

Comando: python validar_barrido.py
No sustituye la validacion sobre productos reales etiquetados.
"""
from __future__ import annotations

import csv
from pathlib import Path
import cv2
import numpy as np

from inspeccion_robusta import InspectorCalidadRobusto
from visualizador_filtros import crear_vistas_filtros

BASE = Path(__file__).resolve().parent
MUESTRAS = {
    'foto_real_borrada': 'pruebas/fecha_11682_centro.png',
    'foto_real_borrada_recorte_estrecho': 'pruebas/fecha_11682_estrecha.png',
    'real_arrastre': 'pruebas/casos_reales/11550_arrastre.png',
    'real_comparacion_sin_arrastre': 'pruebas/casos_reales/161708_comparacion.png',
    'sintetica_sana': 'pruebas/barrido_normal.png',
    'sintetica_espacios_intencionales': 'pruebas/barrido_spaces.png',
    'sintetica_borrado_total': 'pruebas/barrido_erased.png',
    'sintetica_borrado_tenue': 'pruebas/barrido_faded.png',
}


def ejecutar():
    destino = BASE/'pruebas'/'resultados_barrido'
    destino.mkdir(parents=True, exist_ok=True)
    inspector = InspectorCalidadRobusto()
    filas = []
    for nombre,archivo in MUESTRAS.items():
        im = cv2.imread(str(BASE/archivo))
        if im is None:
            raise FileNotFoundError(str(BASE/archivo))
        r = inspector.analizar(im)
        vistas = crear_vistas_filtros(im,r)
        cv2.imwrite(str(destino/(nombre+'_05_mascara.png')),vistas['05  Tinta segmentada (real)'])
        cv2.imwrite(str(destino/(nombre+'_06_sospecha.jpg')),vistas['06  Zonas sospechosas (real)'])
        filas.append({
            'muestra':nombre,'archivo':archivo,'estado':r.estado,'motivo':r.motivo,
            'indice_continuidad':r.metricas.get('indice_continuidad_tinta',0),
            'franjas':int(r.metricas.get('franjas_continuidad_tinta',0)),
            'coincidencias':int(r.metricas.get('coincidencias_continuidad',0)),
            'confirmada':int(r.metricas.get('continuidad_confirmada',0)),
            'indice_arrastre_interno':r.metricas.get('indice_arrastre_interno',0),
        })
        print(f'{nombre:37s}: {r.estado:7s} | continuidad={filas[-1]["indice_continuidad"]:.2f} '
              f'| {r.motivo[:80]}')
    with (destino/'resultados.csv').open('w',encoding='utf-8-sig',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=list(filas[0]));writer.writeheader();writer.writerows(filas)
    print('Resultados guardados en:',destino)
    return filas


if __name__ == '__main__':
    ejecutar()

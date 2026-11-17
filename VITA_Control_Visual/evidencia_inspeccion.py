"""Evidencia de las capturas que REALMENTE votaron por producto.

El historial de imagenes evita diagnosticar una aprobacion solo con una foto
posterior del panel (que puede representar otro fotograma). Se guarda SOLO
el recorte de la fecha: original BGR, mascara etapa 05, y zonas etapa 06.
La escritura sucede fuera del hilo grafico en el mismo trabajador de captura.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


def registrar_evidencia(base: Path, producto: int, muestra: int,
                        recorte_bgr: np.ndarray, resultado) -> Path:
    if recorte_bgr is None or recorte_bgr.size == 0:
        raise ValueError('No hay recorte de fecha para registrar')
    carpeta = Path(base) / f'producto_{int(producto):04d}'
    carpeta.mkdir(parents=True, exist_ok=True)
    prefijo = f'foto_{int(muestra):03d}'
    original = carpeta / (prefijo + '_original.jpg')
    if not cv2.imwrite(str(original), recorte_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(f'No se pudo escribir {original}')
    def salvar_mascara(mascara, sufijo):
        if mascara is None:
            return
        if mascara.shape[:2] != recorte_bgr.shape[:2]:
            return
        cv2.imwrite(str(carpeta/(prefijo+sufijo)), np.uint8(mascara>0)*255)
    salvar_mascara(resultado.mascara_tinta, '_05_tinta.png')
    salvar_mascara(resultado.mascara_sospechosa, '_06_sospechas.png')
    linea = {
        'captura':int(muestra),
        'timestamp':datetime.now().astimezone().isoformat(timespec='milliseconds'),
        'estado':str(resultado.estado),
        'motivo':str(resultado.motivo),
        'metricas':{str(k):float(v) for k,v in (resultado.metricas or {}).items()
                    if isinstance(v,(int,float,np.integer,np.floating)) and np.isfinite(v)},
        'recorte':original.name,
    }
    with (carpeta / 'diagnostico.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(linea, ensure_ascii=False)+'\n')
    return original

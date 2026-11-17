"""Consulta y exportacion de sesiones del modo operador de Nutreo.

Lee exclusivamente CSV/JSON generados por el motor original. No reevalua
productos ni modifica decisiones. Mantiene el motivo tecnico para auditoria.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import json
from pathlib import Path
from typing import Any

# Orden acordado para el informe sencillo del personal de planta.
# La informacion tecnica (hora, motivo y tipo de cierre) se conserva
# internamente para auditoria, pero no se expone en el CSV del operario.
CAMPOS_EXPORT = (
    ('Producto', 'producto_id'),
    ('Resultado', 'resultado'),
    ('Buenas', 'buenas'),
    ('Malas', 'malas'),
    ('Inciertas', 'inciertas'),
    ('Línea', 'linea'),
    ('Turno', 'turno'),
)
COLUMNAS_EXPORT = tuple(etiqueta for etiqueta, _ in CAMPOS_EXPORT)


def clasificar(resultado: str, motivo: str) -> str:
    """Un NO PASA preventivo nunca se etiqueta como defecto confirmado."""
    if resultado in ('BIEN', 'PASA'):
        return 'aprobado'
    m = (motivo or '').upper()
    if any(s in m for s in (
        'PREVENTIVO', 'NO PASA PREVENTIVO', 'INSPECCION INTERRUMPIDA',
        'SIN VOTOS EVALUABLES', 'BUENAS INSUFICIENTES', 'EMPATE',
    )):
        return 'sin_evidencia'
    return 'no_pasa'


def sanitizar_meta(meta: Any) -> dict:
    """Valores de usuario cortos, sin caracteres de control o saltos de linea."""
    meta = meta if isinstance(meta, dict) else {}
    # Compatibilidad: las sesiones antiguas pueden contener lote/referencia
    # en disco, pero el panel solo utiliza linea y turno desde esta version.
    limites = {'linea': 48, 'turno': 48}
    salida = {}
    for campo, limite in limites.items():
        v = str(meta.get(campo, '') or '')
        salida[campo] = ''.join(c for c in v if c >= ' ' and c != '\x7f').strip()[:limite]
    return salida


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _cargar_meta(path: Path) -> dict:
    try:
        return sanitizar_meta(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError):
        return sanitizar_meta({})


def cargar_historial(carpeta: Path, limite_archivos: int = 1500) -> list[dict]:
    """Una fila por inspeccion; IDs son unicos solamente dentro de su sesion."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    filas = []
    for archivo in sorted(carpeta.glob('sesion_*.csv'), reverse=True)[:limite_archivos]:
        sesion = archivo.stem
        meta = _cargar_meta(archivo.with_suffix('.json'))
        try:
            with archivo.open('r', encoding='utf-8-sig', newline='') as fd:
                for fila in csv.DictReader(fd):
                    if not fila.get('producto_id'):
                        continue
                    raw = str(fila.get('decision', '')).strip().upper()
                    resultado = 'PASA' if raw == 'BIEN' else 'NO PASA'
                    motivo = str(fila.get('motivo', ''))
                    item = {
                        'fecha_hora': str(fila.get('fecha_hora', '')),
                        'sesion': sesion,
                        **meta,
                        'producto_id': str(fila.get('producto_id', '')),
                        'resultado': resultado,
                        'tipo': clasificar(raw, motivo),
                        'buenas': _int(fila.get('buenas')),
                        'malas': _int(fila.get('malas')),
                        'inciertas': _int(fila.get('ambiguas')) + _int(fila.get('desenfocadas')),
                        'fotos_totales': _int(fila.get('fotos_totales')),
                        'votos_validos': _int(fila.get('votos_validos')),
                        'motivo': motivo,
                        'finalizacion': str(fila.get('finalizacion', '')),
                    }
                    filas.append(item)
        except (OSError, UnicodeError, csv.Error):
            continue
    filas.sort(key=lambda r: (r['fecha_hora'], r['sesion'], _int(r['producto_id'])), reverse=True)
    return filas


def filtrar_historial(filas: list[dict], *, desde='', hasta='', resultado='',
                      sesion='', buscar='', tipo='') -> list[dict]:
    buscar = (buscar or '').strip().casefold()
    salida = []
    for fila in filas:
        fecha = fila['fecha_hora'][:10]
        if desde and fecha < desde: continue
        if hasta and fecha > hasta: continue
        if resultado and fila['resultado'] != resultado: continue
        if sesion and fila['sesion'] != sesion: continue
        if tipo and fila['tipo'] != tipo: continue
        if buscar:
            campos = ('linea', 'turno', 'producto_id', 'resultado')
            if not any(buscar in str(fila.get(c, '')).casefold() for c in campos):
                continue
        salida.append(fila)
    return salida


def estadisticas(filas: list[dict]) -> dict:
    pasa = sum(f['resultado'] == 'PASA' for f in filas)
    sin_evidencia = sum(f['tipo'] == 'sin_evidencia' for f in filas)
    return {
        'total': len(filas),
        'pasa': pasa,
        'no_pasa': len(filas) - pasa,
        'sin_evidencia': sin_evidencia,
        'no_pasa_con_evidencia': len(filas) - pasa - sin_evidencia,
        'porcentaje_pasa': round(100. * pasa / len(filas), 1) if filas else 0.,
    }


def exportar_csv(filas: list[dict]) -> bytes:
    """BOM para Excel y neutralizacion de formulas CSV en campos de texto."""
    def segura(v):
        s = str(v if v is not None else '')
        if s.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + s
        return s
    memoria = io.StringIO(newline='')
    w = csv.writer(memoria)
    w.writerow(COLUMNAS_EXPORT)
    for fila in filas:
        w.writerow([segura(fila.get(clave, '')) for _, clave in CAMPOS_EXPORT])
    return ('\ufeff' + memoria.getvalue()).encode('utf-8')

# HISTORICO - REGLA ANTERIOR (SUSTITUIDA)

Esta nota describe una implementacion anterior que ya NO esta activa.
La politica vigente exige **7 capturas completas y al menos 5 BUENAS**,
ademas de que BUENAS > MALAS. Consulta `CAMBIOS_ZONA_SEGURA_Y_5_BUENAS.md`.

# Nutreo - Mayoría real BUENAS frente a MALAS

## Problema anterior

El sistema podia rechazar una fecha con más evaluaciones BUENAS que MALAS
cuando no alcanzaba cierto numero de votos evaluables o cuando el porcentaje
de muestras inciertas era alto. Esto no correspondia al criterio solicitado.

## Regla nueva

La clasificacion individual del filtro robusto sigue siendo BIEN / MAL /
REVISAR. El seguimiento conserva una cuenta independiente de: BUENAS,
MALAS e INCIERTAS (incluye borrosas).

- **BUENAS > MALAS: PASA.**
- **MALAS > BUENAS: NO PASA.**
- **Empate: NO PASA preventivo**, por no haber lado ganador.
- **0 BUENAS y 0 MALAS: NO PASA preventivo**, sin evidencia suficiente.

Las inciertas **NO votan** ni se convierten en malas. Siempre se informa
el numero de votos evaluables y se agrega un AVISO DE CONFIABILIDAD si hubo
pocos votos o demasiadas incertidumbres. El aviso **NO cambia la mayoria**.

## Ejemplos

| Capturas totales | Buenas | Malas | Inciertas | Decision |
|---:|---:|---:|---:|---|
| 30 | 13 | 2 | 15 | PASA |
| 31 | 13 | 2 | 16 | PASA + aviso de confiabilidad |
| 30 | 12 | 13 | 5 | NO PASA |
| 7 | 4 | 1 | 2 | PASA |
| 7 | 3 | 3 | 1 | NO PASA, empate |
| 7 | 0 | 0 | 7 | NO PASA, sin votos |

## Muestras y recuadro

Si en la interfaz pones **7 fotos**, significa **7 capturas totales**:
BUENAS + MALAS + INCIERTAS = 7. Ya no se siguen tomando hasta 24 o 28
para buscar siete votos favorables. Cada tipo de captura tiene el mismo
intervalo minimo (75 ms, modificable en la interfaz), por lo que las
inciertas no aparecen en rafaga.

Cuando se completan las capturas, la decision queda congelada y el
recuadro/ID sigue asociado al mismo producto hasta que YOLO deje de
detectarlo durante el tiempo de ausencia configurado (650 ms por defecto
mas fotogramas vacios). Las cajas duplicadas no crean productos nuevos
en el modo de un solo carril.

## Ejecutar

Desde PowerShell, dentro de la carpeta `Nutreo_Control_Calidad`:

```powershell
python interfaz_nutreo.py
```

O sin interfaz, con 30 capturas por producto:

```powershell
python iniciar_calidad.py --camara 0 --fotos 30 --intervalo-ms 75
```

## Limitaciones

El voto mayoritario mejora la estabilidad frente a errores esporadicos,
pero fotogramas muy similares no son independientes. Una camara mala o
un filtro sistematicamente equivocado puede generar una mayoria errada.
En la configuracion estricta solicitada, 1 BUENA + 6 INCIERTAS implica
PASA con aviso: **no es seguro interpretarlo como verificacion industrial
confiable sin acordar criterios adicionales de evidencia**. No se ha
verificado el flujo con camara y banda fisicas.

> DOCUMENTO HISTORICO de una version anterior. **No describe la politica actual.**
> La politica actual esta en `CAMBIOS_MAYORIA_REAL.md`: 7 capturas totales, mayoria buenas vs malas.

# NUTREO - Correccion del seguimiento y del contador de inciertas

## Problemas corregidos

**Antes:** despues de llegar a siete votos buenos/malos, una interrupcion
pequena de YOLO podia hacer que la misma fecha regresara como otro ID.
Ademas, cuando aparecian fotos ambiguas, el motor intentaba obtener siete
votos evaluables, permitiendo hasta 24 o 28 intentos. Esto hacia que las
inciertas aumentaran mas que las fotos buenas.

**Ahora:**

1. El limite configurado (`7` inicialmente) es el **numero total de fotos**.
   Una foto puede ser buena, mala o incierta. Solo buena y mala suman votos,
   pero las tres cuentan como **una captura**. Por eso los contadores nunca
   superan el numero de capturas, salvo que configures intencionalmente
   `--max-muestras` con un numero mayor en el programa tradicional.
2. Cada foto se toma como minimo cada `75 ms` por el mismo producto. Las
   inciertas no se cuentan en cada fotograma: siguen exactamente la misma
   cadencia que las buenas/malas. Si la camara procesa menos FPS, el intervalo
   efectivo sera mayor.
3. Cuando se completa la votacion, la decision **PASA** o **NO PASA** queda
   congelada, igual que todos los contadores. El producto **NO cambia de ID**
   por ese motivo y el recuadro permanece visible mientras YOLO lo detecta.
4. Si YOLO pierde temporalmente la caja, se mantiene la pista durante
   `650 ms` por defecto. Mientras tanto la GUI marca el ultimo recuadro gris
   como posicion anterior, **no como una deteccion nueva**. Si YOLO recupera
   la fecha a tiempo, continua con el mismo ID y sin nuevos votos.
5. Solo tras una ausencia suficientemente larga se retira la pista y una
   nueva deteccion puede obtener un ID nuevo.
6. La caja dibujada se suaviza para reducir saltos por pequenas variaciones
   del detector. La asociacion geometrica admite variaciones de tamano.

## Ejemplo de las siete capturas

| Foto | Resultado individual | Buenas | Malas | Inciertas |
|---|---|---|---|---|
| 1 | BIEN | 1 | 0 | 0 |
| 2 | REVISAR | 1 | 0 | 1 |
| 3 | BIEN | 2 | 0 | 1 |
| 4 | MAL | 2 | 1 | 1 |
| 5 | REVISAR | 2 | 1 | 2 |
| 6 | BIEN | 3 | 1 | 2 |
| 7 | BIEN | 4 | 1 | 2 |

Resultado final: **PASA**. La pista sigue presente y no toma nuevas muestras.
Si hay menos de tres votos evaluables o menos del 50 % de fotos evaluables,
el resultado final es **NO PASA por inspeccion insuficiente**. Esto NO
significa que exista un defecto de tinta confirmado.

## Ejecutar

Archivo principal de la interfaz grafica:

```powershell
python interfaz_nutreo.py
```

O con un entorno virtual de Windows:

```powershell
.\.venv\Scripts\python.exe interfaz_nutreo.py
```

La interfaz tiene un ajuste **Mantener ID sin YOLO (ms)**, con valor inicial
650. Si observas que se crea un ID nuevo por una perdida temporal de YOLO,
puedes aumentar este tiempo con cuidado. Si los productos pasan muy juntos,
un valor alto puede fusionar dos productos diferentes.

Programa tradicional sin interfaz:

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --intervalo-ms 75 --ausencia-ms 650
```

## Comprobaciones realizadas

Se ejecutaron pruebas automatizadas con fechas presentes durante decenas de
fotogramas despues de la decision, detecciones YOLO que desaparecen y vuelven,
variaciones en el tamano del recuadro, cadencia de muestreo, 7 intentos
inciertos y registro de una sola decision por ID.

**Limite importante:** estas son pruebas del codigo. No se ha validado la
camara, la iluminacion, la velocidad real de la banda ni `best.pt` con
Ultralytics en el computador de produccion. Sin sensor fisico de presencia
no se puede garantizar que dos paquetes pegados o superpuestos pertenezcan
a identidades diferentes.

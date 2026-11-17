# Nutreo - recorte de fecha para evitar el codigo de barras

## Problema observado

En la foto aportada de la interfaz, el area de "Zonas sospechosas" mostraba
marcas naranjas en los bordes del recorte. La fecha visible parece estar bien
impresa, pero en el mismo empaque hay una etiqueta con codigo de barras y
transiciones intensas de color/iluminacion.

La version anterior de `iniciar_calidad.py` **ampliaba** la caja de YOLO un 6%
a cada lado. Asi los filtros podian evaluar elementos del empaque en lugar de
analizar exclusivamente los trazos de la fecha.

## Correccion aplicada

El area que se envia a OpenCV es ahora mas estrecha en el **eje corto** del
recuadro detectado:

- Una fecha horizontal: se reduce la ALTURA.
- Una fecha vertical: se reduce la ANCHURA, porque el texto esta girado.
- Por defecto se recorta **15% de cada lado del eje corto** (30% en total).
- La direccion larga conserva solo un margen de 2% para proteger los extremos
  del texto, en lugar de expandir los cuatro lados.
- Los recortes muy pequenos tienen proteccion de tamano minimo.
- Los filtros, las mascaras, los paneles de la interfaz y la caja de seguimiento
  utilizan **el mismo recorte realmente evaluado**.
- La regla de decision por producto no cambia: BUENAS > MALAS = PASA;
  MALAS >= BUENAS = NO PASA; INCIERTAS no votan.

No se cuentan caracteres, no se usa OCR ni se impone formato a la fecha.

## Usar la interfaz

Abre `interfaz_nutreo.py`. En la franja de configuracion hay un nuevo campo:

**Reducir alto (%)**: valor inicial **15**.

Se aplica al eje corto para que funcione aunque la camara vea la fecha girada.

- `0`: sin recortar por los lados (util si YOLO ya ajusta perfectamente la caja).
- `10`: recorte suave, conserva mas espacio alrededor de los trazos.
- `15`: valor inicial recomendado para el empaque fotografiado.
- `20`: puede servir si aun se incluye una franja de etiqueta/barcode.
- `30`: maximo permitido; usar solo si se confirma que NO corta caracteres.

Para cambiarlo hay que **DETENER** e **INICIAR** nuevamente; no cambia
la inspeccion en mitad de un producto.

### Inicio por terminal

```powershell
python interfaz_nutreo.py
```

O en la consola clasica:

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --recorte-borde 15
```

Para verificar una foto manual con coordenadas fijas:

```powershell
python iniciar_calidad.py --imagen foto.jpg --roi 100 100 500 260 --recorte-borde 15
```

La ROI manual se usara como caja inicial y se acortara antes de analizarla.

## Como comprobar que se corrigio

1. Abre `interfaz_nutreo.py` y selecciona `15` en **Reducir alto (%)**.
2. Coloca el producto frente a la camara y confirma que la caja visible deja
   fuera los bordes de la etiqueta y del codigo de barras.
3. Abre las vistas `01 Fecha detectada` y `06 Zonas sospechosas`.
4. Si todavia entra la etiqueta, prueba `20`; si se cortan los extremos o
   las partes superiores de las letras, baja a `10`, `5` o `0`.
5. Guarda un video o fotogramas de la camara real para validar la tasa de
   falsos rechazos. Una fotografia de un monitor introduce artefactos extra.

**Limitacion:** el recorte interior reduce la posibilidad de analizar un codigo
de barras adyacente, pero si YOLO encuadra la etiqueta entera o el codigo de
barras ocupa la zona central, el recorte por porcentajes NO puede identificar
por si solo que pixeles son de la fecha. En ese caso hay que mejorar las cajas
YOLO, ajustar una ROI estable o entrenar la separacion texto/etiqueta.

## Archivos cambiados

- `iniciar_calidad.py`: `caja_recorte`, `inspeccionar`, parametro CLI.
- `interfaz_nutreo.py`: campo **Reducir alto (%)** y paso del mismo ROI al
  seguimiento y al visor de filtros.
- `pruebas/test_recorte_barcode.py`: 7 verificaciones nuevas para recorte
  horizontal, vertical, proteccion de recortes pequenos, exclusion de bandas
  externas, interfaz, paneles y votacion.

### Verificacion efectuada

- 68 pruebas automatizadas satisfactorias (incluidas 7 nuevas).
- Interfaz Tk comprobada en escritorio virtual, valor 15/20 configurable.
- No se verifico YOLO con una camara industrial ni la banda real en este entorno.
- Los resultados de la foto del monitor no son medidas fiables de la calidad
  fisica de la tinta debido a desenfoque, moire y reflejos.

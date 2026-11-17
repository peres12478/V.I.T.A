# Nutreo: inspeccion concentrada en la tinta de la fecha

## Que se resolvio

El inspector anterior podia declarar `REVISAR` o `MAL` al detectar una raya **del material o de una etiqueta** dentro del recorte de YOLO. Su mascara de proximidad podia extenderse hasta una ventana de `61 x 61` pixeles, y una sola metrica moderada activaba el texto generico `Trazos ambiguos`.

En la version nueva, **YOLO conserva la responsabilidad de localizar la fecha**. Solo cuando el seguimiento de la banda autoriza una nueva captura, `InspectorCalidadRobusto` evalua la region. El analisis de tinta usa la propia mascara del texto y un entorno inmediato dependiente del grosor del trazo. El fondo restante no se trata como un defecto.

**No se agrego OCR obligatorio, conteo de caracteres, longitud de fecha ni formato esperado.**

## Arquitectura preservada

1. **YOLO / vision artificial** (`best.pt`, `iniciar_calidad.py`): encuentra y recorta la region donde esta impresa la fecha. Mantiene el ajuste del recuadro en su eje corto para reducir partes de codigos de barras.
2. **Calidad fisica de impresion** (`calidad_impresion.py`, `inspeccion_robusta.py`): contrasta la tinta con el material, analiza componentes conectados, grosor, manchas, interrupciones y posible arrastre. Un defecto debe tener evidencia *en la tinta o justo al lado de ella*.
3. **Control de produccion** (`seguimiento_banda.py`, `validacion_visibilidad.py`): exige entrada a la zona segura, toma un numero configurado de capturas, conserva el mismo ID hasta que el producto sale, aplica la votacion.
4. **Interfaz** (`interfaz_nutreo.py`, `visualizador_filtros.py`): muestra cada etapa y el motivo real del analisis. No simula mascaras.

## Cambios concretos

### 1. Segmentacion local de la fecha

- Se conservan los canales LAB, la polaridad de tinta oscura, clara o de color, y la segmentacion por contraste.
- Se identifican componentes extensos y muy delgados cercanos al borde del recorte, o en una franja exterior del eje corto, compatibles con borde de etiqueta / linea de empaque. Se **excluyen como bandas ajenas**. No se descartan puntuacion ni caracteres pequenos por su cantidad.
- Esta exclusion es deliberadamente conservadora: si una mancha o codigo de barras se superpone directamente a la fecha, la geometria por si sola no puede asegurar que se trate de tinta distinta. En ese caso hay que mejorar la iluminacion o entrenar mejor el detector para recortar solamente la fecha.

### 2. Zonas sospechosas ligadas a tinta

- Antes, una busqueda muy amplia podia incluir texturas, sombras o rayas externas.
- Ahora la distancia de busqueda es de **2 a 7 px segun el grosor del trazo**. Se busca barrido fuera del nucleo de tinta, pero solamente en ese anillo local.
- La busqueda direccional usa **6 orientaciones**, en vez de 12, para reducir CPU.
- No se pintan como naranja los problemas globales de camara ni una baja SNR sin defecto espacial.
- Las acumulaciones gruesas que realmente disparan la regla de manchas ahora tienen **evidencia visible en la etapa 06**.

### 3. Diagnosticos explicitos

- `Aviso: contraste relativo limitado (SNR ...)` **no bloquea por si solo una mascara limpia**: el SNR puede bajar por textura del envase, no necesariamente por mala impresion. Si la camara de verdad carece de detalle, el modulo robusto decide `CAPTURA NO EVALUABLE`.
- `Posible barrido junto a tinta (...)` significa que se ha detectado una estructura lineal *asociada espacialmente* con el trazado. Requiere indicadores geometricos concordantes para que una evidencia debil cuente como defecto.
- `CAPTURA NO EVALUABLE: ...` corresponde a ruido, desenfoque, saturacion u otra limitacion de la camara.
- `MAL` se sigue reservando para evidencia fisica mas fuerte o corroborada; `REVISAR` no se convierte automaticamente en un voto malo.

La interfaz muestra **CAMARA / TINTA / ZONAS** con SNR, barrido cercano, halo cercano, pixeles sospechosos, bandas externas descartadas y el radio usado. Se conserva el resultado de las dos verificaciones cuando las hay.

### 4. Procesamiento mas eficiente

- El inspector solo se ejecuta cuando el seguimiento **admite** otra foto, no por cada fotograma de la vista previa.
- La segunda pasada CLAHE/bilateral ahora solo se hace para un `MAL` o un `REVISAR` con motivo medido y captura util; las fotos `BIEN` sin problemas de camara no se recalculan.
- La interfaz **no reconvierte las 6 miniaturas en cada cuadro**; solo cuando se acepta una muestra nueva para el producto.
- En mediciones locales del inspector sin YOLO (Python/OpenCV en este entorno), el tiempo por inspeccion fue: imagen sintetica **17,5 ms antigua / 14,4 ms nueva**; imagen real `1995.jpg` **26,2 ms antigua / 19,3 ms nueva**. Son valores indicativos de este entorno, no mediciones del equipo o la camara del usuario.

## Votacion preservada

- Numero de capturas configurable; `7` por defecto.
- **PASA** solamente al completar las capturas, con **5 o mas BUENAS** por defecto y `BUENAS > MALAS`.
- Las `INCIERTAS` no se suman a `MALAS`, pero si ocupan una captura del total, de modo que no se acumulen sin limite.
- Un resultado de `1 BUENA / 0 MALAS / 6 INCIERTAS` es **NO PASA por evidencia insuficiente**, no por defecto de tinta demostrado.
- El mismo producto conserva ID, recuadro y resultado mientras sigue visible; una desaparicion corta de YOLO no abre otro producto de inmediato.

## Como ejecutar

En la carpeta `Nutreo_Control_Calidad` del ZIP, desde Visual Studio Code:

```powershell
python -m pip install -r requirements.txt
python interfaz_nutreo.py
```

La camara a color permanece en el panel principal. Tambien puedes usar **Video de prueba** y escoger un MP4 grabado de la banda. Si ya tienes tu `.venv`, el equivalente es:

```powershell
.\.venv\Scripts\python.exe interfaz_nutreo.py
```

Configuracion inicial recomendada para diagnostico: `Fotos totales = 7`, `Min. buenas = 5`, `Intervalo = 75 ms`, `Reducir alto = 15 %`, `Margen zona = 8 %`, `Confirmaciones = 3`. Cuando uses 50 capturas, debes verificar que el producto permanece suficiente tiempo en la zona segura. Los valores son de **prototipo**, no de certificacion industrial.

## Prueba de aceptacion recomendada en la banda

Graba video de (a) fecha buena sobre empaque uniforme, (b) misma fecha con reflejo/sombra, (c) empaque con codigo de barras proximo pero fuera del texto, (d) tinta fisicamente corrida y (e) tinta tenue o cortada. Marca manualmente los resultados reales antes de comparar. Anota para cada video: si YOLO recorta completo, metricas de TINTA, pixeles naranja, motivos por captura, votos y resultado final.

**Criterio de calidad:** una sombra aislada fuera de la tinta no debe generar defecto; una mancha o arrastre que afecte fisicamente los trazos si debe detectarse. Con las muestras actuales no se puede garantizar la tasa de falsos rechazos o escapes: la calibracion con tu camara y empaques etiquetados sigue pendiente.

## Pruebas de codigo

```powershell
python -m unittest discover -s pruebas -p "test_*.py" -q
```

Se ejecutaron **89 pruebas automatizadas** y una prueba de apertura/renderizado de la interfaz en entorno grafico virtual. Se probo la logica con ejemplos reales y sinteticos. No se ejecuto `best.pt` contra una banda fisica ni se valido la camara en este entorno.

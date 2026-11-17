# Nutreo — Calibración exploratoria de arrastre sobre la fecha

## Resultado reproducido

La foto `11550.jpg` compartida por el usuario muestra una franja horizontal de arrastre y pérdida parcial de impresión. Antes de los cambios, el inspector robusto la clasificaba **BIEN** en distintos recortes, aunque visualmente no cumple el criterio de calidad. Después, en el recorte de fecha usado para la regresión, produce **MAL** con el motivo **«Arrastre lineal prolongado que atraviesa la tinta»**.

Se revisó el ZIP `iLoveZIP_Create.zip`: contiene **68 fotografías completas** de empaques distintos (varias fotos del mismo producto), **sin etiquetas independientes de bueno/malo**. Para inspeccionar la tinta hay que pasar a OpenCV una región de fecha delimitada por YOLO, no la foto entera. Se eligieron algunos recortes controlados de estas imágenes para pruebas. Las fotos del empaque azul en el ZIP muestran una marca semejante a la del ejemplo reportado; no constituyen defectos confirmados por inspección industrial independiente.

| Imagen de recorte | Anterior | Actual | Observación |
|---|---|---|---|
| `defecto_confirmado_11550.png` | BIEN | **MAL** | Defecto señalado por el usuario |
| `defecto_similar_164304.png` | BIEN | **MAL** | Arrastre semejante, imagen del ZIP |
| `defecto_similar_164308.png` | BIEN | **MAL** | Arrastre semejante, imagen del ZIP |
| `comparacion_sin_arrastre_visible_161708.png` | BIEN | **BIEN** | Control visual sin la franja característica |

Estos resultados no son una estimación de sensibilidad, especificidad o precisión general. Para obtenerlas hacen falta etiquetas humanas verificadas por muestra, con suficientes productos distintos y una división independiente de entrenamiento/prueba.

## Qué cambió el código

1. **Nuevo `deteccion_arrastre_interno.py`:** conserva el color del recorte y calcula gradientes sobre la luminancia de LAB. Busca varias crestas lineales prolongadas y paralelas a la dirección de la fecha, con solapamiento sobre la zona segmentada como tinta. No usa OCR, longitud de fecha ni cantidad de caracteres.
2. **Protección contra falsos positivos:** una sombra suave, el código de barras lateral y dos líneas impresas oscuras no bastan para que el nuevo detector declare MAL en los controles sintéticos. Requiere trazos de contraste intermedio, varios bordes prolongados y contacto espacial con el área de impresión. Las variables son heurísticas, no una prueba perfecta de que todo trazo sea tinta corrida.
3. **`calidad_impresion.py`:** la evidencia corroborada cambia `estado` a `MAL`, añade el motivo y mezcla la máscara del arrastre con las **zonas sospechosas**; un caso parcial se puede tratar como `REVISAR`.
4. **`inspeccion_robusta.py`:** contrasta la posible anomalía con una segunda pasada cuando corresponde. Si el resultado cambia sustancialmente por el preprocesamiento, evita atribuir sin suficiente evidencia un defecto físico.
5. **`interfaz_nutreo.py`:** muestra el índice de *arrastre interno* y el número de crestas en el panel, junto a las áreas naranjas localizadas. El recuento de píxeles sospechosos coincide con lo que se muestra.
6. **Recorte YOLO por defecto: `12 %` por cada lado del eje corto.** En una toma del ZIP, el 15 % ocultaba la evidencia; el 12 % la conserva. Sigue siendo configurable en **Reducir alto (%)** para otros productos. NO se cambia el modelo YOLO `best.pt`.
7. **Seguimiento y votación:** sin cambios en la política ya acordada (por defecto 7 capturas, al menos 5 BUENAS y más BUENAS que MALAS). Una muestra clasificada MAL no equivale necesariamente a NO PASA del producto hasta finalizar su votación.

## Ejecución normal en Windows

Abrir el ZIP del proyecto nuevo en Visual Studio Code, instalar si es necesario `python -m pip install -r requirements.txt` y ejecutar:

```powershell
python interfaz_nutreo.py
```

Parámetros iniciales recomendados para la prueba con el mismo producto: **Reducir alto = 12 %**, **Fotos totales = 7**, **Min. buenas = 5**. Con la fecha frente a la cámara, abrir **05 Tinta segmentada** y **06 Zonas sospechosas** y comprobar que las marcas de arrastre se relacionan con los caracteres. Si la fecha queda cortada o se mezcla el código de barras, corregir la configuración y registrar una nueva prueba.

Para ensayar sin webcam ni YOLO usando los **recortes de ejemplo** incluidos:

```powershell
python validar_calibracion.py
```

Se crea `salida_calibracion/informe_recortes.csv` y dos imágenes por recorte (`_05_tinta.png`, `_06_sospechas.jpg`). Para pasar otra carpeta de fotos ya recortadas:

```powershell
python validar_calibracion.py --carpeta C:\ruta\a\recortes
```

**No pasar el ZIP de 68 fotografías completas directamente al inspector**: ese es el trabajo del detector YOLO. En este entorno se han ejecutado las pruebas de OpenCV y las simulaciones de seguimiento, pero no pudo cargarse `best.pt` en Ultralytics ni capturarse una banda/cámara real.

## Limitaciones y siguiente validación

- La apariencia de una foto muy comprimida, fuera de foco o con reflejos fuertes puede confundirse con tinta corrida. Es necesaria una captura nítida, iluminación estable y ajuste del recorte al material.
- Una falsa alarma también es posible sobre líneas decorativas, arrugas o texturas similares; los filtros añadidos reducen algunos casos conocidos, no todos.
- Si el recorte YOLO no incluye el área dañada, ningún filtro de tinta podrá analizar lo que quedó fuera. El ajuste del 12 % es una **hipótesis inicial** obtenida de estas muestras, no un valor universal.
- El reconocimiento de daños no se ha validado con suficientes muestras independientes. Seleccionar impresiones buenas y defectuosas en producción, etiquetarlas manualmente y calcular una matriz de confusión por tipo de empaque y velocidad.
- Mantener una política conservadora sobre productos sin inspección suficiente; un defecto `MAL` necesita comprobarse consistentemente en los fotogramas del mismo producto.
- Los tiempos del nuevo detector aislado rondaron **4,8 ms de mediana** para un recorte local de 750×145 píxeles en este entorno. No representan latencia completa de YOLO, GUI ni rendimiento garantizado en Windows.

**Importante:** no usar una tasa de aciertos calculada sobre varias tomas casi idénticas del mismo empaque como si fueran productos independientes.

## Archivo para una validación industrial posterior

`pruebas/plantilla_etiquetado_68.csv` lista las 68 fotografías del ZIP del usuario,
con campos **vacíos** para el veredicto de una persona y la identificación
real del producto. No se rellenan automáticamente: una predicción del programa
no es una verdad de terreno. Agrupar por producto evita contar fotografías
repetidas como evaluaciones independientes.

La imagen `VISTA_CALIBRACION_ARRASTRE.jpg` muestra la salida real de OpenCV
para el defecto reportado y para un ejemplo visual de comparación.

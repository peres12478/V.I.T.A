# NUTREO — inspección reforzada desde la máscara 05

## Problemas reportados

El usuario mostró una impresión con una franja borrada/tachón en la que el panel `05 Tinta segmentada` mostraba un gran vacío negro y restos blancos. El registro contenía **46 BUENAS, 0 MALAS, 4 INCIERTAS, PASA**. Otra pantalla mostraba una raya blanca aislada por debajo de los caracteres. Esto confirma **falsos positivos observados en producción**, pero una fotografía del monitor no conserva el fotograma BGR exacto que generó cada voto.

## Qué cambió

Se conserva `best.pt`, YOLO, OpenCV, seguimiento y la regla **al menos 5 buenas y más buenas que malas**. No se agregó OCR ni OpenVINO.

- `auditoria_mascara.py`: nueva auditoría de la **máscara de tinta real**: busca franjas interiores con muy poca tinta **pero restos fragmentados**, utilizando áreas, alturas y proximidad entre componentes conectados. No compara formatos ni cantidad de caracteres.
- La auditoría detecta también ciertas **reglas horizontales largas y aisladas** que entraron en la ROI de la fecha. Ese caso es **REVISAR por recorte contaminado**, no un defecto de tinta confirmado.
- `inspeccion_robusta.py`: integra la auditoría después de la comprobación de continuidad. Si la auditoría encuentra evidencia sospechosa, un estado BIEN pasa a **REVISAR** (no suma buena). Las marcas se incorporan a `mascara_sospechosa`, visible en la etapa 06.
- `interfaz_nutreo.py`: muestra `AUDITORIA MASCARA 05` en el panel de métricas y ofrece la casilla `Guardar pruebas 05/06 de cada voto` (activada por defecto).
- `evidencia_inspeccion.py`: guarda, por **cada captura que realmente votó**, el recorte BGR original, su máscara 05, la máscara 06 y un `diagnostico.jsonl` con decisión, motivo, métricas, hora y número de captura. Las carpetas se organizan por **sesión** y por producto. No guarda toda la escena de cámara.
- `verificar_etapa05.py`: reproduce casos reportados, ejemplos normales y el recorte original previamente guardado, sin cámara ni YOLO.

## Qué hace y qué NO puede hacer la máscara

**Blanco** = tinta que logró segmentarse. **Negro** = fondo estimado, pero también podría ser tinta completamente borrada. La máscara por sí sola **no conoce los caracteres que deberían existir**.

Si aparecen restos fragmentados en una gran zona vacía interior, la auditoría puede bloquear BUENA. El inspector sigue consultando la imagen BGR original, el barrido de continuidad y los otros indicadores para **confirmar** una impresión borrada. Una ausencia totalmente limpia e indistinguible de un espacio intencional sigue siendo ambigua sin una referencia buena del producto.

Se evita exigir exactamente dos líneas, contar dígitos o imponer una cadena esperada. Los límites geométricos son **experimentales** y deben calibrarse con ejemplos **etiquetados por una persona** de diversos materiales y lotes.

## Cómo ejecutar

Desde la carpeta `Nutreo_Control_Calidad`:

```powershell
python -m pip install -r requirements.txt
python interfaz_nutreo.py
```

Para repetir los ejemplos:

```powershell
python verificar_etapa05.py
python -m unittest discover -s pruebas -p "test_*.py" -q
```

Los resultados visuales se generan en `salida_auditoria_05/`.

### Dónde encontrar cada captura realmente evaluada

El directorio `evidencias_inspeccion/sesion_AAAAMMDD_HHMMSS_.../producto_0001/` contendrá, para cada muestra:

- `foto_001_original.jpg`: recorte original enviado al inspector.
- `foto_001_05_tinta.png`: máscara usada para la comprobación.
- `foto_001_06_sospechas.png`: anomalías localizadas, si las hubiera.
- `diagnostico.jsonl`: una línea JSON por muestra, con `estado`, `motivo` y `metricas`.

La salida final por producto sigue registrada en `registros_gui.csv`. Para comparar un producto que salió PASA, revisa las fotos y estados de su carpeta, no solo el popup de una máscara ampliada.

## Pruebas realizadas aquí

- **128 pruebas automatizadas** en el entorno sin cámara (incluyen los 120 casos anteriores, más ocho nuevos).
- Máscara **extraída de fotografía de pantalla** `11709`: sospecha de pérdida interior, **REVISAR** al auditar la máscara; no es prueba directa de lo que clasificó la cámara original.
- Máscara **extraída de fotografía de pantalla** `11713`: línea ajena a los trazos, **REVISAR** por recorte contaminado.
- Imagen BGR del recorte defectuoso `fecha_11682_centro.png`: **MAL** por barrido de continuidad corroborado.
- Recorte sano `barrido_normal.png`: **BIEN**.
- Texto normal con espacios intencionales `barrido_spaces.png`: **BIEN**.
- GUI abrió en una pantalla virtual. No fue posible ejecutar `best.pt` con Ultralytics ni conectar aquí la cámara física.
- Coste adicional medido para `auditoria_mascara.py`, sin YOLO ni captura: aprox. **0,7–6,6 ms** según la resolución de las máscaras probadas en este equipo. No implica un FPS garantizado.

## Próxima validación indispensable

Ejecutar el mismo **producto defectuoso y otro bueno** con la cámara, guardar todos los votos y revisar las carpetas. Para medir precisión real, registrar etiquetas humanas `BUENA/MALA` de cada impresión, incluyendo recortes completos, desenfocados, tinta negra sobre blanco y sobre envases de distintos colores. No automatizar expulsión industrial con solo estas pruebas.

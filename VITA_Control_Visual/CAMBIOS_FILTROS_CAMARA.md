# Nutreo — Mejoras para cámaras de calidad desconocida

## Respuesta sobre la escala de grises

**Sí se usa información de luminancia**, como señal auxiliar para detectar el contraste de los trazos, pero **no se descarta el color**: la cámara captura BGR, se trabaja también con los canales de color de LAB y la vista principal muestra la imagen original **a color**. Una imagen en blanco/negro de la máscara de tinta solo se abre si se agrega `--mostrar-mascara`.

## Archivos y ejecución

El punto de entrada de todo el sistema continúa siendo **`iniciar_calidad.py`**.

Desde la terminal de VS Code, dentro de la carpeta del proyecto, después de instalar `requirements.txt`:

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --intervalo-ms 75
```

Por defecto usa **`--filtros robusto`**. También se puede especificar:

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --filtros robusto
```

Para comparar con la versión anterior de los filtros (NO cambia la votación):

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --filtros original
```

Diagnóstico de una fotografía en modo sin ventana/YOLO, mediante ROI manual de **un ejemplo específico**, no una coordenada que deba fijarse para la cámara real:

```powershell
python iniciar_calidad.py --imagen imagenes_prueba/1995.jpg --roi 360 447 523 1020 --sin-ventana --filtros robusto
```

Para investigar errores en la cámara, agregue `--guardar-muestras` para guardar los recortes muestreados. Use `--mostrar-mascara` solo si desea abrir una ventana **adicional** con la máscara de segmentación; no hace falta para evaluar.

## Qué cambia técnicamente

El nuevo archivo `inspeccion_robusta.py` envuelve al análisis físico existente en `calidad_impresion.py`, sin modificar su método de identificación de defectos.

1. **Evaluación de la captura ANTES de aceptar su resultado.** Mide rango útil de luminancia, contraste cromático local, fracción de saturación, ruido de alta frecuencia y detalle/gradientes relativos al contraste. Estas magnitudes son *de calidad de imagen*, no un defecto de tinta.
2. **Color LAB conservado.** Una tinta diferente al material en color, pero similar en brillo, no se descarta como ilegible solo por su valor de grises.
3. **CLAHE moderado (solo luminancia).** Cuando una primera inspección es dudosa, genera una versión con contraste local limitado para corroborar sin modificar permanentemente la imagen ni perder la información de color.
4. **Reducción suave de ruido, bajo demanda.** Si el estimador encuentra ruido importante, utiliza un filtro bilateral ligero para una segunda inspección, tratando de conservar los bordes. No inventa ni reconstruye trazos ausentes.
5. **Concordancia de resultados y de máscaras.** Si la primera y segunda inspección discrepan, o la máscara cambia excesivamente, no declara un defecto con esa única captura: el resultado interno pasa a `REVISAR`.
6. **Protección ante resolución insuficiente.** Trazos de aproximadamente un píxel no contienen suficiente detalle para comprobar pequeñas roturas, aunque puedan verse como caracteres. Se evita una falsa conclusión segura.
7. **Votación temporal intacta.** Las imágenes de calidad de captura insuficiente se omiten como votos; el seguimiento mantiene múltiples imágenes del mismo producto y finalmente emite `BIEN` o `MAL`. Si faltan evidencias, el motivo registrado es **INSPECCION INSUFICIENTE**, no «tinta defectuosa confirmada».

Se preservan máscaras para diagnóstico y las métricas `camara_*`, `concordancia_mascaras` y `segunda_pasada` se incluyen en el resultado de inspección. No se emplean OCR, longitud ni cantidad de caracteres para clasificar.

## Límites y validación que todavía hace falta

Estas reglas son **umbrales experimentales**, no están calibradas para una cámara real. Una cámara con desenfoque crónico, reflejos sobre plástico o contraste óptico insuficiente puede entregar muchas muestras `REVISAR`. El sistema entonces terminaría en **`MAL` por inspección insuficiente** para evitar aprobar sin evidencia. Esto **no significa que la impresión sea defectuosa**.

**No existe un filtro capaz de reconstruir físicamente trazos que la óptica nunca registró.** Hay que medir la distancia, foco, velocidad de banda, tiempo de exposición, iluminación y mínimo grosor de tinta en píxeles. El uso de un sensor/encoder sincronizado se recomienda antes de automatizar una expulsión física.

Validar con imágenes de la cámara y condiciones reales (buena/mala impresión etiquetadas por una persona): ruido, brillo, luz baja, paquetes de distintos materiales, velocidad máxima y escenas con varios productos. Evaluar **por producto**, no por fotograma.

## Pruebas locales realizadas

La batería automatizada ahora tiene **34 pruebas**, incluidas degradaciones sintéticas de ruido, contraste extremadamente bajo, desenfoque severo y trazos submuestreados, además de ejemplos reales con recortes manuales. No se probó una cámara ni YOLO real en este entorno; no se ha medido una precisión industrial ni un FPS de producción.

Ejecutar:

```powershell
python -m unittest discover -s pruebas -p "test_*.py" -v
```

Referencias técnicas:

- CLAHE: https://docs.opencv.org/4.12.0/d5/daf/tutorial_py_histogram_equalization.html
- Filtrado bilateral: https://docs.opencv.org/4.12.0/d4/d86/group__imgproc__filter.html
- Umbralización adaptativa: https://docs.opencv.org/4.12.0/d7/d4d/tutorial_py_thresholding.html
- Importancia de exposición y sincronización en la banda: https://www.keyence.com/products/vision/resources/guides/what-are-shutter-speed-and-exposure-time.jsp

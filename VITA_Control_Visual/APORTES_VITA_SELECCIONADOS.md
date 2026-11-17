# Nutreo — mejoras seleccionadas de VITA v0.1

## Proyecto principal

Esta versión **continúa sobre Nutreo_COMPLETO_05**. El ZIP VITA_Nutreo_v0.1_20261108(1).zip se utilizó solo como referencia. No se reemplazaron YOLO (`best.pt`), el inspector de tinta, el barrido de continuidad, la auditoría de máscara 05/06, el seguimiento de banda ni la interfaz Tkinter.

## Funciones incorporadas

1. **Guardia de captura (`captura_segura.py`)**: adapta la validación del flujo de VITA. Antes de ejecutar YOLO, examina si la escena está negra, prácticamente uniforme o si se están entregando fotogramas iguales. Un cuadro no útil **no llega al detector y no suma votos**. Los cuadros idénticos al anterior tampoco se cuentan como nuevas muestras; un periodo prolongado de cuadros repetidos se reporta como posible congelamiento de la fuente.
2. **Elección de controlador y resolución**: nuevos campos `Controlador` (auto, msmf o dshow) y `Resolución solicitada` (automática, 1280x720, 1920x1080) en `interfaz_nutreo.py`. Windows puede presentar la cámara del celular bajo MSMF aunque DirectShow no funcione. Si el controlador elegido no puede abrir la cámara, se prueban otros. La resolución solicitada es orientativa: la cámara puede entregar otra.
3. **Diagnósticos Sobel/Tenengrad en la ROI**: las métricas `gradiente_tenengrad` y `anisotropia_gradiente` se calculan solo cuando Nutreo toma una nueva muestra. Se guardan con los datos de evidencia; ayudan a comparar movimientos y desenfoque sin declarar MALA una tipografía inclinada por tener una medida alta. La calidad de captura existente de `inspeccion_robusta.py` sigue siendo la que decide si el recorte es evaluable.
4. **Cierre seguro ante caída de cámara**: si la fuente falla durante una inspección en curso, el producto pendiente se registra `NO PASA` por **INSPECCIÓN INTERRUMPIDA**, no por defecto de tinta. Se conserva el resultado de productos que ya estaban decididos; la cámara no debe fabricar una aprobación a partir de un flujo congelado.
5. **Herramienta `diagnosticar_camaras.py`**: prueba índices y controladores de cámara sin cargar YOLO; imprime resolución real recibida, fotogramas útiles y FPS aproximados. Útil para comprobar webcams virtuales de celular, USB y dispositivos conectados por Enlace Móvil.

## Funciones deliberadamente no incorporadas

- Reconocimiento OCR, plantillas de fecha, requisitos fijos de longitud y comparación de fechas o lotes.
- OpenVINO y exportaciones a modelos alternativos.
- El consenso basado en lecturas de caracteres de VITA, porque Nutreo evalúa la calidad **física** de la impresión sin conocer el contenido del texto.
- La selección automática de la primera cámara con imagen: podría escoger la cámara equivocada. Nutreo deja elegir el índice manualmente.

## Uso

Instala dependencias (desde la carpeta del proyecto):

```powershell
python -m pip install -r requirements.txt
```

Abre la interfaz:

```powershell
python interfaz_nutreo.py
```

Para probar la cámara del celular sin abrir YOLO:

```powershell
python diagnosticar_camaras.py --backend msmf --max-indice 6 --resolucion 1280x720
```

Si no aparece, prueba `--backend dshow`. En la interfaz selecciona el índice que entregó imagen útil. Para una cámara lenta, comienza con **1280x720**; para detalles de impresión difíciles, compara la nitidez y los tiempos con **1920x1080**. Ambos dependen de la cámara y del hardware real.

## Verificación de software

Desde la carpeta `Nutreo_Control_Calidad`:

```powershell
python -m unittest discover -s pruebas -p "test_*.py" -v
python validar_barrido.py
python verificar_etapa05.py
```

Los tests nuevos verifican rechazo de cuadros negros, uniformes y congelados, que cuadros idénticos no multipliquen votos, diagnóstico de gradiente y cierre preventivo cuando se pierde la cámara. También hay pruebas integradas con detector y video **simulados** para verificar el paso por el trabajador de la interfaz.

## Limitaciones para puesta en producción

- Una imagen muy oscura o lisa puede ser un empaque legítimo. Por seguridad se omite la captura; es un problema de inspección, no una condena automática a la tinta.
- Un checksum igual tras reducir la imagen sirve para detectar cuadros repetidos, pero puede considerar iguales escenas realmente estáticas. El intervalo de muestra y el seguimiento continúan intactos.
- Una cámara virtual puede bloquearse aun mostrando una imagen dinámica; una imagen de candado no siempre puede reconocerse con reglas generales de luminancia. Para ello hay que validar con la fuente real.
- La pérdida de señal y la mala calidad de impresión son categorías distintas. No utilizar NO PASA por falla de captura como indicador de defecto de fábrica.
- Estas verificaciones **no demuestran una tasa de acierto industrial**. Requieren probar con la cámara real, velocidades de banda y productos etiquetados por una persona. En este entorno no se ha ejecutado Ultralytics sobre la cámara física.

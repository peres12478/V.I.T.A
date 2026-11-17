# V.I.T.A. — Panel nativo para el personal de Nutreo

**Proyecto:** V.I.T.A. — Visión artificial para inspección. Nutreo es la empresa destinataria.

## Iniciar sin navegador ni servidor

1. En Windows, descomprime el paquete completo y abre la carpeta `Nutreo_Control_Calidad`.
2. Instala las dependencias desde esa carpeta: `python -m pip install -r requirements.txt`.
3. Ejecuta **`python panel_operador.py`** o haz doble clic en `INICIAR_PANEL_OPERADOR_WINDOWS.bat`.
4. En la ventana selecciona **Cámara** (0, 1, etc.); pulsa **Buscar** para explorar los índices disponibles. Si no aparece en el sondeo, puedes escribir el número manualmente. Elige un **Controlador** (Auto, MSMF o DirectShow) y resolución.
5. Si quieres, introduce datos de **Línea y Turno** (son opcionales y no intervienen en la inspección). Pulsa **INICIAR**.
6. Visualiza la cámara en vivo, estado, último producto, resumen de la sesión e historial. **DETENER** finaliza la inspección de forma segura.
7. El historial se guarda en `registros_operador/` y se exporta a CSV desde la misma ventana. En la pestaña **Historial y exportación** se muestran exclusivamente **Producto, Resultado, Buenas, Malas, Inciertas, Línea y Turno**, en ese orden. El CSV tiene esas mismas siete columnas, sin fecha/hora, lote, referencia ni explicación. Las evidencias (fotograma original, máscara 05, sospechas 06, métricas) se almacenan en `evidencias_operador/`.

**No hay HTTP, servidor local, pestaña de navegador, JPEG ni puertos de red.** La ventana utiliza Tkinter/Pillow para mostrar el fotograma BGR producido por el motor.

## Dos interfaces, un solo análisis

- **Centro técnico:** `python interfaz_nutreo.py` — modelo YOLO, controles técnicos, filtros, máscaras y calibración.
- **Panel de planta:** `python panel_operador.py` — operación sin ajustes de diagnóstico.

Ambos importan y ejecutan las **mismas clases `Trabajador`, `ProcesadorNutreo` e `InspectorCalidadRobusto`** desde `interfaz_nutreo.py`, `inspeccion_robusta.py` y todos los módulos OpenCV existentes. No hay un detector simplificado en la interfaz de planta.

El panel de planta solicita `captura_reciente=True`, que usa un hilo de lectura de cámara y conserva el fotograma más reciente, evitando que YOLO procese imágenes acumuladas. También usa `evidencia_asincrona=True` para escribir recortes/máscaras en otro hilo. **Estas optimizaciones no eliminan las etapas de control de calidad ni cambian la votación.** Las máscaras siguen analizándose aunque no se muestren como seis paneles técnicos.

En el panel de planta se muestran `fps_analisis`, duración por análisis y fotogramas omitidos cuando el motor dispone de esas mediciones.

## Limitaciones y uso responsable

- Un resultado **NO PASA preventivo** por falta de evidencia, cámara interrumpida o votos insuficientes debe distinguirse de un defecto físico confirmado. El historial conserva esa distinción.
- No es un sistema calibrado o certificado para controlar rechazos industriales de forma autónoma. Antes de operar como control de producción, validar en la banda real con muestras buenas y defectuosas supervisadas.
- La conexión inalámbrica del celular puede limitar FPS. Probar resolución 1280x720, controlador MSMF o DShow y, si es posible, USB con modo webcam compatible.
- La resolución y el índice de cámara se seleccionan **antes** de iniciar. No abras ambas interfaces con la misma cámara simultáneamente.
- El modelo `best.pt` y las dependencias Python siguen siendo necesarios. El paquete **no incluye el entorno virtual ni PyTorch/Ultralytics preinstalados**: la primera instalación puede requerir descargas.
- El código no instala OCR ni OpenVINO.

## Verificaciones

```powershell
python -m unittest discover -s pruebas -p 'test_*.py'
```

Para pruebas sin cámara también se proporciona `python verificar_etapa05.py`.

## Historial simplificado (versión de planta)

En el formulario solo aparecen **Línea** y **Turno**. El CSV exportado respeta este orden:

`Producto,Resultado,Buenas,Malas,Inciertas,Línea,Turno`

Las fechas, motivos técnicos y evidencias siguen conservándose **internamente** para trazabilidad y diagnóstico; no se muestran ni se exportan desde este informe simplificado. Los históricos creados por versiones anteriores continúan siendo legibles.

# V.I.T.A. — Integracion de escritorio y mejora de captura

## Arquitectura entregada

La base del proyecto se conserva: `interfaz_nutreo.py` sigue siendo el centro técnico y `ProcesadorNutreo` sigue siendo el único procesador para detección de fechas, inspección de tinta, seguimiento y votos. La aplicación para el personal de Nutreo ahora se inicia con `panel_operador.py` como ventana nativa Tkinter.

**Se retiró la interfaz web del operador y su servidor HTTP local.** No hay endpoint de cámara, transmisión MJPEG/JPEG, puerto 8767, navegador, ni servidor embebido. Las imágenes viajan desde el trabajador a la GUI por una cola de memoria limitada a los cuadros más recientes.

### Etapas de inspección conservadas

1. YOLO con `best.pt` delimita la fecha.
2. `InspectorCalidadRobusto` aplica el análisis de la máscara, contornos, distribución y calidad de tinta, barrido de continuidad, detección de arrastre y auditoría de la etapa 05.
3. `SeguimientoBanda` agrupa los votos por producto y aplica las reglas de cierre, mínimos y mayoría.
4. `evidencia_inspeccion.py` registra recorte original, máscara 05, sospechas 06, métricas y motivo de la muestra.
5. `RegistroEventos` guarda cada producto en CSV; `historial_operador.py` consulta, filtra y exporta.

Se mantiene el mismo comportamiento de voto entre el centro técnico y el panel de planta; `mostrar_etapas=False` en el panel solo evita construir miniaturas para la GUI, NO evita los cálculos internos.

### Cambios de rendimiento

- `camara_buffer.py` implementa un hilo de lectura continua para cámara: solo se analiza el fotograma nuevo más reciente, evitando que YOLO procese una cola de imágenes atrasadas.
- `evidencia_en_cola.py` guarda imágenes y métricas en un hilo dedicado. Al cerrar se vacía la cola. No se pierden evidencias por descartar la cola.
- Renderizado nativo con OpenCV BGR → PIL → Tkinter, limitado a aproximadamente 15 actualizaciones por segundo, sin convertir a JPEG para la interfaz.
- Diagnóstico de FPS de análisis, duración por fotograma y cantidad aproximada de imágenes descartadas si YOLO trabaja más lento que la cámara.
- Se preserva el bloqueo de votos con imágenes congeladas o sin señal.

**No se promete una mejora fija en FPS:** el rendimiento final depende del hardware, la calidad del enlace inalámbrico y el modelo YOLO. La omisión de cuadros antiguos no significa omitir análisis de alguna muestra ya admitida para votar; las muestras solo se cuentan cuando `SeguimientoBanda` las evalúa.

### Controles del personal de planta

- Cámara configurable en la GUI (índices manuales y búsqueda opcional), backend Auto/MSMF/DirectShow y resolución.
- Iniciar/detener desde la ventana, sin argumentos obligatorios.
- Cámara en vivo, estado y razón de inspección, votos, último producto, contadores y apartado de historial con exportación CSV.
- Campos opcionales de línea y turno; nunca determinan la clasificación visual.
- Distinción de rechazo por defecto frente a cierre preventivo por insuficiencia de evidencia.

### Verificación y limitaciones

Se ejecutan las pruebas unitarias originales y las adicionales del panel nativo y captura asíncrona. Una prueba gráfica de Tkinter bajo una pantalla virtual comprueba que la interfaz abre sin cámara. No se dispone aquí de la cámara del usuario ni del hardware de la banda, por lo que falta verificar FPS, precisión y robustez con muestras físicas. No instalar ni usar OCR ni OpenVINO.

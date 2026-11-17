> **Actualizacion posterior al informe:** el inspector restringe el analisis
> de barridos y halos a la proximidad de la tinta, excluye bandas largas
> ajenas al sello y muestra motivos de incertidumbre medibles. La interfaz
> reutiliza resultados hasta recibir una nueva muestra. Leer
> `MEJORA_FOCO_EXCLUSIVO_TINTA.md` para las reglas actuales y las limitaciones.

> NOTA DE VERSION: Este informe describe la evaluacion fisica; la politica de votacion vigente se detalla en `CAMBIOS_MAYORIA_REAL.md`. Las condiciones antiguas de cantidad minima no vetan una mayoria favorable.

# Informe técnico — control de calidad física de fechas impresas

**Alcance:** análisis de la tinta, no verificación semántica de fechas. **Estado:** prototipo con análisis por fotograma y votación temporal binaria por producto; sin validación industrial.

## 1. Diagnóstico de los materiales recibidos

El ZIP del proyecto suministrado incluye `best.pt`, `hola.py` y dos ejemplos en `Probe`. El código original usa Ultralytics YOLO para localizar una fecha en la cámara y dibujar la predicción; no tiene lógica de control de calidad. El otro ZIP aporta 10 fotografías distintas de empaques, varias con brillo, pliegues y fondo coloreado. Los nombres no proporcionan una etiqueta de verdad-terreno (BIEN/MAL), por lo que **no es metodológicamente válido** usarlas para entrenar un clasificador supervisado sin revisión humana.

Dos ejemplos contrastantes, procesados con recortes manuales **solo para verificar el módulo OpenCV**:

| Foto | Zona manual original [x1,y1,x2,y2] | Resultado inicial | Lectura técnica | 
| --- | --- | --- | --- |
| `1995.jpg` | `[360,447,523,1020]` | `MAL` | El operador de barrido detecta marcas lineales prolongadas que atraviesan la zona de tinta; podrían corresponder a arrastre, pero deben etiquetarse manualmente. |
| `1757.jpg` | `[458,558,565,940]` | `REVISAR` | Contraste local irregular/reflejos: no hay evidencia para condenar ni aprobar con seguridad. |
| `1806.jpg` | `[340,425,500,1030]` | `BIEN` | No se detectó un indicio físico grave en ese recorte; no significa aprobación certificada. |

Los resultados dependen del recorte: ampliar la ROI hasta incluir arrugas o gráficos puede cambiar un BIEN a REVISAR. Por eso importa verificar las cajas producidas por YOLO.

No se dispone aquí del paquete `ultralytics` ni del acceso físico a la cámara: **no se han medido los FPS totales ni el desempeño de `best.pt`**. La integración lógica está implementada, pero su validación final corresponde al PC de producción.

## 2. Comparación de tecnologías

| Familia | Ventajas | Riesgos | Uso propuesto |
| --- | --- | --- | --- |
| Procesamiento clásico: Lab, corrección de luz, morfología, distancia, componentes | Rápido, interpretable, poco entrenamiento; localiza algunas manchas y trazos deformes | Umbrales sensibles a sustrato/iluminación, inferencia de letras truncadas sin referencia es ambigua | **Activo hoy como tamizaje inicial** |
| Aprendizaje supervisado por descriptores | Aprende cuándo una irregularidad física es aceptable | Requiere muestras bien etiquetadas y distintas por empaque/lote | Random Forest **opcional**, a entrenar después de anotación |
| Anomalía profunda basada en muestras sanas (EfficientAD / PatchCore) | Detecta patrones físicos anómalos sin enumerar todas las fallas posibles; devuelve mapas locales | Cambios de material, posición, brillo y tipografía también pueden parecer anomalías; demanda datos normales y validación | **Candidato para siguiente fase** sobre ROI de impresión, condicionado a datos reales |
| OCR auxiliar | Contribuye a estimar legibilidad de un código específico | Puede fallar con fuentes dot-matrix y fechas válidas de formatos nuevos | Solo como **evidencia auxiliar**, nunca por longitud/caracteres |

EfficientAD (WACV 2024) presenta un modelo student-teacher de baja latencia en GPU: https://openaccess.thecvf.com/content/WACV2024/html/Batzner_EfficientAD_Accurate_Visual_Anomaly_Detection_at_Millisecond-Level_Latencies_WACV_2024_paper.html

PatchCore (CVPR 2022) emplea un banco de características nominales: https://openaccess.thecvf.com/content/CVPR2022/html/Roth_Towards_Total_Recall_in_Industrial_Anomaly_Detection_CVPR_2022_paper.html

Implementación y opciones en Anomalib:
- https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html
- https://anomalib.readthedocs.io/en/stable/markdown/guides/reference/models/image/efficient_ad.html

Limitaciones de generalización documentadas en conjuntos industriales reales:
- https://doi.org/10.1016/j.compind.2024.104151
- https://ieeexplore.ieee.org/abstract/document/11701006 (análisis de iluminación y resolución en MVTec AD 2, 2026)

Morfología implementada con OpenCV:
- https://docs.opencv.org/doc/doxygen/html/d9/d61/tutorial_py_morphological_ops.html
- https://docs.opencv.org/4.12.0/d3/dbe/tutorial_opening_closing_hats.html

## 3. Arquitectura propuesta

```
CAMARA / VIDEO
    |
    v
YOLO best.pt (solo encuentra regiones de fecha; no hace OCR)
    |
    v
ROI por fotograma (con margen minimo)
    |
    +--> Normalizar iluminación local en CIELAB, elegir polaridad y contraste
    |    de tinta oscura / clara / cromática
    |
    +--> Máscaras fuerte/tenue; componentes conectados; distancia
    |    de trazos; cierre morfológico pequeño; contornos implícitos
    |
    +--> Anomalías: manchas de grosor extremo, barridos lineales
    |    multiorientación, tinta tenue y posibles discontinuidades
    |
    +--> (Opcional) modelo supervisado con etiquetas humanas
    |
    +--> (Fase futura) EfficientAD entrenado con suficientes muestras sanas
    |
    v
BIEN / MAL / REVISAR (SIN FECHA si YOLO no detecta)
    |
    v
PANTALLA con imagen real, ROI, motivo y métricas instrumentables
```

### 3.1. Integración temporal para banda transportadora (nueva)

La decisión del analizador de tinta para **un fotograma** puede ser `BIEN`, `MAL` o `REVISAR` por incertidumbre. La decisión de inspección de **un producto** es obligatoriamente **`BIEN` o `MAL`**: se implementa por separado en `seguimiento_banda.py`.

```text
YOLO detecta fecha -> inspector fisico de tinta -> resultado por fotograma
               |                            |
               +--> asociacion de cajas -> producto_id unico
                                            |
                                muestras espaciadas (ej. 75 ms)
                                            |
                        votos validos BIEN / MAL (REVISAR se omite)
                                            |
                         al alcanzar 7 votos, o salir de escena
                                            |
                 mayoria -> BIEN o MAL; empate -> MAL
                       muestras insuficientes -> MAL preventivo
                                            |
                    CSV UNA FILA POR PRODUCTO + pantalla
```

Parámetros iniciales: `--fotos 7`, `--min-fotos 3`, `--intervalo-ms 75`, `--ausencia-ms 350`, `--max-sin-ver 5`, `--min-fraccion 0.5` y `--max-muestras 24`. **Ninguno de estos valores es un estándar probado en la banda de Nutreo.**

**Caso**: 5 BIEN y 2 MAL -> producto BIEN. 2 BIEN y 5 MAL -> producto MAL. 2 BIEN y 2 MAL antes de abandonar la cámara -> MAL por empate. 1 BIEN y 5 ambiguas -> MAL con motivo de **inspección insuficiente**, sin afirmar que la tinta sea físicamente defectuosa.

La asociación usa predicción simple del movimiento, solapamiento entre cajas y consistencia de área, no reconocimiento del texto. Dos fechas cercanas o paquetes pegados podrían intercambiar IDs; en instalación productiva agregar **sensor de presencia, barrera fotoeléctrica, encoder y/o seguimiento con identidad física**, además de validar distancias de rechazo. Una decisión en pantalla no activa ningún expulsor en esta versión.

**Precaución estadística:** los fotogramas de una misma fecha no son muestras independientes; la mayoría mitiga fluctuaciones transitorias del clasificador pero no reemplaza un modelo de defectos validado. Deben medirse sensibilidad, especificidad, pérdidas de seguimiento y falsas aprobaciones por **paquete completo** y por tipo de material.

La normalización local minimiza variaciones suaves de iluminación; la elección de tinta clara/oscura admite substratos de múltiples colores. La dirección de trazos se inspecciona con elementos estructurantes rotados; el diámetro local se aproxima a partir de la transformada de distancia del interior de la máscara. Se priorizan **evidencias concordantes**, no pequeños cambios de píxel. La calibración de umbrales deberá realizarse con defectos reales y muestras de referencia aprobadas, separando datos por lotes/colores/materiales.

**Punto importante:** el cierre morfológico no demuestra por sí solo que faltó tinta; la forma normal de algunos números y fuentes discontinuas puede producir el mismo patrón. Del mismo modo, un carácter grande no constituye por sí solo una acumulación anormal. Por eso existe REVISAR y la recomendación de entrenar sobre piezas reales.

## 4. Generalización: cómo entrenar sin memorizar fechas

La representación debe estar centrada en **textura y geometría de la tinta**, no en patrones del texto. Para EfficientAD, entrenar con ROI rectificada, normalizada y con fondo minimizado, y no con empaques completos llenos de otras etiquetas. Aun así, hay que incluir fechas de numerosas longitudes, fuentes, tamaños y orientaciones, además de superficies mate, brillantes, metálicas, azules, amarillas, blancas y otras realmente presentes en planta.

Una forma de avanzar:

1. Registrar imágenes *sanas verificadas* y *defectuosas verificadas*, con captura de alta nitidez y anotación opcional de máscara de defecto.
2. Separar el conjunto de prueba por **material + lote + día de captura** y, si es posible, por máquina/línea. No dividir fotogramas adyacentes al azar.
3. Añadir ejemplos de defectos reales: impresiones tenues, parcialmente ausentes, corridas, solapamientos, manchas y caracteres deformes. Anotar el impacto en legibilidad sin forzar formatos.
4. Comparar sobre el mismo conjunto tres modelos: clásico solo, clásico + RF, clásico + EfficientAD/PatchCore.
5. Medir falsos aprobados de piezas realmente malas, falsos rechazados de buenas, recall de defectos críticos, sensibilidad por material, latencia p50/p95 y consistencia de fotogramas.
6. Elegir umbrales según riesgo industrial y pruebas ciegas; no usar como rechazo automatizado un modelo que no se haya validado en empaques nunca vistos.

La **lectura humana** o un OCR opcional puede añadir evidencia de legibilidad, pero un OCR que no reconoce algo no significa necesariamente que está defectuoso. No se debe rechazar por número de caracteres, sintaxis ni longitud esperada.

## 5. Factores físicos imprescindibles

- **Iluminación difusa** y, para plásticos brillantes, ensayar polarización cruzada. Evitar flashes puntuales que oculten tinta.
- **Distancia fija y enfoque controlado**; lograr varios píxeles por grosor de trazo. Un defecto inferior a la resolución óptica no puede reconstruirse por software de manera fiable.
- **Tiempo de exposición suficiente** para congelar el movimiento sin blur; bloquear ganancia, exposición y balance de blancos si es posible.
- **ROI de tinta bien delimitada**, con margen moderado que incluya arrastres pero no textos decorativos y códigos de barras cercanos.
- **Pruebas bajo cambios de lote y material**, especialmente reflexión especular, bolsas arrugadas y diseños con impresiones de color similar al fondo.

## 6. Estado de desarrollo

**Implementado y probado**: analizador OpenCV de tinta, clasificación individual triestado, visualización de decisión final binaria por producto, asociación temporal por geometría, integración por fotograma, prueba en imagen con ROI manual, registro CSV y 34 tests automatizados (incluida integración con YOLO simulado). Se conservan el modelo YOLO y fotografías originales del usuario. El clasificador supervisado opcional tiene entrenamiento y carga integrados, **pero no se ha entrenado sin etiquetas**.

**No demostrado todavía**: calidad/cuantificación del detector YOLO real en cámara, conservación de identidad entre productos adyacentes en la banda, velocidad extremo a extremo en Windows, generalización a empaques nuevos, reconocimiento seguro de todos los defectos enumerados y verificación completa de legibilidad. La interfaz no sustituye ensayos industriales ni inspección humana en casos ambiguos.


## Actualizacion: calidad de captura y preprocesamiento robusto

El nuevo `inspeccion_robusta.py` agrega evaluacion prudente de ruido, contraste luminico/cromatico, detalle fino y saturacion, y segunda pasada con CLAHE ligero o filtro bilateral, para que una captura insuficiente no sea interpretada como defecto fisico de tinta. Cambios, pruebas y limites: `CAMBIOS_FILTROS_CAMARA.md`. Se preserva la votacion binaria y no se usa OCR ni formato de fecha para clasificar.

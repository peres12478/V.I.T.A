**Camara de celular / Wi-Fi:** consulta [`MEJORA_CAMARA_CELULAR_INALAMBRICA.md`](MEJORA_CAMARA_CELULAR_INALAMBRICA.md) para evitar parpadeo de ZONA SEGURA y diagnosticar frames repetidos.

# NUEVO: Panel operativo para el personal de Nutreo

El proyecto incluye **dos interfaces que comparten el mismo motor de inspección**:

- `python interfaz_nutreo.py`: centro técnico de calibración y pruebas.
- `python panel_operador.py`: panel **de escritorio** para el personal de Nutreo. El operario selecciona cámara y controlador dentro de la ventana. Sin navegador, HTTP ni servidor local. Usa el mismo motor YOLO+OpenCV del centro técnico, con historial y exportación CSV.
  Los campos de producción del panel son **Línea** y **Turno**. El historial visible y CSV exportado muestran **Producto, Resultado, Buenas, Malas, Inciertas, Línea, Turno**; no incluyen hora ni explicación.

El nuevo modo mantiene todos los archivos, modelos, detectores y pruebas existentes. No usa OCR ni OpenVINO. **No abras ambos modos a la vez en el mismo PC**, porque compiten por la cámara. La interfaz web no controla PLC ni actuadores. Consulta [`MODO_OPERADOR_NUTREO.md`](MODO_OPERADOR_NUTREO.md) antes de utilizar el panel en planta.

---

# BARRIDO ADAPTATIVO DE CONTINUIDAD — VERSION ACTUAL

Lee primero **`BARRIDO_CONTINUIDAD_TINTA_2026.md`**. Este proyecto conserva
YOLO (`best.pt`), OpenCV, la interfaz de Windows y los votos por producto.
Se anadio un barrido geometrico para detectar franjas de tinta borradas dentro
de la fecha, **sin OCR, OpenVINO ni conteo de caracteres**. La etapa 06 ahora
muestra las lineas virtuales cuando se localiza una ausencia de tinta.
Ejecuta `python interfaz_nutreo.py`. Prueba recortes sin camara con
`python validar_barrido.py`. Las secciones siguientes documentan versiones
historicas; la documentacion de este apartado prevalece donde una regla difiera.

---

# CORRECCION DE VOTOS Y TRAZOS (NUEVA VERSION)

Lea primero `CORRECCIONES_VOTOS_Y_TRAZOS.md`. El campo Max. fotos es un limite superior: con al menos 5 BUENAS y mas BUENAS que MALAS, el producto puede PASAR aunque salga antes de alcanzar el maximo. Nuevo detector conservador de tinta debilitada. Sin OCR/OpenVINO.

---

# Nutreo — actualizacion de calibracion de arrastre (noviembre 2026)

La version actual incluye `deteccion_arrastre_interno.py`, que corrige un falso BIEN
reportado en `11550.jpg`. El **recorte por defecto es 12 %**, no 15 %,
para evitar cortar partes de la franja en algunas fechas. No se usa OCR ni
conteo de caracteres. Ejecutar `python interfaz_nutreo.py`. Para probar los
recortes incluidos sin YOLO ni camara, `python validar_calibracion.py`.

Lee **[`CALIBRACION_ARRASTRE_2026.md`](CALIBRACION_ARRASTRE_2026.md)** antes
de usar un rechazo automatico en la banda: esta validado por pruebas de software,
no por suficientes ejemplos industriales etiquetados.

---

# ACTUALIZACION: ENFOQUE EXCLUSIVO EN TINTA Y RENDIMIENTO

Esta version incluye mejoras contra falsas alertas por bordes de etiquetas,
rayas del fondo y sombras que no pertenecen a la fecha. El resultado de la
etapa **06 Zonas sospechosas** usa un entorno pequeno de la tinta; los fallos
de camara se muestran por separado. Ademas, las miniaturas solo se actualizan
cuando se admite una nueva captura, y las fotos claramente buenas evitan una
segunda inspeccion costosa.

**Iniciar GUI:** `python interfaz_nutreo.py`.
**Leer detalles y limitaciones:** [`MEJORA_FOCO_EXCLUSIVO_TINTA.md`](MEJORA_FOCO_EXCLUSIVO_TINTA.md).
**Reglas de banda conservadas:** 7 capturas por defecto, minimo 5 BUENAS,
mayoria BUENAS > MALAS, zona segura y mismo producto hasta salir.

---

# ACTUALIZACION ACTUAL: zona segura y minimo cinco BUENAS

**Archivo principal:** `python interfaz_nutreo.py` (Windows / VS Code).

YOLO encuentra el recuadro pero NO se evalua hasta que entra completamente
al margen seguro (8% de cada borde de la imagen) y conserva un tamano
consistente durante 3 detecciones. Esto no supone que el producto este quieto:
puede avanzar por la banda.

**Decision final:** se deben completar 7 capturas y tener **al menos 5
BUENAS y mas BUENAS que MALAS**. Las inciertas no suman votos y sí ocupan
una captura. 1 BUENA contra 0 MALAS + 6 inciertas => **NO PASA**. Las
salidas prematuras reciben **NO PASA por inspeccion incompleta**.

Nuevos controles GUI: **Min. buenas = 5**, **Margen zona = 8%**,
**Confirmaciones = 3**. No usa OCR, umbrales de longitud ni conteo de
caracteres. Mira `CAMBIOS_ZONA_SEGURA_Y_5_BUENAS.md` para detalles.

> NOTA: Las secciones historicas siguientes describen versiones anteriores;
> si hay discrepancias, PREVALECE la politica de esta actualizacion.


## Actualizacion: recorte de fecha sin codigo de barras

Se redujo el area de inspeccion sobre el eje corto de la caja YOLO para
evitar considerar el borde de la etiqueta como defecto fisico de la tinta.
El ajuste inicial de esta version es **12% por lado**. En `interfaz_nutreo.py` puedes usar el
campo **Reducir alto (%)** (0 a 30) antes de pulsar INICIAR.
El recuadro dibujado y los seis paneles muestran el area verdaderamente
analizada, no una caja distinta. Ver `CAMBIOS_RECORTE_ETIQUETA.md`.

Para la version sin interfaz:
`python iniciar_calidad.py --camara 0 --fotos 7 --recorte-borde 15`

# Nutreo | Control visual de calidad de tinta

**Prototipo funcional de inspección, NO sistema industrial validado.**

Este proyecto conserva `best.pt` y analiza cada fotograma en tiempo real: **cámara -> YOLO (fecha) -> evaluación física de tinta -> seguimiento de la MISMA fecha -> voto temporal -> resultado BINARIO por producto**.

**Modo banda (cámara o vídeo): la decisión FINAL únicamente es `BIEN` o `MAL`.** Mientras se reúnen las muestras aparece `ANALIZANDO`, que no es un tercer resultado final. La inspección individual sigue siendo BIEN/MAL/REVISAR internamente, pero `REVISAR` no cuenta como voto. Si faltan fotos evaluables, se rechaza preventivamente como `MAL` con la causa **INSPECCION INSUFICIENTE** para no confundirlo con un defecto de tinta confirmado.

**No examina número de caracteres, longitud, formato, orden, año ni validez de una fecha.** No se emplea OCR para decidir calidad. El término BIEN significa «sin evidencia grave según las reglas iniciales»; no equivale a certificación. `REVISAR` protege las muestras individuales ante ambigüedad; no aparece como decisión final por producto.

## NUEVA INTERFAZ GRAFICA (recomendada)

El **archivo principal de la nueva interfaz es `interfaz_nutreo.py`**.
Este nuevo archivo Python abre la camara en color, enseña las etapas de
filtrado y muestra `ESPERANDO PRODUCTO`, `EVALUANDO PRODUCTO`, `PASA` o
`NO PASA`, con historial de productos y votos. No requiere abrir otras
ventanas de OpenCV. Los filtros se ven dentro de la misma interfaz.

```powershell
python -m pip install -r requirements.txt
python interfaz_nutreo.py
```

También puedes usar `./.venv/Scripts/python.exe interfaz_nutreo.py` en
Windows (en PowerShell: `.\.venv\Scripts\python.exe interfaz_nutreo.py`).
Consulta **[GUI_NUTREO.md](GUI_NUTREO.md)** para ver la instalación paso a paso.

El programa anterior `iniciar_calidad.py` sigue funcionando de forma
independiente si deseas utilizar solo la ventana tradicional.

## Nuevo: filtros robustos para distintas cámaras

El programa tradicional sin interfaz sigue arrancando con `iniciar_calidad.py`. Por defecto utiliza el nuevo `inspeccion_robusta.py`, que mantiene el video BGR **en color**, combina la luminancia y los canales cromáticos LAB y examina el nivel de detalle, ruido y contraste de cada recorte. CLAHE y el filtrado bilateral se usan solo para obtener una comprobación adicional cuando hay sospechas: si los análisis se contradicen, el fotograma se descarta como `REVISAR` y no se confunde un posible desenfoque con mala impresión.

**Vista normal en color, sin máscara adicional:**

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --filtros robusto
```

Para comparar el comportamiento anterior, cambia solo `--filtros robusto` por `--filtros original`. **No agregues `--mostrar-mascara` si no quieres una segunda ventana en blanco y negro.** Más detalles, limitaciones y pruebas en [`CAMBIOS_FILTROS_CAMARA.md`](CAMBIOS_FILTROS_CAMARA.md).

## Requisitos

- Windows 10/11 con una cámara USB que OpenCV pueda abrir, Python 3.10 a 3.12 y conexión a Internet para instalar dependencias por primera vez.
- Se incluye el archivo original `best.pt`, pero **no se ha ejecutado en el entorno de creación de este paquete** porque `ultralytics` no estuvo disponible. Su funcionamiento con tu cámara y sistema deberá verificarse en tu PC.
- Para inspección confiable, iluminar sin reflejos y capturar suficientemente cerca para que cada trazo de tinta ocupe varios píxeles. La calidad óptica es más importante que subir arbitrariamente la sensibilidad del algoritmo.

## Inicio rápido (Windows)

1. Descomprime completamente el ZIP en una carpeta (no ejecutes desde la vista previa del ZIP).
2. Ejecuta **`INICIAR_CALIDAD_WINDOWS.bat`**. Este archivo prepara `.venv`, instala `ultralytics`, `opencv-python`, `numpy` y abre la cámara 0 con el sistema completo.
3. Pon **un empaque en movimiento bajo la cámara**. Veras `ESPERANDO FECHA COMPLETA` y luego `ANALIZANDO 1/7`... hasta la decision; si sale antes se marca NO PASA preventivo por inspeccion incompleta.
4. Presiona **Q** para cerrar, **S** para guardar una captura o **R** para cerrar las pistas y empezar nuevos identificadores. Para guardar automáticamente los recortes individuales utiliza `--guardar-muestras`.
5. Cada producto finalizado queda en `registros_banda.csv` con **una fila por producto, el conteo de votos, la causa y la cantidad de fotos descartadas**.

Alternativa desde CMD/PowerShell, dentro de la carpeta descomprimida:

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python iniciar_calidad.py --camara 0 --fotos 7 --intervalo-ms 75
```

Para seleccionar otra cámara:

```powershell
.venv\Scripts\python iniciar_calidad.py --camara 1
```

## Como funciona la votacion temporal en la banda

- YOLO localiza la fecha y conserva el mismo ID mientras permanezca visible.
- El modulo `validacion_visibilidad.py` confirma zona segura y 3 detecciones
  con tamano consistente; no pide que la banda se detenga.
- Solo entonces se ejecuta la inspeccion de tinta en el recorte existente.
- Se toman 7 fotos TOTALES (incluidas inciertas), separadas >= 75 ms.
- Para PASA son necesarias >= 5 BUENAS y BUENAS > MALAS al finalizar 7 fotos.
- Salida antes de siete fotos: NO PASA por inspeccion incompleta.

Comando de ejemplo:

```powershell
python iniciar_calidad.py --camara 0 --fotos 7 --min-buenas 5 --zona-segura-pct 8 --confirmaciones-fecha 3
```

Guardar las imágenes realmente muestreadas (útil en pruebas, puede ocupar espacio):

```powershell
.venv\Scripts\python iniciar_calidad.py --camara 0 --guardar-muestras
```

Procesar un vídeo guardado de la banda sin abrir ventana y guardar un segundo vídeo anotado:

```powershell
.venv\Scripts\python iniciar_calidad.py --video prueba_banda.mp4 --fotos 7 --sin-ventana --registro registro_prueba.csv --salida-video inspeccion.mp4
```

Si detectas imágenes borrosas que el analizador aún clasifica como válidas, puedes excluirlas con `--min-nitidez VALOR`, pero **no existe un umbral universal**: hay que calibrarlo con imágenes de tu cámara. Por defecto es `0` (filtro de nitidez desactivado); los recortes que la inspección de tinta declara ambiguos ya se descartan del voto.

**Para probar el modo banda sin un archivo de vídeo ni una cámara conectada** ejecuta la batería de 34 tests sintéticos y de integración descrita más adelante. `--imagen` es un **diagnóstico de una foto**, no la votación temporal.

### Importante para la banda física

El seguimiento actual es **geométrico**: funciona mejor cuando las fechas se desplazan de manera continua y los productos tienen separación visible. **Si dos paquetes se tocan, se cruzan, quedan en el mismo punto entre capturas o el detector pierde una fecha**, no se garantiza que las observaciones pertenezcan al mismo producto. Para una línea industrial con rechazos automáticos conviene añadir **sensor de presencia (fotocélula/encoder) y sincronización con el expulsor**, además de medir tiempo de tránsito y velocidad máxima. Una cámara y un algoritmo no garantizan por sí solos la identificación física del paquete.

El mismo defecto físico puede aparecer en varias imágenes correlacionadas; la mayoría reduce ruido ocasional **pero no multiplica automáticamente la precisión** y puede ocultar fallas visibles solo en ciertas orientaciones. La tasa de falsas aprobaciones/rechazos debe validarse **por producto**, no contando fotogramas de un mismo paquete como independientes. Los valores 7, 75 ms y 3 son **configuración de prueba**, no parámetros industriales validados.

Para probar una foto automáticamente con YOLO (requiere `ultralytics`):

```powershell
.venv\Scripts\python iniciar_calidad.py --imagen imagenes_prueba\1995.jpg --salida resultado.jpg
```

Para reproducir **solo** la inspección visual de la foto `1995.jpg` con una zona manual, sin necesidad de cargar YOLO:

```powershell
.venv\Scripts\python iniciar_calidad.py --imagen imagenes_prueba\1995.jpg --roi 360 447 523 1020 --salida resultado.jpg
```

**Esas coordenadas son exclusivas de la fotografía de prueba**. En cámara en vivo, las calcula el YOLO de `best.pt` en cada fotograma. No se memorizan ni reutilizan en futuras imágenes.

Para probar las fotografías de tu ZIP y generar un CSV de resultados:

```powershell
.venv\Scripts\python probar_lote.py --carpeta imagenes_prueba --salida resultados_lote
```

Si deseas analizar con tinta clara en un envase oscuro, el sistema elige polaridad automáticamente, pero puedes forzarla con `--polaridad clara` (también `oscura` o `color`).

## Criterios físicos de evaluación

La inspección utiliza `cv2.COLOR_BGR2LAB` para analizar contraste sobre empaques de diferentes colores, estimación de iluminación local, polaridad de tinta, máscaras adaptativas, componentes conectados, contornos equivalentes a cambios de grosor obtenidos con transformada de distancia, cierres morfológicos pequeños, búsqueda de marcas prolongadas en varias orientaciones y análisis de tinta tenue alrededor de trazos. Estas magnitudes son independientes del formato de la fecha.

**MAL por imagen** exige señales físicas fuertes y no una irregularidad pequeña. **REVISAR por imagen** se usa cuando la muestra resulta tenue o ambigua, o cuando no puede aislarse la tinta. **BIEN por imagen** implica que no se activó un criterio grave en la zona detectada. La decisión final por producto es aparte y binaria. Los parámetros son heurísticos iniciales y requieren ajuste con imágenes del proceso de producción.

Se incluye `entrenar_calidad.py` como **clasificador supervisado opcional**. Su objetivo es mejorar el diagnóstico con ejemplos reales previamente etiquetados. No se inventan etiquetas a partir de los 10 ejemplos suministrados ni se simula un modelo entrenado.

## Entrenar un clasificador opcional

1. Organiza manualmente recortes de fecha etiquetados, por ejemplo:

```
datos_calidad/
  BIEN/
    lote_1/imagen1.jpg
    lote_2/imagen2.jpg
  MAL/
    lote_3/imagen3.jpg
    lote_4/imagen4.jpg
```

2. Reúne **al menos 30 por clase**, además de **8 lotes independientes o más**, con presencia de ambas clases en varios lotes. Estos mínimos son una protección básica, no una cantidad suficiente garantizada para generalizar a todos los materiales.
3. Añade las librerías de entrenamiento y ejecuta:

```powershell
.venv\Scripts\python -m pip install scikit-learn joblib
.venv\Scripts\python entrenar_calidad.py --datos datos_calidad --salida clasificador_calidad.joblib
.venv\Scripts\python iniciar_calidad.py --camara 0 --modelo-calidad clasificador_calidad.joblib
```

El entrenamiento se realiza sobre **descriptores físicos de tinta**, no sobre caracteres ni cadenas. La validación separa lotes para evitar que capturas casi iguales aparezcan tanto en entrenamiento como en prueba. El modelo es un Random Forest inicial; si se reúnen suficientes buenas muestras, el siguiente paso técnico recomendado es evaluar **EfficientAD** sobre recortes normalizados (ver `INFORME_TECNICO.md`). Carga solamente archivos `.joblib` de confianza, ya que son formatos basados en pickle.

## Probar el código sin cámara ni YOLO

```powershell
.venv\Scripts\python -m unittest discover -s pruebas -p "test_*.py" -v
```

Las pruebas incluyen texto de varias longitudes y formatos, tinta clara sobre fondo oscuro, manchas sintéticas, las zonas reales `1995.jpg` y `1757.jpg`, seguimiento entre fotogramas, mayorías, empate, muestras ambiguas, dos productos simultáneos y un CSV integrado. **No equivalen a sensibilidad/especificidad industrial**, ni a una evaluación del detector YOLO.

## Opcional: crear un ejecutable en Windows

Ejecuta `CREAR_EXE_WINDOWS.bat` para preparar una **carpeta con ejecutable** mediante PyInstaller. Este paso usa un instalador grande (PyTorch/Ultralytics), requiere Internet y no se pudo ejecutar ni verificar en Windows dentro de este entorno. La carpeta resultante debe probarse en el mismo Windows y con la cámara deseada. El archivo `.bat` de inicio es la opción más sencilla.

## Límites actuales

- Una fotografía aislada no ofrece una referencia verdadera de cómo **debía** verse cada carácter. Algunas roturas, caracteres tapados o superpuestos son inherentemente ambiguos sin ejemplos normales/defectuosos del proceso.
- No hay **clasificador de calidad preentrenado ni prueba de precisión**. `best.pt` solo localiza regiones según su entrenamiento original.
- No se ejecutó `best.pt` con Ultralytics ni se conectó una cámara real aquí. **Sí se ejecutaron el analizador OpenCV, el seguimiento, los 34 tests automatizados y una integración con detector YOLO simulado**; esto no acredita el seguimiento real en una banda.
- La legibilidad se **estima indirectamente** a partir de contraste y continuidad. El sistema todavía no demuestra que un humano pueda leer toda la fecha, ni contiene verificación OCR. OCR puede agregarse como comprobación auxiliar, jamás como regla de conteo/formato.
- Reflejos, impresiones a muy baja resolución, pliegues y sustratos muy texturados pueden necesitar mejor iluminación, nueva cámara o datos de entrenamiento específicos. No activar rechazo automático en la banda sin validación con el operador.

## Archivos principales

- `iniciar_calidad.py`: cámara/vídeo, YOLO, visualización de banda, votación temporal y CSV.
- `seguimiento_banda.py`: asociación de la MISMA fecha en varios fotogramas, votación binaria y cierre por producto.
- `calidad_impresion.py`: inspección física de tinta sin OCR.
- `probar_lote.py`: pruebas por directorio e informe CSV.
- `entrenar_calidad.py`: clasificador opcional, requiere datos etiquetados.
- `best.pt`: modelo original suministrado (sin modificar).
- `hola_original.py`: archivo original suministrado (sin modificar).
- `pruebas/`: tests, recortes de ejemplo e imágenes con resultados preliminares.
- `INFORME_TECNICO.md`: análisis de alternativas, justificación y validación propuesta.


## Votacion actual

Regla vigente: **PASA solo si se completan las capturas configuradas,
BUENAS >= 5 y BUENAS > MALAS**. De lo contrario NO PASA con motivo
especifico; las inciertas nunca se convierten en MALAS. Ver
`CAMBIOS_ZONA_SEGURA_Y_5_BUENAS.md`.

---

## Actualización: máscara 05 como control de integridad (noviembre 2026)

La auditoría `auditoria_mascara.py` verifica franjas con **pérdida de tinta y restos fragmentados** antes de admitir un voto BIEN. Si la máscara no permite distinguir claramente un espacio normal de un borrado, la salida es `REVISAR`, nunca una aprobación automática por ausencia de marcas naranjas.

En la interfaz, activar `Guardar pruebas 05/06 de cada voto` guarda cada recorte real en `evidencias_inspeccion/`, organizado por sesión y por producto. Para las pruebas sin cámara ejecutar:

```powershell
python verificar_etapa05.py
```

Ver `MEJORA_MASCARA_05_Y_EVIDENCIAS.md` para detalle, resultados y limitaciones. **Sin OCR/Tesseract ni OpenVINO.**

## Aportes de VITA v0.1 (seleccionados)

Se mantiene el motor original YOLO + OpenCV + seguimiento. Se agregaron
protecciones para camaras sin senal, cuadros repetidos, posibilidad de elegir
MSMF/DirectShow, resolucion solicitada y diagnosticos de nitidez sobre la ROI.
**No se agregaron OCR ni OpenVINO.** Consulta `APORTES_VITA_SELECCIONADOS.md`.

Camara del celular/USB: `python diagnosticar_camaras.py --backend msmf`.



## V.I.T.A. — entrega escritorio

El nombre oficial del proyecto es **V.I.T.A.**; Nutreo es la empresa destinataria. Para el nuevo panel nativo y su arquitectura, ver [`MODO_OPERADOR_VITA.md`](MODO_OPERADOR_VITA.md). La documentacion `MODO_OPERADOR_NUTREO.md` procede de una version web obsoleta y ha sido reemplazada.

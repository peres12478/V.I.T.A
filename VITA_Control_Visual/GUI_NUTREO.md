> **Versión actual:** la configuración inicial de `Reducir alto (%)` es **12**;
> la referencia a 15 % más abajo corresponde a la versión histórica.
> El inspector incorpora la detección de arrastre interno: consultar
> `CALIBRACION_ARRASTRE_2026.md`.

> **Version actual:** los indicadores de TINTA y ZONAS explican que medicion
> activo una alerta. La etapa 06 resalta solo evidencia fisica localizada
> junto a los trazos; los problemas de camara se diagnostican por separado.
> Ver `MEJORA_FOCO_EXCLUSIVO_TINTA.md`.

# NUTREO - interfaz grafica de inspeccion en banda

## Archivo principal de la interfaz

**`interfaz_nutreo.py`**. Es independiente del programa antiguo
`iniciar_calidad.py` pero importa sus funciones de YOLO y registro, junto a
`inspeccion_robusta.py`, `calidad_impresion.py` y `seguimiento_banda.py`.
**No debes ejecutar cada archivo por separado.**

### En Windows desde Visual Studio Code

1. Descomprime el ZIP y abre **la carpeta `Nutreo_Control_Calidad`** en VS Code.
2. Abre una terminal de PowerShell, dentro de esa carpeta.
3. Si aun no instalaste las dependencias:

   ```powershell
   python -m pip install -r requirements.txt
   ```

   Tambien puedes utilizar el entorno virtual que venias usando:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Ejecuta SOLO:

   ```powershell
   python interfaz_nutreo.py
   ```

   O usando el entorno virtual:

   ```powershell
   .\.venv\Scripts\python.exe interfaz_nutreo.py
   ```

5. En la ventana, selecciona `Camara` (indice `0`, o `1` si es otra), o
   `Video de prueba` y elige un archivo. Pulsa **INICIAR**.

**El modelo `best.pt` debe permanecer en la misma carpeta que**
`interfaz_nutreo.py`. Esta version utiliza **Tkinter** (incluido normalmente
con Python de Windows), **Pillow**, OpenCV y Ultralytics.

## Que muestra la interfaz

- **Camara en vivo:** fotograma original a color con un rectangulo YOLO y
  un ID para la fecha de cada producto.
- **Estado derecho:** cuando YOLO no detecta una fecha muestra
  `ESPERANDO PRODUCTO`. Mientras recopila capturas, muestra
  `ESPERANDO FECHA COMPLETA` hasta que el recuadro este centrado y estable; luego `EVALUANDO PRODUCTO`. Cuando el tracker decide, `PASA` (buena) o
  `NO PASA` (predominan malas, empate, menos de 5 buenas o inspeccion incompleta).
- **Votacion:** cuenta fotos buenas, malas y ambiguas; el objetivo inicial son
  **7 capturas TOTALES** de la misma fecha, separadas por 75 ms como minimo.
- **Como se evalua la fecha:** seis paneles. **Haz clic en una imagen para ampliarla** y leer que significa. Incluyen recorte, luminosidad LAB,
  fondo estimado, diferencia de luminosidad ilustrativa, mascara de tinta
  **real** y zonas sospechosas **reales**.
- **Explicacion:** muestra el motivo exacto que devuelve el inspector de
  cada fotograma, diagnostico de captura y la ejecucion (o no) de la segunda
  pasada del filtro robusto.
- **Registro:** una sola fila por producto evaluado en `registros_gui.csv`.
  El historial tambien aparece en pantalla.

### Importante sobre los filtros visuales

La interfaz no inventa las mascaras: las dos ultimas proceden de la salida
`Resultado` del modulo `calidad_impresion.py` / `inspeccion_robusta.py`.
Las imagenes LAB, fondo y diferencia son una forma de **inspeccionar el
preprocesamiento**. La diferencia de luminosidad es una vista explicativa y
**no significa que la clasificacion se haga solo en escala de grises**: el
algoritmo original tambien puede seleccionar tinta por contraste cromatico.
CLAHE/bilateral se usan solo cuando el inspector robusto decide hacer una
segunda pasada; el panel indica si esa segunda verificacion se ejecuto.

**No se realiza OCR, conteo de caracteres ni validacion del formato de fecha.**

## Motivos para NO PASA

- La mayoria de las muestras validas indican **MAL**.
- Hubo empate y se aplico la politica conservadora.
- No se consiguio **ningun** voto evaluable. En este caso el registro dice
  **SIN VOTOS EVALUABLES** y el rechazo es preventivo, no defecto confirmado.
- Para PASA exige al menos **5 BUENAS**, mas BUENAS que MALAS y todas las capturas configuradas. Una sola buena NUNCA aprueba.

Se mantiene la politica binaria solicitada (pasa/no pasa), pero la fase
interna admite `REVISAR` para NO votar con fotos tecnicamente dudosas.

## Ajustes de la barra superior

- **Camara 0:** indice de la camara USB. Prueba 1 o 2 si no hay imagen.
- **Video de prueba:** analiza una grabacion sin necesidad de banda real.
- **Fotos totales:** numero de capturas por fecha (las inciertas ocupan una captura pero no votan).
- **Intervalo ms:** tiempo minimo entre fotos usadas para votar del mismo
  producto. Un intervalo de 75 ms requiere que el codigo permanezca visible
  bastante tiempo; en bandas rapidas tal vez sea mejor reducirlo tras medir
  velocidad, obturador y FPS de la camara.
- **YOLO conf.:** umbral de confianza para la **deteccion de fecha**, no
  confianza en la calidad de impresion.

## Limitaciones que se deben comprobar en la banda

- La interfaz esta probada con un detector simulado y el modulo de inspeccion
  real en fotografias. **No se probo la camara ni YOLO `best.pt` ejecutandose
  fisicamente en tu PC** en este entorno.
- El seguimiento actual asocia detecciones por posicion/solapamiento;
  productos muy juntos pueden cruzarse. Para produccion es recomendable
  agregar un sensor de presencia o encoder para identificar cada empaque.
- Los umbrales de deteccion de defectos son experimentales; deben calibrarse
  y validar aciertos/falsos rechazos con muestras etiquetadas antes de conectar
  un expulsor automatico.
- Si la ventana es mas alta que tu pantalla, usa la rueda del mouse para
  bajar hasta las imagenes de filtros y el registro.
- Si aparece un error de permisos de camara, cierra aplicaciones que ya esten
  usando ese dispositivo y habilita el acceso de Python a la camara.

## Archivo nuevo de apoyo

`visualizador_filtros.py` solo crea los 6 paneles explicativos. **No cambia**
la clasificacion ni la votacion. El procesamiento principal original sigue
funcionando con `iniciar_calidad.py` sin abrir la nueva ventana.


## Cambio de la version actual: zona segura + 5 buenas

**Primero ver la fecha completa, luego votar.** YOLO detecta desde el inicio,
pero NO se ejecuta el inspector ni se suma ninguna foto mientras el recuadro
este cerca del borde o no se confirme estable durante **3 detecciones**.
El recuadro puede moverse: se compara su tamano, NO una posicion fija.

Al quedar dentro del margen seguro del **8%**, se inicia la inspeccion:
**7 capturas TOTALES** por defecto, con separacion minima de 75 ms. Cada
captura puede ser BUENA, MALA o INCIERTA (no vota). La pantalla muestra el
balance y cuantas BUENAS faltan para llegar al minimo.

**Se aprueba solo cuando se completan las 7 capturas y se cumplen AMBAS:**

- **BUENAS >= 5**.
- **BUENAS > MALAS**.

Si sale de la zona antes de completar las 7 fotos, el producto recibe
**NO PASA preventivo por inspeccion incompleta**. Nunca se convierte una
foto no evaluable en fallo fisico confirmado. El ID no cambia al completar
la votacion; se libera solo despues de ausencia de YOLO confirmada.

Los controles de la interfaz **Min. buenas**, **Margen zona (%)** y
**Confirmaciones** permiten adaptar el sistema a una banda especifica.
El minimo de BUENAS no puede configurarse por debajo de 5.

**No se usa OCR ni conteo de caracteres.** La comprobacion de visibilidad
no garantiza una fecha fisicamente completa si YOLO detecta una parte en el
centro: requiere validacion en la banda y, para mayor seguridad, sensor de
presencia o seguimiento del empaque.

## Recorte interior contra falsos indicios del barcode

En la configuracion superior hay un campo **Reducir alto (%)**, inicialmente 15.
Recorta 15% por lado en el eje corto de la deteccion YOLO (alto si la fecha
es horizontal, ancho si esta girada). Cambia a 20 si la etiqueta aun entra,
o a 10/5/0 si el texto se corta. Deten y reinicia para aplicar el cambio.
Consulta `CAMBIOS_RECORTE_ETIQUETA.md` para detalles.

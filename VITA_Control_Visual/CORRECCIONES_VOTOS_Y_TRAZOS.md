# Nutreo: correcciones a los casos 11669 y 11670

## Diagnostico de las capturas

**11670 (producto bueno)**: el programa registro 41 BUENAS, 0 MALAS y 0 INCIERTAS, pero genero `NO PASA` porque el maximo configurado era 50 fotos y el producto desaparecio tras 41. El problema estaba en `_terminar()` de `seguimiento_banda.py`, que rechazaba sin considerar los votos si `muestreos < objetivo`.

**11669 (impresion visualmente incompleta)**: el programa acumulo 42 BUENAS, 0 MALAS y 6 INCIERTAS. La validacion de zona segura solo comprobaba el rectangulo de YOLO; el inspector de tinta podia clasificar BIEN trazos muy debilitados si no detectaba arrastres o manchas fuertes. El numero de BUENAS no garantiza que el codigo este integro.

## Cambios implementados

1. **Maximo de capturas, no cantidad obligatoria.** 50 es ahora el limite superior. Si el empaque sale antes, el cierre toma la decision segun los votos disponibles. El sistema **no emite la decision final mientras el producto siga en la camara**, salvo que se alcance el limite.
2. **Aprobacion:** `BUENAS >= 5` y `BUENAS > MALAS` (o el minimo indicado por la interfaz). `INCIERTAS` no son votos negativos. Ejemplo: `41 BUENAS, 0 MALAS, maximo 50` => PASA al confirmarse la salida. `1 BUENA, 0 MALAS` => NO PASA por evidencia insuficiente.
3. **Freno a BUENAS con tinta debilitada.** `integridad_trazos.py` compara el contraste de trazos contiguos en la propia fecha. Si hay una franja interior persistentemente muy tenue respecto a sus vecinos, devuelve `REVISAR`, nunca `BIEN`. El analisis no cuenta letras, lineas ni valida el formato.
4. **Verificacion de bordes del recorte.** Cuando segmentos relevantes tocan la frontera del recorte, se marca `REVISAR`, ya que no puede asegurarse la integridad de ese trazo.
5. **Intervalo inicial de captura: 180 ms**, en vez de 75 ms, para reducir votos consecutivos excesivamente correlacionados. El operador puede cambiarlo segun velocidad, FPS y tiempo disponible.
6. **Interfaz mas clara.** "Max. fotos" en lugar de "Fotos totales"; el balance favorable es PROVISIONAL y no se colorea como aprobacion definitiva hasta que diga PASA. Se muestra el indice de debilitamiento local para diagnosticar alertas.
7. **Sin OCR/Tesseract y sin OpenVINO.** El motor sigue siendo YOLO `best.pt` + OpenCV + seguimiento temporal. No se anaden dependencias.

## Comprobaciones

- **107 pruebas automatizadas + 21 subpruebas:** satisfactorias en este entorno.
- Un caso artificial de fecha legible pero con franja debilitada al 65-85% que antes generaba `BIEN` ahora genera `REVISAR`. La variante limpia sigue `BIEN`.
- Recorte original de `11550`: `MAL` por arrastre de tinta (detector previo conservado).
- Recorte original de comparacion `161708`: `BIEN`.
- Recorte aproximado tomado de la **fotografia de la pantalla** `11669`: `REVISAR` por falta de detalle. Esto NO verifica el fotograma original capturado por el telefono.
- Simulacion de seguimiento con 41 BUENAS/50 maximas y ausencia confirmada: `PASA` y un solo registro.

## Limitacion que no debe ocultarse

Sin conocer el contenido esperado de la fecha, una referencia visual o un modelo supervisado calibrado con impresiones defectuosas, **no es posible demostrar que existe un caracter totalmente ausente** si ese lugar no presenta ninguna huella de tinta. El nuevo filtro busca degradaciones medibles (trazos tenues, cortes contra el recorte), no reconstruye caracteres perdidos. Tampoco puede distinguir siempre falta real de tinta de falta de enfoque o movimiento. Estos casos pueden quedar como `REVISAR` y el producto puede salir `NO PASA` por evidencia insuficiente, no por defecto demostrado.

No deben utilizarse los umbrales actuales para rechazos automaticos en produccion sin validar con fotogramas originales de la camara y muestras BUENAS/MALAS etiquetadas.

## Uso

En Windows, descomprime el ZIP, abre `Nutreo_Control_Calidad` en VS Code y ejecuta:

```powershell
python -m pip install -r requirements.txt
python interfaz_nutreo.py
```

Para repetir todas las pruebas:

```powershell
python -m unittest discover -s pruebas -v
```

Recomendacion para la prueba de camara: fija el telefono, enfoca la fecha, usa iluminacion constante, selecciona entre 7 y 15 fotos maximas con intervalo de 180 ms inicialmente, y compara la decision con un registro humano de productos buenos y defectuosos. Si un producto bueno no llega a 5 fotos evaluables, modifica el intervalo en funcion del tiempo que pasa por la zona segura.

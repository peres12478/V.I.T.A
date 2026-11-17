# Actualizacion: votacion temporal para banda transportadora

## Nuevo comportamiento

- En camara y video, cada deteccion YOLO se analiza con el **inspector fisico de tinta existente**, sin contar caracteres.
- `seguimiento_banda.py` conserva las muestras de la **misma fecha** mientras se mueve y evita mezclar votos por cada region asignando un ID.
- Se intentan reunir **7 fotos evaluables**, separadas **75 ms**. Si predomina BIEN -> BIEN; si predomina MAL -> MAL; empate -> MAL.
- La etiqueta interna REVISAR de cada foto **se descarta del voto**. La ultima version decide **solo** comparando BUENAS y MALAS. Empates o ausencia total de votos resultan NO PASA preventivo, sin afirmar defecto de impresion; los avisos por poca evidencia no anulan una mayoria favorable. Ver `CAMBIOS_MAYORIA_REAL.md`.
- **En pantalla** aparece `ANALIZANDO N/7` durante la toma de muestras. Al cerrar la votacion aparece `BIEN` o `MAL` **sin tercer estado final**.
- Se emite **un solo evento/registro CSV por ID de producto**. Los datos salen en `registros_banda.csv`.
- `--guardar-muestras` almacena las fotos muestreadas en `muestras_banda/producto_00001/...` para auditoria, si se necesita.

## Inicio

1. Extraer el ZIP completo.
2. Ejecutar `INICIAR_CALIDAD_WINDOWS.bat` (instalacion inicial requiere Internet).
3. Enfocar el sector donde la fecha pasa frente a la camara.
4. Verificar que `ANALIZANDO` avance y que aparezca un **BIEN** o un **MAL** al alcanzar suficientes muestras; revisar el archivo CSV.

Alternativa:

```powershell
.venv\Scripts\python iniciar_calidad.py --camara 0 --fotos 7 --min-fotos 3 --intervalo-ms 75
```

Si la banda es muy rapida, los parámetros de muestras e intervalo **deben calibrarse** con los FPS reales, el ancho del campo de vision y la velocidad del empaque. No existe un numero de fotos universal.

## Pruebas completadas

El modulo de banda se verifico originalmente con **23 tests automatizados**; la version integrada actual pasa **34 pruebas** sin fallas: sensor de tinta OpenCV; varios formatos y empaques; mayorias; empate; muestras ambiguas; desenfoque configurable; varios productos; no duplicacion; integracion con un detector YOLO simulado y escritura CSV.

Tambien se ejecuto **un ensayo de lectura de video simulado** (24 fotogramas, 20 FPS), verificando una sola aprobacion con 7 votos y la escritura del video anotado y el CSV. **No se probo la camara ni el archivo real `best.pt` con Ultralytics** en el equipo final.

## Limitaciones antes de rechazar paquetes automaticamente

- El tracker geometrico NO identifica con certeza dos empaques pegados o con cajas solapadas; para la banda real se recomienda sensor de presencia/encoder o seguimiento fiable de objetos.
- El tiempo de respuesta depende del hardware y de la velocidad del transportador.
- Varios fotogramas cercanos estan correlacionados: la mayoria reduce fluctuaciones, pero **no garantiza** detectar una falla persistente ni una que solo aparezca bajo cierta perspectiva.
- Debe validarse el sistema **por producto completo** con muestras reales buenas y defectuosas, y no activar un expulsor sin pruebas de posicion y sincronizacion.

Ver `README.md` para todos los parametros y `INFORME_TECNICO.md` para el razonamiento tecnico.


**Actualizacion filtros de camara:** ahora `iniciar_calidad.py` activa por defecto `--filtros robusto`; ver `CAMBIOS_FILTROS_CAMARA.md`. No se necesita `--mostrar-mascara` para inspeccionar (la vista principal permanece a color).


**ACTUALIZACION:** Las condiciones de `min_validas` y `proporcion_minima`
son SOLO avisos de confiabilidad; no cambian el resultado por mayoria.
Consulta `CAMBIOS_MAYORIA_REAL.md`; los detalles historicos anteriores
pueden referirse a versiones con umbrales de evaluabilidad.

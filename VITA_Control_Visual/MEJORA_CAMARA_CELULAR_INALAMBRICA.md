# Nutreo - Camara de celular (Wi-Fi o camara virtual)

## Problema identificado en la version anterior

En `Trabajador.run`, cada fotograma duplicado se mostraba como `frame.copy()`.
Esa imagen NO llevaba los recuadros dibujados por `ProcesadorNutreo`: desaparecian
la caja de YOLO y la ZONA SEGURA, y regresaban cuando llegaba el siguiente
fotograma distinto. Ademas, se reemplazaba `ultima_muestra` con `CAPTURA NO UTIL`.

La camara virtual puede entregar el mismo cuadro varias veces antes de tener una
imagen nueva. Eso no significa que la FECHA este ausente, ni es evidencia de mala
impresion. En ese periodo no deben sumarse votos.

## Correcciones

1. Retencion de la ultima imagen *ya anotada*. La caja de producto, ZONA SEGURA,
   los paneles de filtros, ID, contadores y ultima muestra no parpadean.
2. Los duplicados se omiten y no generan votos. Si la pausa supera 0.8 s,
   se indica `VIDEO EN ESPERA - SIN NUEVO VOTO` sin ocultar las marcas.
3. El umbral de congelamiento requiere >=45 repeticiones **y** >=2.5 s.
   Repeticiones rapidas durante pocos milisegundos no generan una alarma falsa.
4. Lectura de camara moderada: 30 ms de pausa cuando el fotograma se repite.
5. Las interrupciones reales y prolongadas conservan la regla segura:
   invalidar el producto pendiente como NO PASA preventivo, sin aprobarlo.
6. `diagnosticar_camaras.py` muestra FPS de lecturas, FPS de frames NUEVOS,
   duplicados, invalidos y pausas maxima.

No se cambia YOLO, best.pt, OpenCV, filtros 05/06, votacion ni umbrales de tinta.
Sin OCR, Tesseract ni OpenVINO.

## Prueba en Windows sin YOLO

Con el celular moviendo un empaque frente a la camara virtual:

```powershell
python diagnosticar_camaras.py --indice 1 --backend msmf --segundos 8 --resolucion 1280x720
```

Si no funciona, probar con `--backend dshow`.
La disponibilidad real depende del driver virtual instalado y la conexion.
Si la tasa `fps_nuevos` es baja o hay pausas largas, reducir resolucion,
mejorar la red Wi-Fi o utilizar USB, si tu aplicacion de camara lo admite.
No se puede compensar con software una red que deja de transmitir frames.

Abrir el centro de pruebas:

```powershell
python interfaz_nutreo.py --camara 1
```

En el apartado CAMARA USB / CELULAR se puede seleccionar `msmf`,
`dshow` o `auto`. Pruebe preferiblemente MSMF y 1280x720 para la camara
virtual; el portatil puede permanecer en `auto`.

### Seguridad de la decision

Un frame repetido nunca suma BUENA ni MALA. Una interrupcion prolongada
no se confunde con tinta defectuosa: se cierra la inspeccion inconclusa
como NO PASA preventivo por captura interrumpida.

### Alcance de las pruebas

Pruebas automatizadas con capturas simuladas; no validado fisicamente con
el celular, la red y la banda transportadora del usuario.

# Nutreo - correccion de detecciones parciales y aprobaciones prematuras

## Objetivo

El codigo de YOLO puede empezar a localizar una fecha cuando parte de los
trazos todavia esta fuera de la imagen. Antes, esa foto se clasificaba como
BUENA y, si era el unico voto evaluable, el algoritmo podia dar PASA.

## Arquitectura vigente

1. `detectar_cajas()` localiza coordenadas YOLO en cada fotograma.
2. `SeguimientoBanda` conserva el mismo ID mientras la region siga presente.
3. `validacion_visibilidad.py` bloquea las fotos hasta que la caja este
   completamente dentro del margen interior de la imagen (**8%**) y tenga
   dimensiones consistentes durante **3 detecciones** consecutivas.
   La posicion PUEDE CAMBIAR, porque el empaque esta en movimiento.
4. Solo cuando la fecha parece completa y toca una captura, se ejecuta
   `InspectorCalidadRobusto.analizar()` sobre el recorte de fecha con recorte
   antietiqueta del 15% en el eje corto.
5. Se registran **7 capturas totales**, buena/mala/incierta, respetando el
   mismo intervalo minimo de 75 ms entre capturas.
6. **PASA solo si se completan las capturas, BUENAS >= 5 y BUENAS > MALAS.**
   Una mayoria de solo 1, 2, 3 o 4 buenas NO aprueba. Las inciertas no son
   negativas pero tampoco permiten saltarse el minimo de cinco buenas.
7. Si sale antes de completar 7 capturas: NO PASA preventivo,
   **INSPECCION INCOMPLETA**, no un defecto fisico confirmado.
8. El recuadro y el resultado final quedan asociados al producto hasta
   que el detector confirma la ausencia durante al menos 650 ms y 3 cuadros.

## Ejemplos con 7 capturas

| BUENAS | MALAS | INCIERTAS | Salida |
|---:|---:|---:|---|
| 1 | 0 | 6 | NO PASA - menos de 5 buenas |
| 4 | 0 | 3 | NO PASA - menos de 5 buenas |
| 5 | 1 | 1 | PASA |
| 5 | 2 | 0 | PASA |
| 3 | 4 | 0 | NO PASA - mayoria mala |
| 0 | 0 | 7 | NO PASA - sin votos |

## Controles nuevos en la interfaz

- **Min. buenas**: predeterminado y minimo permitido 5.
- **Margen zona (%)**: predeterminado 8. Si el producto entra/sale de
  forma parcial, sube gradualmente (10-12%). Si no hay espacio suficiente
  para 7 fotos, reduce el margen tras comprobar que no se trunca la fecha.
- **Confirmaciones**: predeterminado 3. Es una comprobacion de estabilidad
  de dimensiones en fotogramas consecutivos, NO de que la fecha este quieta.
- **Fotos totales**: predeterminado 7 (entre 5 y 50).
- **Reducir alto (%)**: preserva la correccion anterior del codigo de barras.

## Ejecucion

```
python interfaz_nutreo.py
```

Modo consola equivalente:

```
python iniciar_calidad.py --camara 0 --fotos 7 --min-buenas 5 --zona-segura-pct 8 --confirmaciones-fecha 3 --intervalo-ms 75
```

## LIMITACIONES

- La zona segura y la estabilidad del recuadro son una **aproximacion** a la
  visibilidad completa. Una deteccion parcial podria aparecer estable en el
  centro de la imagen. Para verificar con mayor seguridad se necesitan
  imagenes reales de la banda y posiblemente sensor fotoelectrico u otra
  forma de reconocer el empaque entero.
- Una mayoria de fotos correlacionadas no equivale a 7 verificaciones
  independientes. La calidad de la camara, la iluminacion y el desenfoque
  se deben validar con productos buenos y defectuosos reales.
- No se usan OCR, formatos esperados ni conteo de caracteres para aprobar.
- No se ha comprobado este codigo contra una banda fisica ni con el
  modelo best.pt corriendo en el PC del usuario; solo hay pruebas simuladas.

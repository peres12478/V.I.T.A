# V.I.T.A. — Historial simplificado para el personal de Nutreo

## Cambios realizados

- Se retiraron **Lote** y **Referencia** del formulario del panel operativo. Solo se registran **Línea** y **Turno**.
- Se retiraron **Hora** y **Explicación** de la tabla de historial visible para el operario.
- La exportación CSV contiene **exactamente siete columnas**, en este orden:
  1. Producto
  2. Resultado
  3. Buenas
  4. Malas
  5. Inciertas
  6. Línea
  7. Turno
- Se mantiene la protección de fórmulas de hojas de cálculo y la codificación UTF-8 con BOM compatible con Excel.
- Los archivos CSV/JSON técnicos que genera el motor **no se modifican**, ni se borran registros de versiones anteriores. Conservan fecha/hora y motivos para auditoría interna. El historial simplificado no incluye esas columnas.
- Se conserva intacto el motor compartido YOLO + OpenCV, la clasificación, máscaras, voto, selección de cámara y aplicación de escritorio sin servidor.

## Abrir

Ejecuta `python panel_operador.py` dentro de `VITA_Control_Visual` y entra a la pestaña **Historial y exportación**. Para una prueba sin cámara: `python -m unittest pruebas.test_panel_operador -v`.

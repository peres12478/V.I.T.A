# NUTREO — Barrido adaptativo de continuidad de tinta

## Problema y por que se incorpora

Una fecha con una **franja central borrada** podia clasificarse como `BIEN`,
porque el resto de las letras tenia buen contraste y los detectores anteriores
estaban centrados en manchas y arrastres, no en **ausencia anomala de tinta**.

La foto real aportada y recortada en `pruebas/fecha_11682_centro.png`
reproduce el error: el inspector anterior devolvia **BIEN**. El inspector
actualizado detecta perdida de tinta alineada en los dos renglones y devuelve
**MAL** en ese recorte; con el recorte mas estrecho devuelve **REVISAR**.

## Como funciona — las lineas invisibles que propusiste

1. **YOLO** delimita la region. El inspector solo recibe ese recorte.
2. OpenCV produce la **mascara real de tinta** (etapa 05).
3. El nuevo `barrido_continuidad.py` identifica los renglones por geometria,
   sin exigir que haya uno, dos o un numero fijo de renglones.
4. Recorre la impresion con ventanas verticales deslizantes. Calcula cuanta
   tinta hay en cada franja, usando ventanas relativas a la altura estimada
   de los trazos. **No exige un caracter en cada linea ni compara texto**.
5. Busca franjas interiores con poca tinta **entre regiones con tinta**.
   Contrasta el vacio con tinta de ambos lados, la presencia de huellas
   tenues en la **imagen BGR original** y la coincidencia entre renglones.
6. **Decision individual**:
   - Evidencia concordante de perdida de tinta: `MAL` (voto malo).
   - Falta grande de tinta, pero explicacion ambigua: `REVISAR` (no vota bueno).
   - Sin anomalias detectadas: conserva el resultado del inspector anterior.
7. **Seguimiento de banda** conserva minimo 5 votos buenos y mas buenos que
   malos. El limite total de fotografias es un maximo, no un requisito:
   un producto con 41 buenas de 50 y 0 malas puede aprobar al salir.

La **etapa 06** dibuja las guias virtuales con lineas finas naranjas y puede
resaltar huellas tenues. Las lineas son una explicacion del analisis: **no**
son tinta real ni "caracteres obligatorios".

## Ejemplos probados localmente

| Recorte | Resultado | Comentario |
| --- | --- | --- |
| `fecha_11682_centro.png` | MAL | Franja borrada y huellas tenues en ambos renglones |
| `fecha_11682_estrecha.png` | REVISAR | La ausencia central es sospechosa, pero menos evidente |
| `11550_arrastre.png` | MAL | Se mantiene el detector previo de arrastre interno |
| `161708_comparacion.png` | BIEN | Ejemplo real de comparacion sin ese arrastre |
| `barrido_normal.png` | BIEN | Texto de prueba sin perdida de tinta |
| `barrido_spaces.png` | BIEN | Espacios grandes intencionales sin falsa alarma |
| `barrido_erased.png` | REVISAR | Hueco ancho sin huellas: no se inventa texto faltante |
| `barrido_faded.png` | REVISAR | Huella demasiado tenue para confirmar defecto fisico |

Resultados reproducibles con:

```powershell
python validar_barrido.py
python -m pytest -q pruebas
```

**118 pruebas automatizadas + 21 subpruebas correctas** en este entorno.
El barrido aislado tardó aproximadamente **1 a 5 ms por recorte** en
las muestras de comprobacion; ese dato no incluye YOLO, webcam ni interfaz.

## Como ejecutar Nutreo

```powershell
python -m pip install -r requirements.txt
python interfaz_nutreo.py
```

No se usa **OCR, pytesseract, Tesseract ni OpenVINO**. Se incluye `best.pt`.
El motor de tinta y la votacion se mantienen intactos salvo por la nueva
comprobacion que evita sumar `BUENA` ante una franja sospechosa.

## Limitaciones importantes

- **Una ausencia completamente limpia de tinta puede ser indistinguible de
  un espacio intencional sin disponer de una referencia del producto**.
  Por ello los huecos ambiguos devuelven `REVISAR` y no `MAL` automatico.
- Los formatos, distribucion y tipografias de fechas cambian. Los barridos
  son adaptativos, **no lineas fijas donde deban aparecer letras**.
- El algoritmo puede no identificar otras causas de ilegibilidad, malas
  etiquetas, reflejos, enfoque incorrecto, movimientos o defectos nuevos.
- La demostracion usa recortes de una fotografia de la impresion; **no**
  demuestra precision industrial en la camara real. Debe evaluarse con
  conjuntos etiquetados de BUENA/MALA y diferentes velocidades de banda.
- Los votos consecutivos de video pueden estar correlacionados. La mejora
  al inspector reduce falsos `BIEN`, pero una repeticion de fotos no sustituye
  una referencia confiable o verificaciones fisicas.
- No conectar un mecanismo automatico de descarte hasta realizar pruebas
  de sensibilidad/especificidad con muestras de fabrica conocidas.

## Recomendacion de siguiente validacion

Recopilar al menos varias decenas de **fotos originales de la camara de Nutreo**,
no fotos tomadas a la pantalla, de productos con defectos y sin ellos.
Clasificarlas manualmente y medir en particular **falsos BIEN** por franja
borrada y falsos MAL por espacios entre datos. Ajustar la distancia de
camara, luz y velocidad antes de retocar umbrales sobre imagenes aisladas.

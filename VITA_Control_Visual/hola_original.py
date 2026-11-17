import os
import cv2
from ultralytics import YOLO

# Obtener la ruta absoluta de la carpeta donde está este script (`hola.py`)
current_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(current_dir, 'best.pt')

# Cargar tu modelo usando la ruta exacta calculada
model = YOLO(model_path)

# Abrir la cámara web
cap = cv2.VideoCapture(0)

print("Iniciando transmisión en tiempo real. Presiona 'q' para salir.")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("No se pudo acceder a la cámara.")
        break

    # Realizar la predicción
    results = model(frame, conf=0.6)

    if len(results[0].boxes) > 0:
        print("¡Fecha de vencimiento detectada!")

    # Mostrar el resultado
    annotated_frame = results[0].plot()
    cv2.imshow("Detección de Fechas en Tiempo Real", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
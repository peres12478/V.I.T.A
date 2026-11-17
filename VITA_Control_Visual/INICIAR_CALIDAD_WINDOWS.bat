@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Instalando entorno virtual de Python...
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import cv2, ultralytics, numpy" >nul 2>&1
if errorlevel 1 (
  echo Instalando dependencias (necesita internet la primera vez)...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto error
)
echo Nutreo: banda transportadora - 7 muestras por producto - resultado BIEN o MAL.
".venv\Scripts\python.exe" iniciar_calidad.py --camara 0 --fotos 7 --min-fotos 3 --intervalo-ms 75
if errorlevel 1 goto error
pause
exit /b 0
:error
echo No fue posible iniciar. Revisa el error anterior.
pause
exit /b 1

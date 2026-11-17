@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Ejecuta primero INICIAR_CALIDAD_WINDOWS.bat para instalar Python y las librerias.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onedir --windowed --name Nutreo_Calidad --add-data "best.pt;." --collect-all ultralytics iniciar_calidad.py
if errorlevel 1 goto error
copy /Y "best.pt" "dist\Nutreo_Calidad\best.pt" >nul
if errorlevel 1 goto error
echo Compilacion terminada. Revisa la carpeta dist\Nutreo_Calidad
echo IMPORTANTE: la compilacion solo puede comprobarse ejecutandola en Windows.
pause
exit /b 0
:error
echo Hubo un error compilando. Revisa los mensajes anteriores.
pause
exit /b 1

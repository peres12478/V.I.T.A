@echo off
setlocal
cd /d "%~dp0"
rem Elige la camara DENTRO del panel. No se necesita servidor ni navegador.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" panel_operador.py
) else (
    python panel_operador.py
)
if errorlevel 1 (
  echo.
  echo No se pudo abrir V.I.T.A. Instala las dependencias:
  echo python -m pip install -r requirements.txt
  pause
)
endlocal

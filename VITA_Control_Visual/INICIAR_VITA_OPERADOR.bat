@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" panel_operador.py
) else (
    python panel_operador.py
)
if errorlevel 1 (
    echo No se pudo iniciar V.I.T.A. Instala las dependencias:
    echo python -m pip install -r requirements.txt
    pause
)
endlocal

@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" interfaz_nutreo.py
) else (
    python interfaz_nutreo.py
)
if errorlevel 1 (
    echo No se pudo iniciar el centro tecnico de V.I.T.A.
    pause
)
endlocal

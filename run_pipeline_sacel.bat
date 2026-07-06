@echo off
cd /d "%~dp0"

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    where py >nul 2>nul
    if %errorlevel%==0 set "PYTHON_EXE=py"
)

if not defined PYTHON_EXE (
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
        set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] No se encontro Python. Instala Python o crea .venv con las dependencias del proyecto.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "SCRIPTS VS\pipeline_sacel.py"
pause

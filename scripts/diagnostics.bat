@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Generating diagnostics zip...
"%PYTHON_EXE%" -c "from src.diagnostics import generate_diagnostics_zip; print(generate_diagnostics_zip())"
exit /b %ERRORLEVEL%

@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Starting development server...
"%PYTHON_EXE%" launcher.py --env development --shell browser --port 18080
exit /b %ERRORLEVEL%

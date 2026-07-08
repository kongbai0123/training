@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Starting application...
echo [Vision Training Studio] Default URL: http://127.0.0.1:18080/
echo [Vision Training Studio] Extra launcher arguments: %*

"%PYTHON_EXE%" launcher.py --env production --shell browser --port 18080 %*
exit /b %ERRORLEVEL%

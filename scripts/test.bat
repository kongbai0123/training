@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Running unittest suite...
"%PYTHON_EXE%" -m unittest discover -s tests -p "test_*.py" -v
exit /b %ERRORLEVEL%

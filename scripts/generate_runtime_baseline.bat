@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

"%PYTHON_EXE%" scripts\generate_runtime_baseline.py %*
exit /b %ERRORLEVEL%

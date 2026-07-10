@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if defined VTS_PYTHON_EXE set "PYTHON_EXE=%VTS_PYTHON_EXE%"

"%PYTHON_EXE%" scripts\package_portable.py
exit /b %ERRORLEVEL%

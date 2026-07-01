@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Stopping existing packaged app processes if any...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process -Name VisionTrainingStudio -ErrorAction SilentlyContinue | Stop-Process -Force"

echo [Vision Training Studio] Building PyInstaller package...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] PyInstaller package failed.
  exit /b %ERRORLEVEL%
)

echo [Vision Training Studio] Package created: dist\VisionTrainingStudio\VisionTrainingStudio.exe
exit /b 0

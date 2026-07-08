@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Stopping existing packaged app processes if any...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path 'dist\VisionTrainingStudio' -ErrorAction SilentlyContinue); $procs=Get-Process -Name VisionTrainingStudio -ErrorAction SilentlyContinue; if ($root) { $prefix=$root.Path; $procs=@($procs | Where-Object { -not $_.Path -or $_.Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) }) }; if ($procs) { $procs | Stop-Process -Force; Start-Sleep -Milliseconds 800 }; $remaining=Get-Process -Name VisionTrainingStudio -ErrorAction SilentlyContinue; if ($root) { $prefix=$root.Path; $remaining=@($remaining | Where-Object { -not $_.Path -or $_.Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) }) }; if ($remaining) { Write-Error ('Unable to stop packaged app process(es): ' + (($remaining | Select-Object -ExpandProperty Id) -join ', ')); exit 1 }"

echo [Vision Training Studio] Building PyInstaller package...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] PyInstaller package failed.
  exit /b %ERRORLEVEL%
)

echo [Vision Training Studio] Package created: dist\VisionTrainingStudio\VisionTrainingStudio.exe
exit /b 0

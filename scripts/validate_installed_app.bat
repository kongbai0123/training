@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "APP_EXE=%~1"
if "%APP_EXE%"=="" set "APP_EXE=%ProgramFiles%\VisionTrainingStudio\VisionTrainingStudio.exe"

if not exist "%APP_EXE%" (
  echo [ERROR] App executable not found: %APP_EXE%
  echo Usage: scripts\validate_installed_app.bat "C:\Path\To\VisionTrainingStudio.exe"
  exit /b 2
)

set "PORT=18115"
set "BASE_URL=http://127.0.0.1:%PORT%"

echo [Vision Training Studio] Validating installed app: %APP_EXE%
start "" "%APP_EXE%" --host 127.0.0.1 --port %PORT% --shell none

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$base='%BASE_URL%';" ^
  "$deadline=(Get-Date).AddSeconds(45);" ^
  "$health=$null; $version=$null;" ^
  "while((Get-Date) -lt $deadline) {" ^
  "  try {" ^
  "    $health=Invoke-RestMethod -Uri ($base + '/api/health') -TimeoutSec 2;" ^
  "    $version=Invoke-RestMethod -Uri ($base + '/api/version') -TimeoutSec 2;" ^
  "    break;" ^
  "  } catch { Start-Sleep -Milliseconds 700 }" ^
  "}" ^
  "if($null -eq $health -or $null -eq $version) { throw 'Installed app health/version check timed out.' }" ^
  "Write-Host ('health=' + ($health | ConvertTo-Json -Compress -Depth 6));" ^
  "Write-Host ('version=' + ($version | ConvertTo-Json -Compress -Depth 6));"

set "RESULT=%ERRORLEVEL%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process -Name VisionTrainingStudio -ErrorAction SilentlyContinue | Stop-Process -Force"

if not "%RESULT%"=="0" (
  echo [ERROR] Installed app validation failed.
  exit /b %RESULT%
)

echo [Vision Training Studio] Installed app validation passed.
exit /b 0

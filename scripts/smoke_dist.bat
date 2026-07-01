@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0\.."

set "EXE=%CD%\dist\VisionTrainingStudio\VisionTrainingStudio.exe"
set "PORT=18105"

if not exist "%EXE%" (
  echo [ERROR] Dist executable not found: %EXE%
  echo Run scripts\package.bat first.
  exit /b 1
)

echo [Vision Training Studio] Starting dist smoke on port %PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$exe=$env:EXE; $port=[int]$env:PORT;" ^
  "$proc=Start-Process -FilePath $exe -ArgumentList @('--port', $port, '--env', 'production', '--shell', 'none') -PassThru -WindowStyle Hidden;" ^
  "try {" ^
  "  $health=$null; $version=$null;" ^
  "  for($i=0; $i -lt 60; $i++){" ^
  "    Start-Sleep -Seconds 1;" ^
  "    try {" ^
  "      $health=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/health') -TimeoutSec 2;" ^
  "      $version=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/version') -TimeoutSec 2;" ^
  "      break;" ^
  "    } catch {}" ^
  "  }" ^
  "  if($null -eq $health){ throw 'Health endpoint did not respond.' }" ^
  "  if($null -eq $version){ throw 'Version endpoint did not respond.' }" ^
  "  Write-Host ('health=' + ($health | ConvertTo-Json -Compress));" ^
  "  Write-Host ('version=' + ($version | ConvertTo-Json -Compress));" ^
  "} finally {" ^
  "  if($proc -and -not $proc.HasExited){ Stop-Process -Id $proc.Id -Force }" ^
  "}"

exit /b %ERRORLEVEL%

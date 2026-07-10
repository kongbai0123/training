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
  "$smokeRoot=Join-Path (Get-Location) 'tmp\dist-smoke-local-app-data';" ^
  "if(Test-Path -LiteralPath $smokeRoot){ Remove-Item -LiteralPath $smokeRoot -Recurse -Force };" ^
  "New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null;" ^
  "$env:LOCALAPPDATA=$smokeRoot; Remove-Item Env:VTS_USER_DATA_DIR -ErrorAction SilentlyContinue; Remove-Item Env:VTS_PROJECTS_DIR -ErrorAction SilentlyContinue;" ^
  "$proc=Start-Process -FilePath $exe -ArgumentList @('--port', $port, '--env', 'production', '--shell', 'none') -PassThru -WindowStyle Hidden;" ^
  "try {" ^
  "  $health=$null; $version=$null; $capabilities=$null; $projects=$null;" ^
  "  for($i=0; $i -lt 60; $i++){" ^
  "    Start-Sleep -Seconds 1;" ^
  "    try {" ^
  "      $health=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/health') -TimeoutSec 2;" ^
  "      $version=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/version') -TimeoutSec 2;" ^
  "      $capabilities=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/system/capabilities') -TimeoutSec 2;" ^
  "      $projects=Invoke-RestMethod -Uri ('http://127.0.0.1:' + $port + '/api/projects') -TimeoutSec 2;" ^
  "      break;" ^
  "    } catch {}" ^
  "  }" ^
  "  if($null -eq $health){ throw 'Health endpoint did not respond.' }" ^
  "  if($null -eq $version){ throw 'Version endpoint did not respond.' }" ^
  "  if($null -eq $capabilities){ throw 'Capabilities endpoint did not respond.' }" ^
  "  $expectedProjects=(Join-Path $smokeRoot 'VisionTrainingStudio\projects').Replace('\','/');" ^
  "  if($health.directories.projects_dir -ne $expectedProjects){ throw ('Packaged projects path is not isolated: ' + $health.directories.projects_dir) }" ^
  "  if(@($projects).Count -ne 0){ throw ('Factory-clean package exposed ' + @($projects).Count + ' project(s).') }" ^
  "  if(-not ($capabilities.runtime.opencv -like '5.*')){ throw ('Unexpected OpenCV runtime: ' + $capabilities.runtime.opencv) }" ^
  "  Write-Host ('health=' + ($health | ConvertTo-Json -Compress));" ^
  "  Write-Host ('version=' + ($version | ConvertTo-Json -Compress));" ^
  "  Write-Host ('opencv=' + $capabilities.runtime.opencv);" ^
  "  Write-Host ('factory_projects=' + @($projects).Count);" ^
  "} finally {" ^
  "  if($proc -and -not $proc.HasExited){ Stop-Process -Id $proc.Id -Force }" ^
  "  $packageRoot=Split-Path -Parent $exe;" ^
  "  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($packageRoot, [System.StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "}"

exit /b %ERRORLEVEL%

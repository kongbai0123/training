@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

echo [Vision Training Studio] Cleaning rebuildable build/cache/tmp and test cache files.
echo [Vision Training Studio] projects/models/logs/exports/dist/release_artifacts will NOT be deleted.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=(Resolve-Path '.').Path;" ^
  "$targets=@('build','cache','tmp','.pytest_cache','__pycache__');" ^
  "foreach($name in $targets){" ^
  "  $path=Join-Path $root $name;" ^
  "  if(Test-Path -LiteralPath $path){" ^
  "    Remove-Item -LiteralPath $path -Recurse -Force;" ^
  "    Write-Host ('removed ' + $name);" ^
  "  }" ^
  "}" ^
  "Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -Filter '__pycache__' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force; Write-Host ('removed ' + $_.FullName) };" ^
  "Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -Filter '.pytest_cache' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force; Write-Host ('removed ' + $_.FullName) };" ^
  "Get-ChildItem -LiteralPath $root -File -Filter 'tmp_xgb_*' | Remove-Item -Force;" ^
  "Write-Host 'runtime cleanup complete';"

exit /b %ERRORLEVEL%

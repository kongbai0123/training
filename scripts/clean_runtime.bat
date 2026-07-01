@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

echo [Vision Training Studio] Cleaning runtime build/cache/tmp files.
echo [Vision Training Studio] projects\ will NOT be deleted.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=(Resolve-Path '.').Path;" ^
  "$targets=@('build','cache','tmp','__pycache__');" ^
  "foreach($name in $targets){" ^
  "  $path=Join-Path $root $name;" ^
  "  if(Test-Path -LiteralPath $path){" ^
  "    Remove-Item -LiteralPath $path -Recurse -Force;" ^
  "    Write-Host ('removed ' + $name);" ^
  "  }" ^
  "}" ^
  "Get-ChildItem -LiteralPath $root -File -Filter 'tmp_xgb_*' | Remove-Item -Force;" ^
  "Write-Host 'runtime cleanup complete';"

exit /b %ERRORLEVEL%

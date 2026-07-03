@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "ISCC_EXE="

for %%P in (
  "ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
  "%ProgramFiles%\Inno Setup 5\ISCC.exe"
) do (
  if not defined ISCC_EXE (
    if exist %%~P set "ISCC_EXE=%%~P"
  )
)

if not defined ISCC_EXE (
  for /f "delims=" %%P in ('where ISCC 2^>nul') do (
    if not defined ISCC_EXE set "ISCC_EXE=%%P"
  )
)

if not defined ISCC_EXE (
  echo [ERROR] Inno Setup Compiler ISCC.exe was not found.
  echo Install Inno Setup 6 or add ISCC.exe to PATH, then rerun scripts\build_installer.bat.
  exit /b 2
)

if not exist "dist\VisionTrainingStudio\VisionTrainingStudio.exe" (
  echo [ERROR] Packaged app not found: dist\VisionTrainingStudio\VisionTrainingStudio.exe
  echo Run scripts\package.bat first.
  exit /b 3
)

echo [Vision Training Studio] Building installer with "%ISCC_EXE%"...
"%ISCC_EXE%" installer\VisionTrainingStudio.iss
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Installer build failed.
  exit /b %ERRORLEVEL%
)

echo [Vision Training Studio] Installer output: installer\output
exit /b 0

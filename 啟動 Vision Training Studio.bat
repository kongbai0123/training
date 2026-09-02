@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo [Vision Training Studio] Windows PowerShell was not found.
  echo This launcher requires Windows 10 or Windows 11.
  pause
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_personal.ps1"
if errorlevel 1 (
  echo.
  echo Vision Training Studio could not be started.
  echo Check the message above, then double-click this file again.
  pause
  exit /b 1
)

exit /b 0

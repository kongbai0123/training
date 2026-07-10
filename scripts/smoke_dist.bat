@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\smoke_dist_offline.ps1" -Mode Installed -Port 18105
exit /b %ERRORLEVEL%

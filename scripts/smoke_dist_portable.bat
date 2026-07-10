@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\smoke_dist_offline.ps1" -Mode Portable -Port 18106
exit /b %ERRORLEVEL%

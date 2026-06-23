@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Vision Training Studio

echo ===================================================
echo   Vision Training Studio - Start Server
echo ===================================================
echo.

cd /d "%~dp0"
echo Working directory: %CD%
echo.

echo [1/4] Checking Python executable...
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)
echo Python: %PYTHON_EXE%
echo.

echo [2/4] Freeing port 8000 if it is already in use...
for /f "tokens=5" %%A in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo Stopping existing process on port 8000, PID %%A
  taskkill /f /pid %%A >nul 2>nul
)
echo Port check completed.
echo.

echo [3/4] Starting backend API...
start "Vision Training Studio API" /min "%PYTHON_EXE%" app.py
echo Waiting for http://127.0.0.1:8000/api/health ...
echo.

set /a WAIT_COUNT=0

:wait_loop
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto ready

set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 goto failed
timeout /t 1 >nul
goto wait_loop

:failed
echo.
echo ===================================================
echo   Startup failed.
echo ===================================================
echo The API did not become healthy within 30 seconds.
echo Please run this command manually to see the error:
echo   "%PYTHON_EXE%" app.py
echo.
pause
exit /b 1

:ready
echo [4/4] Server is ready.
echo Opening http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
echo.
echo Vision Training Studio is running.
echo Keep the API window open while using the app.
echo.
pause
exit /b 0

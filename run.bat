@echo off
chcp 65001 > nul
title Vision Training Studio

echo ===================================================
echo   Vision Training Studio - 可視化辨識訓練流程平台
echo ===================================================
echo.

cd /d "%~dp0"
echo 目前工作目錄：%cd%

echo [1/3] 正在釋放 port 8000 的佔用進程...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
  echo 發現佔用進程 PID: %%a，正在強制釋放...
  taskkill /f /pid %%a 2>nul
)

if exist ".venv\Scripts\python.exe" (
  set PYTHON_EXE=.venv\Scripts\python.exe
  echo 偵測到虛擬環境，使用：%PYTHON_EXE%
) else (
  set PYTHON_EXE=python
  echo 未偵測到虛擬環境，使用系統：%PYTHON_EXE%
)

echo [2/3] 正在背景啟動後端 API 伺服器...
start "Vision Training Studio API" /min %PYTHON_EXE% app.py

echo [3/3] 正在等待伺服器啟動就緒 (最多 30 秒)...
set /a count=0

:wait_loop
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto ready

set /a count+=1
if %count% geq 30 goto failed
timeout /t 1 >nul
goto wait_loop

:failed
echo.
echo ===================================================
echo   錯誤：伺服器未能於 30 秒內啟動。
echo   請檢查 app.py 啟動 log 或相關依賴是否正確安裝。
echo ===================================================
pause
exit /b 1

:ready
echo.
echo 伺服器已就緒！正在啟動瀏覽器並開啟 http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
echo 啟動完成！
echo.

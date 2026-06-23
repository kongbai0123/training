@echo off
chcp 65001 > nul
title Vision Training Studio
echo ===================================================
echo   Vision Training Studio - 可視化辨識訓練流程平台
echo ===================================================
echo.
echo [1/3] 正在釋放 port 8000 的佔用進程...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
  echo 發現佔用進程 PID: %%a，正在強制釋放...
  taskkill /f /pid %%a 2>nul
)

echo [2/3] 正在背景啟動後端 API 伺服器...
start "" /b python app.py

echo [3/3] 正在等待伺服器啟動就緒...
timeout /t 2 >nul

echo.
echo 正在啟動瀏覽器並開啟 http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
echo 啟動完成！後端伺服器正於此視窗背景運行中。
echo 如需關閉服務，可直接關閉此視窗。
echo.

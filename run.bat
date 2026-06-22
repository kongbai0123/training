@echo off
chcp 65001 > nul
title Vision Training Studio
echo ===================================================
echo   Vision Training Studio - 可視化辨識訓練流程平台
echo ===================================================
echo.
echo [1/2] 正在啟動預設瀏覽器並打開 http://127.0.0.1:8000 ...
start http://127.0.0.1:8000

echo [2/2] 正在啟動後端 API 伺服器...
python app.py
pause

# 疑難排解

## 1. 啟動失敗

可能原因：

- Python 環境未安裝依賴
- port 被占用
- runtime folder 無法寫入
- 舊的 exe 還在背景執行

建議：

```bat
scripts\build.bat
scripts\start_dev.bat
```

查看：

```text
logs/
```

## 2. Port 被占用

症狀：

```text
Address already in use
```

解法：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18105 --env production --shell none
```

或關閉舊的 `VisionTrainingStudio.exe`。

## 3. PyInstaller 打包失敗 WinError 5

症狀：

```text
PermissionError: [WinError 5] 存取被拒
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

原因：舊的 exe 正在執行，Windows 鎖住檔案。

解法：

```bat
taskkill /F /IM VisionTrainingStudio.exe
scripts\package.bat
```

`scripts\package.bat` 會嘗試先關閉舊程序。

## 4. 前端畫面樣式不完整

可能原因：

- 外部 CDN 被封鎖
- browser cache 使用舊版資源
- static 檔案未隨 dist 更新

解法：

- 強制重新整理
- 重新執行 `scripts\package.bat`
- 檢查 browser console
- 確認 `static/vendor/` 存在，且打包後位於 `dist/VisionTrainingStudio/_internal/static/vendor/`

## 5. RNN / XGBoost CSV 無法訓練

檢查：

- CSV 是否有 header row
- feature columns 是否存在於 CSV
- target column 是否存在於 CSV
- task type 與 target 類型是否一致
- sequence window 設定是否合理

修改 feature / target 後，舊 run 可能顯示 config mismatch，這是正常提示。

## 6. 模型導入後不能訓練

目前只有符合 trainable contract 的模型會進入訓練 selector。custom package 通過 manifest validation 不代表可訓練。

原則：

```text
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

## 7. 健康檢查失敗

檢查：

```text
http://127.0.0.1:<port>/api/health
http://127.0.0.1:<port>/api/version
```

若無回應，先查看 exe 是否仍在啟動中，再看 `logs/`。

## 8. 不小心產生大量暫存檔

使用：

```bat
scripts\clean_runtime.bat
```

此腳本只清理 build/cache/tmp 與 root smoke temp，不刪 `projects/`。

## 9. 產生診斷包

若需要排查啟動、資料夾、GPU、版本或近期錯誤，可產生 diagnostics zip：

```bat
scripts\diagnostics.bat
```

診斷包預設包含：

```text
diagnostics.json
health.json
project_summary.json
exclusions.json
logs/*.log
requirements.txt
version.json
```

診斷包預設不包含：

```text
raw images
videos
model weights
完整 project folder
```

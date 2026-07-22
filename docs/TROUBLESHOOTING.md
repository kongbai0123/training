# 疑難排解

## 1. 啟動失敗

常見原因：

- Python 或 packaged dependency 缺失。
- port 被占用。
- runtime folder 無法建立或無寫入權限。
- packaged exe 仍在執行，導致重新打包或覆蓋失敗。

先執行：

```bat
scripts\build.bat
scripts\start_dev.bat
```

查看日誌：

```text
logs/
```

## 2. Port 被占用

症狀：

```text
Address already in use
```

改用其他 port：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18105 --env production --shell none
```

也可以關閉正在執行的 `VisionTrainingStudio.exe`。

## 3. PyInstaller WinError 5

症狀：

```text
PermissionError: [WinError 5] Access is denied
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

通常代表 exe 仍在執行或被 Windows 鎖定。

處理方式：

```bat
taskkill /F /IM VisionTrainingStudio.exe
scripts\package.bat
```

## 4. 前端畫面異常或樣式沒更新

可能原因：

- browser cache。
- package 未重新建立。
- `static/vendor/` 沒有被打包。
- `static/index.html` 仍引用外部 CDN。

處理方式：

- 重新整理瀏覽器。
- 重新執行 `scripts\package.bat`。
- 檢查 browser console。
- 確認 `dist\VisionTrainingStudio\_internal\static\vendor\` 存在。

## 5. RNN / XGBoost CSV 無法訓練

請檢查：

- CSV 是否有 header row。
- feature columns 是否存在於 CSV。
- target column 是否存在於 CSV。
- task type 與 target 型態是否一致。
- sequence length、stride、horizon 是否合理。

readiness check 失敗時，先依 UI 顯示修正資料或設定，不要直接啟動訓練。

## 6. 模型匯入後不能訓練

模型匯入與訓練啟用是不同階段：

```text
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

custom package 需要通過 manifest validation、dry-run policy、enablement 與 integration checks。

## 7. 健康檢查

服務啟動後檢查：

```text
http://127.0.0.1:<port>/api/health
http://127.0.0.1:<port>/api/version
```

如果 health 無回應，查看 `logs\launcher.log` 與 backend log。

## 8. 清理暫存

清理開發環境暫存：

```bat
scripts\clean_runtime.bat
```

清理前確認不會刪除需要保留的 `projects/`、`models/` 或使用者資料。

## 9. 產生診斷報告

```bat
scripts\diagnostics.bat
```

診斷包預期包含：

```text
diagnostics.json
health.json
project_summary.json
exclusions.json
logs/*.log
requirements.txt
version.json
```

診斷包不得包含：

```text
raw images
videos
model weights
完整 project folder
```

## 10. 專案助理輸入後沒有回答

1. 確認已開啟專案。
2. 若顯示「請先同步專案產物」，按「立即同步」。
3. 送出後應顯示「正在搜尋」；若長時間未結束，檢查 `logs\launcher.log` 與 backend log。
4. 無來源回答代表知識庫沒有符合的專案依據，並非訓練失敗。

## 11. 評估圖表找不到下載檔

評估下載固定寫入 Windows 使用者的「下載」資料夾，而不是 AppData。下載成功通知會顯示完整路徑；同名檔案會另存為 `名稱 (1).svg`。若失敗，確認下載資料夾可建立與可寫入。

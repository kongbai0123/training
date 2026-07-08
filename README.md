# Vision Training Studio

Vision Training Studio 是一套本地優先的 AI 訓練與推論工具，目標是在 Windows 電腦上提供可安裝、可打包、可移植的商業級工作流程。系統目前支援 CNN / YOLO 影像訓練、LabelMe 標註整合、資料集切分、資料增強、模型評估、推論、模型比較，以及 RNN / Sequence / XGBoost 類型的序列資料訓練流程。

本專案不是單一 demo script，而是以可交付桌面軟體為目標設計：原始碼、執行資料、使用者專案、模型、日誌、暫存與打包輸出都有明確邊界。

## 主要功能

- CNN / YOLO 專案建立、影像匯入、LabelMe 標註同步、YOLO label 轉換。
- Train / Val / Test split、資料增強、品質檢查與輸出。
- YOLO 訓練、訓練狀態監控、run history、metrics、artifacts 與 weights 管理。
- RNN / Sequence 專案、CSV 匯入、feature / target 設定、readiness check。
- XGBoost baseline 與 PyTorch LSTM backend。
- 模型目錄、專案模型、匯入模型與 custom package manifest 驗證。
- 單機 FastAPI backend、靜態前端、桌面 launcher、診斷報告。
- PyInstaller onedir 打包與 Inno Setup installer 設定。

## 系統需求

- Windows 10 / 11 x64。
- 開發模式需要 Python 3.11。
- 前端語法檢查需要 Node.js，但正式 packaged runtime 不應要求使用者自行安裝 Node.js。
- GPU 為選配；沒有 NVIDIA GPU 時應回落 CPU 或顯示明確提示。
- 打包 installer 需要 PyInstaller；建立安裝檔需要 Inno Setup。

## 快速啟動

開發模式：

```bat
scripts\start_dev.bat
```

測試：

```bat
scripts\test.bat
```

建置檢查：

```bat
scripts\build.bat
```

打包：

```bat
scripts\package.bat
```

packaged runtime smoke test：

```bat
scripts\smoke_dist.bat
```

產生診斷報告：

```bat
scripts\diagnostics.bat
```

## 打包輸出

PyInstaller 打包後的主要執行檔：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

如果需要提供給一般使用者，應優先交付 installer 或 portable zip，而不是要求使用者進入 repo 根目錄執行開發腳本。

## 專案結構

應提交到 Git 的主要內容：

```text
app.py
launcher.py
src/
static/
tests/
docs/
packaging/
installer/
scripts/
README.md
requirements.txt
requirements-build.txt
version.json
VERSION
```

不應提交的 runtime / build / 使用者資料：

```text
projects/
models/
logs/
cache/
tmp/
build/
dist/
config/
licenses/
exports/
release_artifacts/
```

## Runtime Data

開發模式下，runtime data 預設放在 repo 根目錄下的 `projects/`、`models/`、`logs/`、`cache/`、`tmp/`。

packaged mode 下，`src/app_paths.py` 會依 frozen 狀態、portable root、`LOCALAPPDATA` 或環境變數解析 user data 位置。可用環境變數：

```text
VTS_APP_HOME
VTS_USER_DATA_DIR
VTS_PROJECTS_DIR
VTS_ENV
VTS_MODE
```

## API Health

啟動後可檢查：

```text
GET /api/health
GET /api/version
GET /api/bootstrap
```

## 文件

- [安裝指南](docs/INSTALL.md)
- [使用者指南](docs/USER_GUIDE.md)
- [開發者指南](docs/DEVELOPER_GUIDE.md)
- [架構文件](docs/ARCHITECTURE.md)
- [部署與打包](docs/DEPLOYMENT.md)
- [疑難排解](docs/TROUBLESHOOTING.md)
- [乾淨機器驗證](docs/CLEAN_MACHINE_VALIDATION.md)
- [測試規範](docs/TESTING_GUIDELINES.md)

## Release Gate

正式 release 前至少執行：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

若要宣稱 installer 可交付，還需要在乾淨 Windows VM 執行 `docs/CLEAN_MACHINE_VALIDATION.md` 的驗證流程。

## 安全注意事項

- 不得提交 API key、token、密碼、私有資料集、模型權重或使用者資料。
- custom model package 的 manifest / sandbox / dry-run 機制只能視為產品層防護，不應宣稱為完整 OS sandbox。
- diagnostics package 不應包含 raw images、videos、model weights 或完整 project folders。

## 目前狀態

目前狀態為 beta / commercial MVP hardening。CNN / YOLO 主流程較完整；RNN / Sequence / XGBoost 為可用但仍需持續強化的流程。正式商業交付前仍需通過完整 release gate 與乾淨機器驗證。

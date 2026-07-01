# Vision Training Studio

Vision Training Studio 是一套本地端 AI 訓練工作室，目標是在 Windows 環境中提供可啟動、可打包、可驗證的 CNN / YOLO、RNN / Sequence 與 XGBoost 訓練流程。

本專案定位為個人本地使用的產品化工具，不包含帳號、金鑰、計費、訂閱或雲端付費服務。設計標準以「可交付的本地商業級軟體」為目標：清楚的資料夾邊界、一鍵腳本、文件、測試、打包、錯誤排查與 release checklist。

## 主要功能

- CNN / YOLO 工作流：資料匯入、LabelMe 同步、資料分割、影像增強、模型訓練、評估、推論、匯出、run history。
- RNN / Sequence 工作流：CSV sequence 匯入、feature / target 設定、window config、readiness 檢查、XGBoost baseline training、RNN / XGBoost dashboard。
- Model Catalog：內建模型、導入模型、訓練產物與模型選擇流程。
- Model Compare：CNN / RNN 分流的模型比較入口與資料契約基礎。
- Artifacts / Run History：訓練輸出、metrics、summary、artifacts 與歷史紀錄管理。
- 本地打包：PyInstaller onedir 產物與 dist smoke test 流程。

## 系統需求

- Windows 10 / 11
- Python 3.11
- NVIDIA GPU 與 CUDA 建議使用，但 CPU fallback 可用於部分流程
- Node.js 僅用於前端 JavaScript syntax check
- PyInstaller 僅在打包時需要

## 快速啟動

開發模式：

```bat
scripts\start_dev.bat
```

執行測試：

```bat
scripts\test.bat
```

靜態檢查與 Python compile：

```bat
scripts\build.bat
```

打包：

```bat
scripts\package.bat
```

dist smoke test：

```bat
scripts\smoke_dist.bat
```

產生診斷包：

```bat
scripts\diagnostics.bat
```

## 專案資料夾邊界

以下是原始碼與產品化檔案，應進 Git：

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
```

以下是 runtime / build / 使用者資料，不應進 Git：

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
```

`projects/` 是使用者專案資料，清理腳本不會刪除它。

## 文件

- [安裝說明](docs/INSTALL.md)
- [使用者指南](docs/USER_GUIDE.md)
- [開發者指南](docs/DEVELOPER_GUIDE.md)
- [架構說明](docs/ARCHITECTURE.md)
- [部署與打包](docs/DEPLOYMENT.md)
- [疑難排解](docs/TROUBLESHOOTING.md)

## 發布標準

每次準備 release 前至少要通過：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

Release checklist 詳見 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 本地化與離線使用

前端必要資源已 vendor 到 `static/vendor/`，包含 Chart.js、Font Awesome、Dropzone 與 Inter 字型 fallback，避免企業內網或離線環境造成 UI 渲染不完整。

## 安全原則

- 不提交 API key、token、密碼或個人敏感資訊。
- 不把使用者資料、模型權重、訓練輸出提交到 Git。
- 模型 package / custom adapter 只允許依照 manifest 與 sandbox policy 逐階段啟用。
- diagnostics 預設不得包含 raw images 或 model weights。

## 目前狀態

目前定位：本地商業 Beta Candidate。CNN / YOLO 主流程已較完整，RNN / XGBoost 正在產品化收斂中。本輪目標不是新增更多模型功能，而是提升文件、腳本、打包、驗證與 UI 狀態一致性。

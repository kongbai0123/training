# 架構文件

## 1. 系統總覽

Vision Training Studio 是本地優先的 Windows AI 訓練工具。整體架構：

```text
launcher.py
  -> FastAPI app.py
    -> src/api/routes/*
    -> project services
    -> training dispatcher
      -> YOLO backend
      -> PyTorch LSTM backend
      -> XGBoost backend
    -> model catalog / registry / sandbox policy
    -> run manager / artifacts
  -> static frontend
```

`launcher.py` 負責啟動本機 backend、尋找可用 port、等待 health check、開啟 webview 或 browser。`app.py` 負責組裝 FastAPI routes、掛載 static frontend、處理全域錯誤與 production mode token 保護。

## 2. 啟動流程

```text
使用者啟動 exe 或 script
  -> launcher 解析 host / port / shell / env
  -> 檢查 port，必要時尋找下一個可用 port
  -> 啟動 uvicorn backend
  -> polling /api/health
  -> 開啟 webview 或 browser
  -> backend 結束時 launcher 清理 process
```

packaged mode 下，`src/app_paths.py` 會依 frozen 狀態解析 app home 與 user data。開發模式下，runtime data 預設位於 repo 根目錄。

## 3. API 邊界

API routes 位於：

```text
src/api/routes/
```

主要 route groups：

- `system.py`：health、version、bootstrap。
- `projects.py`：project CRUD。
- `project_layout.py`：layout report 與 migration。
- `datasets.py`：影像、影片、zip、local import。
- `annotation_labelme.py`：LabelMe sync、convert、annotation import。
- `dataset_split.py`：資料切分。
- `augmentation.py`：增強預覽與套用。
- `training_orchestration.py`：start training、compare、export。
- `training_runs.py`：run history、metrics、artifacts、stop、abort。
- `rnn_config.py`：sequence readiness、config、CSV import。
- `inference.py`：image / sequence inference。
- `models.py`：model catalog、import、custom package flow。
- `diagnostics.py`：diagnostics report。

## 4. Project Layout

`src/project_layout.py` 是資料樹標準來源。新專案使用 v3 layout：

```text
projects/{project_id}/
├─ project.json
├─ _meta/layout_version.json
├─ dataset/
│  ├─ images/raw
│  ├─ images/imported
│  ├─ images/rejected
│  ├─ videos/raw
│  ├─ videos/frames
│  └─ metadata
├─ annotations/
│  ├─ current/labelme
│  ├─ current/yolo
│  ├─ current/coco
│  ├─ current/masks
│  ├─ drafts/manual
│  ├─ drafts/auto_label
│  ├─ versions
│  └─ review
├─ splits/
├─ augmentations/jobs
├─ augmentations/profiles
├─ training/runs
├─ training/registry
├─ sequences
├─ auto_labeling/jobs
├─ inference/jobs
├─ inference/cache
├─ exports
├─ history
├─ logs
├─ tmp
└─ cache
```

legacy project 仍透過 resolver fallback 支援。新功能不得直接硬編碼 legacy path。

## 5. Training Architecture

`TrainerDispatcher` 根據 project training config 選擇 backend：

```text
ultralytics_yolo -> YOLOBackend
pytorch_lstm     -> RNNBackend
sklearn_xgboost  -> XGBoostBackend
```

訓練狀態由 `TrainingStateStore` 統一提供給 API / UI。thread runner 負責背景執行、duplicate guard、runner cleanup 與 lifecycle 管理。

## 6. Run Artifacts

每個 training run 預期輸出：

```text
metrics.json
run_summary.json
train_config.json
backend.json
metric_schema.json
artifact_manifest.json
weights/
```

compare、export、inference 應讀取 artifact manifest 與 run summary，不應依賴單一 backend 的私有輸出格式。

## 7. Model System

模型系統原則：

```text
Model Package First
Extension Second
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

模型來源包含 built-in catalog、imported models、project trained models 與 custom packages。custom package 必須經過 manifest validation、dry-run policy、enablement 與 integration checks。

## 8. Runtime Data

runtime data 與 source code 分離：

```text
projects/   使用者專案
models/     匯入或使用者模型
logs/       啟動與執行日誌
cache/      快取
tmp/        暫存
dist/       打包輸出
build/      打包中間產物
```

清理工具不得未告知刪除 `projects/` 或使用者模型資料。

# 架構文件

## 1. 系統總覽

Vision Training Studio 是本地優先的 Windows AI 訓練工具。整體架構：

公開資訊架構以資料為第一層：影像訓練、序列訓練、表格資料預測。CNN、RNN 與 XGBoost 僅作為內部相容識別或工作區內模型名稱；公開改名不會改寫資料契約。

```text
launcher.py
  -> FastAPI app.py
    -> src/api/routes/*
    -> project services
    -> training dispatcher
      -> YOLO backend
      -> RT-DETR backend
      -> TorchVision vision backend
      -> Transformers D-FINE backend
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
├─ dataset/tables
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
ultralytics_rtdetr -> RTDETRBackend
pytorch_torchvision -> TorchVisionBackend
transformers_dfine -> DFineBackend
pytorch_lstm     -> RNNBackend
sklearn_xgboost  -> XGBoostBackend
xgboost_tabular  -> TabularXGBoostBackend
```

視覺模型沿用既有 CNN 專案儲存格式，但以 `training_category` 區分圖片分類、物件偵測、實例分割與語意分割。這讓舊專案仍可讀取，同時避免所有 segmentation 模型混在同一組。TorchVision backend 直接讀取專案影像、類別、方框與 polygon 標註；D-FINE backend 將方框轉為 COCO annotation 後訓練。

Tabular 專案使用獨立 `tabular_classification`／`tabular_regression` task type 與 `TabularXGBoostBackend`。它與 RNN 的 `sklearn_xgboost` backend 共用低階訓練函式，但資料 loader、前處理契約、推論服務與工作區皆相互隔離，因此不會把既有序列專案改名或遷移。

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

`artifact_manifest.json` 使用 metadata contract v2，為每個已知產物記錄 SHA-256、content type、producer 版本，並可附帶 dataset/model lineage。`backend.json` 與 `metric_schema.json` 維持既有 v1 契約，避免舊讀取器誤判其 payload 已變更。

### Unified Evaluation Contract

評估 API 以已完成 Run 為唯一資料來源，輸出共同的 `metric_schema`、`metric_cards`、`capabilities` 與 `diagnostics`。UI 依 capability 顯示適用面板，而不是依畫面複製三套流程：

```text
completed run
  -> metrics.json + metric_schema.json
  -> normalized evaluation response
  -> shared classification/regression metrics
  -> image plots | sequence diagnostics | tabular feature importance
```

此邊界保留 `task_type`、`architecture`、`backend`、run 與 export contract 的相容性。舊影像專案的 `results.csv` 仍可 fallback；序列／表格資料的結構化 `history` 與 `best_metrics` 會直接正規化，不把影像 BBox／Polygon 或序列 Window／Stride 假設外洩至其他架構。

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

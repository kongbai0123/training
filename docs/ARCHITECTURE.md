# 架構說明

## 1. 高階架構

```text
launcher.py
  -> app.py / FastAPI
    -> project services
    -> training dispatcher
      -> YOLO / CNN backend
      -> RNN / XGBoost backend
    -> model catalog / import / registry
    -> run manager / artifacts
  -> static frontend
```

## 2. 啟動層

`launcher.py` 負責產品模式啟動，包括：

- port 選擇
- production / development mode
- health polling
- desktop shell 或 browser 啟動
- logs 目錄初始化

`app.py` 提供 FastAPI routes、static assets 與主要 API。

## 3. Training State 與 Runner

`TrainingStateStore` 擁有 UI / API 可見的 active training state：

```text
status
epoch
total_epochs
metrics
error
run_id
backend
architecture
timestamps
```

`ThreadTrainingJobRunner` 擁有 active thread registry、duplicate guard 與 runner cleanup。訓練 execution lifecycle 仍由對應 backend / trainer 控制。

## 4. CNN / YOLO

CNN workflow 包含：

- dataset import
- LabelMe / YOLO label conversion
- split
- augmentation
- YOLO training
- evaluation
- inference
- export
- compare

YOLO 訓練流程不得因產品化文件與腳本清理而改變。

## 5. RNN / Sequence / XGBoost

RNN workflow 包含：

- CSV sequence import
- feature / target config
- sequence window config
- readiness
- model selector
- XGBoost baseline training
- dashboard / history / artifacts

XGBoost 是可用 baseline；RNN deep learning 模型仍需依 readiness 與 backend 實作狀態標示。

## 6. Run Artifacts

每個 run 應盡量具備：

```text
metrics.json
run_summary.json
train_config.json
backend.json
metric_schema.json
artifact_manifest.json
weights/
```

舊 run 缺少部分 contract 檔案時，服務層應 fallback，而不是直接失敗。

## 7. Model System

模型系統分為：

- Built-in model catalog
- Imported models
- Project trained models
- Custom package / adapter roadmap

核心原則：

```text
Model Package First
Extension Second
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

## 8. Runtime Data

runtime data 與 source code 分離：

```text
projects/   使用者專案
models/     導入模型與模型資產
logs/       日誌
cache/      快取
tmp/        暫存
dist/       打包輸出
build/      打包中間產物
```

`clean_runtime.bat` 不得刪除 `projects/`。

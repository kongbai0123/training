# 使用者指南

Vision Training Studio 提供本機 AI 訓練與推論流程。使用者主要透過瀏覽器或桌面 shell 操作 UI，後端服務只綁定本機位址。

## 1. 建立專案

1. 開啟應用程式。
2. 進入 Projects。
3. 建立新專案，選擇任務類型。
4. 輸入專案名稱與 class names。

新專案會使用 v3 layout，資料會放在：

```text
projects/{project_id}/
```

## 2. CNN / 視覺模型流程

典型流程：

1. 建立 CNN / 視覺模型專案，選擇圖片分類、物件偵測、實例分割或語意分割。
2. 匯入影像或資料夾。
3. 使用 LabelMe 建立或同步標註。
4. 偵測與分割任務需建立方框或 polygon；圖片分類可依類別資料夾匯入，不需要畫框。
5. 建立 Train / Val / Test split。
6. 視需要執行資料增強。
7. 設定 model、epochs、batch size、image size、device。
8. 開始訓練並查看 dashboard、metrics、artifacts。
9. 使用已訓練模型進行推論、評估、比較或匯出。

訓練模型選單固定依任務分類：

- **圖片分類（整張圖，不畫框）**：ResNet18、MobileNetV3 Large、EfficientNet-B0。
- **物件偵測（方框）**：YOLO、RT-DETR、D-FINE Small、Faster R-CNN、FCOS。
- **物件輪廓分割（可分別計數）**：YOLO Segmentation、Mask R-CNN。
- **畫面區域分割（像素分類）**：U-Net、DeepLabV3。

尚未安裝的預訓練權重仍會顯示「需先安裝」，不會從清單消失。內建 U-Net 是程式模板，不需要另外下載。ByteTrack 與 BoT-SORT 用於影片推論中的跨幀追蹤，不是獨立訓練模型，因此不列在訓練模型選單。

## 3. RNN / Sequence / XGBoost 流程

典型流程：

1. 建立 RNN / Sequence 專案。
2. 匯入 CSV sequence data。
3. 設定 feature columns 與 target column。
4. 設定 sequence length、stride、horizon。
5. 執行 readiness check。
6. 選擇 PyTorch LSTM 或 XGBoost backend。
7. 開始訓練並查看 metrics、artifacts 與 run history。

RNN deep learning backend 仍屬 beta；XGBoost baseline 適合作為 tabular / sequence baseline。

## 4. Feature Columns 格式

feature columns 可使用逗號或分號分隔，例如：

```text
speed,acceleration,temperature
```

請確認 CSV header 內存在所有 feature columns 與 target column。若欄位不存在，readiness check 會阻止訓練。

## 5. Model Catalog

模型來源分為：

- Built-in models
- Imported models
- Project trained models

匯入模型不代表可直接訓練：

```text
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

custom package 需要通過 manifest validation、dry-run policy 與 enablement 狀態檢查。

## 6. Run History 與 Artifacts

每次訓練會產生 run folder，常見內容包括：

```text
metrics.json
run_summary.json
train_config.json
backend.json
metric_schema.json
artifact_manifest.json
weights/
```

請透過 UI 或 API 管理 run history，不要手動刪除仍在使用中的 run 資料。

## 7. 安全使用

- 不要把私有資料集、模型權重或專案資料提交到 Git。
- 不要手動移動 `projects/{project_id}` 內部資料夾，除非同時更新 project metadata。
- 若遇到啟動或訓練問題，先查看 `logs/`，再執行 `scripts\diagnostics.bat`。

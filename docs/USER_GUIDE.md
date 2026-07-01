# 使用者指南

Vision Training Studio 以左側模式切換分成 CNN 與 RNN / Sequence 兩個工作域。上方共同功能包含總覽、歷史紀錄與設定；其餘功能依目前模式切換。

## 1. CNN / YOLO 工作流

建議順序：

1. 建立或開啟專案。
2. 進入資料集頁面匯入圖片、ZIP 或資料夾。
3. 使用 LabelMe 或匯入標註。
4. 建立 Train / Val / Test split。
5. 視需求設定物理擴充。
6. 進入 CNN 模型訓練，選擇模型、epochs、batch size、image size 與 device。
7. 開始訓練並查看 dashboard、epoch history、artifacts 與 run history。
8. 使用模型測試、模型比較或匯出功能。

## 2. RNN / Sequence 與 XGBoost 工作流

建議順序：

1. 建立 RNN / Sequence 專案。
2. 匯入 CSV feature sequence。
3. 設定 feature columns 與 target column。
4. 設定 sequence window，例如 sequence length、stride、horizon。
5. 執行 readiness 檢查。
6. 選擇 RNN / XGBoost 模型。
7. 若選擇 XGBoost baseline，可直接訓練並檢視 dashboard、artifacts 與 run history。

RNN deep learning backend 仍以 Preview / Beta 語意呈現；XGBoost baseline 已可作為 tabular / sequence baseline 使用。

## 3. Feature Columns 快速輸入

Feature 欄位支援以逗號或分號快速輸入，例如：

```text
speed,acceleration;temperature
```

系統會切成 chips 並與 CSV 欄位做 readiness 檢查。修改 feature / target 後，舊 run 可能顯示 config mismatch，代表該 run 使用的欄位設定與目前設定不同。

## 4. Model Catalog 與模型導入

模型選擇分為：

- Built-in models
- Imported models
- Project trained models

目前可訓練的 CNN 導入模型以 YOLO `.pt` 為主。其他 package / adapter 類型需通過 manifest 與 sandbox policy，未啟用前不會加入訓練 selector。

## 5. 歷史紀錄

Browse History / Run History 用於管理 CNN、RNN、XGBoost 相關專案、訓練 run、artifacts 與推論紀錄。RNN / XGBoost 類資料應以 sequence / tabular 語意顯示，避免混入 CNN image history。

## 6. 進度與狀態

長時間作業會以 HUD / 狀態卡提示目前狀態。若看到 disabled、warning 或 error，請先依 UI 提供的修復建議完成前置條件。

## 7. 建議操作方式

- 不要手動刪除 `projects/` 內檔案，除非確定不再需要該專案。
- 清理暫存請使用 `scripts\clean_runtime.bat`。
- 若 UI 顯示與預期不一致，先重整頁面並檢查 `logs/`。

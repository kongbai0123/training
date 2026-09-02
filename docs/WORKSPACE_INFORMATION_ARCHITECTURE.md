# 工作區資訊架構

## 分類原則

使用者先依「資料長什麼樣」選擇工作區，再於工作區內選擇模型。頂層不得使用 CNN、RNN、YOLO 或 XGBoost 等演算法名稱。

| 舊公開名稱 | 新公開名稱 | 適用資料 | 內部相容識別 |
| --- | --- | --- | --- |
| CNN 視覺訓練 | 影像訓練 | 圖片、方框、Polygon、像素遮罩 | `cnn` 與既有影像 `task_type` |
| RNN 序列訓練 | 序列訓練 | 有時間順序、序列 ID、Window／Stride／Horizon 的資料 | `rnn`、`sequence_classification`、`sequence_regression` |
| Tabular 表格模型 | 表格資料預測 | 每列互相獨立的 CSV 樣本 | `tabular`、`tabular_classification`、`tabular_regression` |

公開名稱只影響導覽與說明，不得改寫既有 `task_type`、`architecture`、`backend`、專案 JSON、Run 或匯出套件。

## 如何選擇工作區

- 資料包含圖片或要輸出分類、BBox、Polygon、遮罩：選「影像訓練」。
- 預測需要前後時間順序、同一設備／個體的連續觀測或滑動視窗：選「序列訓練」。
- 每列 CSV 可獨立判斷，不需要參考上一列或下一列：選「表格資料預測」。
- XGBoost 是模型選項，不是資料型態。它可在序列工作區作為展平視窗 baseline，也可在表格工作區處理獨立資料列。

## 專屬與共用頁面

| 工作區 | 專屬資料準備 | 共用生命週期頁面 | 模型選項範例 |
| --- | --- | --- | --- |
| 影像訓練 | 圖片、影像標註、資料分割、影像增強、自動標註 | 訓練、評估、模型測試、Run 比較、模型版本、匯出 | YOLO、RT-DETR、D-FINE、TorchVision、U-Net |
| 序列訓練 | CSV 序列、時間欄位、序列 ID、特徵／目標、Window／Stride／Horizon | 訓練、評估、序列測試、Run 比較、模型版本、匯出 | LSTM、GRU、BiLSTM、XGBoost baseline |
| 表格資料預測 | CSV 欄位、特徵 X、目標 Y、缺失值與切分設定 | 訓練、評估、單筆／批次測試、Run 比較、模型版本、匯出 | XGBoost（目前提供） |

共用頁面共用導覽、Run 與狀態語意；內容依 capability 顯示。影像專屬 BBox／Polygon、序列專屬 Window／Stride、表格專屬特徵重要度不得出現在不相容工作區。

## 相容性規則

1. 不執行自動破壞式資料遷移。
2. 舊名稱與舊頁面識別應安全映射至新公開名稱。
3. API 與儲存格式繼續使用既有機器識別；只替換使用者可見文案。
4. 模型能力由 `task_type`、`architecture`、`backend` 與 Run artifact 判斷，不以翻譯後的顯示名稱判斷。

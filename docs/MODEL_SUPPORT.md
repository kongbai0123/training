# 模型支援矩陣

## 狀態定義

| 狀態 | 定義 |
|---|---|
| 可執行 | 已接入訓練生命週期，具備測試與對應產物 |
| 選配下載 | 不隨原廠程式附帶，需由使用者確認下載 |
| 研究輪廓 | 只提供 benchmark 與選型資訊，不允許執行 |
| 待研究 | 尚未完成 Windows、授權、訓練與匯出驗證 |

## CNN 視覺模型

| 家族 | 任務 | 型號 | 狀態 | 後端 | 授權重點 |
|---|---|---|---|---|---|
| YOLOv8 | Detection / Segmentation | n、s、m、l、x | 可執行、選配下載 | `ultralytics_yolo` | AGPL-3.0 或商業授權 |
| YOLO11 | Detection / Segmentation | n、s、m、l、x | 可執行、選配下載 | `ultralytics_yolo` | AGPL-3.0 或商業授權 |
| YOLO26 | Detection / Segmentation | n、s、m、l、x | 可執行、選配下載 | `ultralytics_yolo` | AGPL-3.0 或商業授權 |
| RT-DETR | Detection | L、X | 可執行、選配下載 | `ultralytics_rtdetr` | Ultralytics 發行與執行條款 |
| RF-DETR | Detection / Segmentation | Nano、Small、Medium、Large | 研究輪廓 | `rfdetr_external` | Apache-2.0；Plus 型號另有 PML 1.0 |
| D-FINE | Detection | 尚未開放 | 待研究 | 尚未接線 | 需完成授權與 Windows 驗證 |
| Faster / Mask R-CNN | Detection / Segmentation | 尚未開放 | 待研究 | 尚未接線 | torchvision BSD-3-Clause；產物能力待驗證 |

## RNN 與結構化序列模型

| 家族 | 任務 | 狀態 | 後端 |
|---|---|---|---|
| LSTM | Sequence Classification / Regression | 可執行 | `pytorch_lstm` |
| GRU | Sequence Classification / Regression | 可執行 | `pytorch_lstm` |
| BiLSTM | Sequence Classification / Regression | 可執行 | `pytorch_lstm` |
| XGBoost | Sequence Classification / Regression | 可執行 | `sklearn_xgboost` |
| FastRNN | Sequence Classification / Regression | 規劃中，不可執行 | `pytorch_fastrnn` |
| Isolation Forest | 異常探索 | 規劃中，不可執行 | `sklearn_isolation_forest` |

## 模型尺寸

| 後綴 | 定位 | 適用情境 |
|---|---|---|
| n | Nano | CPU、低顯存、快速驗證 |
| s | Small | 一般本機訓練與速度／品質平衡 |
| m | Medium | 中高階 GPU、較高品質需求 |
| l | Large | 高顯存、品質優先 |
| x | Extra Large | 最大容量、長時間訓練與高階 GPU |

模型中心會依目前任務、資料量、GPU、VRAM、RAM、磁碟與速度／精度目標排序。硬體不足的模型不會消失，但會顯示不建議或不可使用原因。

## Benchmark 使用原則

- 官方與第三方 benchmark 必須顯示來源、資料集、輸入尺寸與執行環境。
- 不同資料集、硬體或輸入尺寸的數值不可直接判定模型優劣。
- 官方 benchmark 只用於選型；最終決策應以目前專案的 run 指標為準。
- 同模型不同 run 應在模型比較頁使用本機產物比較。

## RF-DETR 研究閘門

RF-DETR 1.8.3 的套件 metadata 未宣告 Windows 支援，訓練 extras 也會引入獨立依賴堆疊。因此目前採預設拒絕：

1. 不在主 runtime 自動安裝 `rfdetr`。
2. 不把研究模型標示為可訓練。
3. 模型中心只顯示 Apache-2.0 型號；Plus 型號不納入執行。
4. 必須完成隔離依賴、Windows GPU 訓練、評估、推論、ONNX 與 packaged smoke 後才可升級狀態。

研究狀態的機器可讀資料位於 `data/model_research_registry.json`，API 為 `GET /api/models/research`。

## RT-DETR 驗證

2026-07-12 開發機 smoke：

- 硬體：NVIDIA GeForce RTX 3060 12 GB
- 模型：RT-DETR-L
- 資料：COCO8
- 設定：1 epoch、320 px、batch 2
- 結果：成功產生 `best.pt`、`last.pt`、`results.csv`
- 驗證：mAP50-95 約 0.66
- 推論：成功產生預測
- 匯出：成功產生約 122.7 MB ONNX

這項 smoke 證明開發環境鏈路可用，但不取代乾淨 Windows portable ZIP 驗收。

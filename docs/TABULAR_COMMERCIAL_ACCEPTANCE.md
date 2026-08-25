# Tabular 商業 CSV 產品驗收

本文件定義 Tabular XGBoost 的可重現產品驗收方式，並記錄 2026-08-25 的實際驗收結果。目的不是比較最先進演算法，而是確認真實商業型 CSV 能完整走通「匯入、設定、訓練、比較、推論、登錄、生命週期與匯出」閉環。

## 驗收結論

- 結果：通過
- 情境：商業分類 1 組、商業迴歸 1 組
- 服務檢查：40 / 40 通過
- 線上來源模式：通過
- 純離線快取模式：通過
- 兩次執行的資料投影 SHA-256 與四組主要訓練指標完全一致

本次執行環境為 Windows AMD64、Python 3.11.9、NumPy 2.4.6、XGBoost 3.2.0。此結果證明目前環境的產品閉環可用，不等同於已完成所有目標電腦的跨機驗證。

## 官方資料來源

### 商業分類：Online Shoppers Purchasing Intention

- 官方頁面：[UCI dataset 468](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset)
- DOI：[10.24432/C5F88Q](https://doi.org/10.24432/C5F88Q)
- 授權：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- 原始壓縮檔 SHA-256：`2972e6184d3ad7beaaa831d9fc2b059dc3ee29df69d1ec593c466a5cd8485d14`
- 原始筆數：12,330
- 任務：是否完成購買的二元分類

數值投影使用 10 個欄位：`administrative`、`administrative_duration`、`informational`、`informational_duration`、`product_related`、`product_related_duration`、`bounce_rates`、`exit_rates`、`page_values`、`special_day`。目標欄位為 `purchase_completed`。

因目前第一方 Tabular 契約只接受數值特徵，本驗收明確排除 `Month`、`OperatingSystems`、`Browser`、`Region`、`TrafficType`、`VisitorType`、`Weekend`。投影會固定加入 98 個特徵缺失值，以驗證只使用訓練切分擬合的 median 補值流程。投影 SHA-256 為 `eb530a3da4399b72dd5c6bd4a040346152ae4cf9da5e3cb1834b16fb8229c48d`。

### 商業迴歸：Seoul Bike Sharing Demand

- 官方頁面：[UCI dataset 560](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand)
- DOI：[10.24432/C5F62R](https://doi.org/10.24432/C5F62R)
- 授權：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- 原始壓縮檔 SHA-256：`139e9908f0a3544bb222386855c9ce107e96467306bb8e4ce936aab59e7baac4`
- 原始筆數：8,760
- 任務：租借腳踏車數量迴歸

數值投影使用 9 個欄位：`hour`、`temperature_c`、`humidity_pct`、`wind_speed_m_s`、`visibility_10m`、`dew_point_c`、`solar_radiation_mj_m2`、`rainfall_mm`、`snowfall_cm`。目標欄位為 `rented_bike_count`。

本驗收明確排除 `Date`、`Seasons`、`Holiday`、`Functioning Day`，固定加入 84 個特徵缺失值。投影 SHA-256 為 `46a75c49de68a4c882a462fd756cd157f55930b3fe0a48a66fc79b68bdd69d91`。

## 實際結果

| 情境 | 訓練切分 | 驗證切分 | 測試切分 | Baseline | Candidate | 品質門檻 | 結果 |
|---|---:|---:|---:|---:|---:|---:|---|
| Online Shoppers 分類 | 8,632 | 1,849 | 1,849 | Macro-F1 0.756311 | Macro-F1 0.787311 | Macro-F1 >= 0.55 | 通過 |
| Seoul Bike 迴歸 | 6,132 | 1,314 | 1,314 | MAE 270.879421 / R² 0.659918 | MAE 197.478178 / R² 0.768630 | R² >= 0.40 | 通過 |

每個情境都以不同超參數完成 baseline 與 candidate 兩次真實 XGBoost 訓練。候選模型之後被用於單筆與 32 筆批次推論、比較報告、模型版本 `v2`、`pending_validation → validated → production` 轉移，以及 Tabular model package 匯出。

## 逐項驗收範圍

每個情境均驗證以下 20 項，共 40 項：

1. CSV 匯入筆數正確。
2. 數值特徵、目標、比例與缺失值策略設定有效。
3. 固定 seed 的 train / validation / test 切分與補值統計可重現。
4. 控制式缺失值確實經過 median 補值。
5. Baseline 訓練完成。
6. Baseline 必要成品存在。
7. Baseline metadata contract v2 與資料 lineage 完整。
8. Baseline 特徵重要度完整且只引用已設定特徵。
9. Candidate 訓練完成。
10. Candidate 必要成品存在。
11. Candidate metadata contract v2 與資料 lineage 完整。
12. Candidate 特徵重要度完整。
13. 兩個 run 可透過比較服務比較並產生建議。
14. 比較服務可輸出 JSON、Markdown、CSV 與 PDF 報告。
15. 單筆推論輸出合法。
16. 32 筆批次 CSV 推論輸出合法。
17. 模型登錄中心保留資料、參數與評估 lineage。
18. 候選模型可依合法狀態轉移升為 production。
19. 匯出 ZIP 的 CRC 與必要模型／前處理／推論契約檔案完整。
20. 商業資料 smoke quality gate 通過。

## 如何重現

首次執行會從上述官方 UCI 位址下載兩個壓縮檔，並在使用前核對固定 SHA-256。原始壓縮檔只會放在被忽略的 `cache/acceptance/uci`，不提交到版本庫。專案、投影 CSV 與模型訓練成品預設建在隔離暫存目錄，執行結束後移除。

```powershell
python scripts/run_tabular_commercial_acceptance.py
```

第一次成功後可禁止網路並重用已驗證快取：

```powershell
python scripts/run_tabular_commercial_acceptance.py --offline
```

機器可讀與人類可讀報告會產生於：

- `build/reports/tabular_commercial_acceptance/acceptance_report.json`
- `build/reports/tabular_commercial_acceptance/acceptance_report.md`

若要保留隔離專案供稽核，可指定工作目錄；該目錄必須位於可安全清理且不含既有使用者資料的位置：

```powershell
python scripts/run_tabular_commercial_acceptance.py --work-dir build/tabular_acceptance_work --keep-work-dir
```

## 可重現性與安全邊界

- 下載來源、壓縮檔成員名稱與 SHA-256 都固定；來源內容變動時直接失敗，不會悄悄換資料。
- CSV 投影使用標準函式庫，欄位順序、換行、標籤映射與缺失值位置固定。
- 同一個 seed 同時控制資料切分與 XGBoost 訓練。
- 缺失值只注入特徵，不變更目標；補值統計只由 training split 擬合。
- 原始大型資料不納入 Git；報告與暫存成品位於既有忽略目錄。
- 驗收會改寫隔離專案根路徑，不會讀寫正式使用者專案。

## 限制與後續驗收

- 本里程碑只涵蓋數值特徵。類別編碼與日期特徵應等正式 contract 擴充後再加入，不應在驗收程式內偷偷做一套不同的前處理。
- 品質門檻是產品 smoke gate，不代表最佳模型或正式業務 SLA。
- 目前實測只覆蓋 Windows AMD64；發行前仍應在實際 portable runtime 與至少一台乾淨目標電腦重跑離線模式。
- 若未來更換資料集、欄位投影、缺失值位置、split contract 或模型版本，必須更新固定雜湊、重新跑完整閉環並保留新的報告。

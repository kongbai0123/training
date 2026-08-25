# v0.2.0 增量更新驗證紀錄

驗證日期：2026-08-25

目標版本：`0.2.0`

來源版本：`0.1.12`

Runtime：`r1`

更新包格式：`1`

## 結論

`VisionTrainingStudio_Update_0.2.0_runtime-r1.vtsupdate` 已通過商業 CSV 產品閉環、完整自動測試、封裝啟動、簽章、雜湊、交易式套用、自動回復及中斷復原驗證。更新只包含第一方程式與 Web 資產，未修改 runtime、後端 API、專案 schema 或使用者資料格式，可由 `v0.1.12` 安全增量升級。

## 發布資產

| 項目 | 結果 |
|---|---|
| 更新包 | `VisionTrainingStudio_Update_0.2.0_runtime-r1.vtsupdate` |
| 檔案大小 | 71,580,929 bytes |
| SHA-256 | `1277b8d8050ed9cea2a3528f2aa97ed75046006ad28658b1e902c07edda75850` |
| 簽章 | Ed25519 驗證通過 |
| 簽章金鑰 ID | `b2170ea6a93b6c26` |
| 變更檔案 | 26 |
| 移除檔案 | 0 |
| `supported_from` | `0.1.12` |
| Runtime 變更 | 0；維持 `r1` |

## 商業 CSV 驗收

以官方 UCI 資料完成兩組真實 XGBoost 訓練與完整模型生產閉環，詳細欄位、固定雜湊、來源授權及重現方式見 [Tabular 商業 CSV 產品驗收](TABULAR_COMMERCIAL_ACCEPTANCE.md)。

| 情境 | 資料量 | 候選結果 | 產品檢查 |
|---|---:|---|---:|
| Online Shoppers 分類 | 12,330 筆、10 個特徵 | Macro-F1 `0.787311` | 20 / 20 |
| Seoul Bike 回歸 | 8,760 筆、9 個特徵 | R² `0.768630`、MAE `197.478178` | 20 / 20 |

合計 40 / 40 項通過，涵蓋欄位辨識、缺失值、可重現切分、兩組實際訓練、metadata v2、特徵重要度、單筆／32 筆批次預測、比較報告、模型登錄、生命週期與匯出套件。線上下載模式與固定快取的純離線模式均通過。

## 程式與介面驗證

- Python 完整測試：`579 passed`。
- Tabular 只會在訓練產物與專案狀態都成功持久化後發布完成／停止等終止狀態；若產物收尾或專案儲存失敗，run 會轉為失敗，且記憶體中的專案變更會回滾，不會留下假完成狀態。
- GitHub Windows runner 曾攔截到 `runneradmin`／`RUNNER~1` 長短路徑別名誤判；修正後仍拒絕 traversal、symbolic link 與 reparse point 繞過，本地完整測試維持通過，正式發布以最後 `main`／tag CI 全部通過為硬閘門。
- JavaScript 語法與 Python compile 建置檢查：通過。
- 繁中 DOM 稽核：11 個主要頁面、1,265 個可見節點、0 問題。
- 英文 DOM 稽核：11 個主要頁面、1,265 個可見節點、0 問題。
- 實際瀏覽器驗收：總覽、欄位、訓練結果、單筆預測、32 筆批次預測、比較、模型版本與匯出均通過。
- 1024 × 768 響應式檢查：無水平溢位。

## 封裝與 Runtime 驗證

- 發布建置環境已與公開 `v0.1.12 runtime-r1` 的 58 個可辨識套件版本逐一比對，差異為 0，`pip check` 通過。
- 曾在發布閘門攔截到建置環境漂移造成的 Pydantic core 不相容；對齊 runtime 後重新建置，未把 runtime 差異納入更新包。
- 凍結程式固定使用 runtime 內建的 h11 HTTP 傳輸，避免選取不完整的選用 httptools namespace。
- 安裝模式離線 smoke：`v0.2.0 / runtime-r1` 啟動成功，0 個預載使用者專案、0 個自動模型下載、0 個外部連線。
- 可攜模式離線 smoke：`v0.2.0 / runtime-r1` 啟動成功，使用者資料正確留在可攜目錄且測試後清理。
- 封裝版直接讀取兩個商業 Tabular 專案；分類單筆預測回傳 `no_purchase`、信心度 `0.99189072`、延遲 `5.240 ms`，回歸單筆預測回傳 `156.3956604`、延遲 `0.827 ms`。

## 更新器驗證

- 更新包 manifest：`target_app_version=0.2.0`、`runtime_version=r1`、`supported_from=[0.1.12]`、`remove=[]`。
- 公開金鑰驗證簽章與全部 26 個 payload SHA-256：通過。
- 以 `v0.1.12` 安裝副本執行正式 updater：交易完成，版本變成 `v0.2.0`。
- 更新後重新啟動離線 smoke：通過。
- 故意移除 staging 版本檔：更新自動回復，26 個受影響檔案完整還原。
- 模擬套用 `_internal/version.json` 後中斷：啟動復原將 26 個受影響檔案完整還原。
- 回復後版本維持 `v0.1.12`，主程式 SHA-256 與原始基線完全相同。

## 相容性與限制

- 既有 CNN、RNN、Tabular 專案與訓練紀錄不需遷移。
- 本版 Tabular 首版只接受數值型特徵；類別與日期欄位仍需由使用者在匯入前轉換。
- 商業資料品質門檻是產品 smoke gate，不代表特定客戶資料的正式 SLA。
- `.vtsupdate` 不是完整安裝程式；新安裝仍以 `v0.1.6` 完整安裝基準開始，再依序更新。
- GitHub 正式發布後，另由公開 latest-release API 與 `v0.1.12` 設定頁再次確認偵測與下載；該網路端結果記錄於本次交付報告。

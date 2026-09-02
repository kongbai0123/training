# 工作區相容性與回滾

本文件定義「影像訓練／序列訓練／表格資料預測」公開名稱重整後的相容邊界。公開名稱與導覽可以更新，已儲存的資料契約不得因此改名。

## 保留的資料契約

- 影像專案沿用既有 `object_detection`、`image_classification`、`instance_segmentation`、`semantic_segmentation`。
- 序列專案沿用 `sequence_classification`、`sequence_regression`；序列 XGBoost backend 仍為 `sklearn_xgboost`。
- 表格專案沿用 `tabular_classification`、`tabular_regression`；backend 仍為 `xgboost_tabular`。
- `project.json` 的未知欄位、`training_runs`、模型登錄資料、run artifacts 與匯出套件不因公開名稱重整而移除或重新命名。
- 讀取舊專案只允許補上缺少的安全預設欄位；不會自動更換 `task_type`、backend，亦不會搬移或刪除資料。需要資料根目錄搬移時，必須另外明確執行遷移工具；預設採複製且保留來源。

## 舊網址映射

路由會先集中正規化，再依專案種類套用頁面隔離：

| 舊頁面識別 | 目前頁面 |
| --- | --- |
| `rag-workbench`、`project-assistant` | `dashboard`（開啟專案助理） |
| `cnn`、`cnn-training` | `training` |
| `rnn`、`rnn-training` | `training` |
| `tabular-model`、`tabular-training` | `tabular` |
| `compare` | `model-compare` |
| `labelme-manager` | `labelme` |

未知頁面識別會安全回到 `dashboard`，不顯示空白工作區。舊頁面映射不會改寫網址以外的專案資料。

## 回滾方式

1. 在發佈前保留目前版本的完整安裝包與專案資料備份。
2. 若新版工作區發生回歸，先停止程式，再以同一安裝方式恢復上一個完整版本；不得使用已撤銷的 `0.2.0 runtime-r1` 增量包。
3. 專案格式識別仍使用原本的 `task_type`、backend 與 artifact contract，因此介面程式回滾不需要批次反向遷移專案。
4. 若曾由使用者明確執行資料根目錄遷移，來源預設仍保留；確認目標副本後才可由使用者另行決定是否刪除來源。
5. 回滾後以既有 CNN、RNN、Tabular 專案各開啟一次，確認 Run History、模型、評估與匯出資料仍可讀。

Windows 正式發佈仍須通過程式碼簽章與完整安裝包門檻；未簽章 QA EXE 不得宣稱為正式對外版本。

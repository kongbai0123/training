# Vision Training Studio 第三方授權盤點（Phase 0）

本文件先做產品化基礎盤點，對應 `requirements.txt`、前端靜態依賴與可執行載入模組。

## 狀態定義

- **Allowed**：允許在閉源商業軟體使用（需保留授權聲明）
- **Notice required**：需保留 NOTICE / LICENSE 檔與授權文字
- **Copyleft risk**：需確認是否觸法或需額外授權條件
- **Commercial license required**：建議商業授權或額外審核
- **Unknown / needs review**：需進一步確認版本與授權條款

## 核心 Python 套件

| 套件 | 版本 | 授權盤點 | 備註 |
|---|---|---|---|
| fastapi | 0.133.1 | Allowed | MIT (預期) |
| uvicorn | 0.41.0 | Allowed | BSD 系列 |
| pydantic | 2.13.4 | Allowed | MIT |
| numpy | 2.4.6 | Allowed | BSD |
| Pillow | 12.2.0 | Allowed | PIL 相關授權 |
| opencv-python | 4.13.0.92 | Notice required | 需確認實際 wheel 套件授權條款 |
| ultralytics | 8.4.68 | Commercial risk | 需確認與版本綁定的商業授權要求 |
| torch (間接) | 依安裝版本 | Notice required | AGPL 機會已排除，但需以實際安裝套件版本確認 |
| nvidia-ml-py | 13.610.43 | Allowed | Apache/MIT 派生（以實際套件為準） |

## 前端與資源

| 套件/資源 | 授權盤點 | 備註 |
|---|---|---|
| Chart.js | Notice required | 需保留授權資訊 |
| Font Awesome | Notice required | CDN/套件來源需確認 |
| Dropzone | Notice required | 需保留 LICENSE/授權註明 |

## 後續行動

- 將 `docs/compliance/license_inventory.md` 與 `docs/compliance/license_inventory.csv` 與 `requirements.txt` 版本一致凍結，作為商用前提文件之一。
- `docs/reports/commercial_risk_report.md` 應補齊 Ultralytics / Torch / 權重檔授權核對結果。
- 所有對外釋出前先輸出完整 `docs/compliance/THIRD_PARTY_LICENSES.md`。

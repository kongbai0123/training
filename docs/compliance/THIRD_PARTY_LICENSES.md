# Vision Training Studio 第三方授權彙整

> 初始化版本：Phase 0（先行盤點）。此檔需在正式打包前完成最終收斂。

## 目的

建立可追溯的第三方授權清單，降低商業化交付風險，避免交付前期臨時補文件造成中斷。

## 清單

- FastAPI / Uvicorn / Pydantic
  - 建議保留官方 LICENSE 文字與版權聲明
- NumPy / Pillow / OpenCV / nvidia-ml-py
  - 保留各自套件授權
- Ultralytics / YOLO
  - 需特別確認特定版本授權策略與是否需商業授權
  - 若授權不明確，需改為不對外宣稱閉源授權保證後再上線
- 前端套件（Chart.js, Font Awesome, Dropzone）
  - 專案發佈資料夾需包含授權聲明頁與 NOTICE 檔

## 建議作法

1. 新增 `licenses/` 或 `third_party/` 資料夾並存放各授權檔。
2. 在安裝器提供「授權聲明」頁面連結。
3. 在診斷報告中保留 `docs/compliance/license_inventory` 與 `docs/reports/commercial_risk_report` 的快照。

# Vision Training Studio 商業化授權風險報告（Phase 0）

## 結論（暫估）

- 目前可先進行「商業化試營運版本」規格驗證，但**正式簽交前**需完成 `Ultralytics / Torch` 授權最終確認。
- 本輪優先建立產品化基礎（路徑治理、啟動器、token、授權閘道、diagnostics），不進行最終商用法務定稿。

## 主要風險項

1. **Ultralytics / YOLO 授權一致性**
   - 目前以版本 `8.4.68` 為主，需以發行版 LICENSE + 官方商業條款為準。
   - 若授權條件要求公開衍生程式碼或有特定條款，需改採授權授課或規避方案。

2. **PyTorch / CUDA 相關授權**
   - PyTorch 本身授權通常可採閉源使用，但需以實際 wheel 分發條件為準，避免在授權邊界外操作。

3. **模型權重授權**
   - 平台預設預載 `yolov8n-seg.pt` 僅供研發測試，若商用需明確權重來源與使用條款。
   - 客戶若上傳自行訓練模型，需明確採用其授權。

4. **前端第三方資源**
   - Chart.js / Font Awesome / Dropzone 需保留 attribution，不可刪除授權聲明。

## 風險處置

- 在 `v0.1.0` 之前先完成 legal review，將風險標註轉換為 Release Gate。
- 嚴禁在未完成 `commercial_risk_report` 結論前進行大規模商用宣稱。

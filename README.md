# Vision Training Studio 🚀

一個專為 Windows 環境設計的 **YOLO 視覺辨識訓練管線與測試評估控制台**。
本專案整合了資料集品質檢測、LabelMe 標註同步、自動化資料集切分 (Train/Val/Test)、物理影像擴增 (Augmentation)、YOLOv8/11 模型訓練、收斂診斷以及測試推論 (Inference Lab)，旨在打造一個適用於多台電腦、雙擊即用的一鍵式視覺工作室。

---

## ✨ 核心優勢與特色

1. **一鍵雙擊啟動 (`run.bat`)**
   - 內建**防禦性啟動控制**：每次雙擊啟動時，會自動檢測並強制殺死任何佔用 `8000` 端口的殘留進程，保證避免 `Errno 10048` 錯誤。
   - **就緒開啟機制**：背景異步拉起後端 Python 服務，主動延遲等待 2 秒使其就緒，最後才開啟瀏覽器網頁，保證 CSS 與 JS 資源一次載入成功。

2. **雙層動態右側面板 (Dynamic Context Panel)**
   - **全域精簡摘要**：在任何頁面僅呈現最核心的專案指標（名稱、任務、影像數、已標註比例、切分狀態），消除冗餘資訊。
   - **依頁面上下文動態變更**：根據目前所在的 Active Page 切換為專屬輔助區，動態提供操作 Next Actions、系統 readiness 檢查與 Warnings。
   - **XSS 安全防範與 SoC**：所有的 builder 僅處理結構化資料模型，統一由渲染引擎進行 DOM 安全 escape，徹底防止 XSS 注入與頁面崩潰。

3. **強健的資料與標註管線**
   - 支援 LabelMe 標註資料的一鍵同步與 YOLO normalized 格式無痛轉換。
   - 資料集一鍵品質檢測：自動檢測出資料集內的重複 (Duplicate) 與損毀 (Corrupted) 影像，並呈報至 Dataset Status。

4. **硬體自適應推薦與非阻塞偵測**
   - 啟動時異步偵測 GPU/CUDA 資源，防範連線中斷或超時阻塞。
   - 依據本機顯示卡 VRAM 尺寸與資料集圖片多寡，自動為使用者計算並填入最佳的訓練超參數推薦配置。

5. **推論實驗室 (Inference Lab)**
   - 支援上傳本機圖片或直接提供本機絕對路徑（已實作上傳與本機路徑互斥 UI 互動，防止狀態衝突）。
   - 即時載入訓練產出的 `best.pt` 進行 polygon 與 bbox 疊加測試。

---

## 🛠️ 快速開始

### 1. 安裝環境
請確保您的電腦已安裝 Python 3.9 ~ 3.11 環境（建議在虛擬環境下執行），接著執行：
```bash
pip install -r requirements.txt
```
*本系統支援 PyTorch 的 CUDA 顯示卡加速，若有 NVIDIA 顯示卡，請安裝對應 CUDA 版本的 PyTorch。*

### 2. 一鍵啟動
在 Windows 系統中，直接**雙擊執行根目錄底下的 `run.bat`**。
* 系統會自動清理佔用端口、背景啟動 API 伺服器，並於 2 秒後自動在預設瀏覽器打開 `http://127.0.0.1:8000`。
* 後端服務正於該 CMD 視窗背景運行中。如需關閉服務，**直接將該 CMD 視窗關閉即可**。

---

## 📂 專案結構簡介

* `app.py`：FastAPI 後端路由與靜態資源伺服器入口。
* `run.bat`：Windows 一鍵啟動腳本。
* `requirements.txt`：Python 依賴包列表。
* `src/`：後端核心邏輯層：
  * `src/project_manager.py`：專案 JSON 配置讀寫與管理。
  * `src/trainer.py`：YOLO 訓練調用與資料校驗。
  * `src/splitter.py`：資料集 Train/Val/Test 隨機/分層切分。
  * `src/augmenter.py`：物理影像增強（亮度、陰影、雨霧等幾何與色彩變換）。
  * `src/training/`：訓練管理器、推薦配置器、收斂診斷器等 MLOps 模組。
* `static/`：前端網頁資源：
  * `static/index.html`：網頁主結構。
  * `static/style.css`：網頁樣式與右側面板微型樣式。
  * `static/app.js`：前端單向資料流與雙層右側面板渲染核心。
  * `static/pages/`：各功能分頁組件（Dashboard, Split, Augmentation, Training, Inference 等）。

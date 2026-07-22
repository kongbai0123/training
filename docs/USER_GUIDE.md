# 使用者指南

Vision Training Studio 提供本機 AI 訓練與推論流程。使用者主要透過瀏覽器或桌面 shell 操作 UI，後端服務只綁定本機位址。

## 1. 建立專案

1. 開啟應用程式。
2. 進入 Projects。
3. 建立新專案，選擇任務類型。
4. 輸入專案名稱與 class names。

新專案會使用 v3 layout，資料會放在：

```text
projects/{project_id}/
```

## 2. CNN / 視覺模型流程

典型流程：

1. 建立 CNN / 視覺模型專案，選擇圖片分類、物件偵測、實例分割或語意分割。
2. 匯入影像或資料夾。
3. 使用 LabelMe 建立或同步標註。
4. 偵測與分割任務需建立方框或 polygon；圖片分類可依類別資料夾匯入，不需要畫框。
5. 建立 Train / Val / Test split。
6. 視需要執行資料增強。
7. 設定 model、epochs、batch size、image size、device。
8. 開始訓練並查看 dashboard、metrics、artifacts。
9. 使用已訓練模型進行推論、評估、比較或匯出。

訓練模型選單固定依任務分類：

- **圖片分類（整張圖，不畫框）**：ResNet18、MobileNetV3 Large、EfficientNet-B0。
- **物件偵測（方框）**：YOLO、RT-DETR、D-FINE Small、Faster R-CNN、FCOS。
- **物件輪廓分割（可分別計數）**：YOLO Segmentation、Mask R-CNN。
- **畫面區域分割（像素分類）**：U-Net、DeepLabV3。

尚未安裝的預訓練權重仍會顯示「需先安裝」，不會從清單消失。內建 U-Net 是程式模板，不需要另外下載。ByteTrack 與 BoT-SORT 用於影片推論中的跨幀追蹤，不是獨立訓練模型，因此不列在訓練模型選單。

### 雨天資料增強

資料增強頁將雨天效果分成三個獨立層次：

- **場景天候**：晴天線索抑制、陰天光色、深度雨霧與遠／中／近三層雨絲。
- **地面互動**：濕地面、積水反射與雨滴水花；道路 Polygon 會優先作為地面遮罩，沒有合適標註時才使用保守的透視地面估計。
- **鏡頭／玻璃效果**：折射水滴獨立控制，不會因選擇一般陰雨預設而自動開啟。

「保護小型目標可見度」只保護行人、車輛、標誌等物件，不會讓道路或其他大型區域避開雨霧。產生預覽後可切換顯示標註；預覽使用 PNG，方便檢查細雨、水花與水滴邊緣。資料增強只會套用到 Train split，Val/Test 保持原始資料。

旋轉、縮放、透視、水平／垂直翻轉與隨機裁剪會同步重映射 Polygon／BBox。垂直翻轉與隨機裁剪預設關閉或為 0，因為具有上下方向語意的場景或靠近影像邊緣的目標可能不適合這類變換；啟用時，風險檢查會提示抽查。設定一旦變更，舊預覽立即失效，必須重新產生並檢查標註位置後才能套用至整個 Train split。

## 3. RNN / Sequence / XGBoost 流程

典型流程：

1. 建立 RNN / Sequence 專案。
2. 匯入 CSV sequence data。
3. 設定 feature columns 與 target column。
4. 設定 sequence length、stride、horizon。
5. 執行 readiness check。
6. 選擇 PyTorch LSTM 或 XGBoost backend。
7. 開始訓練並查看 metrics、artifacts 與 run history。

RNN deep learning backend 仍屬 beta；XGBoost baseline 適合作為 tabular / sequence baseline。

## 4. Feature Columns 格式

feature columns 可使用逗號或分號分隔，例如：

```text
speed,acceleration,temperature
```

請確認 CSV header 內存在所有 feature columns 與 target column。若欄位不存在，readiness check 會阻止訓練。

## 5. Model Catalog

模型來源分為：

- Built-in models
- Imported models
- Project trained models

匯入模型不代表可直接訓練：

```text
Import != Execute
Valid Manifest != Trainable
Registered != Enabled
```

custom package 需要通過 manifest validation、dry-run policy 與 enablement 狀態檢查。

## 6. Run History 與 Artifacts

每次訓練會產生 run folder，常見內容包括：

```text
metrics.json
run_summary.json
train_config.json
backend.json
metric_schema.json
artifact_manifest.json
weights/
```

請透過 UI 或 API 管理 run history，不要手動刪除仍在使用中的 run 資料。

## 7. 專案助理

右上角「助理」會搜尋目前專案已同步的資料集摘要、訓練 Run、評估、匯出合約與錯誤紀錄。它用於解釋現況、整理風險與提供下一個檢查方向，不會自動修改參數或取代正式評估。

- 專案首次開啟時會檢查知識庫；若為空，請在助理內按「立即同步」。
- Enter 送出問題；Shift+Enter 換行。
- 「正在搜尋」表示系統正在比對目前專案來源，完成前不會重複送出。
- 回答沒有引用來源時不應作為決策依據；先同步專案產物或匯入相關報告再提問。

## 8. 評估圖表下載

CNN 與 RNN 評估圖表會以 SVG 向量格式直接儲存至目前 Windows 使用者的「下載」資料夾。若同名檔案已存在，系統會保留舊檔並建立帶編號的新檔，不會寫入 AppData 專案資料夾。

## 9. 安全使用

- 不要把私有資料集、模型權重或專案資料提交到 Git。
- 不要手動移動 `projects/{project_id}` 內部資料夾，除非同時更新 project metadata。
- 若遇到啟動或訓練問題，先查看 `logs/`，再執行 `scripts\diagnostics.bat`。

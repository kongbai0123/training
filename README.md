<div align="center">

# Vision Training Studio

**本地優先的 Windows 通用模型訓練工作台**

從資料匯入、標註與序列設定，到訓練、任務感知評估、模型比較及部署產物匯出。

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](docs/INSTALL.md)
[![Version](https://img.shields.io/badge/version-0.1.0-2563EB)](VERSION)
[![Package](https://img.shields.io/badge/package-Portable%20EXE-16A34A)](docs/INSTALL.md)
[![Runtime](https://img.shields.io/badge/end--user%20runtime-No%20Python%20required-0F766E)](docs/INSTALL.md)

[Windows 版本](https://github.com/kongbai0123/training/releases) · [使用指南](docs/USER_GUIDE.md) · [安裝說明](docs/INSTALL.md) · [問題排除](docs/TROUBLESHOOTING.md)

</div>

![Vision Training Studio 總覽介面](docs/assets/app-overview.png)

## Windows 下載

正式使用以 **Windows x64 Portable EXE 套件**為主。使用者不需要另外安裝 Python 或 Node.js。

1. 前往 [GitHub Releases](https://github.com/kongbai0123/training/releases)。
2. 下載 `VisionTrainingStudio_<version>_Windows_x64_portable.zip`。
3. 完整解壓縮後執行 `VisionTrainingStudio.exe`。

> `VisionTrainingStudio.exe` 必須與同層的 `_internal` 資料夾一起使用。請勿只複製單一 EXE。

## 產品能力

| 工作流程 | CNN 影像訓練 | RNN 序列訓練 |
|---|---|---|
| 資料 | 圖片、資料夾、ZIP | CSV、CSV ZIP、序列資料 |
| 資料設定 | 類別、LabelMe、人工與自動標註 | 時間欄、序列 ID、特徵、目標、任務類型 |
| 資料準備 | 品質檢查、Train/Val/Test、影像增強 | 缺失檢查、Window/Stride/Horizon、切分與正規化 |
| 模型 | Ultralytics YOLO Detection / Segmentation | LSTM、GRU、BiLSTM、XGBoost |
| 評估 | mAP、Precision、Recall、混淆與輸出檢視 | Accuracy、Macro-F1、MAE、RMSE、Confusion Matrix、Residual Plot |
| 比較 | 不同模型與不同 Run | 不同模型與同模型不同 Run |
| 匯出 | PT、ONNX、Markdown Report | Model Package、Schema、Scaler、Inference Contract、Report |

## 實際介面

<table>
  <tr>
    <td width="50%"><strong>CNN 影像訓練流程</strong></td>
    <td width="50%"><strong>RNN 序列訓練流程</strong></td>
  </tr>
  <tr>
    <td><img src="docs/assets/cnn-training-flow.png" alt="CNN 影像訓練流程介面"></td>
    <td><img src="docs/assets/rnn-training-flow.png" alt="RNN 序列訓練流程介面"></td>
  </tr>
</table>

## 使用流程

```text
建立專案
  → 匯入圖片或序列資料
  → 完成 CNN 標註或 RNN Schema 設定
  → 執行品質檢查與資料切分
  → 選擇模型並啟動訓練
  → 檢視任務對應指標與診斷
  → 比較 Run 並匯出部署產物
```

CNN 與 RNN 使用獨立的資料準備、評估與匯出流程；專案建立後，介面只呈現該專案適用的功能。

## 系統需求

| 項目 | 建議環境 |
|---|---|
| 作業系統 | Windows 10 / 11 x64 |
| 記憶體 | 16 GB 以上，依資料與模型大小調整 |
| 儲存空間 | 至少保留 10 GB，另加資料集與模型所需空間 |
| GPU | NVIDIA GPU 選配；無 GPU 時依功能回落 CPU 或顯示明確提示 |
| 網路 | 核心訓練流程可在本機執行；模型下載或外部服務依使用情境決定 |

## 本地資料與隱私

- 專案、模型、logs、cache、exports 與暫存資料不提交至 Git。
- packaged mode 會將使用者資料與程式本體分離。
- 軟體不應在未告知使用者的情況下上傳資料或刪除專案。
- API key、token、密碼、私有資料集與模型權重不得提交至 repo。

## 開發與建置

只有原始碼開發者需要 Python 3.11。正式 Portable EXE 使用者不需要開發環境。

```bat
scripts\start_dev.bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

PyInstaller 輸出：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

核心原始碼與使用者資料維持分離：

```text
src/          後端與核心服務
static/       前端介面與本地資源
tests/        單元、整合與靜態驗證
scripts/      啟動、測試、建置、打包與診斷
packaging/    PyInstaller 設定
installer/    Windows installer 設定
docs/         安裝、使用、架構、部署與疑難排解
```

## 文件

- [安裝指南](docs/INSTALL.md)
- [使用者指南](docs/USER_GUIDE.md)
- [開發者指南](docs/DEVELOPER_GUIDE.md)
- [架構文件](docs/ARCHITECTURE.md)
- [部署與打包](docs/DEPLOYMENT.md)
- [測試規範](docs/TESTING_GUIDELINES.md)
- [乾淨 Windows 驗證](docs/CLEAN_MACHINE_VALIDATION.md)
- [已知問題](docs/KNOWN_ISSUES.md)
- [疑難排解](docs/TROUBLESHOOTING.md)

## Release Gate

正式發布至少需要通過：完整測試、建置檢查、PyInstaller 打包、packaged runtime smoke，以及乾淨 Windows VM 驗證。未完成乾淨機器驗證前，不宣稱為正式 production release。

## 專案狀態

目前版本為 `0.1.0` commercial MVP。CNN / YOLO 與 RNN / Sequence 主流程可操作，但仍應依 [已知問題](docs/KNOWN_ISSUES.md) 與 [乾淨機器驗證](docs/CLEAN_MACHINE_VALIDATION.md) 完成正式交付檢查。

## 授權

本 repo 尚未附公開開源授權。外部使用、修改與散布條款請向專案維護者確認；第三方元件資訊位於 `docs/compliance/`。

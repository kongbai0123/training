# 專案資料樹與路徑規範

本文件定義 Vision Training Studio 的原始碼、建置輸出與使用者資料邊界。新增檔案前，應先依此表確認歸屬，避免將執行期資料放入原始碼目錄或提交至 Git。

## Repository Tree

```text
VisionTrainingStudio/
├─ .github/                 GitHub issue 與自動化設定
├─ data/                    隨程式交付的小型內建 catalog / metadata
├─ docs/                    使用、架構、部署、測試與合規文件
│  ├─ assets/               README 與文件使用的介面截圖
│  ├─ compliance/           第三方授權與清冊
│  └─ reports/              研究與風險報告
├─ installer/               Windows 安裝器設定
├─ packaging/               PyInstaller 與元件打包入口
├─ scripts/                 啟動、測試、建置、打包、稽核與診斷工具
├─ src/                     Python 後端與核心業務邏輯
│  ├─ api/routes/           FastAPI route 邊界
│  ├─ model_system/         模型 catalog、相容性與安裝邏輯
│  └─ training/             訓練、比較與匯出服務
├─ static/                  離線前端與 vendored 靜態資源
│  ├─ core/                 bootstrap、router 與頁面註冊
│  ├─ pages/                頁面行為模組
│  ├─ state/i18n/           英文與繁中字典
│  ├─ styles/               design tokens、元件與頁面 CSS
│  └─ vendor/               離線字型、icon、Chart.js 等資源
├─ tests/                   單元、整合、contract 與 UI 靜態測試
├─ tools/                   開發工具所需的受控檔案
├─ app.py                   FastAPI 應用入口
├─ launcher.py              桌面啟動與本機服務管理
├─ run.bat                  根目錄相容啟動入口
├─ requirements*.txt        runtime / build / test 依賴
├─ VERSION / version.json   版本來源
└─ README.md                專案入口文件
```

## Runtime Data Tree

以下資料夾是執行期或建置產物，不屬於原始碼，也不得提交至 Git：

```text
user-data/
├─ projects/                使用者專案、資料集、runs、weights、評估與匯出
├─ models/                  已安裝或使用者匯入的模型
├─ components/              離線 LabelMe 等可選元件
├─ config/                  使用者設定
├─ licenses/                本機授權狀態
├─ project_assistant/       專案助理索引、狀態與 sandbox 產物
├─ exports/                 跨專案或相容輸出
├─ logs/                    launcher 與應用程式診斷日誌
├─ cache/                   可重建快取
└─ tmp/                     可清除暫存

repository build output/
├─ build/                   PyInstaller 中間產物，可重建
├─ dist/                    未壓縮的可執行程式輸出
└─ release_artifacts/       Portable ZIP、元件 ZIP 與 release 候選產物
```

## Path Resolution

路徑由 `src/app_paths.py` 集中解析：

| 模式 | 程式本體 | 使用者資料 |
|---|---|---|
| Source mode | repository root | repository root 下的相容資料夾 |
| Installed / packaged | EXE 與 `_internal` | `%LOCALAPPDATA%\VisionTrainingStudio` |
| Portable mode | EXE 目錄 | 只有同層存在 `portable.mode` 時使用 EXE 目錄 |
| Explicit override | `VTS_APP_HOME` | `VTS_USER_DATA_DIR` / `VTS_PROJECTS_DIR` |

業務模組不得自行硬編碼磁碟代號、使用者名稱或 `D:\software\yolo`。新增 runtime 路徑時，應先加入 `src/app_paths.py`，再由服務引用。

## Ownership Rules

| 資料類型 | 正確位置 | 可清理 | 可提交 Git |
|---|---|---:|---:|
| Python 業務邏輯 | `src/` | 否 | 是 |
| 前端頁面與 CSS | `static/` | 否 | 是 |
| 文件與正式截圖 | `docs/` | 否 | 是 |
| 自動測試 | `tests/` | 否 | 是 |
| 使用者專案與模型 | user-data | 未經確認不可 | 否 |
| log / cache / tmp | user-data | 是，依清理政策 | 否 |
| build | repository `build/` | 是 | 否 |
| dist / release artifacts | `dist/`, `release_artifacts/` | release 確認後 | 否 |

## Cleanup Boundary

`scripts/clean_runtime.bat` 只處理可重建的 build、cache、tmp 與 Python 測試快取。它不得刪除：

- `projects/`
- `models/`
- `components/`
- `logs/`
- `exports/`
- `dist/`
- `release_artifacts/`

要移除交付包或使用者資料時，必須由使用者明確指定目標資料夾。

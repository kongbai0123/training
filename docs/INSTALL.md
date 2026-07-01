# 安裝說明

本文件說明如何在 Windows 本地環境安裝與啟動 Vision Training Studio。

## 1. 原始碼開發模式

需求：

- Windows 10 / 11
- Python 3.11
- Node.js，僅用於 `node --check`
- NVIDIA GPU optional

建議流程：

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
scripts\start_dev.bat
```

預設啟動後會開啟本地服務，通常為：

```text
http://127.0.0.1:18080/
```

## 2. 已打包 dist 版本

打包後主程式位於：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

啟動：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

無桌面殼測試模式：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18105 --env production --shell none
```

健康檢查：

```text
http://127.0.0.1:18105/api/health
http://127.0.0.1:18105/api/version
```

## 3. Installer

若已安裝 Inno Setup，可用：

```bat
ISCC installer\VisionTrainingStudio.iss
```

安裝器輸出位置：

```text
installer\output\
```

## 4. 使用者資料位置

本 repo 開發模式會使用專案根目錄中的 runtime folders，例如：

```text
projects/
models/
logs/
cache/
tmp/
```

打包版本應保持「程式本體」與「使用者資料」分離。正式部署前請依 `docs/DEPLOYMENT.md` 的 release checklist 驗證資料路徑。

## 5. 常見安裝問題

- `python` 找不到：確認 Python 3.11 已加入 PATH，或啟用 `.venv`。
- `PyInstaller` 找不到：執行 `python -m pip install -r requirements-build.txt`。
- port 被占用：改用 `--port` 指定其他 port，或關閉舊的 `VisionTrainingStudio.exe`。
- GPU 無法使用：先確認 NVIDIA driver / CUDA / PyTorch CUDA build 是否匹配；CPU fallback 不保證所有大型訓練都適合。

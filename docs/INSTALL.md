# 安裝指南

本文說明 Vision Training Studio 的 Windows Portable EXE、開發安裝與 installer 建置方式。

## 1. 一般使用者：Windows Portable EXE

1. 從 [GitHub Releases](https://github.com/kongbai0123/training/releases) 下載 `VisionTrainingStudio_<version>_Windows_x64_portable.zip`。
2. 將 ZIP 完整解壓縮到可寫入的資料夾。
3. 執行 `VisionTrainingStudio.exe`。

Portable EXE 已包含必要 runtime，一般使用者不需要安裝 Python 或 Node.js。`VisionTrainingStudio.exe` 必須與 `_internal` 位於同一套件目錄，不可只移動單一 EXE。

## 2. 開發模式安裝

需求：

- Windows 10 / 11 x64
- Python 3.11
- Node.js，僅用於 JavaScript syntax check
- NVIDIA GPU 為選配

建立虛擬環境並安裝依賴：

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

啟動開發模式：

```bat
scripts\start_dev.bat
```

預設會啟動本機服務並開啟：

```text
http://127.0.0.1:18080/
```

## 3. 建立 Packaged Runtime

建立 PyInstaller onedir package：

```bat
scripts\package.bat
```

主要輸出：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

執行：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

不開 UI，只啟動 backend 供檢查：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18105 --env production --shell none
```

健康檢查：

```text
http://127.0.0.1:18105/api/health
http://127.0.0.1:18105/api/version
```

## 4. Installer

installer 設定檔：

```text
installer\VisionTrainingStudio.iss
```

建置 installer：

```bat
scripts\build_installer.bat
```

如果系統找不到 `ISCC.exe`，請先安裝 Inno Setup，或將 Inno Setup 安裝路徑加入 `PATH`。

installer 輸出預期位於：

```text
installer\output\
```

## 5. Runtime Data

以下資料夾是使用者資料或執行期資料，不應提交到 Git：

```text
projects/
models/
logs/
cache/
tmp/
config/
licenses/
exports/
```

清理開發環境暫存可使用：

```bat
scripts\clean_runtime.bat
```

清理前請確認腳本不會移除需要保留的使用者專案資料。

## 6. 常見安裝問題

- `python` 找不到：確認 Python 3.11 已安裝並加入 PATH，或使用 `.venv\Scripts\python.exe`。
- `PyInstaller` 找不到：執行 `python -m pip install -r requirements-build.txt`。
- port 被占用：改用 `--port` 指定其他 port。
- GPU 不可用：確認 NVIDIA driver、CUDA 與 PyTorch CUDA build；否則使用 CPU fallback。
- packaged app 啟動失敗：查看 `logs\launcher.log` 或執行 `scripts\diagnostics.bat`。

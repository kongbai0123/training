# 開發者指南

## 1. 開發原則

本專案以本地可交付產品為目標，不接受只在單一開發機可跑的臨時 demo。所有功能需考慮：

- 可移植路徑
- 設定與 runtime data 分離
- 明確錯誤訊息
- 可測試
- 可打包
- 不污染使用者專案資料

## 2. 常用指令

```bat
scripts\start_dev.bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

## 3. 測試策略

後端：

```bat
python -m unittest discover -s tests -p "test_*.py" -v
```

前端 syntax check：

```bat
node --check static\app.js
node --check static\pages\training.js
node --check static\pages\training_modes.js
```

Python compile：

```bat
python -m py_compile app.py launcher.py
python -m compileall -q src
```

## 4. 資料夾規則

不得提交：

```text
projects/
models/
logs/
cache/
tmp/
build/
dist/
config/
licenses/
exports/
*.pt
*.onnx
*.engine
```

可提交：

```text
src/
static/
tests/
docs/
scripts/
packaging/
installer/
version.json
requirements*.txt
```

## 5. UI 變更規則

- CNN 與 RNN mode 不得互相污染 DOM state。
- RNN preview / disabled / available 狀態要明確。
- 長時間作業應使用一致的 progress / state UI。
- 新增 UI 狀態時優先使用 `product-state-card` 類型樣式。

## 6. Model / Package 安全規則

- `.py`、`.c`、`.cpp`、`.exe` 不可直接當作模型執行。
- custom package 必須先走 manifest validation。
- 未通過 sandbox approval 前不得加入 training selector。
- 未知 Python 不得 import，不得執行。

## 7. 打包注意事項

PyInstaller rebuild 前應先關閉舊的 `VisionTrainingStudio.exe`，否則 Windows 可能鎖定 `dist\VisionTrainingStudio\VisionTrainingStudio.exe` 造成 `PermissionError: WinError 5`。

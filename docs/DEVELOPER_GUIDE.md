# 開發者指南

本專案目標是可交付、可安裝、可移植的本地 AI 工具，不是只在開發機可跑的 demo。任何功能修改都應維持 source code、runtime data、使用者資料與打包輸出的邊界。

## 1. 開發原則

- 不使用絕對路徑或固定磁碟代號。
- 不假設使用者已安裝 Python、Node.js、CUDA 或其他開發工具。
- 使用 `src/app_paths.py` 解析 app home、user data、projects、logs、cache、tmp。
- 專案資料路徑應透過 `src/project_layout.py`，避免各模組自行拼路徑。
- API routes 放在 `src/api/routes/*`，`app.py` 只負責組裝。
- runtime data 不進 Git。

## 2. 常用指令

```bat
scripts\start_dev.bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

## 3. 測試

完整測試：

```bat
scripts\test.bat
```

Python compile check：

```bat
python -m py_compile app.py launcher.py
python -m compileall -q src
```

JavaScript syntax check：

```bat
node --check static\app.js
```

若新增前端頁面，請對新增的 `static/pages/*.js` 執行 `node --check`。

## 4. Git 邊界

應提交：

```text
src/
static/
tests/
docs/
scripts/
packaging/
installer/
app.py
launcher.py
requirements*.txt
version.json
VERSION
```

不應提交：

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
release_artifacts/
*.pt
*.onnx
*.engine
```

## 5. API 與測試 patch 規則

測試可以從 `app.py` 匯入 FastAPI app：

```python
from app import app
```

但不要透過 `app.py` patch route 內部相依物件。請 patch 實際擁有 dependency 的 module，例如：

```python
patch("src.api.routes.training_orchestration.ProjectManager.get_project")
```

## 6. Model Package 安全規則

- `.py`、`.c`、`.cpp`、`.exe` 等可執行內容不得在匯入時直接執行。
- custom package 必須先通過 manifest validation。
- dry-run approval 不等於可正式啟用。
- sandbox policy 是產品層防護，不是完整 OS 隔離。

## 7. 打包注意事項

重新打包前請關閉正在執行的 `VisionTrainingStudio.exe`。如果 exe 仍在執行，Windows 可能導致 PyInstaller 出現 `PermissionError: WinError 5`。

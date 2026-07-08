# 乾淨機器驗證

本文定義 Vision Training Studio 在乾淨 Windows VM 上的 packaged runtime 與 installer 驗證流程。

## 1. 驗證目標

Package 驗證需要確認：

- packaged runtime 可啟動。
- `/api/health` 可回應。
- `/api/version` 可回應。
- 不依賴 repo working tree。
- 不要求使用者自行安裝 Python 或 Node.js。
- runtime data 寫入 user data 位置，而不是安裝目錄。

Installer 驗證需要確認：

- installer 可在乾淨 Windows VM 安裝。
- Start Menu shortcut 可啟動 app。
- desktop shortcut 可啟動 app，如果 installer 有建立。
- uninstall 會移除安裝檔案。
- uninstall 不會刪除使用者 projects、models、logs、exports。

## 2. Package Smoke

在開發機建立 package：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

packaged runtime 路徑：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

手動啟動 backend-only：

```bat
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18106 --env production --shell none
```

檢查：

```text
http://127.0.0.1:18106/api/health
http://127.0.0.1:18106/api/version
```

## 3. Installer Validation

建立 installer：

```bat
scripts\build_installer.bat
```

在乾淨 Windows VM：

1. 複製 installer 或 portable package 到 VM。
2. 安裝 `VisionTrainingStudio_Setup_*.exe`，或解壓 portable package。
3. 啟動 `VisionTrainingStudio.exe`。
4. 確認 app 不需要 Python、Node.js、repo working tree。
5. 確認 health endpoint 回應。
6. 確認 version endpoint 回應。
7. 建立 sample project。
8. 確認 logs 已建立。
9. 確認 user data 沒有寫入 `D:\software\yolo` 或其他開發機路徑。
10. 透過 Windows Apps / Programs uninstall。
11. 確認安裝檔案被移除。
12. 確認 user projects、models、logs、exports 仍保留。

如需用本機 dist 模擬 installed app validation：

```bat
scripts\validate_installed_app.bat "D:\software\yolo\dist\VisionTrainingStudio\VisionTrainingStudio.exe"
```

正式 installer 驗證應改用實際安裝路徑，例如：

```bat
scripts\validate_installed_app.bat "C:\Program Files\VisionTrainingStudio\VisionTrainingStudio.exe"
```

## 4. Installer Checklist

```text
[ ] installer can run on clean Windows x64 VM
[ ] app launches from Start Menu shortcut
[ ] desktop shortcut launches app, if selected
[ ] GET /api/health returns healthy
[ ] GET /api/version returns packaged version
[ ] logs are created
[ ] user data is outside Program Files
[ ] uninstall removes installed application files
[ ] uninstall does not delete user projects/models/logs/exports
```

## 5. Evidence Template

每個 release candidate 應保留以下記錄：

```text
Release candidate:
Date:
Machine or VM:
Windows version:
Artifact:
Install mode: installer / portable

[ ] install or extract succeeded
[ ] app launched
[ ] /api/health passed
[ ] /api/version passed
[ ] user data path is outside install directory
[ ] logs were created
[ ] no developer absolute path required
[ ] Start Menu shortcut works
[ ] desktop shortcut works, if selected
[ ] uninstall succeeded
[ ] user data retained after uninstall

Notes:
Evidence files:
```

## 6. 已知限制

- package smoke test 不能取代乾淨 VM installer validation。
- 如果機器沒有 Inno Setup，`scripts\build_installer.bat` 會被 `ISCC.exe` 缺失阻擋。
- custom package sandbox policy 不應在 release note 中描述為完整 OS-level sandbox。

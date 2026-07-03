# 乾淨機器驗證紀錄

## 目的

本文件用來記錄 Vision Training Studio 的 package 與 installer 層級驗證。  
它明確區分「本機 packaged runtime smoke」與「真正乾淨機器或 VM 安裝驗證」。

## 驗證範圍

Package 層級驗證：

- packaged runtime 可以啟動。
- `/api/health` 正常回應。
- `/api/version` 正常回應。

Installer 層級驗證：

- 乾淨 Windows 機器或 VM 可以安裝。
- app 可以從 installer 建立的捷徑啟動。
- 使用者資料與安裝目錄分離。
- 解除安裝不會未告知刪除使用者資料。
- 不依賴開發機路徑、repo working tree 或隱藏本機狀態。

## 目前證據

日期：2026-07-03

目前已完成的是本機 package smoke，不是乾淨機器 installer 驗證。

環境：

- Repository path：`D:\software\yolo`
- Smoke test packaged runtime path：`dist\VisionTrainingStudio\_internal`
- Version：`0.1.0`
- Installer script：`installer\VisionTrainingStudio.iss`
- Package script：`scripts\package.bat`
- Installer build script：`scripts\build_installer.bat`
- Installed app validation script：`scripts\validate_installed_app.bat`
- Smoke script：`scripts\smoke_dist.bat`

已完成指令：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
scripts\validate_installed_app.bat "D:\software\yolo\dist\VisionTrainingStudio\VisionTrainingStudio.exe"
```

目前狀態：

- Local test suite：pass
- Build checks：pass
- PyInstaller package build：pass
- Dist smoke：pass
- Installed app validation script against local dist exe：pass
- Installer build on this machine：blocked，`ISCC.exe` not found
- Clean-machine installer validation：pending

## Windows 乾淨 VM Checklist

請使用未依賴本 repo working tree 的 Windows x64 VM 或另一台 Windows x64 電腦。

1. 只複製 release artifact 或 installer output 到該機器。
2. 使用 `VisionTrainingStudio_Setup_0.1.0.exe` 安裝，或使用 portable package 解壓驗證。
3. 啟動 `VisionTrainingStudio.exe`。
4. 確認 app 會在安裝目錄外建立使用者資料夾。
5. 開啟 health endpoint：

```text
GET /api/health
```

6. 開啟 version endpoint：

```text
GET /api/version
```

7. 建立或開啟一個小型 sample project。
8. 確認 log 會寫入預期 runtime log 目錄。
9. 確認啟動不需要 `D:\software\yolo` 等開發機絕對路徑。
10. 從 Windows Apps/Programs 解除安裝。
11. 確認安裝目錄已移除。
12. 確認使用者 project、model、log、export 沒有被未告知刪除。

安裝後可執行：

```bat
scripts\validate_installed_app.bat "C:\Program Files\VisionTrainingStudio\VisionTrainingStudio.exe"
```

## Installer 驗收條件

```text
[ ] installer 不要求不必要的 administrator 權限
[ ] Start Menu shortcut 可啟動 app
[ ] desktop shortcut 可啟動 app，如果安裝時有選取
[ ] GET /api/health 回傳 healthy
[ ] GET /api/version 回傳 packaged version
[ ] log 正常建立
[ ] user data 與 program files 分離
[ ] uninstall 移除 installed application files
[ ] uninstall 不會靜默刪除 user projects/models/logs/exports
```

## 已知缺口

- repo 目前尚未記錄真正乾淨機器或 VM installer 執行結果。
- 目前證據只證明本機 packaged runtime smoke。
- Inno Setup installer output 必須在 `scripts\package.bat` 成功後再產生。
- 本機目前找不到 `ISCC.exe`，installer 實際產出需在已安裝 Inno Setup 的機器上完成。

## Evidence Template

每個 release candidate 請複製此區塊填寫。

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

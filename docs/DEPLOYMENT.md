# 部署與打包指南

## 1. Package Build

從專案根目錄執行 PyInstaller 打包：

```bat
scripts\package.bat
```

底層打包指令：

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
```

預期輸出入口：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

## 2. Dist Smoke Test

執行 packaged runtime 煙霧測試：

```bat
scripts\smoke_dist.bat
```

測試會檢查：

```text
GET /api/health
GET /api/version
```

這只證明本機 packaged runtime 可以啟動，不等同於 installer 已在乾淨機器完成驗證。

## 3. Installer Build

Windows installer 定義檔：

```text
installer\VisionTrainingStudio.iss
```

在 `scripts\package.bat` 成功後，用 Inno Setup 建置 installer：

```powershell
scripts\build_installer.bat
```

預期 installer 輸出：

```text
installer\output\
```

## 4. 版本同步

release 前需確認以下檔案版本一致：

```text
VERSION
version.json
installer\VisionTrainingStudio.iss
packaging\vision_training_studio.spec
README.md
docs\RELEASE_NOTES_TEMPLATE.md
CHANGELOG.md
```

## 5. Release 驗證指令

產生 release candidate 前至少執行：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

最低驗收條件：

```text
[ ] unittest pass
[ ] JavaScript syntax check pass
[ ] Python compile checks pass
[ ] PyInstaller package build pass
[ ] dist smoke health endpoint pass
[ ] dist smoke version endpoint pass
[ ] README and docs updated
[ ] no projects/logs/cache/tmp/build/dist committed
```

## 6. 乾淨機器驗證

package 與 installer 層級驗證紀錄固定放在：

```text
docs\CLEAN_MACHINE_VALIDATION.md
```

宣稱 release 可在其他電腦安裝前，必須完成該文件中的 Windows 乾淨 VM checklist。

`scripts\smoke_dist.bat` 只能證明本機 packaged runtime 啟動成功，不能取代乾淨機器 installer 驗證。

乾淨機器或 VM 安裝後，可用下列腳本驗證已安裝 app：

```bat
scripts\validate_installed_app.bat "C:\Program Files\VisionTrainingStudio\VisionTrainingStudio.exe"
```

PyInstaller warning 分類紀錄：

```text
docs\PYINSTALLER_WARNING_AUDIT.md
```

## 7. Release Artifacts

建議 release artifact 目錄：

```text
release_artifacts\
  build_manifest.json
  checksum.txt
  release_notes.md
  license_inventory.md
  THIRD_PARTY_LICENSES.md
```

除非 release 流程明確要求，否則不要將產生物提交到 repo。

## 8. Offline Asset Check

前端 runtime asset 應 vendored 到：

```text
static\vendor\
```

release 前需檢查 `static\index.html` 與前端 bundle，避免非預期外部 CDN 依賴：

```text
https://fonts.googleapis.com
https://fonts.gstatic.com
https://cdnjs.cloudflare.com
https://cdn.jsdelivr.net
```

若有刻意 vendor runtime asset，請同步更新 `static\vendor\README.md`。

## 9. Diagnostics Package

產生 diagnostics：

```bat
scripts\diagnostics.bat
```

API endpoint：

```text
GET /api/diagnostics/report
```

diagnostics package 應包含 app version、health payload、recent logs、project summary、system status 與 runtime paths。

不得包含 raw images、private datasets、model weights 或完整 project folders。

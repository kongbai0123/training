# 部署與打包

本文定義 Vision Training Studio 的打包、smoke test、installer 與 release validation 流程。

## 1. Package Build

使用 PyInstaller 建立 onedir package：

```bat
scripts\package.bat
```

等效核心指令：

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
```

主要輸出：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

## 2. Dist Smoke Test

打包後執行：

```bat
scripts\smoke_dist.bat
```

至少驗證：

```text
GET /api/health
GET /api/version
```

smoke test 通過只代表 packaged runtime 可啟動，不代表 installer 已通過乾淨機器驗證。

## 3. Installer Build

Windows installer 設定：

```text
installer\VisionTrainingStudio.iss
```

建置 installer：

```bat
scripts\build_installer.bat
```

輸出預期位置：

```text
installer\output\
```

如果 `ISCC.exe` 不存在，installer build 會被阻擋，需要先安裝 Inno Setup。

## 4. Release Validation

release candidate 至少需要執行：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

檢查項目：

```text
[ ] unit / integration tests pass
[ ] Python compile checks pass
[ ] JavaScript syntax checks pass
[ ] PyInstaller package build pass
[ ] dist smoke health endpoint pass
[ ] dist smoke version endpoint pass
[ ] README and docs are readable
[ ] no projects/logs/cache/tmp/build/dist committed
```

## 5. Clean Machine Validation

installer 或 portable package 對外發布前，需要依照：

```text
docs\CLEAN_MACHINE_VALIDATION.md
```

在乾淨 Windows VM 驗證：

- 不依賴 repo working tree。
- 不要求使用者自行安裝 Python / Node.js。
- user data 不寫入 Program Files。
- `/api/health` 與 `/api/version` 可用。
- uninstall 不刪除使用者專案、模型與日誌。

## 6. Release Artifacts

建議 release artifact：

```text
release_artifacts/
  build_manifest.json
  checksum.txt
  release_notes.md
  docs/compliance/license_inventory.md
  docs/compliance/THIRD_PARTY_LICENSES.md
```

`release_artifacts/` 是輸出資料，不應提交到 Git，除非 release 流程明確要求。

## 7. Offline Asset Check

正式 package 不應依賴 CDN。請確認 `static/index.html` 沒有引用下列外部來源：

```text
https://fonts.googleapis.com
https://fonts.gstatic.com
https://cdnjs.cloudflare.com
https://cdn.jsdelivr.net
```

前端第三方資源應放在：

```text
static/vendor/
```

## 8. Diagnostics Package

產生 diagnostics：

```bat
scripts\diagnostics.bat
```

API endpoint：

```text
GET /api/diagnostics/report
```

diagnostics package 可包含 app version、health payload、recent logs、project summary、system status 與 runtime paths。不得包含 raw images、private datasets、videos、model weights 或完整 project folders。

## 9. 關於 exe 位置

目前 PyInstaller 標準輸出為：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

對使用者交付時，可以再建立外層捷徑、installer shortcut 或 portable zip 根目錄 launcher。建議不要把 exe 直接搬離 onedir 目錄，除非同時調整 PyInstaller spec 與 runtime asset resolution，否則 `_internal`、`static`、依賴 DLL 與 resource path 可能失效。
# Incremental update releases

Use a temporary `release/vX.Y.Z` stabilization branch, merge the validated
source to `main`, tag the exact release commit, and publish binary assets through
a GitHub Release draft. Branches are not update download channels.

Version 0.1.4 is the full-installer bootstrap for the updater. Compatible
`runtime-r1` releases after that may ship the signed `.vtsupdate` asset without
repacking the multi-gigabyte AI runtime. Runtime changes still require a full
installer.

The local release helper creates a draft only:

```powershell
scripts\publish_update_release.ps1 -Tag v0.1.5 -Assets <signed update>,<checksums>
```

Review every uploaded asset before publishing. Enable immutable releases in the
GitHub repository when available.

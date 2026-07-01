# 部署與打包

## 1. 打包指令

正式封裝請使用：

```bat
scripts\package.bat
```

底層 PyInstaller 指令：

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
```

輸出：

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

## 2. Dist Smoke Test

```bat
scripts\smoke_dist.bat
```

檢查：

```text
GET /api/health
GET /api/version
```

## 3. Installer

若已安裝 Inno Setup：

```powershell
ISCC installer\VisionTrainingStudio.iss
```

輸出：

```text
installer\output\
```

## 4. 版本同步規則

版本資訊來源：

```text
version.json
installer\VisionTrainingStudio.iss
packaging\vision_training_studio.spec
README.md / docs
```

Release 前需確認上述版本一致。若版本升級，應同步更新：

- `version.json`
- installer version
- release notes
- build manifest

## 5. Release Checklist

Release 前至少確認：

```text
[ ] unittest pass
[ ] node syntax check pass
[ ] py_compile / compileall pass
[ ] PyInstaller build pass
[ ] dist exe health check pass
[ ] browser console no new errors
[ ] CNN project can open
[ ] RNN / XGBoost project can open
[ ] dashboard / artifacts / run history render
[ ] README / docs updated
[ ] no projects/logs/cache/tmp/build/dist committed
```

建議執行：

```bat
scripts\test.bat
scripts\build.bat
scripts\package.bat
scripts\smoke_dist.bat
```

## 6. Release Artifacts

每次正式 release 建議產生：

```text
release_artifacts/
├─ build_manifest.json
├─ checksum.txt
├─ release_notes.md
├─ license_inventory.md
└─ THIRD_PARTY_LICENSES.md
```

目前 repo 已有 `license_inventory.md` 與 `THIRD_PARTY_LICENSES.md`，後續可加入 release artifact 產生腳本。

## 7. Offline Asset Plan

目前前端必要 runtime assets 已 vendor 到：

```text
static/vendor/
```

包含：

- Font Awesome
- Chart.js
- Dropzone
- Inter font fallback

正式 release 前仍需檢查 `static/index.html` 不應直接引用：

```text
https://fonts.googleapis.com
https://fonts.gstatic.com
https://cdnjs.cloudflare.com
https://cdn.jsdelivr.net
```

若升級 vendor 檔案，請同步更新 `static/vendor/README.md` 與第三方授權文件。

## 8. Diagnostics Zip 規格

Diagnostics zip 預設應包含：

```text
app version
health payload
recent logs
project summary
system status
runtime paths
```

預設不得包含：

```text
raw images
model weights
private datasets
完整 project folder
```

如需包含敏感資料，必須由使用者明確確認。

目前可用入口：

```bat
scripts\diagnostics.bat
```

API：

```text
GET /api/diagnostics/report
```

Production 模式下 API 需要 `X-VTS-Token`，由 `/api/bootstrap` 取得。

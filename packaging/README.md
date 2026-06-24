# Vision Training Studio Packaging

Build the Windows local onedir bundle from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\vision_training_studio.spec
```

Output:

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

Smoke test:

```powershell
dist\VisionTrainingStudio\VisionTrainingStudio.exe --port 18105 --env production --shell none
```

Then check:

```text
http://127.0.0.1:18105/api/health
http://127.0.0.1:18105/
```

Desktop shell:

```powershell
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

Installer build, when Inno Setup is installed:

```powershell
ISCC installer\VisionTrainingStudio.iss
```

Installer output:

```text
installer\output\VisionTrainingStudio_Setup_0.1.0.exe
```

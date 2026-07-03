# PyInstaller Warning Audit

## Purpose

This document classifies PyInstaller warnings seen during package builds so release hardening can distinguish expected optional imports from actionable packaging risks.

## Current Build

Date: 2026-07-03

Command:

```bat
scripts\package.bat
```

Warning file:

```text
build\vision_training_studio\warn-vision_training_studio.txt
```

Package output:

```text
dist\VisionTrainingStudio\VisionTrainingStudio.exe
```

## Actions Taken

The PyInstaller spec now filters obvious non-runtime collection noise:

- NumPy test modules
- SciPy test modules
- Torch testing modules
- XGBoost testing modules
- non-Windows pywebview platforms: Android, Cocoa, GTK, Qt, CEF
- optional cloud/experiment integrations such as W&B, Ray, Neptune, MLflow, DVC Live, Comet, ClearML
- optional model/export stacks not part of the current packaged runtime contract, such as TensorRT, OpenVINO, CoreML, TensorFlow.js, ONNX2TF

## Expected Warning Classes

These warnings are expected unless the corresponding optional feature becomes part of the supported runtime contract:

```text
Unix-only stdlib modules: pwd, grp, fcntl, termios, resource
Jython/Java probes: java, org.python
Optional PyInstaller runtime probes
Optional FastAPI/Pydantic tooling: mypy, email_validator, fastapi_cli
Optional Ultralytics integrations: wandb, ray, clearml, comet_ml, roboflow
Optional Ultralytics export backends: TensorRT, OpenVINO, CoreML, TensorFlow.js, RKNN, NCNN, MNN, Paddle
Optional pywebview platforms not used on Windows EdgeChromium
```

## Actionable Warning Classes

Treat these as release blockers if they appear after spec filtering and smoke tests fail:

```text
Missing app modules under src.*
Missing static files
Missing version.json
Missing PyQt5 / WebView2 runtime files required by selected shell
Missing torch / torchvision / ultralytics runtime modules used by inference or training
Missing xgboost runtime modules if sklearn_xgboost is included in the release contract
```

## Required Verification

After any spec change, run:

```bat
scripts\package.bat
scripts\smoke_dist.bat
```

For release candidates, also run:

```bat
scripts\build_installer.bat
scripts\validate_installed_app.bat "C:\Program Files\VisionTrainingStudio\VisionTrainingStudio.exe"
```

## Current Limitation

The local machine used for this audit does not have `ISCC.exe` available, so installer generation must be completed on a machine with Inno Setup installed.

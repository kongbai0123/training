# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parent
datas = []
binaries = []
hiddenimports = []

try:
    package_datas, package_binaries, package_hiddenimports = collect_all("cryptography")
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports
except Exception:
    pass

a = Analysis(
    [str(ROOT / "updater" / "updater.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "cv2", "numpy", "scipy", "transformers", "ultralytics"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VisionTrainingStudioUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

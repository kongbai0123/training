# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "version.json"), "."),
    (str(ROOT / "requirements.txt"), "."),
]

hiddenimports = [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "multipart.multipart",
    "pydantic_core",
]
binaries = []

for package_name in [
    "fastapi",
    "starlette",
    "pydantic",
    "uvicorn",
    "sse_starlette",
    "ultralytics",
    "lap",
    "webview",
    "pythonnet",
    "clr_loader",
    "proxy_tools",
    "bottle",
]:
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hiddenimports
    except Exception:
        pass

for package_name in ["cv2", "PIL", "numpy"]:
    try:
        datas += collect_data_files(package_name)
        hiddenimports += collect_submodules(package_name)
    except Exception:
        pass


a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VisionTrainingStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VisionTrainingStudio",
)

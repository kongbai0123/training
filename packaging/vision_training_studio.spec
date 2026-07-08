# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "data"), "data"),
    (str(ROOT / "docs" / "UI_DESIGN_SYSTEM.md"), "docs"),
    (str(ROOT / "version.json"), "."),
    (str(ROOT / "requirements.txt"), "."),
]

EXCLUDED_MODULE_PREFIXES = (
    "numpy.tests",
    "numpy.typing.tests",
    "numpy.f2py.tests",
    "numpy.fft.tests",
    "numpy.lib.tests",
    "numpy.linalg.tests",
    "numpy.ma.tests",
    "numpy.matrixlib.tests",
    "numpy.polynomial.tests",
    "numpy.random.tests",
    "numpy.testing.tests",
    "scipy.tests",
    "torch.testing",
    "xgboost.testing",
    "webview.platforms.android",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    "webview.platforms.cef",
)

EXCLUDES = [
    "pytest",
    "_pytest",
    "mypy",
    "tensorboard",
    "wandb",
    "ray",
    "neptune",
    "mlflow",
    "dvclive",
    "comet_ml",
    "clearml",
    "roboflow",
    "streamlit",
    "flask",
    "timm",
    "super_gradients",
    "hub_sdk",
    "pymongo",
    "tensorflowjs",
    "onnx2tf",
    "openvino",
    "tensorrt",
    "coremltools",
]


def keep_hidden_import(module_name):
    return not any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in EXCLUDED_MODULE_PREFIXES
    )


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
    "xgboost",
]:
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += [name for name in package_hiddenimports if keep_hidden_import(name)]
    except Exception:
        pass

for package_name in ["cv2", "PIL", "numpy"]:
    try:
        datas += collect_data_files(package_name)
        hiddenimports += [name for name in collect_submodules(package_name) if keep_hidden_import(name)]
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
    excludes=EXCLUDES,
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

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata


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
    "numpy._pyinstaller.tests",
    "numpy.distutils.tests",
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
    "torch.utils.tensorboard",
    "onnx.reference",
    "xgboost.testing",
    "xgboost.spark",
    "xgboost.dask",
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
    "super_gradients",
    "hub_sdk",
    "pymongo",
    "tensorflowjs",
    "onnx2tf",
    "onnx.reference",
    "openvino",
    "tensorrt",
    "coremltools",
    # Optional ecosystems pulled in by broad third-party package hooks. Vision
    # Training Studio does not expose these runtimes and must not inherit them
    # from the build machine's global Python environment.
    "tensorflow",
    "tensorflow_probability",
    "keras",
    "tf_keras",
    "jax",
    "flax",
    "diffusers",
    "gradio",
    "altair",
    "openai",
    "yt_dlp",
    "imageio",
    "pyarrow",
    "h5py",
    "IPython",
    "watchdog",
    "strawberry",
    "sentry_sdk",
    "django",
    "opentelemetry",
    "ddtrace",
]


def keep_hidden_import(module_name):
    if module_name.endswith(".tests") or ".tests." in module_name:
        return False
    return not any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in EXCLUDED_MODULE_PREFIXES
    )


hiddenimports = [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "bottle",
    "multipart.multipart",
    "pydantic_core",
]
binaries = []

try:
    datas += copy_metadata("opencv-python")
except Exception:
    pass

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
    "xgboost",
    "transformers",
    "huggingface_hub",
    "safetensors",
    "timm",
]:
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(
            package_name,
            filter_submodules=keep_hidden_import,
        )
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hiddenimports
    except Exception:
        pass

for package_name in ["cv2", "PIL", "numpy"]:
    try:
        datas += collect_data_files(package_name)
        hiddenimports += collect_submodules(package_name, filter=keep_hidden_import)
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

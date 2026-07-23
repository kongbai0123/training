from __future__ import annotations

import json
import os
from pathlib import Path

from src.app_paths import APP_HOME, STATIC_DIR as _STATIC_DIR, PROJECTS_DIR as _PROJECTS_DIR

APP_ENV = os.environ.get("VTS_ENV", os.environ.get("VTS_MODE", "development")).lower()
BASE_DIR = APP_HOME
PROJECTS_DIR = _PROJECTS_DIR
STATIC_DIR = _STATIC_DIR
APP_VERSION = "0.0.0"
RUNTIME_VERSION = "unknown"
UPDATE_PACKAGE_FORMAT_VERSION = 1
VERSION_INFO = {
    "product": "Vision Training Studio",
    "version": APP_VERSION,
    "app_version": APP_VERSION,
    "runtime_version": RUNTIME_VERSION,
    "package_format_version": UPDATE_PACKAGE_FORMAT_VERSION,
    "update_channel": "stable",
    "edition": "Local",
    "build": "unknown",
    "channel": "commercial-mvp",
}

_version_file = BASE_DIR / "version.json"
if _version_file.exists():
    try:
        with _version_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)
            if isinstance(payload, dict):
                VERSION_INFO.update(payload)
                APP_VERSION = str(VERSION_INFO.get("app_version", VERSION_INFO.get("version", APP_VERSION)))
                VERSION_INFO["version"] = APP_VERSION
                VERSION_INFO["app_version"] = APP_VERSION
                RUNTIME_VERSION = str(VERSION_INFO.get("runtime_version", RUNTIME_VERSION))
                UPDATE_PACKAGE_FORMAT_VERSION = int(
                    VERSION_INFO.get("package_format_version", UPDATE_PACKAGE_FORMAT_VERSION)
                )
    except Exception:
        APP_VERSION = "0.0.0"
        VERSION_INFO["version"] = APP_VERSION
        VERSION_INFO["app_version"] = APP_VERSION

# Device Configuration
HAS_GPU = False
DEVICE = "cpu"
DEVICE_NAME = "CPU"

try:
    import torch

    HAS_GPU = torch.cuda.is_available()
    DEVICE = "0" if HAS_GPU else "cpu"
    DEVICE_NAME = torch.cuda.get_device_name(0) if HAS_GPU else "CPU"
except ImportError:
    HAS_GPU = False
    DEVICE = "cpu"
    DEVICE_NAME = "CPU (PyTorch not installed)"

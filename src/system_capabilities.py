from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict

from src.app_paths import USER_DATA_DIR


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"
    except Exception:
        return "unknown"


def _opencv_version() -> str:
    installed_version = _package_version("opencv-python")
    if installed_version != "not_installed":
        return installed_version
    try:
        import cv2

        return str(cv2.__version__)
    except Exception:
        return "not_installed"


def _memory_capability() -> Dict[str, Any]:
    try:
        import psutil

        memory = psutil.virtual_memory()
        return {
            "status": "available",
            "total_gb": round(memory.total / (1024**3), 1),
            "available_gb": round(memory.available / (1024**3), 1),
            "percent_used": round(memory.percent, 1),
        }
    except Exception as exc:
        return {"status": "unavailable", "total_gb": None, "available_gb": None, "percent_used": None, "error": str(exc)}


def _cpu_capability() -> Dict[str, Any]:
    physical_cores = None
    logical_cores = os.cpu_count()
    try:
        import psutil

        physical_cores = psutil.cpu_count(logical=False)
        logical_cores = psutil.cpu_count(logical=True) or logical_cores
    except Exception:
        pass
    return {
        "architecture": platform.machine() or "unknown",
        "name": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unknown",
        "physical_cores": physical_cores,
        "logical_cores": logical_cores,
    }


def _disk_capability(path: Path) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {
            "status": "available",
            "path": path.resolve().as_posix(),
            "total_gb": round(usage.total / (1024**3), 1),
            "available_gb": round(usage.free / (1024**3), 1),
            "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total else 0.0,
        }
    except Exception as exc:
        return {"status": "unavailable", "path": path.as_posix(), "error": str(exc)}


def _gpu_capability() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "available": False,
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "torch_version": _package_version("torch"),
        "cuda_runtime": None,
    }
    try:
        import torch

        result["cuda_available"] = bool(torch.cuda.is_available())
        result["available"] = result["cuda_available"]
        result["cuda_runtime"] = getattr(torch.version, "cuda", None)
        result["device_count"] = int(torch.cuda.device_count()) if result["cuda_available"] else 0
        devices = []
        for index in range(result["device_count"]):
            properties = torch.cuda.get_device_properties(index)
            devices.append({
                "index": index,
                "name": properties.name,
                "vram_total_mb": int(properties.total_memory / (1024**2)),
                "compute_capability": f"{properties.major}.{properties.minor}",
            })
        result["devices"] = devices
    except Exception as exc:
        result["error"] = str(exc)
    return result


def get_system_capabilities() -> Dict[str, Any]:
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "python": platform.python_version(),
        },
        "cpu": _cpu_capability(),
        "memory": _memory_capability(),
        "disk": _disk_capability(USER_DATA_DIR),
        "gpu": _gpu_capability(),
        "runtime": {
            "opencv": _opencv_version(),
            "ultralytics": _package_version("ultralytics"),
            "xgboost": _package_version("xgboost"),
        },
    }

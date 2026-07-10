import os

from fastapi import APIRouter

from src.config import APP_ENV, APP_VERSION, BASE_DIR, PROJECTS_DIR, STATIC_DIR, VERSION_INFO
from src.license_manager import build_license_report
from src.local_session import current_bootstrap
from src.system_capabilities import get_system_capabilities


router = APIRouter()
LOCAL_TRUSTED_MODE = os.environ.get("LOCAL_TRUSTED_MODE", "false").lower() in ("true", "1", "yes")


@router.get("/api/version")
def get_version():
    return VERSION_INFO


@router.get("/api/bootstrap")
def bootstrap():
    return current_bootstrap(APP_VERSION, APP_ENV)


@router.get("/api/system/capabilities")
def system_capabilities():
    return get_system_capabilities()


@router.get("/api/health")
def health_check():
    torch_version = "Not installed"
    has_gpu = False
    device_name = "CPU"
    memory = {
        "available_gb": None,
        "total_gb": None,
        "percent_used": None,
        "status": "unavailable",
    }
    try:
        import torch

        torch_version = torch.__version__
        has_gpu = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if has_gpu else "CPU"
    except Exception:
        pass
    try:
        import psutil

        ram = psutil.virtual_memory()
        memory = {
            "available_gb": round(ram.available / (1024**3), 1),
            "total_gb": round(ram.total / (1024**3), 1),
            "percent_used": round(ram.percent, 1),
            "status": "available",
        }
    except Exception:
        pass

    return {
        "status": "healthy",
        "mode": APP_ENV,
        "version": APP_VERSION,
        "local_trusted_mode": LOCAL_TRUSTED_MODE,
        "device": {
            "has_gpu": has_gpu,
            "device_name": device_name,
            "torch_version": torch_version,
        },
        "memory": memory,
        "directories": {
            "base_dir": str(BASE_DIR.resolve().as_posix()),
            "projects_dir": str(PROJECTS_DIR.resolve().as_posix()),
            "static_dir": str(STATIC_DIR.resolve().as_posix()),
        },
        "license": build_license_report(),
    }

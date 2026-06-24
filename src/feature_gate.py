from __future__ import annotations

from typing import Iterable, Set

from fastapi import HTTPException

from src.license_manager import LicenseManager
from src.app_paths import APP_DATA_CONFIG


REQUIRED_FEATURES = {
    "training": "training",
    "auto_labeling": "auto_labeling",
    "inference": "inference",
    "export_onnx": "export_onnx",
}


def require_feature(feature: str):
    manager = LicenseManager(APP_DATA_CONFIG.get("mode", "development"))

    def _decorator():
        status = manager.validate({feature})
        if not status.valid:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "FEATURE_DISABLED",
                        "message": status.reason,
                        "feature": feature,
                    }
                },
            )
        return True

    return _decorator


def can_access(feature_set: Iterable[str]) -> bool:
    manager = LicenseManager(APP_DATA_CONFIG.get("mode", "development"))
    result = manager.validate(set(feature_set))
    return result.valid

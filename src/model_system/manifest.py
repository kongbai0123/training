from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.model_system.constants import MODEL_MANIFEST_NAME, MODEL_STATUS_VALIDATED_BASIC


def build_yolo_pt_manifest(
    *,
    model_id: str,
    display_name: str,
    task_family: str,
    weight_file: str,
    original_filename: str,
    status: str = MODEL_STATUS_VALIDATED_BASIC,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name": display_name,
        "architecture": "cnn",
        "backend": "ultralytics_yolo",
        "task_family": task_family,
        "source": "user_import",
        "format": "pt",
        "weight_file": weight_file,
        "original_filename": original_filename,
        "trainable": True,
        "inference_supported": True,
        "evaluation_supported": True,
        "imported": True,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def build_yolo_yaml_manifest(
    *,
    model_id: str,
    display_name: str,
    task_family: str,
    model_file: str,
    original_filename: str,
    status: str = MODEL_STATUS_VALIDATED_BASIC,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name": display_name,
        "architecture": "cnn",
        "backend": "ultralytics_yolo",
        "task_family": task_family,
        "source": "user_import",
        "format": "yaml",
        "weight_file": model_file,
        "original_filename": original_filename,
        "trainable": True,
        "inference_supported": False,
        "evaluation_supported": False,
        "imported": True,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def build_onnx_manifest(
    *,
    model_id: str,
    display_name: str,
    task_family: str,
    model_file: str,
    original_filename: str,
    status: str = MODEL_STATUS_VALIDATED_BASIC,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name": display_name,
        "architecture": "cnn",
        "backend": "onnxruntime",
        "task_family": task_family,
        "source": "user_import",
        "format": "onnx",
        "weight_file": model_file,
        "original_filename": original_filename,
        "trainable": False,
        "inference_supported": True,
        "evaluation_supported": False,
        "imported": True,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def build_rnn_package_manifest(
    *,
    model_id: str,
    display_name: str,
    task_family: str,
    weight_file: str,
    original_filename: str,
    package_files: Dict[str, str],
    status: str = MODEL_STATUS_VALIDATED_BASIC,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name": display_name,
        "architecture": "rnn",
        "backend": "pytorch_lstm",
        "task_family": task_family,
        "source": "user_import",
        "format": "rnn_package",
        "weight_file": weight_file,
        "original_filename": original_filename,
        "package_files": package_files,
        "trainable": False,
        "inference_supported": True,
        "evaluation_supported": False,
        "imported": True,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def build_custom_package_manifest(
    *,
    model_id: str,
    display_name: str,
    task_family: str,
    package_file: str,
    original_filename: str,
    package_files: Dict[str, str],
    status: str,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "display_name": display_name,
        "architecture": "custom",
        "backend": "custom_package",
        "task_family": task_family,
        "source": "custom_package",
        "format": "custom_package",
        "weight_file": package_file,
        "original_filename": original_filename,
        "package_files": package_files,
        "trainable": False,
        "inference_supported": False,
        "evaluation_supported": False,
        "imported": True,
        "execution_enabled": False,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def read_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(import_dir: Path, manifest: Dict[str, Any]) -> Path:
    import_dir.mkdir(parents=True, exist_ok=True)
    path = import_dir / MODEL_MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path

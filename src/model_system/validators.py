from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from src.model_system.constants import (
    MODEL_STATUS_FAILED,
    MODEL_STATUS_REGISTERED_DISABLED,
    MODEL_STATUS_REJECTED,
    MODEL_STATUS_VALIDATED_BASIC,
    VALIDATION_REPORT_NAME,
)


ALLOWED_YOLO_TASK_FAMILIES = {"detection", "segmentation"}
ALLOWED_ONNX_TASK_FAMILIES = {"classification", "detection", "segmentation"}
ALLOWED_RNN_TASK_FAMILIES = {"sequence_classification", "sequence_regression"}
RNN_PACKAGE_REQUIRED_FILES = {
    "model_manifest.json",
    "model.pt",
    "feature_schema.json",
    "normalization_stats.json",
    "sequence_config.json",
}
CUSTOM_PACKAGE_REQUIRED_FIELDS = {
    "schema_version",
    "model_id",
    "model_name",
    "model_type",
    "task",
    "runtime",
    "artifacts",
    "input_spec",
    "output_spec",
    "capabilities",
    "security",
    "dependency_policy",
}
CUSTOM_PACKAGE_REQUIRED_OBJECTS = {
    "runtime",
    "artifacts",
    "input_spec",
    "output_spec",
    "capabilities",
    "security",
    "dependency_policy",
}


def validate_yolo_pt_import(source_path: Path, task_family: str) -> Dict[str, Any]:
    task = str(task_family or "").strip().lower()
    checks = []
    warnings = [
        "Deep model loading is intentionally skipped in this phase. The model is validated by file existence, extension, and task selection only."
    ]
    errors = []

    checks.append({"name": "file_exists", "passed": source_path.exists() and source_path.is_file()})
    if not source_path.exists() or not source_path.is_file():
        errors.append("Model file does not exist.")

    checks.append({"name": "extension_check", "passed": source_path.suffix.lower() == ".pt", "value": source_path.suffix.lower()})
    if source_path.suffix.lower() != ".pt":
        errors.append("Only YOLO .pt weights are supported in this phase.")

    checks.append({"name": "task_family_check", "passed": task in ALLOWED_YOLO_TASK_FAMILIES, "value": task})
    if task not in ALLOWED_YOLO_TASK_FAMILIES:
        errors.append("Task family must be detection or segmentation.")

    checks.append({"name": "ultralytics_load_optional", "passed": None, "skipped": True})

    return {
        "status": MODEL_STATUS_FAILED if errors else MODEL_STATUS_VALIDATED_BASIC,
        "created_at": datetime.now().isoformat(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def validate_yolo_yaml_import(source_path: Path, task_family: str) -> Dict[str, Any]:
    task = str(task_family or "").strip().lower()
    checks = []
    warnings = [
        "YAML import is limited to YOLO model architecture YAML. Dataset YAML files are rejected."
    ]
    errors = []

    checks.append({"name": "file_exists", "passed": source_path.exists() and source_path.is_file()})
    if not source_path.exists() or not source_path.is_file():
        errors.append("Model YAML file does not exist.")

    suffix_ok = source_path.suffix.lower() in {".yaml", ".yml"}
    checks.append({"name": "extension_check", "passed": suffix_ok, "value": source_path.suffix.lower()})
    if not suffix_ok:
        errors.append("Only YOLO .yaml / .yml architecture files are supported in this phase.")

    checks.append({"name": "task_family_check", "passed": task in ALLOWED_YOLO_TASK_FAMILIES, "value": task})
    if task not in ALLOWED_YOLO_TASK_FAMILIES:
        errors.append("Task family must be detection or segmentation.")

    parsed = _read_yaml_dict(source_path) if source_path.exists() and source_path.is_file() else {}
    has_backbone = isinstance(parsed.get("backbone"), list)
    has_head = isinstance(parsed.get("head"), list)
    looks_like_dataset = any(key in parsed for key in ("train", "val", "test", "names")) and "backbone" not in parsed
    checks.append({"name": "model_architecture_yaml_check", "passed": has_backbone and has_head})
    checks.append({"name": "dataset_yaml_rejection", "passed": not looks_like_dataset})

    if looks_like_dataset:
        errors.append("This looks like a YOLO dataset YAML, not a model architecture YAML.")
    elif not (has_backbone and has_head):
        errors.append("YOLO model architecture YAML must contain backbone and head lists.")

    return {
        "status": MODEL_STATUS_FAILED if errors else MODEL_STATUS_VALIDATED_BASIC,
        "created_at": datetime.now().isoformat(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def _read_yaml_dict(path: Path) -> Dict[str, Any]:
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def copy_yolo_pt_to_import(source_path: Path, import_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / "best.pt"
    shutil.copy2(source_path, target)
    return target, {
        "name": "copy_success",
        "passed": target.exists() and target.is_file(),
        "target": target.name,
        "size_bytes": target.stat().st_size if target.exists() else 0,
    }


def copy_yolo_yaml_to_import(source_path: Path, import_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / "model.yaml"
    shutil.copy2(source_path, target)
    return target, {
        "name": "copy_success",
        "passed": target.exists() and target.is_file(),
        "target": target.name,
        "size_bytes": target.stat().st_size if target.exists() else 0,
    }


def validate_onnx_import(source_path: Path, task_family: str) -> Dict[str, Any]:
    task = str(task_family or "").strip().lower()
    checks = []
    warnings = [
        "ONNX import is registered as inference-only in this phase. Training, export, and runtime execution are not enabled here."
    ]
    errors = []

    checks.append({"name": "file_exists", "passed": source_path.exists() and source_path.is_file()})
    if not source_path.exists() or not source_path.is_file():
        errors.append("ONNX model file does not exist.")

    checks.append({"name": "extension_check", "passed": source_path.suffix.lower() == ".onnx", "value": source_path.suffix.lower()})
    if source_path.suffix.lower() != ".onnx":
        errors.append("Only .onnx model files are supported for ONNX import.")

    checks.append({"name": "task_family_check", "passed": task in ALLOWED_ONNX_TASK_FAMILIES, "value": task})
    if task not in ALLOWED_ONNX_TASK_FAMILIES:
        errors.append("Task family must be classification, detection, or segmentation.")

    checks.append({"name": "onnxruntime_load_optional", "passed": None, "skipped": True})

    return {
        "status": MODEL_STATUS_FAILED if errors else MODEL_STATUS_VALIDATED_BASIC,
        "created_at": datetime.now().isoformat(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def copy_onnx_to_import(source_path: Path, import_dir: Path) -> Tuple[Path, Dict[str, Any]]:
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / "model.onnx"
    shutil.copy2(source_path, target)
    return target, {
        "name": "copy_success",
        "passed": target.exists() and target.is_file(),
        "target": target.name,
        "size_bytes": target.stat().st_size if target.exists() else 0,
    }


def validate_rnn_package_dir(import_dir: Path, task_family: str) -> Dict[str, Any]:
    task = str(task_family or "").strip().lower()
    checks = []
    warnings = [
        "RNN package import only validates package structure in this phase. PyTorch loading and RNN training are not executed."
    ]
    errors = []

    checks.append({"name": "task_family_check", "passed": task in ALLOWED_RNN_TASK_FAMILIES, "value": task})
    if task not in ALLOWED_RNN_TASK_FAMILIES:
        errors.append("Task family must be sequence_classification or sequence_regression.")

    for required in sorted(RNN_PACKAGE_REQUIRED_FILES):
        path = import_dir / required
        passed = path.exists() and path.is_file()
        checks.append({"name": f"required_file:{required}", "passed": passed})
        if not passed:
            errors.append(f"RNN package is missing required file: {required}")

    source_manifest_path = import_dir / "model_manifest.json"
    if source_manifest_path.exists():
        try:
            payload = json.loads(source_manifest_path.read_text(encoding="utf-8"))
            manifest_architecture = str(payload.get("architecture", "")).lower()
            manifest_backend = str(payload.get("backend", "")).lower()
            checks.append({"name": "package_manifest_architecture", "passed": manifest_architecture in {"", "rnn"}, "value": manifest_architecture})
            checks.append({"name": "package_manifest_backend", "passed": manifest_backend in {"", "pytorch_lstm"}, "value": manifest_backend})
            if manifest_architecture and manifest_architecture != "rnn":
                errors.append("RNN package model_manifest.json architecture must be rnn.")
            if manifest_backend and manifest_backend != "pytorch_lstm":
                warnings.append("RNN package backend is not pytorch_lstm; it will be registered as pytorch_lstm preview only.")
        except Exception as exc:
            errors.append(f"RNN package model_manifest.json is not valid JSON: {exc}")

    return {
        "status": MODEL_STATUS_FAILED if errors else MODEL_STATUS_VALIDATED_BASIC,
        "created_at": datetime.now().isoformat(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def _safe_extract_zip(source_path: Path, import_dir: Path, package_label: str) -> Dict[str, Any]:
    import_dir.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() != ".zip":
        return {"name": "extract_zip", "passed": False, "status": "failed", "errors": [f"Only .zip {package_label} packages are supported."]}

    try:
        with zipfile.ZipFile(source_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_name = member.filename.replace("\\", "/")
                if member_name.startswith("/") or ".." in Path(member_name).parts:
                    return {"name": "extract_zip", "passed": False, "errors": [f"Unsafe package path: {member.filename}"]}
                target = (import_dir / member_name).resolve()
                if import_dir.resolve() not in target.parents:
                    return {"name": "extract_zip", "passed": False, "errors": [f"Package path escapes import directory: {member.filename}"]}
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as destination:
                    shutil.copyfileobj(source, destination)
    except zipfile.BadZipFile:
        return {"name": "extract_zip", "passed": False, "status": "failed", "errors": [f"{package_label} package is not a valid zip file."]}

    extracted = sorted(path.relative_to(import_dir).as_posix() for path in import_dir.rglob("*") if path.is_file())
    return {
        "name": "extract_zip",
        "passed": True,
        "status": "passed",
        "file_count": len(extracted),
        "files": extracted,
    }


def extract_rnn_package_to_import(source_path: Path, import_dir: Path) -> Dict[str, Any]:
    return _safe_extract_zip(source_path, import_dir, "RNN model")


def extract_custom_package_to_staging(source_path: Path, staging_dir: Path) -> Dict[str, Any]:
    return _safe_extract_zip(source_path, staging_dir, "custom model")


def validate_custom_package_dir(staging_dir: Path, import_id: str, package_name: str) -> Dict[str, Any]:
    checks = []
    errors = []
    warnings = [
        "Custom model package import is manifest-only in Phase P1-A. Package code is not imported, compiled, executed, or enabled."
    ]
    manifest_valid = False
    manifest_payload: Dict[str, Any] = {}

    manifest_path = staging_dir / "model_manifest.json"
    manifest_exists = manifest_path.exists() and manifest_path.is_file()
    checks.append({
        "name": "manifest_exists",
        "passed": manifest_exists,
        "status": "passed" if manifest_exists else "failed",
        "message": "model_manifest.json found." if manifest_exists else "model_manifest.json is missing.",
    })
    if not manifest_exists:
        errors.append("Custom model package must contain model_manifest.json.")
    else:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                manifest_payload = payload
            else:
                errors.append("model_manifest.json must contain a JSON object.")
        except Exception as exc:
            errors.append(f"model_manifest.json is not valid JSON: {exc}")

    missing_fields = sorted(field for field in CUSTOM_PACKAGE_REQUIRED_FIELDS if field not in manifest_payload)
    checks.append({
        "name": "manifest_schema",
        "passed": not missing_fields and bool(manifest_payload),
        "status": "passed" if not missing_fields and bool(manifest_payload) else "failed",
        "missing_fields": missing_fields,
        "message": "Required fields are present." if not missing_fields and bool(manifest_payload) else "Required manifest fields are missing.",
    })
    if missing_fields:
        errors.append(f"model_manifest.json is missing required fields: {', '.join(missing_fields)}")

    for field in sorted(CUSTOM_PACKAGE_REQUIRED_OBJECTS):
        value = manifest_payload.get(field)
        passed = isinstance(value, dict)
        checks.append({
            "name": f"{field}_contract",
            "passed": passed,
            "status": "passed" if passed else "failed",
            "message": f"{field} is declared." if passed else f"{field} must be an object.",
        })
        if not passed and field in manifest_payload:
            errors.append(f"{field} must be an object.")

    runtime = manifest_payload.get("runtime") if isinstance(manifest_payload.get("runtime"), dict) else {}
    entrypoint = runtime.get("entrypoint")
    checks.append({
        "name": "entrypoint_declared",
        "passed": bool(runtime.get("kind")) and bool(entrypoint),
        "status": "passed" if bool(runtime.get("kind")) and bool(entrypoint) else "failed",
        "message": f"{entrypoint} declared but not executed." if entrypoint else "runtime.kind and runtime.entrypoint are required.",
    })
    if runtime and (not runtime.get("kind") or not entrypoint):
        errors.append("runtime must include kind and entrypoint.")

    dependency_policy = manifest_payload.get("dependency_policy") if isinstance(manifest_payload.get("dependency_policy"), dict) else {}
    install_allowed = bool(dependency_policy.get("install_allowed"))
    checks.append({
        "name": "dependency_policy",
        "passed": not install_allowed,
        "status": "passed" if not install_allowed else "blocked",
        "message": "Dependency installation disabled." if not install_allowed else "Dependency installation is not allowed in Phase P1-A.",
    })
    if install_allowed:
        warnings.append("dependency_policy.install_allowed was requested but is blocked in Phase P1-A.")

    security = manifest_payload.get("security") if isinstance(manifest_payload.get("security"), dict) else {}
    blocked_permissions = [
        key for key in ("requires_network", "writes_files", "requires_shell")
        if bool(security.get(key))
    ]
    checks.append({
        "name": "sandbox_permission",
        "passed": not blocked_permissions,
        "status": "passed" if not blocked_permissions else "blocked",
        "blocked_permissions": blocked_permissions,
        "message": "No network, shell, or file-write permission requested." if not blocked_permissions else "Requested permissions are blocked in Phase P1-A.",
    })
    if blocked_permissions:
        warnings.append(f"Requested permissions are blocked in Phase P1-A: {', '.join(blocked_permissions)}")

    checks.append({
        "name": "execution_policy",
        "passed": False,
        "status": "blocked",
        "message": "P1-A is validation-only. Execution is disabled.",
    })

    manifest_valid = not errors
    status = MODEL_STATUS_REGISTERED_DISABLED if manifest_valid else MODEL_STATUS_REJECTED
    return {
        "import_id": import_id,
        "package_name": package_name,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "manifest_valid": manifest_valid,
        "execution_enabled": False,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "blocked_reasons": [
            "Execution is disabled in Phase P1-A.",
            "Package is not added to training or inference selectors.",
        ],
        "next_allowed_action": "manual_review" if manifest_valid else "fix_manifest",
        "manifest": manifest_payload if manifest_valid else {},
    }


def write_validation_report(import_dir: Path, report: Dict[str, Any]) -> Path:
    import_dir.mkdir(parents=True, exist_ok=True)
    path = import_dir / VALIDATION_REPORT_NAME
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path

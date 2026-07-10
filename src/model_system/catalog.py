from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.model_registry import ModelRegistry
from src.model_system.constants import (
    BUILTIN_MODEL_CATALOG_PATH,
    MODEL_DECISION_METADATA_PATH,
    IMPORTED_MODELS_RELATIVE_DIR,
    MODEL_MANIFEST_NAME,
    MODEL_STATUS_MISSING_FILE,
    MODEL_STATUS_REGISTERED_DISABLED,
    MODEL_STATUS_VALIDATED_BASIC,
)
from src.model_system.manifest import (
    build_custom_package_manifest,
    build_onnx_manifest,
    build_rnn_package_manifest,
    build_yolo_pt_manifest,
    build_yolo_yaml_manifest,
    read_manifest,
    write_manifest,
)
from src.model_system.install_state import resolve_builtin_install_state
from src.model_system.validators import (
    copy_onnx_to_import,
    copy_yolo_pt_to_import,
    copy_yolo_yaml_to_import,
    extract_custom_package_to_staging,
    extract_rnn_package_to_import,
    validate_custom_package_dir,
    validate_onnx_import,
    validate_rnn_package_dir,
    validate_yolo_pt_import,
    validate_yolo_yaml_import,
    write_source_manifest,
    write_validation_report,
)
from src.model_system.sandbox_gate import (
    append_sandbox_audit,
    build_dry_run_request,
    read_sandbox_audit,
    read_source_manifest,
    record_approval_decision,
)
from src.model_system.sandbox_policy import (
    build_p5_registry_enablement_policy,
    build_p6_limited_integration_contract,
)
from src.model_system.sandbox_runner import (
    DEFAULT_SANDBOX_DRY_RUN_RUNNER,
    SANDBOX_DRY_RUN_PLAN_NAME,
    build_sandbox_dry_run_plan,
)
from src.project_layout import ProjectLayout
from src.security_utils import safe_filename


def normalize_task_family(task_type: Optional[str]) -> Optional[str]:
    task = str(task_type or "").strip().lower()
    if not task:
        return None
    if "seg" in task:
        return "segmentation"
    if "detect" in task or task in {"bbox", "object_detection"}:
        return "detection"
    if "sequence_classification" in task:
        return "sequence_classification"
    if "sequence_regression" in task:
        return "sequence_regression"
    return task


def safe_model_slug(value: str) -> str:
    stem = Path(safe_filename(value or "model")).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "model"


class ModelCatalog:
    @classmethod
    def list_all(cls, project: Optional[Dict[str, Any]] = None, architecture: Optional[str] = None) -> List[Dict[str, Any]]:
        models = cls._load_builtin_models()
        if project:
            models.extend(cls._load_imported_models(project))
            models.extend(cls._load_project_trained_models(project))
        if architecture:
            models = [item for item in models if item.get("architecture") == architecture]
        return models

    @classmethod
    def list_trainable(
        cls,
        project: Optional[Dict[str, Any]] = None,
        task_family: Optional[str] = None,
        architecture: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_task = normalize_task_family(task_family)
        models = [
            item for item in cls.list_all(project=project, architecture=architecture)
            if bool(item.get("trainable"))
        ]
        if normalized_task:
            models = [item for item in models if normalize_task_family(item.get("task_family")) == normalized_task]
        return models

    @classmethod
    def list_inference_supported(
        cls,
        project: Optional[Dict[str, Any]] = None,
        task_family: Optional[str] = None,
        architecture: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_task = normalize_task_family(task_family)
        models = [
            item for item in cls.list_all(project=project, architecture=architecture)
            if bool(item.get("inference_supported"))
        ]
        if normalized_task:
            models = [item for item in models if normalize_task_family(item.get("task_family")) == normalized_task]
        return models

    @classmethod
    def get_model(cls, project: Optional[Dict[str, Any]], model_id: str) -> Optional[Dict[str, Any]]:
        return next((item for item in cls.list_all(project=project) if item.get("model_id") == model_id), None)

    @classmethod
    def register_imported_model(cls, manifest_path: str) -> Dict[str, Any]:
        manifest = read_manifest(Path(manifest_path))
        return manifest

    @classmethod
    def refresh_project_models(cls, project_id: str) -> Dict[str, Any]:
        return {"project_id": project_id, "refreshed_at": datetime.now().isoformat()}

    @classmethod
    def request_custom_package_dry_run(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Dry-run approval is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        source_manifest = read_source_manifest(import_dir)
        request = build_dry_run_request(import_dir, model, source_manifest)
        return {
            "success": request.get("runtime_supported", False),
            "model": model,
            "dry_run": request,
            "dry_run_report_path": (import_dir / "dry_run_report.json").as_posix(),
        }

    @classmethod
    def record_custom_package_dry_run_approval(
        cls,
        project: Dict[str, Any],
        model_id: str,
        decision: str,
        approved_by: str = "local_user",
        note: str = "",
    ) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Dry-run approval is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        decision_payload = record_approval_decision(import_dir, model, decision, approved_by=approved_by, note=note)
        return {
            "success": True,
            "model": model,
            "approval": decision_payload,
            "dry_run_report_path": (import_dir / "dry_run_report.json").as_posix(),
        }

    @classmethod
    def run_custom_package_mock_dry_run(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Mock dry-run is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        report = DEFAULT_SANDBOX_DRY_RUN_RUNNER.run(import_dir, model)
        return {
            "success": report.get("status") == "MOCK_DRY_RUN_COMPLETED",
            "model": model,
            "dry_run": report,
            "mock_dry_run_report_path": (import_dir / "mock_dry_run_report.json").as_posix(),
            "dry_run_report_path": (import_dir / "dry_run_report.json").as_posix(),
        }

    @classmethod
    def build_custom_package_sandbox_plan(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Sandbox plan is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        plan = build_sandbox_dry_run_plan(import_dir, model)
        return {
            "success": plan.get("status") == "SANDBOX_PLAN_READY",
            "model": model,
            "plan": plan,
            "sandbox_plan_path": (import_dir / SANDBOX_DRY_RUN_PLAN_NAME).as_posix(),
        }

    @classmethod
    def get_custom_package_sandbox_audit(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Sandbox audit is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        return {
            "success": True,
            "model": model,
            "audit": read_sandbox_audit(import_dir),
            "audit_log_path": (import_dir / "sandbox_audit_log.jsonl").as_posix(),
        }

    @classmethod
    def evaluate_custom_package_enablement(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Enablement policy is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        source_manifest = read_source_manifest(import_dir)
        policy_model = {**model}
        if isinstance(source_manifest.get("capabilities"), dict):
            policy_model["capabilities"] = source_manifest["capabilities"]
        dry_run_report = _read_json(import_dir / "dry_run_report.json")
        sandbox_plan = _read_json(import_dir / SANDBOX_DRY_RUN_PLAN_NAME)
        policy = build_p5_registry_enablement_policy(policy_model, dry_run_report, sandbox_plan)
        policy_path = import_dir / "registry_enablement_policy.json"
        _write_json(policy_path, policy)
        append_sandbox_audit(import_dir, "registry_enablement_policy_evaluated", policy)
        return {
            "success": True,
            "model": model,
            "enablement": policy,
            "enablement_policy_path": policy_path.as_posix(),
        }

    @classmethod
    def build_custom_package_integration_contract(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        model = cls.get_model(project, model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        if model.get("format") != "custom_package":
            return {"success": False, "error": "Integration contract is only available for custom_package models"}

        import_dir = Path(model.get("manifest_path", "")).parent
        source_manifest = read_source_manifest(import_dir)
        policy_model = {**model}
        if isinstance(source_manifest.get("capabilities"), dict):
            policy_model["capabilities"] = source_manifest["capabilities"]
        enablement = _read_json(import_dir / "registry_enablement_policy.json")
        if not enablement:
            dry_run_report = _read_json(import_dir / "dry_run_report.json")
            sandbox_plan = _read_json(import_dir / SANDBOX_DRY_RUN_PLAN_NAME)
            enablement = build_p5_registry_enablement_policy(policy_model, dry_run_report, sandbox_plan)
        contract = build_p6_limited_integration_contract(policy_model, enablement)
        contract_path = import_dir / "limited_integration_contract.json"
        _write_json(contract_path, contract)
        append_sandbox_audit(import_dir, "limited_integration_contract_evaluated", contract)
        return {
            "success": True,
            "model": model,
            "integration": contract,
            "integration_contract_path": contract_path.as_posix(),
        }

    @classmethod
    def import_yolo_pt(
        cls,
        *,
        project: Dict[str, Any],
        source_path: Path,
        display_name: str,
        task_family: str,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        slug = safe_model_slug(display_name or source_path.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"imported.yolo.{slug}.{timestamp}"
        import_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR / model_id

        validation = validate_yolo_pt_import(source_path, task_family)
        if validation["status"] != MODEL_STATUS_VALIDATED_BASIC:
            import_dir.mkdir(parents=True, exist_ok=True)
            write_validation_report(import_dir, validation)
            return {"success": False, "model": None, "validation": validation}

        target, copy_check = copy_yolo_pt_to_import(source_path, import_dir)
        validation["checks"].append(copy_check)
        if not copy_check.get("passed"):
            validation["status"] = "failed"
            validation.setdefault("errors", []).append("Failed to copy model file into project imports.")

        manifest = build_yolo_pt_manifest(
            model_id=model_id,
            display_name=display_name or source_path.stem,
            task_family=normalize_task_family(task_family) or "segmentation",
            weight_file=target.name,
            original_filename=source_path.name,
            status=validation["status"],
        )
        manifest_path = write_manifest(import_dir, manifest)
        report_path = write_validation_report(import_dir, validation)
        entry = cls._entry_from_import_manifest(layout.project_dir, manifest_path)

        return {
            "success": validation["status"] != "failed",
            "model": entry,
            "manifest_path": manifest_path.as_posix(),
            "validation_report_path": report_path.as_posix(),
            "validation": validation,
        }

    @classmethod
    def import_yolo_yaml(
        cls,
        *,
        project: Dict[str, Any],
        source_path: Path,
        display_name: str,
        task_family: str,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        slug = safe_model_slug(display_name or source_path.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"imported.yolo_yaml.{slug}.{timestamp}"
        import_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR / model_id

        validation = validate_yolo_yaml_import(source_path, task_family)
        if validation["status"] != MODEL_STATUS_VALIDATED_BASIC:
            import_dir.mkdir(parents=True, exist_ok=True)
            write_validation_report(import_dir, validation)
            return {"success": False, "model": None, "validation": validation}

        target, copy_check = copy_yolo_yaml_to_import(source_path, import_dir)
        validation["checks"].append(copy_check)
        if not copy_check.get("passed"):
            validation["status"] = "failed"
            validation.setdefault("errors", []).append("Failed to copy model YAML into project imports.")

        manifest = build_yolo_yaml_manifest(
            model_id=model_id,
            display_name=display_name or source_path.stem,
            task_family=normalize_task_family(task_family) or "segmentation",
            model_file=target.name,
            original_filename=source_path.name,
            status=validation["status"],
        )
        manifest_path = write_manifest(import_dir, manifest)
        report_path = write_validation_report(import_dir, validation)
        entry = cls._entry_from_import_manifest(layout.project_dir, manifest_path)

        return {
            "success": validation["status"] != "failed",
            "model": entry,
            "manifest_path": manifest_path.as_posix(),
            "validation_report_path": report_path.as_posix(),
            "validation": validation,
        }

    @classmethod
    def import_onnx(
        cls,
        *,
        project: Dict[str, Any],
        source_path: Path,
        display_name: str,
        task_family: str,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        slug = safe_model_slug(display_name or source_path.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"imported.onnx.{slug}.{timestamp}"
        import_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR / model_id

        validation = validate_onnx_import(source_path, task_family)
        if validation["status"] != MODEL_STATUS_VALIDATED_BASIC:
            import_dir.mkdir(parents=True, exist_ok=True)
            write_validation_report(import_dir, validation)
            return {"success": False, "model": None, "validation": validation}

        target, copy_check = copy_onnx_to_import(source_path, import_dir)
        validation["checks"].append(copy_check)
        if not copy_check.get("passed"):
            validation["status"] = "failed"
            validation.setdefault("errors", []).append("Failed to copy ONNX model into project imports.")

        manifest = build_onnx_manifest(
            model_id=model_id,
            display_name=display_name or source_path.stem,
            task_family=normalize_task_family(task_family) or "segmentation",
            model_file=target.name,
            original_filename=source_path.name,
            status=validation["status"],
        )
        manifest_path = write_manifest(import_dir, manifest)
        report_path = write_validation_report(import_dir, validation)
        entry = cls._entry_from_import_manifest(layout.project_dir, manifest_path)

        return {
            "success": validation["status"] != "failed",
            "model": entry,
            "manifest_path": manifest_path.as_posix(),
            "validation_report_path": report_path.as_posix(),
            "validation": validation,
        }

    @classmethod
    def import_rnn_package(
        cls,
        *,
        project: Dict[str, Any],
        source_path: Path,
        display_name: str,
        task_family: str,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        slug = safe_model_slug(display_name or source_path.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"imported.rnn_package.{slug}.{timestamp}"
        import_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR / model_id

        extract_check = extract_rnn_package_to_import(source_path, import_dir)
        validation = validate_rnn_package_dir(import_dir, task_family)
        validation["checks"].insert(0, extract_check)
        if not extract_check.get("passed"):
            validation["status"] = "failed"
            validation.setdefault("errors", []).extend(extract_check.get("errors", ["Failed to extract RNN model package."]))

        if validation["status"] != MODEL_STATUS_VALIDATED_BASIC:
            write_validation_report(import_dir, validation)
            return {"success": False, "model": None, "validation": validation}

        source_manifest = import_dir / "model_manifest.json"
        preserved_source_manifest = import_dir / "source_model_manifest.json"
        if source_manifest.exists():
            source_manifest.replace(preserved_source_manifest)

        package_files = {
            "source_manifest": "source_model_manifest.json",
            "model": "model.pt",
            "feature_schema": "feature_schema.json",
            "normalization_stats": "normalization_stats.json",
            "sequence_config": "sequence_config.json",
        }
        label_encoder = import_dir / "label_encoder.json"
        if label_encoder.exists():
            package_files["label_encoder"] = "label_encoder.json"

        manifest = build_rnn_package_manifest(
            model_id=model_id,
            display_name=display_name or source_path.stem,
            task_family=normalize_task_family(task_family) or "sequence_classification",
            weight_file="model.pt",
            original_filename=source_path.name,
            package_files=package_files,
            status=validation["status"],
        )
        manifest_path = write_manifest(import_dir, manifest)
        report_path = write_validation_report(import_dir, validation)
        entry = cls._entry_from_import_manifest(layout.project_dir, manifest_path)

        return {
            "success": validation["status"] != "failed",
            "model": entry,
            "manifest_path": manifest_path.as_posix(),
            "validation_report_path": report_path.as_posix(),
            "validation": validation,
        }

    @classmethod
    def import_custom_package(
        cls,
        *,
        project: Dict[str, Any],
        source_path: Path,
        display_name: str,
        task_family: str,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        slug = safe_model_slug(display_name or source_path.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        import_id = f"imp_{timestamp}_{slug}"
        model_id = f"custom.package.{slug}.{timestamp}"
        staging_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR / "staging" / import_id

        extract_check = extract_custom_package_to_staging(source_path, staging_dir)
        validation = validate_custom_package_dir(staging_dir, import_id, source_path.name)
        validation["checks"].insert(0, {
            **extract_check,
            "status": "passed" if extract_check.get("passed") else "failed",
            "message": "Package extracted inside staging directory." if extract_check.get("passed") else "Package extraction failed.",
        })
        if not extract_check.get("passed"):
            validation["status"] = "REJECTED"
            validation["manifest_valid"] = False
            validation.setdefault("errors", []).extend(extract_check.get("errors", ["Failed to extract custom model package."]))

        package_files = {"package": source_path.name}
        if validation.get("manifest"):
            source_manifest_path = write_source_manifest(staging_dir, validation["manifest"])
            package_files["source_manifest"] = source_manifest_path.name
        if validation.get("source_manifest_path"):
            package_files["original_manifest"] = validation["source_manifest_path"]
        if validation.get("package_root"):
            package_files["package_root"] = validation["package_root"]

        task = normalize_task_family(task_family) or normalize_task_family(validation.get("manifest", {}).get("task")) or "custom"
        display = display_name or validation.get("manifest", {}).get("model_name") or source_path.stem
        manifest = build_custom_package_manifest(
            model_id=model_id,
            display_name=display,
            task_family=task,
            package_file=package_files.get("source_manifest") or "",
            original_filename=source_path.name,
            package_files=package_files,
            status=validation["status"] if validation.get("manifest_valid") else "REJECTED",
        )
        manifest_path = write_manifest(staging_dir, manifest)
        report_path = write_validation_report(staging_dir, validation)
        entry = cls._entry_from_import_manifest(layout.project_dir, manifest_path)

        return {
            "success": bool(validation.get("manifest_valid")),
            "model": entry if validation.get("manifest_valid") else None,
            "manifest_path": manifest_path.as_posix(),
            "validation_report_path": report_path.as_posix(),
            "validation": validation,
        }

    @staticmethod
    def _load_builtin_models() -> List[Dict[str, Any]]:
        if not BUILTIN_MODEL_CATALOG_PATH.exists():
            return []
        try:
            data = json.loads(BUILTIN_MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
        models = data if isinstance(data, list) else []
        decision_metadata = ModelCatalog._load_decision_metadata()
        return [
            resolve_builtin_install_state(ModelCatalog._normalize_entry(
                ModelCatalog._merge_decision_metadata(item, decision_metadata)
            ))
            for item in models
            if isinstance(item, dict)
        ]

    @staticmethod
    def _load_decision_metadata() -> Dict[str, Any]:
        if not MODEL_DECISION_METADATA_PATH.exists():
            return {"families": {}, "models": {}}
        try:
            payload = json.loads(MODEL_DECISION_METADATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"families": {}, "models": {}}
        return payload if isinstance(payload, dict) else {"families": {}, "models": {}}

    @staticmethod
    def _merge_decision_metadata(entry: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(entry)
        model_meta = (metadata.get("models") or {}).get(str(entry.get("model_id") or ""), {})
        family_id = str(model_meta.get("model_family") or entry.get("model_family") or "")
        family_meta = (metadata.get("families") or {}).get(family_id, {})
        if family_id:
            merged["model_family"] = family_id
        decision_profile = {
            **(family_meta.get("decision_profile") or {}),
            **(model_meta.get("decision_profile") or {}),
        }
        if decision_profile:
            merged["decision_profile"] = decision_profile
        if isinstance(model_meta.get("benchmark"), dict):
            merged["benchmark"] = model_meta["benchmark"]
        license_name = model_meta.get("license") or family_meta.get("license")
        if license_name:
            merged["license"] = license_name
        return merged

    @staticmethod
    def _load_imported_models(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        layout = ProjectLayout.from_project(project)
        imports_dir = layout.project_dir / IMPORTED_MODELS_RELATIVE_DIR
        if not imports_dir.exists():
            return []
        entries = []
        for manifest_path in sorted(imports_dir.glob(f"*/{MODEL_MANIFEST_NAME}")):
            try:
                entries.append(ModelCatalog._entry_from_import_manifest(layout.project_dir, manifest_path))
            except Exception:
                continue
        for manifest_path in sorted((imports_dir / "staging").glob(f"*/{MODEL_MANIFEST_NAME}")):
            try:
                entries.append(ModelCatalog._entry_from_import_manifest(layout.project_dir, manifest_path))
            except Exception:
                continue
        return entries

    @staticmethod
    def _entry_from_import_manifest(project_dir: Path, manifest_path: Path) -> Dict[str, Any]:
        manifest = read_manifest(manifest_path)
        entry = ModelCatalog._normalize_entry(manifest)
        weight_file = manifest.get("weight_file") or manifest.get("weight")
        weight_path = manifest_path.parent / str(weight_file or manifest_path.name)
        entry["weight"] = weight_path.as_posix()
        entry["weight_path"] = weight_path.as_posix()
        entry["manifest_path"] = manifest_path.as_posix()
        entry["relative_path"] = weight_path.relative_to(project_dir).as_posix() if project_dir in weight_path.parents else weight_path.name
        if not weight_path.exists() and entry.get("status") != MODEL_STATUS_REGISTERED_DISABLED:
            entry["status"] = MODEL_STATUS_MISSING_FILE
            entry["trainable"] = False
            entry["inference_supported"] = False
        return entry

    @staticmethod
    def _load_project_trained_models(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries = []
        for model in ModelRegistry.list_deployable_models(project):
            weight_type = model.get("weight_type")
            if weight_type != "best":
                continue
            task_family = normalize_task_family(model.get("task_type") or project.get("task_type"))
            path = model.get("internal_weight_path")
            entries.append(ModelCatalog._normalize_entry({
                "model_id": f"trained.{model.get('run_id')}.{weight_type}",
                "display_name": f"{model.get('run_id')} / {weight_type}.pt",
                "architecture": model.get("architecture") or "cnn",
                "backend": model.get("backend") or "ultralytics_yolo",
                "task_family": task_family,
                "source": "project_trained",
                "format": "pt",
                "weight": path,
                "weight_path": path,
                "trainable": True,
                "inference_supported": True,
                "evaluation_supported": True,
                "imported": False,
                "status": model.get("status") or "available",
                "run_id": model.get("run_id"),
                "weight_type": weight_type,
                "created_at": model.get("created_at"),
                "file_size": model.get("file_size"),
            }))
        return entries

    @staticmethod
    def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(entry)
        normalized["task_family"] = normalize_task_family(normalized.get("task_family") or normalized.get("task_type"))
        normalized.setdefault("architecture", "cnn")
        normalized.setdefault("backend", "ultralytics_yolo")
        normalized.setdefault("source", "builtin")
        normalized.setdefault("format", "pt")
        normalized.setdefault("trainable", False)
        normalized.setdefault("inference_supported", False)
        normalized.setdefault("evaluation_supported", False)
        normalized.setdefault("imported", normalized.get("source") == "user_import")
        normalized.setdefault("status", "available")
        normalized["training_value"] = normalized.get("weight_path") or normalized.get("weight") or normalized.get("weight_file") or ""
        return normalized


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

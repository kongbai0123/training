from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.custom_model_package import CustomModelPackageValidator
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.security_utils import safe_filename


class ModelCatalog:
    """Project-scoped model catalog and import service.

    Import means "copy into project + register metadata". Custom packages are
    validation-only and never enter the training selector in this phase.
    """

    BUILTINS: List[Dict[str, Any]] = [
        {"model_id": "builtin::yolov8n-seg", "display_name": "YOLOv8n Segmentation (Recommended)", "training_value": "yolov8n-seg.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "segmentation", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::yolov8s-seg", "display_name": "YOLOv8s Segmentation", "training_value": "yolov8s-seg.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "segmentation", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::yolov8m-seg", "display_name": "YOLOv8m Segmentation", "training_value": "yolov8m-seg.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "segmentation", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::yolov8n", "display_name": "YOLOv8n Detection", "training_value": "yolov8n.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "detection", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::yolov8s", "display_name": "YOLOv8s Detection", "training_value": "yolov8s.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "detection", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::yolov8n-cls", "display_name": "YOLOv8n Classification", "training_value": "yolov8n-cls.pt", "source": "builtin", "backend": "ultralytics_yolo", "architecture": "cnn", "task_family": "classification", "format": "pt", "status": "ready", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::lstm", "display_name": "LSTM Sequence Model", "training_value": "lstm", "source": "builtin", "backend": "pytorch_lstm", "architecture": "rnn", "task_family": "sequence_classification", "format": "adapter", "status": "preview", "trainable": True, "inference_supported": False},
        {"model_id": "builtin::xgboost-sequence", "display_name": "XGBoost Sequence Baseline", "training_value": "xgboost", "source": "builtin", "backend": "sklearn_xgboost", "architecture": "rnn", "task_family": "sequence_classification", "format": "adapter", "status": "ready", "trainable": True, "inference_supported": False},
    ]

    @classmethod
    def list_all(cls, project: Dict[str, Any], architecture: Optional[str] = None) -> List[Dict[str, Any]]:
        models: List[Dict[str, Any]] = []
        models.extend(dict(item) for item in cls.BUILTINS)
        models.extend(cls._load_catalog(project))
        for trained in ModelRegistry.list_models(project):
            models.append(cls._project_trained_record(trained))
        if architecture:
            normalized = str(architecture).lower()
            models = [item for item in models if str(item.get("architecture") or "").lower() == normalized]
        return models

    @classmethod
    def list_trainable(cls, project: Dict[str, Any], task_family: Optional[str] = None, architecture: Optional[str] = None) -> List[Dict[str, Any]]:
        return [item for item in cls.list_all(project, architecture) if item.get("trainable") and cls._task_compatible(item, task_family)]

    @classmethod
    def list_inference_supported(cls, project: Dict[str, Any], task_family: Optional[str] = None, architecture: Optional[str] = None) -> List[Dict[str, Any]]:
        return [item for item in cls.list_all(project, architecture) if item.get("inference_supported") and cls._task_compatible(item, task_family)]

    @classmethod
    def import_yolo_pt(cls, project: Dict[str, Any], source_path: Path, display_name: str, task_family: str) -> Dict[str, Any]:
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".pt" or not source_path.exists() or source_path.stat().st_size <= 0:
            return cls._failed("Only non-empty .pt model weights are supported.")
        model_id, model_dir, dest = cls._copy_import(project, "yolo_pt", source_path)
        record = cls._base_record(project, model_id, display_name or source_path.stem, task_family, model_dir, dest)
        record.update({"format": "pt", "backend": "ultralytics_yolo", "architecture": "cnn", "status": "ready", "trainable": True, "inference_supported": False, "training_value": dest.resolve().as_posix()})
        cls._upsert_record(project, record)
        return {"success": True, "model": record, "validation": {"status": "passed", "checks": [{"name": "pt_file", "status": "passed", "passed": True}], "errors": [], "warnings": []}}

    @classmethod
    def import_yolo_yaml(cls, project: Dict[str, Any], source_path: Path, display_name: str, task_family: str) -> Dict[str, Any]:
        source_path = Path(source_path)
        if source_path.suffix.lower() not in {".yaml", ".yml"} or not source_path.exists():
            return cls._failed("Only YOLO model architecture .yaml / .yml files are supported.")
        text = source_path.read_text(encoding="utf-8", errors="ignore")
        if any(f"{key}:" in text for key in ("train", "val", "test")) and "backbone:" not in text and "head:" not in text:
            return cls._failed("This looks like a dataset YAML. Import a YOLO model architecture YAML instead.")
        model_id, model_dir, dest = cls._copy_import(project, "yolo_yaml", source_path)
        record = cls._base_record(project, model_id, display_name or source_path.stem, task_family, model_dir, dest)
        record.update({"format": "yaml", "backend": "ultralytics_yolo", "architecture": "cnn", "status": "ready", "trainable": True, "inference_supported": False, "training_value": dest.resolve().as_posix()})
        cls._upsert_record(project, record)
        return {"success": True, "model": record, "validation": {"status": "passed", "checks": [{"name": "model_yaml", "status": "passed", "passed": True}], "errors": [], "warnings": []}}

    @classmethod
    def import_onnx(cls, project: Dict[str, Any], source_path: Path, display_name: str, task_family: str) -> Dict[str, Any]:
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".onnx" or not source_path.exists() or source_path.stat().st_size <= 0:
            return cls._failed("Only non-empty .onnx files are supported.")
        model_id, model_dir, dest = cls._copy_import(project, "onnx", source_path)
        record = cls._base_record(project, model_id, display_name or source_path.stem, task_family, model_dir, dest)
        record.update({"format": "onnx", "backend": "onnx", "architecture": cls._architecture_for_task(task_family), "status": "registered_inference_only", "trainable": False, "inference_supported": False, "training_value": ""})
        cls._upsert_record(project, record)
        return {"success": True, "model": record, "validation": {"status": "inference_only", "checks": [{"name": "onnx_file", "status": "passed", "passed": True}], "errors": [], "warnings": ["ONNX imports are not trainable."]}}

    @classmethod
    def import_rnn_package(cls, project: Dict[str, Any], source_path: Path, display_name: str, task_family: str) -> Dict[str, Any]:
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".zip":
            return cls._failed("RNN model package must be a .zip file.")
        required = {"model.pt", "feature_schema.json", "normalization_stats.json", "sequence_config.json"}
        try:
            with zipfile.ZipFile(source_path, "r") as zf:
                names = {Path(name).name for name in zf.namelist() if not name.endswith("/")}
        except zipfile.BadZipFile:
            return cls._failed("Invalid ZIP file.")
        missing = sorted(required - names)
        validation = {"status": "preview" if not missing else "invalid_package", "checks": [{"name": "rnn_required_files", "status": "passed" if not missing else "failed", "passed": not missing, "detail": ", ".join(missing)}], "errors": ["Missing required files: " + ", ".join(missing)] if missing else [], "warnings": ["RNN package import is preview/inference metadata only in this phase."]}
        if missing:
            return {"success": False, "validation": validation}
        model_id, model_dir, dest = cls._copy_import(project, "rnn_package", source_path)
        record = cls._base_record(project, model_id, display_name or source_path.stem, task_family, model_dir, dest)
        record.update({"format": "rnn_package", "backend": "pytorch_lstm", "architecture": "rnn", "status": "preview", "trainable": False, "inference_supported": False, "training_value": ""})
        cls._upsert_record(project, record)
        return {"success": True, "model": record, "validation": validation}

    @classmethod
    def import_custom_package(cls, project: Dict[str, Any], source_path: Path, display_name: str, task_family: str) -> Dict[str, Any]:
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".zip":
            return cls._failed("Custom model package must be a .zip file.")
        validation = CustomModelPackageValidator.validate_zip(source_path)
        model_id, model_dir, dest = cls._copy_import(project, "custom_package", source_path)
        manifest_model = (validation.get("normalized_manifest") or {}).get("model") or {}
        record = cls._base_record(project, model_id, display_name or manifest_model.get("name") or source_path.stem, task_family or manifest_model.get("task_type") or "custom", model_dir, dest)
        record.update({
            "format": "custom_package",
            "backend": str(manifest_model.get("framework") or "custom"),
            "architecture": str(manifest_model.get("architecture") or cls._architecture_for_task(task_family)),
            "status": validation.get("status"),
            "trainable": False,
            "inference_supported": False,
            "training_value": "",
            "execution_enabled": False,
            "validation_status": validation.get("status"),
            "manifest_path": validation.get("manifest_path"),
        })
        cls._write_json(model_dir / "validation.json", validation)
        cls._write_json(model_dir / "manifest.normalized.json", validation.get("normalized_manifest") or {})
        gate = cls._permission_gate(record, validation)
        cls._write_json(model_dir / "sandbox_gate.json", gate)
        cls._append_audit(model_dir, "custom_package_imported", {"validation_status": validation.get("status"), "execution_enabled": False})
        cls._upsert_record(project, record)
        return {"success": True, "model": record, "validation": validation, "approval": {"status": "not_requested", "execution_enabled": False}, "dry_run": {"status": "not_started", "execution_enabled": False}}

    @classmethod
    def request_custom_package_dry_run(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        validation = cls._load_validation(project, record)
        gate = cls._permission_gate(record, validation)
        payload = {"status": "approval_required_execution_disabled", "approval_status": "pending", "permission_gate": gate, "blocked_reasons": cls._phase_gate_reasons(validation), "execution_enabled": False}
        cls._write_json(cls._record_dir(project, record) / "dry_run_request.json", payload)
        cls._append_audit(cls._record_dir(project, record), "dry_run_requested", payload)
        return {"success": True, "model": record, "dry_run": payload}

    @classmethod
    def record_custom_package_dry_run_approval(cls, project: Dict[str, Any], model_id: str, decision: str, approved_by: str = "local_user", note: str = "") -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        decision = str(decision or "").lower().strip()
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        payload = {"status": "recorded_execution_disabled", "decision": decision, "approved_by": approved_by, "note": note, "created_at": cls._now(), "execution_enabled": False, "blocked_reasons": cls._phase_gate_reasons(cls._load_validation(project, record))}
        cls._write_json(cls._record_dir(project, record) / "dry_run_approval.json", payload)
        cls._append_audit(cls._record_dir(project, record), "dry_run_approval_recorded", payload)
        return {"success": True, "model": record, "approval": payload}

    @classmethod
    def build_custom_package_sandbox_plan(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        validation = cls._load_validation(project, record)
        manifest = validation.get("normalized_manifest") or {}
        plan = {
            "status": "planned_execution_disabled",
            "model_id": model_id,
            "steps": [
                {"name": "prepare_isolated_workspace", "enabled": False},
                {"name": "install_allowlisted_dependencies", "enabled": False},
                {"name": "load_adapter_entrypoint", "enabled": False},
                {"name": "run_contract_probe", "enabled": False},
                {"name": "collect_metrics_and_artifacts", "enabled": False},
            ],
            "input_contract": manifest.get("input") or {},
            "output_contract": manifest.get("output") or {},
            "metrics_contract": manifest.get("metrics") or {},
            "blocked_reasons": cls._phase_gate_reasons(validation),
            "execution_enabled": False,
        }
        cls._write_json(cls._record_dir(project, record) / "sandbox_plan.json", plan)
        cls._append_audit(cls._record_dir(project, record), "sandbox_plan_built", plan)
        return {"success": True, "model": record, "plan": plan}

    @classmethod
    def run_custom_package_mock_dry_run(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        validation = cls._load_validation(project, record)
        manifest = validation.get("normalized_manifest") or {}
        metrics = {str(name): None for name in ((manifest.get("metrics") or {}).get("required") or [])}
        dry_run = {"status": "mock_completed_execution_disabled", "synthetic_input": manifest.get("input") or {}, "synthetic_output": manifest.get("output") or {}, "metrics": metrics, "artifacts": [], "execution_enabled": False, "blocked_reasons": cls._phase_gate_reasons(validation)}
        cls._write_json(cls._record_dir(project, record) / "mock_dry_run.json", dry_run)
        cls._append_audit(cls._record_dir(project, record), "mock_dry_run_completed", dry_run)
        return {"success": True, "model": record, "dry_run": dry_run}

    @classmethod
    def get_custom_package_sandbox_audit(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        audit_path = cls._record_dir(project, record) / "sandbox_audit.jsonl"
        events: List[Dict[str, Any]] = []
        if audit_path.exists():
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return {"success": True, "model": record, "audit": {"events": events, "execution_enabled": False}}

    @classmethod
    def evaluate_custom_package_enablement(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        validation = cls._load_validation(project, record)
        enablement = {"status": "disabled_by_phase_gate", "can_train": False, "can_infer": False, "can_execute_adapter": False, "catalog_visible": True, "training_selector_visible": False, "blocked_reasons": cls._phase_gate_reasons(validation)}
        cls._write_json(cls._record_dir(project, record) / "enablement.json", enablement)
        cls._append_audit(cls._record_dir(project, record), "enablement_evaluated", enablement)
        return {"success": True, "model": record, "enablement": enablement}

    @classmethod
    def build_custom_package_integration_contract(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        record = cls._require_custom_record(project, model_id)
        validation = cls._load_validation(project, record)
        manifest = validation.get("normalized_manifest") or {}
        integration = {"status": "contract_ready_execution_disabled" if validation.get("understood") else "contract_incomplete", "model": manifest.get("model") or {}, "entrypoints": manifest.get("entrypoints") or {}, "input": manifest.get("input") or {}, "output": manifest.get("output") or {}, "metrics": manifest.get("metrics") or {}, "artifact_contract": {"write_root": "project/training/runs/{run_id}", "required": ["metrics.json", "run_summary.json", "artifact_manifest.json"]}, "ui_contract": {"progress": "epoch_or_step", "logs": "jsonl", "training_selector_enabled": False}, "execution_enabled": False}
        cls._write_json(cls._record_dir(project, record) / "integration_contract.json", integration)
        cls._append_audit(cls._record_dir(project, record), "integration_contract_built", integration)
        return {"success": True, "model": record, "integration": integration}

    @staticmethod
    def _project_trained_record(model: Dict[str, Any]) -> Dict[str, Any]:
        task = str(model.get("task_type") or "").lower()
        return {
            "model_id": model.get("model_id"),
            "display_name": f"{model.get('run_id', '--')} / {model.get('weight_type', '--')}",
            "training_value": model.get("internal_weight_path"),
            "source": "project_trained",
            "backend": model.get("backend") or "ultralytics_yolo",
            "architecture": model.get("architecture") or "cnn",
            "task_family": "segmentation" if "seg" in task else "classification" if "class" in task else "detection",
            "format": "pt",
            "status": model.get("status") or "ready",
            "trainable": True,
            "inference_supported": True,
            **model,
        }

    @classmethod
    def _base_record(cls, project: Dict[str, Any], model_id: str, display_name: str, task_family: str, model_dir: Path, artifact_path: Path) -> Dict[str, Any]:
        rel_dir = model_dir.resolve().relative_to(ProjectLayout.from_project(project).project_dir.resolve()).as_posix()
        return {"model_id": model_id, "project_id": project.get("project_id"), "display_name": display_name.strip() or model_id, "task_family": task_family, "source": "user_import", "created_at": cls._now(), "updated_at": cls._now(), "storage_dir": rel_dir, "artifact_path": artifact_path.resolve().as_posix(), "artifact_name": artifact_path.name, "sha256": cls._sha256(artifact_path)}

    @classmethod
    def _copy_import(cls, project: Dict[str, Any], prefix: str, source_path: Path) -> tuple[str, Path, Path]:
        model_id = cls._new_model_id(prefix)
        model_dir = cls._imports_dir(project) / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        dest = model_dir / safe_filename(source_path.name)
        shutil.copy2(source_path, dest)
        return model_id, model_dir, dest

    @classmethod
    def _imports_dir(cls, project: Dict[str, Any]) -> Path:
        path = ProjectLayout.from_project(project).project_dir / "models" / "imports"
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    @classmethod
    def _catalog_path(cls, project: Dict[str, Any]) -> Path:
        return cls._imports_dir(project) / "catalog.json"

    @classmethod
    def _load_catalog(cls, project: Dict[str, Any]) -> List[Dict[str, Any]]:
        path = cls._catalog_path(project)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("models", []) if isinstance(data, dict) else []
            return [item for item in items if isinstance(item, dict)]
        except Exception:
            return []

    @classmethod
    def _save_catalog(cls, project: Dict[str, Any], models: List[Dict[str, Any]]) -> None:
        cls._write_json(cls._catalog_path(project), {"version": 1, "updated_at": cls._now(), "models": models})

    @classmethod
    def _upsert_record(cls, project: Dict[str, Any], record: Dict[str, Any]) -> None:
        models = [item for item in cls._load_catalog(project) if item.get("model_id") != record.get("model_id")]
        models.append(record)
        models.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        cls._save_catalog(project, models)

    @classmethod
    def _require_custom_record(cls, project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        for record in cls._load_catalog(project):
            if record.get("model_id") == model_id:
                if record.get("format") != "custom_package":
                    raise ValueError("Model is not a custom package")
                return record
        raise ValueError("Custom package model not found")

    @classmethod
    def _load_validation(cls, project: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
        path = cls._record_dir(project, record) / "validation.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _record_dir(cls, project: Dict[str, Any], record: Dict[str, Any]) -> Path:
        project_dir = ProjectLayout.from_project(project).project_dir.resolve()
        storage_dir = str(record.get("storage_dir") or "")
        resolved = (project_dir / storage_dir).resolve()
        imports_root = cls._imports_dir(project)
        if resolved != imports_root and imports_root not in resolved.parents:
            raise ValueError("Imported model storage path escapes project imports directory")
        return resolved

    @classmethod
    def _permission_gate(cls, record: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        manifest = validation.get("normalized_manifest") or {}
        security = manifest.get("security") or validation.get("security_policy") or {}
        entrypoints = manifest.get("entrypoints") or {}
        requested: List[Dict[str, Any]] = []
        if security.get("allow_network"):
            requested.append({"name": "network", "risk": "high", "allowed": False})
        if security.get("allow_shell"):
            requested.append({"name": "shell", "risk": "high", "allowed": False})
        write_policy = str(security.get("allow_write", "project_only"))
        if write_policy.lower() not in {"none", "false"}:
            requested.append({"name": f"write:{write_policy}", "risk": "low" if write_policy.lower() in {"project", "project_only", "artifacts_only"} else "high", "allowed": write_policy.lower() in {"project", "project_only", "artifacts_only"}})
        if not requested:
            requested.append({"name": "readonly_package_probe", "risk": "low", "allowed": False})
        return {"model_id": record.get("model_id"), "runtime_kind": (manifest.get("model") or {}).get("framework") or "custom", "entrypoint": entrypoints.get("trainer") or entrypoints.get("predictor") or "--", "requested_permissions": requested, "execution_enabled": False, "phase": "P1-A_validation_only"}

    @staticmethod
    def _phase_gate_reasons(validation: Dict[str, Any]) -> List[str]:
        return [
            "Phase P1-A only validates package contracts; adapter import and execution are disabled.",
            "A valid manifest does not make the package trainable until sandbox dry-run and metrics/artifact bridges exist.",
            *[str(item) for item in (validation.get("blocked_reasons") or [])],
        ]

    @staticmethod
    def _task_compatible(model: Dict[str, Any], task_family: Optional[str]) -> bool:
        if not task_family:
            return True
        wanted = str(task_family).lower()
        actual = str(model.get("task_family") or "").lower()
        if wanted == actual:
            return True
        if "seg" in wanted:
            return actual == "segmentation"
        if "detect" in wanted or wanted == "object_detection":
            return actual == "detection"
        if "class" in wanted and "sequence" not in wanted:
            return actual == "classification"
        if "sequence" in wanted:
            return actual.startswith("sequence") or str(model.get("architecture") or "").lower() == "rnn"
        return True

    @staticmethod
    def _architecture_for_task(task_family: str) -> str:
        return "rnn" if "sequence" in str(task_family or "").lower() else "cnn"

    @staticmethod
    def _failed(message: str) -> Dict[str, Any]:
        return {"success": False, "validation": {"status": "failed", "checks": [], "errors": [message], "warnings": []}}

    @staticmethod
    def _new_model_id(prefix: str) -> str:
        safe_prefix = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in prefix.lower()).strip("_") or "model"
        return f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def _append_audit(cls, model_dir: Path, event_type: str, payload: Dict[str, Any]) -> None:
        event = {"event_type": event_type, "created_at": cls._now(), "payload": payload}
        with (model_dir / "sandbox_audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

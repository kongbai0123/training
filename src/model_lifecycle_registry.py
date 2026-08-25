from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager


LIFECYCLE_STATUSES = ("pending_validation", "validated", "production", "retired")
ALLOWED_TRANSITIONS = {
    "pending_validation": {"validated", "retired"},
    "validated": {"production", "retired"},
    "production": {"retired"},
    "retired": set(),
}


class ModelLifecycleRegistry:
    @classmethod
    def list_versions(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        registry = cls._load(project)
        changed = str(registry.get("schema_version") or "") != "2.0"
        registry["schema_version"] = "2.0"
        models = [item for item in ModelRegistry.list_models(project) if item.get("weight_type") == "best"]
        existing = {str(item.get("model_id")): item for item in registry.get("versions") or []}
        next_version = max([int(item.get("version_number") or 0) for item in existing.values()] or [0]) + 1
        for model in sorted(models, key=lambda item: item.get("created_at") or ""):
            model_id = str(model.get("model_id") or "")
            if not model_id:
                continue
            if model_id in existing:
                record = existing[model_id]
                for key in (
                    "architecture",
                    "backend",
                    "task_type",
                    "model_name",
                    "model_format",
                    "model_path",
                    "sha256",
                    "file_size",
                    "primary_metric_name",
                    "primary_metric_value",
                    "dataset_lineage",
                    "training_parameters",
                    "evaluation",
                ):
                    source_key = "weight_path_display" if key == "model_path" else key
                    value = model.get(source_key)
                    if value is not None and record.get(key) != value:
                        record[key] = value
                        changed = True
                continue
            record = {
                "model_id": model_id,
                "version_number": next_version,
                "version": f"v{next_version}",
                "run_id": model.get("run_id"),
                "architecture": model.get("architecture"),
                "backend": model.get("backend"),
                "task_type": model.get("task_type"),
                "model_name": model.get("model_name"),
                "model_format": model.get("model_format"),
                "model_path": model.get("weight_path_display"),
                "sha256": model.get("sha256") or "",
                "file_size": model.get("file_size"),
                "primary_metric_name": model.get("primary_metric_name"),
                "primary_metric_value": model.get("primary_metric_value"),
                "dataset_lineage": model.get("dataset_lineage") or {},
                "training_parameters": model.get("training_parameters") or {},
                "evaluation": model.get("evaluation") or {},
                "status": "pending_validation",
                "previous_model_id": None,
                "created_at": model.get("created_at") or _now(),
                "updated_at": _now(),
                "limitations": [],
            }
            registry.setdefault("versions", []).append(record)
            registry.setdefault("events", []).append({
                "event": "registered",
                "model_id": model_id,
                "from": None,
                "to": "pending_validation",
                "at": _now(),
            })
            existing[model_id] = record
            next_version += 1
            changed = True
        if changed:
            cls._save(project, registry)
        versions = sorted(registry.get("versions") or [], key=lambda item: int(item.get("version_number") or 0), reverse=True)
        return {
            "schema_version": str(registry.get("schema_version") or "2.0"),
            "project_id": project.get("project_id"),
            "statuses": list(LIFECYCLE_STATUSES),
            "versions": versions,
            "events": list(reversed((registry.get("events") or [])[-100:])),
        }

    @classmethod
    def transition(
        cls,
        project_id: str,
        project: Dict[str, Any],
        model_id: str,
        target_status: str,
        *,
        limitations: List[str] | None = None,
    ) -> Dict[str, Any]:
        target_status = str(target_status or "").strip().lower()
        if target_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"Unsupported lifecycle status: {target_status or '--'}")
        cls.list_versions(project)
        registry = cls._load(project)
        record = next((item for item in registry.get("versions") or [] if item.get("model_id") == model_id), None)
        if not record:
            raise ValueError("Model version was not found.")
        current = str(record.get("status") or "pending_validation")
        if target_status == current:
            return {"changed": False, "model": record}
        if target_status not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Lifecycle transition {current} -> {target_status} is not allowed.")

        previous_production = None
        if target_status == "production":
            for candidate in registry.get("versions") or []:
                if candidate is record or candidate.get("status") != "production":
                    continue
                if candidate.get("task_type") != record.get("task_type"):
                    continue
                candidate["status"] = "retired"
                candidate["superseded_by"] = model_id
                candidate["updated_at"] = _now()
                previous_production = candidate.get("model_id")
                registry.setdefault("events", []).append({
                    "event": "superseded",
                    "model_id": candidate.get("model_id"),
                    "from": "production",
                    "to": "retired",
                    "at": _now(),
                    "superseded_by": model_id,
                })
            record["previous_model_id"] = previous_production

        record["status"] = target_status
        record["updated_at"] = _now()
        if limitations is not None:
            record["limitations"] = [str(item).strip() for item in limitations if str(item).strip()]
        registry.setdefault("events", []).append({
            "event": "status_changed",
            "model_id": model_id,
            "from": current,
            "to": target_status,
            "at": _now(),
        })
        if target_status == "production":
            project_snapshot = copy.deepcopy(project)
            project.setdefault("current", {})["best_model_id"] = model_id
            try:
                project_saved = ProjectManager.save_project(project_id, project)
            except Exception as exc:
                project.clear()
                project.update(project_snapshot)
                raise RuntimeError("Unable to update the project's production model.") from exc
            if not project_saved:
                project.clear()
                project.update(project_snapshot)
                raise RuntimeError("Unable to update the project's production model.")
            try:
                cls._save(project, registry)
            except Exception as exc:
                project.clear()
                project.update(project_snapshot)
                try:
                    project_rolled_back = ProjectManager.save_project(project_id, project)
                except Exception as rollback_exc:
                    raise RuntimeError(
                        "Unable to update the model lifecycle registry or roll back the project's production model."
                    ) from rollback_exc
                if not project_rolled_back:
                    raise RuntimeError(
                        "Unable to update the model lifecycle registry or roll back the project's production model."
                    ) from exc
                raise RuntimeError(
                    "Unable to update the model lifecycle registry; the project's production model was rolled back."
                ) from exc
        else:
            cls._save(project, registry)
        return {"changed": True, "model": record, "previous_production_model_id": previous_production}

    @staticmethod
    def _path(project: Dict[str, Any]) -> Path:
        return ProjectLayout.from_project(project).project_dir / "training" / "registry" / "model_versions.json"

    @classmethod
    def _load(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        path = cls._path(project)
        if not path.exists():
            return {"schema_version": "2.0", "versions": [], "events": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("versions"), list):
                payload.setdefault("events", [])
                return payload
        except Exception:
            pass
        raise ValueError("Model lifecycle registry is invalid.")

    @classmethod
    def _save(cls, project: Dict[str, Any], payload: Dict[str, Any]) -> None:
        path = cls._path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["schema_version"] = "2.0"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)


def _now() -> str:
    return datetime.now().isoformat()

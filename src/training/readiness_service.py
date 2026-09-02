"""Single training-readiness contract shared by UI and training start."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src.training.dispatcher import TrainerDispatcher


class TrainingReadinessService:
    @staticmethod
    def _blocker(error: str, index: int) -> Dict[str, Any]:
        message = str(error or "Training requirement is not satisfied.")
        lower = message.lower()
        if any(word in lower for word in ("dataset", "image", "csv", "sample", "sequence")):
            code, page = "DATASET_MISSING", "data"
        elif any(word in lower for word in ("annotation", "label")):
            code, page = "ANNOTATIONS_NOT_READY", "annotation"
        elif any(word in lower for word in ("split", "train/val", "validation")):
            code, page = "SPLIT_NOT_READY", "split"
        elif any(word in lower for word in ("model", "weight", "backend")):
            code, page = "MODEL_NOT_READY", "training"
        else:
            code, page = f"READINESS_BLOCKER_{index + 1}", "training"
        return {"code": code, "message": message, "field": None, "action_page": page}

    @classmethod
    def check(cls, project_id: str, project: Dict[str, Any], partial_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
        config = dict(project.get("training_config") or {})
        config.update({key: value for key, value in (partial_config or {}).items() if value is not None})
        backend = TrainerDispatcher.resolve_backend(project, config)
        errors = backend.validate_readiness(project, config)
        blockers = [cls._blocker(error, index) for index, error in enumerate(errors)]
        if blockers:
            phase = blockers[0]["action_page"]
            next_action = {"page": blockers[0]["action_page"], "label": blockers[0]["message"]}
        else:
            phase = "ready"
            next_action = {"page": "training", "label": "Start training"}
        return {
            "project_id": project_id,
            "project_revision": int(project.get("revision") or 0),
            "architecture": str(getattr(backend, "architecture", config.get("architecture") or "cnn")),
            "backend": str(getattr(backend, "backend_name", config.get("backend") or "")),
            "ready": not blockers,
            "phase": phase,
            "blockers": blockers,
            "warnings": [],
            "next_action": next_action,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

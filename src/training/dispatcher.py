from __future__ import annotations

from typing import Any, Dict, Optional

from src.training.backends import RNNBackend, XGBoostBackend, YOLOBackend
from src.training.base_backend import TrainingBackend
from src.training.state_store import TrainingStateStore


class TrainerDispatcher:
    DEFAULT_BACKEND = "ultralytics_yolo"
    _backends: Dict[str, TrainingBackend] = {
        DEFAULT_BACKEND: YOLOBackend(),
        "pytorch_lstm": RNNBackend(),
        "sklearn_xgboost": XGBoostBackend(),
    }

    @classmethod
    def resolve_backend(
        cls,
        project: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> TrainingBackend:
        project = project or {}
        config = config or (project.get("training_config") or {})
        backend_name = config.get("backend") or cls.DEFAULT_BACKEND
        backend = cls._backends.get(backend_name)
        if not backend:
            raise ValueError(f"Unsupported training backend: {backend_name}")
        return backend

    @classmethod
    def start_training(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        backend = cls.resolve_backend(project)
        result = backend.start_training(project)
        project_id = project.get("project_id")
        if project_id:
            raw_status = backend.get_status(project_id)
            TrainingStateStore.update_from_backend(
                project_id,
                raw_status,
                architecture=backend.architecture,
                backend=backend.backend_name,
            )
        return result

    @classmethod
    def stop_training(
        cls,
        project_id: str,
        project: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        backend = cls.resolve_backend(project or {})
        result = backend.stop_training(project_id)
        raw_status = backend.get_status(project_id)
        TrainingStateStore.update_from_backend(
            project_id,
            raw_status,
            architecture=backend.architecture,
            backend=backend.backend_name,
        )
        return result

    @classmethod
    def get_status(
        cls,
        project_id: str,
        project: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        backend = cls.resolve_backend(project or {})
        raw_status = backend.get_status(project_id)
        return TrainingStateStore.update_from_backend(
            project_id,
            raw_status,
            architecture=backend.architecture,
            backend=backend.backend_name,
        )

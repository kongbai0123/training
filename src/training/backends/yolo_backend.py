from __future__ import annotations

from typing import Any, Dict

from src.trainer import YOLOTrainer
from src.training.base_backend import TrainingBackend
from src.training.backends.yolo_training_service import YOLOTrainingService


class YOLOBackend(TrainingBackend):
    backend_name = "ultralytics_yolo"
    architecture = "cnn"

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> list[str]:
        return YOLOTrainingService.validate_readiness(project, config)

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        return YOLOTrainingService.prepare_dataset(project)

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        YOLOTrainer.start_training(project)
        return {
            "status": "started",
            "backend": self.backend_name,
            "architecture": self.architecture,
            "run_id": (project.get("training_config") or {}).get("run_id", ""),
        }

    def stop_training(self, project_id: str) -> Dict[str, Any]:
        YOLOTrainer.stop_training(project_id)
        return {
            "status": "stopping",
            "backend": self.backend_name,
            "architecture": self.architecture,
        }

    def get_status(self, project_id: str) -> Dict[str, Any]:
        status = dict(YOLOTrainer.get_status(project_id) or {})
        status.setdefault("backend", self.backend_name)
        status.setdefault("architecture", self.architecture)
        return status

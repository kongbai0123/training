from __future__ import annotations

from typing import Any, Dict

from src.trainer import YOLOTrainer
from src.training.base_backend import TrainingBackend
from src.training.backends.yolo_training_service import YOLOTrainingService


class RTDETRBackend(TrainingBackend):
    """RT-DETR adapter using the shared Ultralytics training lifecycle."""

    backend_name = "ultralytics_rtdetr"
    architecture = "cnn"

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> list[str]:
        blockers = YOLOTrainingService.validate_readiness(project, config)
        task = str(project.get("task_type") or "").lower()
        if "segment" in task:
            blockers.append("RT-DETR supports object detection projects only.")
        return blockers

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        return YOLOTrainingService.prepare_dataset(project)

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        config = project.setdefault("training_config", {})
        config["backend"] = self.backend_name
        YOLOTrainer.start_training(project)
        return {
            "status": "started",
            "backend": self.backend_name,
            "architecture": self.architecture,
            "run_id": config.get("run_id", ""),
        }

    def stop_training(self, project_id: str) -> Dict[str, Any]:
        YOLOTrainer.stop_training(project_id)
        return {"status": "stopping", "backend": self.backend_name, "architecture": self.architecture}

    def get_status(self, project_id: str) -> Dict[str, Any]:
        status = dict(YOLOTrainer.get_status(project_id) or {})
        status.setdefault("backend", self.backend_name)
        status.setdefault("architecture", self.architecture)
        return status

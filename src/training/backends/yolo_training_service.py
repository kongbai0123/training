from __future__ import annotations

from typing import Any, Dict, List

from src.trainer import YOLOTrainer
from src.training.readiness import validate_training_readiness


class YOLOTrainingService:
    @staticmethod
    def validate_readiness(project: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        return validate_training_readiness(project, config)

    @staticmethod
    def prepare_dataset(project: Dict[str, Any]) -> str:
        return YOLOTrainer.prepare_yolo_dataset(project)

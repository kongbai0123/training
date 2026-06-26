from __future__ import annotations

from typing import Any, Dict


class TrainingBackend:
    backend_name: str = ""
    architecture: str = ""

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        raise NotImplementedError

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def stop_training(self, project_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_status(self, project_id: str) -> Dict[str, Any]:
        raise NotImplementedError

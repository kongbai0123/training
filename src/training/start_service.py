from __future__ import annotations

from typing import Any, Dict

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.training.dispatcher import TrainerDispatcher
from src.training.run_manager import RunManager


class TrainingStartServiceError(RuntimeError):
    pass


class TrainingReadinessError(TrainingStartServiceError):
    pass


class TrainingRunAlreadyExists(TrainingStartServiceError):
    pass


class TrainingStartService:
    OPTIONAL_CONFIG_KEYS = (
        "sequence_length",
        "stride",
        "horizon",
        "task_head",
        "hidden_size",
        "num_layers",
        "dropout",
        "bidirectional",
        "gradient_clip_norm",
        "early_stopping_patience",
    )

    @classmethod
    def start(cls, project_id: str, project: Dict[str, Any], config: Any) -> Dict[str, Any]:
        config_dict = cls._config_to_dict(config)
        backend = TrainerDispatcher.resolve_backend(project, config_dict)
        readiness_errors = backend.validate_readiness(project, config_dict)
        if readiness_errors:
            raise TrainingReadinessError("Training readiness check failed:\n" + "\n".join(readiness_errors))

        run_id = str(config_dict.get("run_id") or "").strip() or RunManager.generate_run_id()
        layout = ProjectLayout.from_project(project)
        run_dir = layout.training_runs_dir() / run_id
        if run_dir.exists():
            raise TrainingRunAlreadyExists(f"Training run '{run_id}' already exists.")

        project["training_config"] = cls._build_training_config(config_dict, run_id)
        ProjectManager.save_project(project_id, project)

        TrainerDispatcher.start_training(project)
        return {"status": "started", "message": "Training started.", "run_id": run_id}

    @classmethod
    def _build_training_config(cls, config: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        training_config = {
            "model": config.get("model"),
            "epochs": config.get("epochs"),
            "batch_size": config.get("batch_size"),
            "imgsz": config.get("imgsz"),
            "lr0": config.get("lr0"),
            "lr0_mode": config.get("lr0_mode") or "auto",
            "device": config.get("device"),
            "patience": config.get("patience"),
            "workers": config.get("workers"),
            "workers_mode": config.get("workers_mode") or "auto",
            "cache": config.get("cache"),
            "amp": config.get("amp"),
            "seed": config.get("seed"),
            "save_period": config.get("save_period"),
            "close_mosaic": config.get("close_mosaic"),
            "optimizer": config.get("optimizer"),
            "run_id": run_id,
        }
        if config.get("backend"):
            training_config["backend"] = config["backend"]
        for key in cls.OPTIONAL_CONFIG_KEYS:
            value = config.get(key)
            if value is not None:
                training_config[key] = value
        return training_config

    @staticmethod
    def _config_to_dict(config: Any) -> Dict[str, Any]:
        if isinstance(config, dict):
            return dict(config)
        if hasattr(config, "dict"):
            return config.dict()
        return dict(getattr(config, "__dict__", {}))

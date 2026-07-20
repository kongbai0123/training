from __future__ import annotations

from pathlib import Path
import os
from typing import Any, Dict, List

from src.training.backends.torchvision_backend import TorchVisionBackend
from src.training.vision.dfine_trainer import train_dfine_model


class DFineBackend(TorchVisionBackend):
    backend_name = "transformers_dfine"

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        errors = super().validate_readiness(project, {**config, "model": "unet"})
        model_path = Path(str(config.get("model") or ""))
        if not model_path.is_absolute():
            from src.app_paths import MODELS_DIR

            model_path = Path(MODELS_DIR) / model_path.name
        if not (model_path / "config.json").exists():
            errors.append("Install D-FINE Small before training.")
        try:
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("USE_FLAX", "0")
            import transformers  # noqa: F401
        except Exception:
            errors.append("The D-FINE Transformers component is not installed in this application build.")
        return errors

    def train_model(self, project: Dict[str, Any], run_dir: Path, config: Dict[str, Any], **callbacks) -> Dict[str, Any]:
        return train_dfine_model(project, run_dir, config, **callbacks)

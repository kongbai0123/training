from __future__ import annotations

from pathlib import Path

from src.app_paths import MODELS_DIR


class ModelStore:
    """Central model-weight storage under the app-scoped ./models directory."""

    WEIGHT_SUFFIXES = {".pt"}

    @staticmethod
    def models_dir() -> Path:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        return MODELS_DIR.resolve()

    @classmethod
    def resolve_training_model(cls, model_value: str) -> str:
        """Resolve user-supplied training weights.

        Built-in Ultralytics model names are allowed. Any local/custom .pt file
        must live under ./models.
        """
        model_value = str(model_value or "").strip()
        if not model_value:
            return model_value

        model_path = Path(model_value).expanduser()
        root = cls.models_dir()

        if model_path.is_absolute():
            resolved = model_path.resolve()
            if not cls._is_inside_models(resolved):
                raise ValueError("Custom weight files must be placed under the app models directory.")
            if not resolved.exists() or not resolved.is_file():
                raise ValueError(f"Custom weight file not found: {resolved}")
            return resolved.as_posix()

        if model_path.parent != Path("."):
            candidate = (root / model_path).resolve()
            if not cls._is_inside_models(candidate):
                raise ValueError("Custom weight files must stay inside the app models directory.")
            if not candidate.exists() or not candidate.is_file():
                raise ValueError(f"Custom weight file not found under models: {model_value}")
            return candidate.as_posix()

        candidate = (root / model_value).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate.as_posix()

        local_candidate = Path(model_value).resolve()
        if local_candidate.exists() and local_candidate.is_file() and local_candidate.suffix.lower() == ".pt":
            raise ValueError("Local .pt weights outside ./models are not allowed. Move the file into ./models first.")

        return model_value

    @classmethod
    def validate_model_store_path(cls, weight_path: Path) -> Path:
        resolved = weight_path.resolve()
        if resolved.suffix.lower() not in cls.WEIGHT_SUFFIXES:
            raise ValueError("Only .pt weights are allowed")
        if not resolved.exists() or not resolved.is_file():
            raise ValueError("Weight file does not exist")
        if not cls._is_inside_models(resolved):
            raise ValueError("Weight path must stay inside MODELS_DIR")
        return resolved

    @classmethod
    def _is_inside_models(cls, path: Path) -> bool:
        root = cls.models_dir()
        return path == root or root in path.parents

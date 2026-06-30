from __future__ import annotations

from pathlib import Path

from src.app_paths import MODELS_DIR, PROJECTS_DIR


class ModelStore:
    """Central model-weight storage under the app-scoped ./models directory."""

    WEIGHT_SUFFIXES = {".pt"}
    PROJECT_IMPORT_SUFFIXES = {".pt", ".yaml", ".yml"}

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
            suffix = resolved.suffix.lower()
            if not cls._is_inside_models(resolved) and not cls._is_inside_project_imports(resolved):
                raise ValueError("Custom weight files must be placed under the app models directory or the project models/imports directory.")
            if cls._is_inside_project_imports(resolved) and suffix not in cls.PROJECT_IMPORT_SUFFIXES:
                raise ValueError("Project imported training models must be .pt, .yaml, or .yml files.")
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
        if local_candidate.exists() and local_candidate.is_file() and local_candidate.suffix.lower() in cls.PROJECT_IMPORT_SUFFIXES:
            if cls._is_inside_project_imports(local_candidate):
                return local_candidate.as_posix()
            raise ValueError("Local training models outside ./models or project models/imports are not allowed. Import the model into the project first.")

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

    @classmethod
    def _is_inside_project_imports(cls, path: Path) -> bool:
        projects_root = PROJECTS_DIR.resolve()
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(projects_root)
        except ValueError:
            return False
        parts = relative.parts
        return len(parts) >= 5 and parts[1] == "models" and parts[2] == "imports"

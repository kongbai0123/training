import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PROJECTS_DIR


class ModelRegistry:
    """Scan trained YOLO weights for a project without loading model files."""

    WEIGHT_TYPES = ("best", "last")

    @staticmethod
    def list_models(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        project_id = project.get("project_id", "")
        project_dir = ModelRegistry._project_dir(project)
        runs_dir = project_dir / "training" / "runs"
        if not runs_dir.exists():
            return []

        models: List[Dict[str, Any]] = []
        for weight_path in sorted(runs_dir.glob("*/weights/*.pt")):
            if weight_path.stem not in ModelRegistry.WEIGHT_TYPES:
                continue
            try:
                internal_path = ModelRegistry._validate_weight_path(weight_path)
            except ValueError:
                continue

            run_dir = weight_path.parent.parent
            run_id = run_dir.name
            metrics = ModelRegistry._read_run_metrics(run_dir)
            training_config = ModelRegistry._read_training_config(project, run_dir)
            stat = weight_path.stat()
            weight_type = weight_path.stem
            task_type = ModelRegistry._infer_task_type(project, training_config, weight_path)

            models.append({
                "model_id": ModelRegistry._model_id(project_id, run_id, weight_type),
                "project_id": project_id,
                "run_id": run_id,
                "weight_type": weight_type,
                "weight_path_display": ModelRegistry._display_path(weight_path),
                "internal_weight_path": internal_path.as_posix(),
                "model_name": training_config.get("model") or metrics.get("model") or "--",
                "task_type": task_type,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_size": stat.st_size,
                "best_map50_m": metrics.get("best_map50_m"),
                "best_map50_95_m": metrics.get("best_map50_95_m"),
                "status": "ready",
                "source": "project_training_runs"
            })

        models.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return models

    @staticmethod
    def resolve_model(project: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        for model in ModelRegistry.list_models(project):
            if model.get("model_id") == model_id:
                weight_path = ModelRegistry._validate_weight_path(Path(model["internal_weight_path"]))
                model["internal_weight_path"] = weight_path.as_posix()
                return model
        raise ValueError("Model not found in registry")

    @staticmethod
    def ensure_inference_dirs(project: Dict[str, Any]) -> Dict[str, Path]:
        base = ModelRegistry._project_dir(project) / "inference"
        paths = {
            "inputs_images": base / "inputs" / "images",
            "outputs_images": base / "outputs" / "images",
            "jobs": base / "jobs",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _project_dir(project: Dict[str, Any]) -> Path:
        dataset_path = Path(project["dataset_path"]).resolve()
        return dataset_path.parent

    @staticmethod
    def _model_id(project_id: str, run_id: str, weight_type: str) -> str:
        return f"{project_id}::{run_id}::{weight_type}"

    @staticmethod
    def _validate_weight_path(weight_path: Path) -> Path:
        resolved = weight_path.resolve()
        projects_root = PROJECTS_DIR.resolve()
        if resolved.suffix.lower() != ".pt":
            raise ValueError("Only .pt weights are allowed")
        if not resolved.exists() or not resolved.is_file():
            raise ValueError("Weight file does not exist")
        if projects_root not in resolved.parents:
            raise ValueError("Weight path must stay inside PROJECTS_DIR")
        if ".." in resolved.as_posix().split("/"):
            raise ValueError("Invalid path traversal")
        return resolved

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(PROJECTS_DIR.resolve()).as_posix()
        except ValueError:
            return path.name

    @staticmethod
    def _read_training_config(project: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
        candidates = [
            run_dir / "config.json",
            run_dir / "args.json",
            run_dir / "training_config.json",
        ]
        for path in candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return project.get("training_config", {}) or {}

    @staticmethod
    def _read_run_metrics(run_dir: Path) -> Dict[str, Optional[float]]:
        metrics: Dict[str, Optional[float]] = {
            "best_map50_m": None,
            "best_map50_95_m": None,
        }

        metrics_json = run_dir / "metrics.json"
        if metrics_json.exists():
            try:
                data = json.loads(metrics_json.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    metrics["best_map50_m"] = ModelRegistry._first_number(data, [
                        "best_map50_m", "map50_m", "metrics/mAP50(M)", "metrics/mAP50(B)", "map50"
                    ])
                    metrics["best_map50_95_m"] = ModelRegistry._first_number(data, [
                        "best_map50_95_m", "map50_95_m", "metrics/mAP50-95(M)", "metrics/mAP50-95(B)", "map"
                    ])
            except Exception:
                pass

        results_csv = run_dir / "results.csv"
        if results_csv.exists():
            try:
                with results_csv.open("r", encoding="utf-8", newline="") as f:
                    rows = list(csv.DictReader(f))
                if rows:
                    metrics["best_map50_m"] = metrics["best_map50_m"] or ModelRegistry._max_column(rows, [
                        "metrics/mAP50(M)", "metrics/mAP50(B)"
                    ])
                    metrics["best_map50_95_m"] = metrics["best_map50_95_m"] or ModelRegistry._max_column(rows, [
                        "metrics/mAP50-95(M)", "metrics/mAP50-95(B)"
                    ])
            except Exception:
                pass

        return metrics

    @staticmethod
    def _first_number(data: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("best") or value.get("value")
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _max_column(rows: List[Dict[str, str]], keys: List[str]) -> Optional[float]:
        values = []
        for row in rows:
            normalized = {key.strip(): value for key, value in row.items()}
            for key in keys:
                try:
                    raw = normalized.get(key)
                    if raw not in (None, ""):
                        values.append(float(raw))
                except (TypeError, ValueError):
                    pass
        return max(values) if values else None

    @staticmethod
    def _infer_task_type(project: Dict[str, Any], training_config: Dict[str, Any], weight_path: Path) -> str:
        model_name = str(training_config.get("model") or weight_path.name).lower()
        project_task = str(project.get("task_type") or "").lower()
        if "seg" in model_name or "segmentation" in project_task:
            return "segmentation"
        if "class" in project_task:
            return "classification"
        return "detection"

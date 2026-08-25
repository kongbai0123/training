import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PROJECTS_DIR
from src.project_layout import ProjectLayout
from src.run_filters import is_test_run


class ModelRegistry:
    """Scan first-party training artifacts without loading executable model content."""

    WEIGHT_TYPES = ("best", "last")
    TRAINING_PARAMETER_KEYS = (
        "model",
        "epochs",
        "learning_rate",
        "lr0",
        "max_depth",
        "subsample",
        "colsample_bytree",
        "seed",
        "workers",
        "task_head",
        "train_ratio",
        "val_ratio",
        "test_ratio",
        "missing_strategy",
        "feature_columns",
        "target_column",
        "feature_config_hash",
    )

    @staticmethod
    def list_models(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        project_id = project.get("project_id", "")
        project_dir = ModelRegistry._project_dir(project)
        runs_dir = project_dir / "training" / "runs"
        if not runs_dir.exists():
            return []

        completed_runs = ModelRegistry._completed_project_runs(project)
        restrict_to_project_runs = bool(project.get("training_runs"))
        models: List[Dict[str, Any]] = []
        candidates = list(runs_dir.glob("*/weights/*.pt")) + list(runs_dir.glob("*/weights/*.json"))
        for weight_path in sorted(candidates):
            if weight_path.stem not in ModelRegistry.WEIGHT_TYPES or weight_path.suffix.lower() not in {".pt", ".json"}:
                continue
            try:
                internal_path = ModelRegistry._validate_weight_path(weight_path)
            except ValueError:
                continue

            run_dir = weight_path.parent.parent
            run_id = run_dir.name
            if restrict_to_project_runs and run_id not in completed_runs:
                continue
            run_record = completed_runs.get(run_id, {})
            if is_test_run(run_id, run_record):
                continue
            metrics = ModelRegistry._read_run_metrics(run_dir)
            training_config = ModelRegistry._read_training_config(project, run_dir)
            backend_contract = ModelRegistry._read_backend_contract(run_dir)
            run_summary = ModelRegistry._read_json_file(run_dir / "run_summary.json")
            artifact_status = str(
                run_summary.get("status") or backend_contract.get("status") or ""
            ).lower()
            if artifact_status and artifact_status != "completed":
                continue
            artifact_manifest = ModelRegistry._read_json_file(run_dir / "artifact_manifest.json")
            artifact_meta = ModelRegistry._read_artifact_metadata(run_dir, weight_path)
            stat = weight_path.stat()
            weight_type = weight_path.stem
            task_type = ModelRegistry._infer_task_type(project, training_config, weight_path, run_dir)

            model_record = {
                "model_id": ModelRegistry._model_id(project_id, run_id, weight_type),
                "project_id": project_id,
                "run_id": run_id,
                "weight_type": weight_type,
                "model_format": weight_path.suffix.lower().lstrip("."),
                "weight_path_display": ModelRegistry._display_path(weight_path),
                "internal_weight_path": internal_path.as_posix(),
                "model_name": run_record.get("model") or training_config.get("model") or metrics.get("model") or "--",
                "task_type": task_type,
                "created_at": run_record.get("completed_at") or run_record.get("created_at") or datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_size": stat.st_size,
                "best_map50_m": metrics.get("best_map50_m"),
                "best_map50_95_m": metrics.get("best_map50_95_m"),
                "primary_metric_name": run_summary.get("primary_metric_name"),
                "primary_metric_value": run_summary.get("primary_metric_value"),
                "lifecycle_status": run_summary.get("model_lifecycle_status") or "pending_validation",
                "training_parameters": {
                    key: training_config[key]
                    for key in ModelRegistry.TRAINING_PARAMETER_KEYS
                    if key in training_config
                },
                "evaluation": {
                    "primary_metric_name": run_summary.get("primary_metric_name"),
                    "primary_metric_value": run_summary.get("primary_metric_value"),
                    "best_epoch": run_summary.get("best_epoch"),
                    "best_metrics": run_summary.get("best_metrics")
                    if isinstance(run_summary.get("best_metrics"), dict)
                    else {},
                },
                "status": "ready",
                "source": "project_training_runs"
            }
            lineage = artifact_manifest.get("lineage") if isinstance(artifact_manifest, dict) else {}
            if isinstance(lineage, dict):
                if isinstance(lineage.get("dataset"), dict):
                    model_record["dataset_lineage"] = dict(lineage["dataset"])
                if isinstance(lineage.get("model"), dict):
                    model_record["model_lineage"] = dict(lineage["model"])
            if backend_contract:
                if backend_contract.get("architecture"):
                    model_record["architecture"] = backend_contract["architecture"]
                if backend_contract.get("backend"):
                    model_record["backend"] = backend_contract["backend"]
            if artifact_meta:
                if artifact_meta.get("role"):
                    model_record["artifact_role"] = artifact_meta["role"]
                if artifact_meta.get("sha256"):
                    model_record["sha256"] = artifact_meta["sha256"]
                model_record["artifact_source"] = "artifact_manifest"
            models.append(model_record)

        models.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return models

    @staticmethod
    def list_deployable_models(project: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the small model set intended for user-facing selectors.

        Historical checkpoints are still available through ``list_models`` for
        cleanup and audit workflows. Runtime selectors should default to the
        current best model, or the newest best checkpoint when current metadata
        is missing.
        """
        models = ModelRegistry.list_models(project)
        best_models = [
            model for model in models
            if str(model.get("weight_type") or "").lower() == "best"
        ]
        if not best_models:
            return []

        current = project.get("current") if isinstance(project.get("current"), dict) else {}
        current_best_id = str(current.get("best_model_id") or "").strip()
        if current_best_id:
            matched = [
                model for model in best_models
                if model.get("model_id") == current_best_id
                or f"::{model.get('run_id')}::best" in current_best_id
                or current_best_id.endswith(f"::{model.get('run_id')}::best")
            ]
            if matched:
                return matched[:1]

        return best_models[:1]

    @staticmethod
    def _completed_project_runs(project: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        completed: Dict[str, Dict[str, Any]] = {}
        for run in project.get("training_runs") or []:
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("run_id") or "").strip()
            if not run_id:
                continue
            if str(run.get("status") or "").lower() != "completed":
                continue
            completed[run_id] = run
        return completed

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
        layout = ProjectLayout.from_project(project)
        base = layout.project_dir / "inference"
        paths = {
            "inputs_images": base / "inputs" / "images",
            "outputs_images": base / "outputs" / "images",
            "jobs": layout.inference_jobs_dir(),
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _project_dir(project: Dict[str, Any]) -> Path:
        return ProjectLayout.from_project(project).project_dir

    @staticmethod
    def _model_id(project_id: str, run_id: str, weight_type: str) -> str:
        return f"{project_id}::{run_id}::{weight_type}"

    @staticmethod
    def _validate_weight_path(weight_path: Path) -> Path:
        resolved = weight_path.resolve()
        projects_root = PROJECTS_DIR.resolve()
        if resolved.suffix.lower() not in {".pt", ".json"} or resolved.name not in {"best.pt", "last.pt", "best.json", "last.json"}:
            raise ValueError("Only first-party best/last .pt or .json model artifacts are allowed")
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
            run_dir / "train_config.json",
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
    def _read_backend_contract(run_dir: Path) -> Dict[str, Any]:
        path = run_dir / "backend.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _read_json_file(path: Path) -> Dict[str, Any]:
        if not path.exists() or not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _read_artifact_metadata(run_dir: Path, weight_path: Path) -> Dict[str, Any]:
        path = run_dir / "artifact_manifest.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            artifacts = data.get("artifacts", []) if isinstance(data, dict) else []
            weight_rel = weight_path.resolve().relative_to(run_dir.resolve()).as_posix()
            for artifact in artifacts:
                if isinstance(artifact, dict) and artifact.get("path") == weight_rel:
                    return artifact
        except Exception:
            return {}
        return {}

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
    def _infer_task_type(project: Dict[str, Any], training_config: Dict[str, Any], weight_path: Path, run_dir: Path) -> str:
        # 1. 優先讀取 run_summary.json 中的 task_type 欄位
        summary_file = run_dir / "run_summary.json"
        if summary_file.exists():
            try:
                summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
                if isinstance(summary_data, dict) and summary_data.get("task_type"):
                    return str(summary_data["task_type"])
            except Exception:
                pass

        # 2. 讀取 training_config 中的 task_type 欄位
        if training_config.get("task_type"):
            return str(training_config["task_type"])

        # 3. 讀取 model name 或權重檔名判定
        model_name = str(training_config.get("model") or weight_path.name).lower()
        
        if "-seg" in model_name or model_name.endswith("seg.pt") or "yolov8n-seg" in model_name:
            return "segmentation"
        if "-cls" in model_name or "cls" in model_name:
            return "classification"
        if "-pose" in model_name or "pose" in model_name:
            return "pose"
        if "-obb" in model_name or "obb" in model_name:
            return "obb"
        if weight_path.suffix.lower() == ".json":
            backend = ModelRegistry._read_backend_contract(run_dir)
            if str(backend.get("architecture") or "").lower() == "tabular":
                return "tabular_regression" if "regression" in str(backend.get("task_type") or "").lower() else "tabular_classification"
            return str(backend.get("task_type") or "sequence_classification")
        if model_name.endswith(".pt") or "yolo" in model_name:
            return "detection"

        return "unknown"

from __future__ import annotations

import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.tabular_config import active_tabular_config, get_tabular_workspace, resolve_tabular_source
from src.training.artifact_manifest import write_artifact_manifest
from src.training.base_backend import TrainingBackend
from src.training.contracts import build_backend_contract
from src.training.metric_schema import build_tabular_metric_schema
from src.training.rnn.xgboost_trainer import train_xgboost_from_dataset
from src.training.runners.thread_runner import DEFAULT_THREAD_TRAINING_RUNNER
from src.training.state_store import TrainingStateStore


class TabularXGBoostBackend(TrainingBackend):
    backend_name = "xgboost_tabular"
    architecture = "tabular"
    _stop_flags: Dict[str, bool] = {}
    _lock = threading.RLock()

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not str(project.get("task_type") or "").lower().startswith("tabular_"):
            errors.append("Tabular XGBoost requires a tabular classification or regression project.")
        try:
            import xgboost  # noqa: F401
        except Exception:
            errors.append("Tabular XGBoost requires the bundled xgboost runtime.")
        try:
            workspace = get_tabular_workspace(project)
            if not workspace.get("ready"):
                errors.extend((workspace.get("validation") or {}).get("errors") or ["Tabular dataset is not ready."])
            persisted_head = str((workspace.get("config") or {}).get("task_head") or "classification").lower()
            requested_head = str(config.get("task_head") or persisted_head).lower()
            if requested_head != persisted_head:
                errors.append("Training task_head must match the saved Tabular data contract.")
        except ValueError as exc:
            errors.append(str(exc))
        errors.extend(_validate_training_parameters(config))
        return list(dict.fromkeys(errors))

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        source = resolve_tabular_source(project)
        if not source:
            raise ValueError("Import a Tabular CSV dataset before training.")
        return source.as_posix()

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(project.get("project_id") or "")
        config = project.get("training_config") or {}
        run_id = str(config.get("run_id") or f"run_tabular_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        if DEFAULT_THREAD_TRAINING_RUNNER.is_running(project_id):
            return {"status": "already_running", "backend": self.backend_name, "architecture": self.architecture, "run_id": run_id}
        if TrainingStateStore.is_training(project_id):
            TrainingStateStore.mark_failed(project_id, "Previous Tabular training did not report a final state.")
        with self._lock:
            self._stop_flags[project_id] = False
        TrainingStateStore.init_run(project_id, run_id, _int(config.get("epochs"), 100), self.architecture, self.backend_name)
        TrainingStateStore.set_field(project_id, "task_type", _task_type(config, project))
        try:
            result = DEFAULT_THREAD_TRAINING_RUNNER.start(
                project_id=project_id,
                run_id=run_id,
                target=self._run_training,
                args=(project,),
                daemon=False,
            )
        except Exception as exc:
            TrainingStateStore.mark_failed(project_id, str(exc), run_id=run_id)
            raise
        if not result.get("started"):
            TrainingStateStore.mark_failed(project_id, "Another training job is already running.", run_id=run_id)
            return {"status": "already_running", "backend": self.backend_name, "architecture": self.architecture, "run_id": result.get("run_id", run_id)}
        return {"status": "started", "backend": self.backend_name, "architecture": self.architecture, "run_id": run_id}

    def stop_training(self, project_id: str) -> Dict[str, Any]:
        with self._lock:
            self._stop_flags[project_id] = True
        TrainingStateStore.mark_stopping(project_id)
        return {"status": "stopping", "backend": self.backend_name, "architecture": self.architecture}

    def get_status(self, project_id: str) -> Dict[str, Any]:
        state = TrainingStateStore.get_state(project_id)
        state.setdefault("backend", self.backend_name)
        state.setdefault("architecture", self.architecture)
        state.setdefault("hardware", {"device": "cpu"})
        return state

    def _run_training(self, project: Dict[str, Any]) -> None:
        from src.training.tabular.dataset import load_csv_tabular_dataset, write_preprocess_artifacts

        project_id = str(project.get("project_id") or "")
        config = project.get("training_config") or {}
        tabular_config = active_tabular_config(project)
        run_id = str(config.get("run_id") or f"run_tabular_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        layout = ProjectLayout.from_project(project)
        run_dir = layout.training_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now().isoformat()
        task_type = _task_type(config, project)
        summary: Dict[str, Any] = {"run_id": run_id, "status": "failed"}
        dataset: Dict[str, Any] | None = None
        try:
            source = resolve_tabular_source(project, tabular_config)
            if not source:
                raise ValueError("Tabular source CSV is missing.")
            effective_config = {**config, **tabular_config, "backend": self.backend_name, "architecture": self.architecture}
            (run_dir / "train_config.json").write_text(json.dumps(effective_config, indent=2, ensure_ascii=False), encoding="utf-8")
            dataset = load_csv_tabular_dataset(
                source,
                target_column=tabular_config["target_column"],
                feature_columns=tabular_config.get("feature_columns") or None,
                split_column=tabular_config.get("split_column") or None,
                task_head=tabular_config.get("task_head") or "classification",
                seed=_int(tabular_config.get("seed"), 42),
                train_ratio=_float(tabular_config.get("train_ratio"), 0.70),
                val_ratio=_float(tabular_config.get("val_ratio"), 0.15),
                test_ratio=_float(tabular_config.get("test_ratio"), 0.15),
            )
            (run_dir / "dataset_snapshot.json").write_text(json.dumps(dataset["summary"], indent=2, ensure_ascii=False), encoding="utf-8")
            write_preprocess_artifacts(run_dir, dataset)
            metrics = train_xgboost_from_dataset(
                dataset,
                run_dir,
                effective_config,
                stop_requested=lambda: self._is_stop_requested(project_id),
                progress_callback=lambda row: TrainingStateStore.append_epoch_metrics(project_id, row, run_id=run_id),
                architecture=self.architecture,
                task_prefix="tabular",
                backend_name=self.backend_name,
            )
            status = "stopped" if self._is_stop_requested(project_id) else "completed"
            summary = self._write_summary(run_dir, task_type, status, metrics, dataset.get("feature_config_hash"))
            if status == "stopped":
                TrainingStateStore.mark_stopped(project_id, "Training stopped by user.", run_id=run_id)
            else:
                TrainingStateStore.mark_completed(project_id, best_model="weights/best.json", run_id=run_id)
        except Exception as exc:
            error = str(exc)
            (run_dir / "error.log").write_text(error, encoding="utf-8")
            summary = self._write_summary(run_dir, task_type, "failed", None, tabular_config.get("feature_config_hash"), error)
            TrainingStateStore.mark_failed(project_id, error, run_id=run_id)
        finally:
            self._write_contracts(run_dir, run_id, task_type, summary.get("status", "failed"), created_at)
            write_artifact_manifest(
                run_dir,
                run_id,
                dataset_lineage={
                    "source_file": tabular_config.get("source_file"),
                    "dataset_sha256": (dataset or {}).get("dataset_hash"),
                    "feature_config_hash": (dataset or {}).get("feature_config_hash") or tabular_config.get("feature_config_hash"),
                    "row_count": ((dataset or {}).get("summary") or {}).get("row_count"),
                },
                model_lineage={
                    "model_id": f"{project_id}::{run_id}::best" if summary.get("status") == "completed" else None,
                    "parent_model_id": None,
                },
            )
            self._update_project_run(project, summary)
            with self._lock:
                self._stop_flags.pop(project_id, None)

    def _write_summary(self, run_dir: Path, task_type: str, status: str, metrics: Dict[str, Any] | None, feature_hash: str | None, error: str = "") -> Dict[str, Any]:
        best = (metrics or {}).get("best_metrics") or {}
        primary = "val/mae" if "regression" in task_type else "val/macro_f1"
        summary = {
            "run_id": run_dir.name,
            "status": status,
            "task_type": task_type,
            "architecture": self.architecture,
            "backend": self.backend_name,
            "model": "xgboost_regressor" if "regression" in task_type else "xgboost_classifier",
            "epochs": int((metrics or {}).get("best_epoch") or 0),
            "best_epoch": int((metrics or {}).get("best_epoch") or 0),
            "best_metrics": best,
            "primary_metric_key": primary,
            "primary_metric_name": "MAE" if primary == "val/mae" else "Macro-F1",
            "primary_metric_value": best.get(primary),
            "feature_config_hash": feature_hash or "",
            "error": error,
            "completed_at": datetime.now().isoformat(),
            "model_lifecycle_status": "pending_validation" if status == "completed" else "training_failed",
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    def _write_contracts(self, run_dir: Path, run_id: str, task_type: str, status: str, created_at: str) -> None:
        contract = build_backend_contract(run_id, self.architecture, self.backend_name, task_type, status, created_at, datetime.now().isoformat())
        (run_dir / "backend.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "metric_schema.json").write_text(json.dumps(build_tabular_metric_schema(task_type), indent=2, ensure_ascii=False), encoding="utf-8")

    def _update_project_run(self, project: Dict[str, Any], summary: Dict[str, Any]) -> None:
        project_id = str(project.get("project_id") or "")
        if not project_id:
            return
        runs = [item for item in project.get("training_runs") or [] if item.get("run_id") != summary.get("run_id")]
        runs.append(summary)
        project["training_runs"] = runs
        current = project.setdefault("current", {})
        current["training_run_id"] = summary.get("run_id")
        if summary.get("status") == "completed":
            current["best_model_id"] = f"{project_id}::{summary.get('run_id')}::best"
        ProjectManager.save_project(project_id, project)

    def _is_stop_requested(self, project_id: str) -> bool:
        with self._lock:
            return bool(self._stop_flags.get(project_id))


def _task_type(config: Dict[str, Any], project: Dict[str, Any]) -> str:
    # The persisted Tabular data contract is authoritative. Request parameters
    # must never relabel classification artifacts as regression (or vice versa).
    head = str(active_tabular_config(project).get("task_head") or "classification").lower()
    return "tabular_regression" if head == "regression" else "tabular_classification"


def _validate_training_parameters(config: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    run_id = str(config.get("run_id") or "").strip()
    if run_id and (
        len(run_id) > 128
        or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in run_id)
    ):
        errors.append("Tabular run_id may contain letters, numbers, underscore, and hyphen only.")

    try:
        epochs = int(config.get("epochs") if config.get("epochs") not in (None, "") else 100)
        if not 1 <= epochs <= 10_000:
            errors.append("Tabular epochs must be between 1 and 10000.")
    except (TypeError, ValueError):
        errors.append("Tabular epochs must be an integer.")

    learning_rate_value = config.get("learning_rate")
    if learning_rate_value in (None, ""):
        learning_rate_value = config.get("lr0")
    _validate_float_range(errors, "learning_rate", learning_rate_value, 0.0, 1.0, lower_inclusive=False)
    _validate_integer_range(errors, "max_depth", config.get("max_depth"), 1, 64, default=4)
    _validate_float_range(errors, "subsample", config.get("subsample"), 0.0, 1.0, lower_inclusive=False, default=0.9)
    _validate_float_range(errors, "colsample_bytree", config.get("colsample_bytree"), 0.0, 1.0, lower_inclusive=False, default=0.9)

    seed = config.get("seed")
    try:
        normalized_seed = int(seed if seed not in (None, "") else 42)
        if normalized_seed < 0:
            errors.append("Tabular seed must be zero or greater.")
    except (TypeError, ValueError):
        errors.append("Tabular seed must be an integer.")
    return errors


def _validate_float_range(
    errors: List[str],
    name: str,
    value: Any,
    minimum: float,
    maximum: float,
    *,
    lower_inclusive: bool,
    default: float = 0.05,
) -> None:
    try:
        normalized = float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        errors.append(f"Tabular {name} must be numeric.")
        return
    lower_valid = normalized >= minimum if lower_inclusive else normalized > minimum
    if not math.isfinite(normalized) or not lower_valid or normalized > maximum:
        lower_text = "at least" if lower_inclusive else "greater than"
        errors.append(f"Tabular {name} must be {lower_text} {minimum:g} and at most {maximum:g}.")


def _validate_integer_range(
    errors: List[str], name: str, value: Any, minimum: int, maximum: int, *, default: int
) -> None:
    try:
        normalized = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        errors.append(f"Tabular {name} must be an integer.")
        return
    if not minimum <= normalized <= maximum:
        errors.append(f"Tabular {name} must be between {minimum} and {maximum}.")


def _int(value: Any, default: int) -> int:
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default

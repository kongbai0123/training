from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.training.artifact_manifest import write_artifact_manifest
from src.training.base_backend import TrainingBackend
from src.training.contracts import build_backend_contract
from src.training.metric_schema import build_rnn_metric_schema
from src.training.rnn.sequence_dataset import RNNSequenceDatasetError, load_csv_feature_sequences, write_preprocess_artifacts
from src.training.rnn_config import active_rnn_config
from src.training.rnn.trainer import RNNTrainingError, train_rnn_from_dataset
from src.training.rnn_readiness import build_rnn_readiness_report
from src.training.runners.thread_runner import DEFAULT_THREAD_TRAINING_RUNNER
from src.training.state_store import TrainingStateStore


class RNNBackend(TrainingBackend):
    backend_name = "pytorch_lstm"
    architecture = "rnn"
    _stop_flags: Dict[str, bool] = {}
    _lock = threading.RLock()

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        model_name = str(config.get("model") or "lstm").lower()
        if "cnn" in model_name:
            errors.append("RNNBackend MVP does not support CNN-LSTM.")

        sequence_length = _int(config.get("sequence_length"), 16)
        stride = _int(config.get("stride"), 8)
        readiness = build_rnn_readiness_report(project, sequence_length=sequence_length, stride=stride)
        csv_summary = readiness.get("summary", {}).get("csv", {})
        if not csv_summary.get("valid"):
            errors.append("RNNBackend MVP requires CSV feature sequence files under project/sequences.")
        if not readiness.get("ready"):
            errors.append(readiness.get("message") or "RNN CSV sequence readiness failed.")
        return errors

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        layout = ProjectLayout.from_project(project)
        sequences_dir = layout.sequences_dir()
        return sequences_dir.as_posix()

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        project_id = project.get("project_id", "")
        config = project.get("training_config") or {}
        run_id = config.get("run_id") or f"run_rnn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if DEFAULT_THREAD_TRAINING_RUNNER.is_running(project_id):
            return {"status": "already_running", "backend": self.backend_name, "architecture": self.architecture, "run_id": run_id}
        if TrainingStateStore.is_training(project_id):
            TrainingStateStore.mark_failed(
                project_id,
                "The previous RNN training did not start or exited without reporting a final state.",
            )

        with self._lock:
            self._stop_flags[project_id] = False

        total_epochs = _int(config.get("epochs"), 10)
        TrainingStateStore.init_run(project_id, run_id, total_epochs, self.architecture, self.backend_name)
        try:
            TrainingStateStore.set_field(project_id, "task_type", _rnn_task_type(config))
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
            TrainingStateStore.mark_failed(
                project_id,
                "RNN training could not start because another training job is already running.",
                run_id=run_id,
            )
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
        state.setdefault("hardware", {})
        return state

    def _run_training(self, project: Dict[str, Any]) -> None:
        project_id = project.get("project_id", "")
        config = project.get("training_config") or {}
        run_id = config.get("run_id") or f"run_rnn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        layout = ProjectLayout.from_project(project)
        run_dir = layout.training_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now().isoformat()
        task_type = _rnn_task_type(config)

        try:
            (run_dir / "train_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            dataset = load_csv_feature_sequences(
                project,
                sequence_length=_int(config.get("sequence_length"), 16),
                stride=_int(config.get("stride"), 8),
                task_head=str(config.get("task_head") or "classification"),
            )
            (run_dir / "dataset_snapshot.json").write_text(
                json.dumps(dataset["summary"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            write_preprocess_artifacts(run_dir, dataset)

            metrics_payload = train_rnn_from_dataset(
                dataset,
                run_dir,
                config,
                stop_requested=lambda: self._is_stop_requested(project_id),
                progress_callback=lambda row: TrainingStateStore.append_epoch_metrics(project_id, row),
            )
            status = "stopped" if self._is_stop_requested(project_id) else "completed"
            summary = self._write_summary(run_dir, task_type, status, metrics_payload, feature_config_hash=dataset.get("feature_config_hash"))
            if status == "stopped":
                TrainingStateStore.mark_stopped(project_id, "Training stopped by user.")
            else:
                TrainingStateStore.mark_completed(
                    project_id,
                    best_model="weights/best.pt",
                    termination_reason=metrics_payload.get("stopped_reason") or None,
                )
            self._update_project_run(project, summary)
            self._write_contracts(run_dir, run_id, task_type, status, created_at)
        except (RNNSequenceDatasetError, RNNTrainingError, Exception) as exc:
            error = str(exc)
            (run_dir / "error.log").write_text(error, encoding="utf-8")
            summary = self._write_summary(run_dir, task_type, "failed", None, error, feature_config_hash=active_rnn_config(project).get("feature_config_hash"))
            TrainingStateStore.mark_failed(project_id, error)
            self._update_project_run(project, summary)
            self._write_contracts(run_dir, run_id, task_type, "failed", created_at)
        finally:
            write_artifact_manifest(run_dir, run_id)
            with self._lock:
                self._stop_flags.pop(project_id, None)

    def _is_stop_requested(self, project_id: str) -> bool:
        with self._lock:
            return bool(self._stop_flags.get(project_id))

    def _write_summary(
        self,
        run_dir: Path,
        task_type: str,
        status: str,
        metrics_payload: Dict[str, Any] | None,
        error: str = "",
        feature_config_hash: str | None = None,
    ) -> Dict[str, Any]:
        best_metrics = (metrics_payload or {}).get("best_metrics", {})
        config = self._summary_config(run_dir)
        primary_key = "val/mae" if "regression" in task_type else "val/macro_f1"
        summary = {
            "run_id": run_dir.name,
            "status": status,
            "task_type": task_type,
            "architecture": self.architecture,
            "backend": self.backend_name,
            "model": str(config.get("model") or (metrics_payload or {}).get("model") or "lstm"),
            "epochs": _int(config.get("epochs"), (metrics_payload or {}).get("total_epochs", 0) or 0),
            "batch_size": _int(config.get("batch_size"), (metrics_payload or {}).get("batch_size", 0) or 0),
            "sequence_length": _int(config.get("sequence_length"), (metrics_payload or {}).get("sequence_length", 0) or 0),
            "stride": _int(config.get("stride"), (metrics_payload or {}).get("stride", 0) or 0),
            "horizon": _int(config.get("horizon"), (metrics_payload or {}).get("horizon", 0) or 0),
            "best_epoch": (metrics_payload or {}).get("best_epoch", 0),
            "best_metrics": best_metrics,
            "primary_metric_key": primary_key,
            "primary_metric_name": "MAE" if primary_key == "val/mae" else "Macro-F1",
            "primary_metric_value": best_metrics.get(primary_key),
            "platform_score": _platform_score(best_metrics, task_type),
            "error": error,
            "completed_at": datetime.now().isoformat(),
            "feature_config_hash": feature_config_hash or "",
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    @staticmethod
    def _summary_config(run_dir: Path) -> Dict[str, Any]:
        path = run_dir / "train_config.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_contracts(self, run_dir: Path, run_id: str, task_type: str, status: str, created_at: str) -> None:
        completed_at = datetime.now().isoformat()
        backend_contract = build_backend_contract(
            run_id=run_id,
            architecture=self.architecture,
            backend=self.backend_name,
            task_type=task_type,
            status=status,
            created_at=created_at,
            completed_at=completed_at,
        )
        (run_dir / "backend.json").write_text(json.dumps(backend_contract, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "metric_schema.json").write_text(
            json.dumps(build_rnn_metric_schema(task_type), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _update_project_run(self, project: Dict[str, Any], summary: Dict[str, Any]) -> None:
        project_id = project.get("project_id")
        if not project_id:
            return
        runs = [run for run in project.get("training_runs", []) if run.get("run_id") != summary.get("run_id")]
        runs.append(summary)
        project["training_runs"] = runs
        project.setdefault("current", {})["training_run_id"] = summary.get("run_id")
        ProjectManager.save_project(project_id, project)


def _int(value: Any, default: int) -> int:
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _rnn_task_type(config: Dict[str, Any]) -> str:
    task_head = str(config.get("task_head") or "classification").lower()
    return "sequence_regression" if task_head == "regression" else "sequence_classification"


def _platform_score(metrics: Dict[str, Any], task_type: str) -> float:
    if "regression" in task_type:
        mae = metrics.get("val/mae")
        try:
            return round(1.0 / (1.0 + float(mae)), 5)
        except (TypeError, ValueError):
            return 0.0
    try:
        return round(float(metrics.get("val/macro_f1", 0.0)), 5)
    except (TypeError, ValueError):
        return 0.0

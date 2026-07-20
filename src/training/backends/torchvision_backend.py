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
from src.training.runners.thread_runner import DEFAULT_THREAD_TRAINING_RUNNER
from src.training.state_store import TrainingStateStore
from src.training.vision import train_torchvision_model, validate_torchvision_model_install


class TorchVisionBackend(TrainingBackend):
    backend_name = "pytorch_torchvision"
    architecture = "cnn"
    _stop_flags: Dict[str, bool] = {}
    _lock = threading.RLock()

    def validate_readiness(self, project: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not project.get("class_names"):
            errors.append("Add at least one class before training.")
        images = project.get("images") or []
        if not any(item.get("split") == "train" for item in images):
            errors.append("Create a dataset split with training images.")
        if not any(item.get("split") == "val" for item in images):
            errors.append("Create a dataset split with validation images.")
        install_error = validate_torchvision_model_install(config.get("model"))
        if install_error:
            errors.append(install_error)
        task = str(project.get("task_type") or "").lower()
        if "semantic" in task or "instance" in task:
            missing = [
                item.get("filename") for item in images
                if item.get("split") in {"train", "val"}
                and not any(len(ann.get("points") or []) >= 3 for ann in item.get("annotations") or [])
            ]
            if missing:
                errors.append(f"Polygon masks are required for segmentation; {len(missing)} split image(s) have no polygon.")
        return errors

    def prepare_dataset(self, project: Dict[str, Any]) -> str:
        return ProjectLayout.from_project(project).resolve_raw_images_dir().path.as_posix()

    def start_training(self, project: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(project.get("project_id") or "")
        config = project.get("training_config") or {}
        run_id = str(config.get("run_id") or f"run_vision_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        if DEFAULT_THREAD_TRAINING_RUNNER.is_running(project_id) or TrainingStateStore.is_training(project_id):
            return {"status": "already_running", "backend": self.backend_name, "architecture": self.architecture, "run_id": run_id}
        with self._lock:
            self._stop_flags[project_id] = False
        TrainingStateStore.init_run(project_id, run_id, int(config.get("epochs") or 10), self.architecture, self.backend_name)
        TrainingStateStore.set_field(project_id, "task_type", project.get("task_type"))
        result = DEFAULT_THREAD_TRAINING_RUNNER.start(
            project_id=project_id, run_id=run_id, target=self._run_training, args=(project,), daemon=False
        )
        return {
            "status": "started" if result.get("started") else "already_running",
            "backend": self.backend_name,
            "architecture": self.architecture,
            "run_id": result.get("run_id", run_id),
        }

    def stop_training(self, project_id: str) -> Dict[str, Any]:
        with self._lock:
            self._stop_flags[project_id] = True
        TrainingStateStore.mark_stopping(project_id)
        return {"status": "stopping", "backend": self.backend_name, "architecture": self.architecture}

    def get_status(self, project_id: str) -> Dict[str, Any]:
        state = TrainingStateStore.get_state(project_id)
        state.setdefault("backend", self.backend_name)
        state.setdefault("architecture", self.architecture)
        return state

    def _run_training(self, project: Dict[str, Any]) -> None:
        project_id = str(project.get("project_id") or "")
        config = project.get("training_config") or {}
        run_id = str(config.get("run_id") or f"run_vision_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        task_type = str(project.get("task_type") or "")
        run_dir = ProjectLayout.from_project(project).training_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now().isoformat()
        try:
            (run_dir / "train_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            metrics = self.train_model(
                project,
                run_dir,
                config,
                stop_requested=lambda: self._is_stop_requested(project_id),
                progress_callback=lambda row: TrainingStateStore.append_epoch_metrics(project_id, row),
            )
            status = "stopped" if self._is_stop_requested(project_id) else "completed"
            summary = self._write_summary(run_dir, task_type, status, metrics)
            if status == "stopped":
                TrainingStateStore.mark_stopped(project_id, "Training stopped by user.")
            else:
                TrainingStateStore.mark_completed(project_id, best_model="weights/best.pt", termination_reason=metrics.get("stopped_reason") or None)
            self._update_project_run(project, summary)
            self._write_contracts(run_dir, run_id, task_type, status, created_at, metrics)
        except Exception as exc:
            error = str(exc)
            (run_dir / "error.log").write_text(error, encoding="utf-8")
            summary = self._write_summary(run_dir, task_type, "failed", None, error=error)
            TrainingStateStore.mark_failed(project_id, error)
            self._update_project_run(project, summary)
            self._write_contracts(run_dir, run_id, task_type, "failed", created_at, None)
        finally:
            write_artifact_manifest(run_dir, run_id)
            with self._lock:
                self._stop_flags.pop(project_id, None)

    def train_model(self, project: Dict[str, Any], run_dir: Path, config: Dict[str, Any], **callbacks) -> Dict[str, Any]:
        return train_torchvision_model(project, run_dir, config, **callbacks)

    def _is_stop_requested(self, project_id: str) -> bool:
        with self._lock:
            return bool(self._stop_flags.get(project_id))

    def _write_summary(self, run_dir: Path, task_type: str, status: str, metrics: Dict[str, Any] | None, error: str = "") -> Dict[str, Any]:
        best_metrics = (metrics or {}).get("best_metrics") or {}
        primary = (metrics or {}).get("primary_metric") or "val/loss"
        summary = {
            "run_id": run_dir.name,
            "status": status,
            "task_type": task_type,
            "architecture": self.architecture,
            "backend": self.backend_name,
            "model": (metrics or {}).get("model"),
            "best_epoch": (metrics or {}).get("best_epoch", 0),
            "best_metrics": best_metrics,
            "primary_metric_name": primary,
            "primary_metric_value": best_metrics.get(primary),
            "error": error,
            "completed_at": datetime.now().isoformat(),
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    def _write_contracts(self, run_dir: Path, run_id: str, task_type: str, status: str, created_at: str, metrics: Dict[str, Any] | None) -> None:
        contract = build_backend_contract(
            run_id, self.architecture, self.backend_name, task_type, status, created_at, datetime.now().isoformat()
        )
        (run_dir / "backend.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
        primary = (metrics or {}).get("primary_metric") or "val/loss"
        schema = {
            "contract_version": "1.0",
            "primary_metric": {"key": primary, "display_name": primary.split("/")[-1], "goal": "minimize" if primary.endswith("loss") else "maximize"},
            "groups": {"loss": ["train/loss", "val/loss"], "quality": [primary]},
        }
        (run_dir / "metric_schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")

    def _update_project_run(self, project: Dict[str, Any], summary: Dict[str, Any]) -> None:
        project_id = project.get("project_id")
        if not project_id:
            return
        latest = ProjectManager.get_project(project_id) or project
        runs = [run for run in latest.get("training_runs", []) if run.get("run_id") != summary.get("run_id")]
        runs.append(summary)
        latest["training_runs"] = runs
        latest.setdefault("current", {})["training_run_id"] = summary.get("run_id")
        if summary.get("status") == "completed":
            latest["current"]["best_model_id"] = f"{project_id}::{summary.get('run_id')}::best"
        ProjectManager.save_project(project_id, latest)

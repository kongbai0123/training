from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any, Dict, Optional


class TrainingStateStore:
    _states: Dict[str, Dict[str, Any]] = {}
    _lock = threading.RLock()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @classmethod
    def idle_state(
        cls,
        architecture: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "idle",
            "epoch": 0,
            "total_epochs": 0,
            "metrics": [],
            "error": "",
            "run_id": "",
            "hardware": {},
            "architecture": architecture,
            "backend": backend,
            "updated_at": None,
            "started_at": None,
            "completed_at": None,
        }

    @classmethod
    def normalize(cls, raw: Dict[str, Any], architecture: str, backend: str) -> Dict[str, Any]:
        raw = raw or {}
        normalized = {
            "status": raw.get("status", "idle"),
            "epoch": raw.get("epoch", 0),
            "total_epochs": raw.get("total_epochs", 0),
            "metrics": raw.get("metrics", []),
            "error": raw.get("error", ""),
            "run_id": raw.get("run_id", ""),
            "hardware": raw.get("hardware", {}),
            "architecture": architecture,
            "backend": backend,
            "updated_at": raw.get("updated_at"),
            "started_at": raw.get("started_at"),
            "completed_at": raw.get("completed_at"),
        }

        for key, value in raw.items():
            if key not in normalized:
                normalized[key] = value
        return normalized

    @classmethod
    def update_from_backend(
        cls,
        project_id: str,
        raw: Dict[str, Any],
        architecture: str,
        backend: str,
    ) -> Dict[str, Any]:
        normalized = cls.normalize(raw, architecture, backend)
        with cls._lock:
            cls._states[project_id] = copy.deepcopy(normalized)
            return copy.deepcopy(normalized)

    @classmethod
    def init_run(
        cls,
        project_id: str,
        run_id: str,
        total_epochs: int,
        architecture: str,
        backend: str,
    ) -> Dict[str, Any]:
        now = cls._now_iso()
        state = {
            "status": "training",
            "epoch": 0,
            "total_epochs": total_epochs,
            "metrics": [],
            "error": "",
            "run_id": run_id,
            "hardware": {},
            "architecture": architecture,
            "backend": backend,
            "updated_at": now,
            "started_at": now,
            "completed_at": None,
        }
        with cls._lock:
            cls._states[project_id] = copy.deepcopy(state)
            return copy.deepcopy(state)

    @classmethod
    def append_epoch_metrics(
        cls,
        project_id: str,
        metrics_data: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with cls._lock:
            state = copy.deepcopy(cls._states.get(project_id, cls.idle_state()))
            if run_id:
                state["run_id"] = run_id
            metrics = list(state.get("metrics") or [])
            normalized_metrics = copy.deepcopy(metrics_data)
            total_epochs = int(state.get("total_epochs") or 0)
            try:
                metric_epoch = int(normalized_metrics.get("epoch", state.get("epoch", 0)) or 0)
            except (TypeError, ValueError):
                metric_epoch = int(state.get("epoch", 0) or 0)
            if total_epochs > 0 and metric_epoch > total_epochs:
                metric_epoch = total_epochs
                normalized_metrics["epoch"] = metric_epoch
            if metrics and metrics[-1].get("epoch") == normalized_metrics.get("epoch"):
                metrics[-1] = normalized_metrics
            else:
                metrics.append(normalized_metrics)
            state["metrics"] = metrics
            state["epoch"] = metric_epoch or state.get("epoch", 0)
            state["updated_at"] = cls._now_iso()
            cls._states[project_id] = copy.deepcopy(state)
            return copy.deepcopy(state)

    @classmethod
    def mark_stopping(cls, project_id: str) -> Dict[str, Any]:
        return cls._set_status(project_id, "stopping")

    @classmethod
    def mark_stopped(cls, project_id: str, error: str = "", run_id: Optional[str] = None) -> Dict[str, Any]:
        extra = {"run_id": run_id} if run_id else None
        return cls._set_status(project_id, "stopped", error=error, extra=extra, complete=True)

    @classmethod
    def mark_completed(
        cls,
        project_id: str,
        best_model: Optional[str] = None,
        run_id: Optional[str] = None,
        termination_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        extra = {}
        if best_model:
            extra["best_model"] = best_model
        if run_id:
            extra["run_id"] = run_id
        if termination_reason:
            extra["termination_reason"] = termination_reason
        if not extra:
            extra = None
        return cls._set_status(project_id, "completed", extra=extra, complete=True)

    @classmethod
    def mark_failed(cls, project_id: str, error: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        extra = {"run_id": run_id} if run_id else None
        return cls._set_status(project_id, "failed", error=error, extra=extra, complete=True)

    @classmethod
    def set_field(cls, project_id: str, key: str, value: Any) -> Dict[str, Any]:
        with cls._lock:
            state = copy.deepcopy(cls._states.get(project_id, cls.idle_state()))
            state[key] = value
            state["updated_at"] = cls._now_iso()
            cls._states[project_id] = copy.deepcopy(state)
            return copy.deepcopy(state)

    @classmethod
    def _set_status(
        cls,
        project_id: str,
        status: str,
        error: str = "",
        extra: Optional[Dict[str, Any]] = None,
        complete: bool = False,
    ) -> Dict[str, Any]:
        with cls._lock:
            state = copy.deepcopy(cls._states.get(project_id, cls.idle_state()))
            state["status"] = status
            if error:
                state["error"] = error
            elif status in {"completed", "stopped"}:
                state["error"] = state.get("error", "")
            if extra:
                state.update(extra)
            now = cls._now_iso()
            state["updated_at"] = now
            if complete:
                state["completed_at"] = now
            cls._states[project_id] = copy.deepcopy(state)
            return copy.deepcopy(state)

    @classmethod
    def get_state(cls, project_id: str) -> Dict[str, Any]:
        with cls._lock:
            return copy.deepcopy(cls._states.get(project_id, cls.idle_state()))

    @classmethod
    def is_training(cls, project_id: str) -> bool:
        with cls._lock:
            state = cls._states.get(project_id)
            return bool(state and state.get("status") == "training")

    @classmethod
    def get(cls, project_id: str) -> Dict[str, Any]:
        return cls.get_state(project_id)

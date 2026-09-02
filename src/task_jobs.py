"""Shared background-task state for long-running UI operations."""

from __future__ import annotations

import threading
import uuid
import json
import os
import tempfile
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional


TaskHandler = Callable[["TaskReporter"], Any]
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE_STATUSES = {"queued", "running", "cancelling"}
MAX_HISTORY_EVENTS = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskJobNotFound(KeyError):
    pass


class TaskReporter:
    def __init__(self, manager: "TaskJobManager", job_id: str):
        self._manager = manager
        self.job_id = job_id

    def update(
        self,
        *,
        phase: Optional[str] = None,
        message: Optional[str] = None,
        progress: Optional[float] = None,
        indeterminate: Optional[bool] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
    ) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        if phase is not None:
            values["phase"] = str(phase)
        if message is not None:
            values["message"] = str(message)
        if progress is not None:
            values["progress"] = max(0.0, min(100.0, float(progress)))
        if indeterminate is not None:
            values["indeterminate"] = bool(indeterminate)
        if current is not None:
            values["current"] = max(0, int(current))
        if total is not None:
            values["total"] = max(0, int(total))
        return self._manager.update(self.job_id, **values)

    def is_cancelled(self) -> bool:
        return self._manager.is_cancelled(self.job_id)


class TaskJobManager:
    """Thread-safe in-process task registry with a stable API/WebSocket payload."""

    def __init__(self, *, max_jobs: int = 200, journal_dir: Optional[Path] = None, retention_days: int = 30):
        self._max_jobs = max(20, int(max_jobs))
        self._journal_dir = Path(journal_dir).resolve() if journal_dir else None
        self._retention_days = max(1, int(retention_days))
        self._jobs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        if self._journal_dir:
            self._journal_dir.mkdir(parents=True, exist_ok=True)
            self._restore_journal()

    def submit(
        self,
        *,
        kind: str,
        title: str,
        handler: TaskHandler,
        project_id: str = "",
        message: str = "Queued",
        phase: str = "queued",
    ) -> Dict[str, Any]:
        job_id = f"task_{kind}_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        job = {
            "job_id": job_id,
            "kind": str(kind),
            "title": str(title),
            "project_id": str(project_id or ""),
            "status": "queued",
            "phase": str(phase),
            "message": str(message),
            "progress": 0.0,
            "indeterminate": True,
            "current": 0,
            "total": 0,
            "result": None,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "completed_at": "",
            "history": [{"phase": str(phase), "message": str(message), "progress": 0.0, "at": now}],
        }
        with self._changed:
            self._jobs[job_id] = job
            self._cancel_events[job_id] = threading.Event()
            self._prune_locked()
            self._persist_locked(job)
            self._changed.notify_all()
        threading.Thread(target=self._run, args=(job_id, handler), daemon=True, name=job_id).start()
        return self.get(job_id)

    def _run(self, job_id: str, handler: TaskHandler) -> None:
        self.update(job_id, status="running", phase="preparing", message="Preparing task", started_at=_utc_now())
        reporter = TaskReporter(self, job_id)
        try:
            if reporter.is_cancelled():
                self.update(job_id, status="cancelled", phase="cancelled", message="Task cancelled", completed_at=_utc_now())
                return
            result = handler(reporter)
            if reporter.is_cancelled():
                self.update(job_id, status="cancelled", phase="cancelled", message="Task cancelled", completed_at=_utc_now())
                return
            self.update(
                job_id,
                status="completed",
                phase="completed",
                message="Task completed",
                progress=100.0,
                indeterminate=False,
                result=result,
                completed_at=_utc_now(),
            )
        except Exception as exc:  # noqa: BLE001 - task boundary records user-safe failure state
            self.update(
                job_id,
                status="failed",
                phase="failed",
                message="Task failed",
                indeterminate=False,
                error=str(exc),
                completed_at=_utc_now(),
            )

    def get(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise TaskJobNotFound(job_id)
            return deepcopy(job)

    def update(self, job_id: str, **values: Any) -> Dict[str, Any]:
        with self._changed:
            job = self._jobs.get(job_id)
            if not job:
                raise TaskJobNotFound(job_id)
            previous_phase = str(job.get("phase") or "")
            job.update(values)
            job["updated_at"] = _utc_now()
            next_phase = str(job.get("phase") or "")
            if next_phase and next_phase != previous_phase:
                job.setdefault("history", []).append({
                    "phase": next_phase,
                    "message": str(job.get("message") or ""),
                    "progress": float(job.get("progress") or 0.0),
                    "at": job["updated_at"],
                })
                job["history"] = job["history"][-MAX_HISTORY_EVENTS:]
            self._jobs.move_to_end(job_id)
            self._persist_locked(job)
            self._changed.notify_all()
            return deepcopy(job)

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._changed:
            event = self._cancel_events.get(job_id)
            job = self._jobs.get(job_id)
            if not event or not job:
                raise TaskJobNotFound(job_id)
            if job["status"] not in TERMINAL_STATUSES:
                event.set()
                job.update({"status": "cancelling", "phase": "cancelling", "message": "Cancelling task", "updated_at": _utc_now()})
                self._persist_locked(job)
                self._changed.notify_all()
            return deepcopy(job)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(job_id)
            return bool(event and event.is_set())

    def wait_for_change(self, job_id: str, updated_at: str, timeout: float = 10.0) -> Dict[str, Any]:
        with self._changed:
            self.get(job_id)
            self._changed.wait_for(
                lambda: self._jobs.get(job_id, {}).get("updated_at") != updated_at,
                timeout=max(0.1, float(timeout)),
            )
            return self.get(job_id)

    def snapshot(self, *, active_only: bool = False) -> list[Dict[str, Any]]:
        with self._lock:
            values = list(self._jobs.values())
            if active_only:
                values = [job for job in values if job.get("status") not in TERMINAL_STATUSES]
            return deepcopy(values)

    def _prune_locked(self) -> None:
        while len(self._jobs) > self._max_jobs:
            removable = next((key for key, value in self._jobs.items() if value.get("status") in TERMINAL_STATUSES), None)
            if not removable:
                return
            self._jobs.pop(removable, None)
            self._cancel_events.pop(removable, None)
            if self._journal_dir:
                journal = self._journal_dir / removable / "job.json"
                journal.unlink(missing_ok=True)
                try:
                    journal.parent.rmdir()
                except OSError:
                    pass

    def _persist_locked(self, job: Dict[str, Any]) -> None:
        if not self._journal_dir:
            return
        job_dir = self._journal_dir / str(job["job_id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        target = job_dir / "job.json"
        fd, temp_name = tempfile.mkstemp(prefix=".job.", suffix=".tmp", dir=job_dir)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(job, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def _restore_journal(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        restored: list[Dict[str, Any]] = []
        for path in self._journal_dir.glob("*/job.json"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    job = json.load(handle)
                updated = datetime.fromisoformat(str(job.get("updated_at") or ""))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if updated < cutoff:
                    path.unlink(missing_ok=True)
                    continue
                if job.get("status") in ACTIVE_STATUSES:
                    now = _utc_now()
                    job.update({
                        "status": "interrupted",
                        "phase": "interrupted",
                        "message": "The application restarted before this task completed.",
                        "error": "Application restarted",
                        "error_code": "APP_RESTARTED",
                        "retryable": True,
                        "retry_action": job.get("retry_action") or {"project_id": job.get("project_id", ""), "kind": job.get("kind", "")},
                        "completed_at": now,
                        "updated_at": now,
                    })
                    job.setdefault("history", []).append({
                        "phase": "interrupted", "message": job["message"], "progress": float(job.get("progress") or 0), "at": now
                    })
                job["history"] = list(job.get("history") or [])[-MAX_HISTORY_EVENTS:]
                restored.append(job)
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                continue
        restored.sort(key=lambda item: str(item.get("updated_at") or ""))
        for expired in restored[:-self._max_jobs]:
            expired_id = str(expired.get("job_id") or "")
            if expired_id:
                expired_path = self._journal_dir / expired_id / "job.json"
                expired_path.unlink(missing_ok=True)
                try:
                    expired_path.parent.rmdir()
                except OSError:
                    pass
        for job in restored[-self._max_jobs:]:
            job_id = str(job.get("job_id") or "")
            if not job_id:
                continue
            self._jobs[job_id] = job
            self._cancel_events[job_id] = threading.Event()
            self._persist_locked(job)


from src.app_paths import TASKS_DIR


task_job_manager = TaskJobManager(journal_dir=TASKS_DIR)

from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple


class ThreadTrainingJobRunner:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    def start(
        self,
        project_id: str,
        run_id: str,
        target: Callable[..., Any],
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        daemon: bool = False,
    ) -> Dict[str, Any]:
        kwargs = kwargs or {}

        with self._lock:
            existing = self._jobs.get(project_id)
            if existing and existing["thread"].is_alive():
                return {
                    "started": False,
                    "reason": "already_running",
                    "project_id": project_id,
                    "run_id": existing["run_id"],
                    "thread_name": existing["thread_name"],
                }

            def wrapped_target() -> None:
                try:
                    target(*args, **kwargs)
                finally:
                    self.cleanup(project_id, run_id)

            thread = threading.Thread(
                target=wrapped_target,
                name=f"training-{project_id}-{run_id}",
                daemon=daemon,
            )
            self._jobs[project_id] = {
                "project_id": project_id,
                "run_id": run_id,
                "thread": thread,
                "thread_name": thread.name,
                "started_at": self._now_iso(),
            }
            thread.start()

            return {
                "started": True,
                "project_id": project_id,
                "run_id": run_id,
                "thread_name": thread.name,
            }

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(project_id)
            return bool(record and record["thread"].is_alive())

    def cleanup(self, project_id: str, run_id: Optional[str] = None) -> None:
        with self._lock:
            record = self._jobs.get(project_id)
            if not record:
                return
            if run_id is not None and record.get("run_id") != run_id:
                return
            self._jobs.pop(project_id, None)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            result: Dict[str, Any] = {}
            for project_id, record in self._jobs.items():
                thread = record["thread"]
                result[project_id] = {
                    "project_id": record["project_id"],
                    "run_id": record["run_id"],
                    "thread_name": record["thread_name"],
                    "started_at": record["started_at"],
                    "alive": thread.is_alive(),
                }
            return copy.deepcopy(result)


DEFAULT_THREAD_TRAINING_RUNNER = ThreadTrainingJobRunner()

from __future__ import annotations

from typing import Any

from src.model_install_manager import MODEL_INSTALL_MANAGER
from src.task_jobs import task_job_manager
from src.training.runners.thread_runner import DEFAULT_THREAD_TRAINING_RUNNER


def active_update_blockers() -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for project_id, job in DEFAULT_THREAD_TRAINING_RUNNER.snapshot().items():
        if job.get("alive"):
            blockers.append(
                {
                    "kind": "training",
                    "id": job.get("run_id") or project_id,
                    "title": f"Training run {job.get('run_id') or project_id}",
                }
            )
    for job in task_job_manager.snapshot(active_only=True):
        if job.get("kind") == "software_update_download":
            continue
        blockers.append(
            {
                "kind": str(job.get("kind") or "background_task"),
                "id": str(job.get("job_id") or ""),
                "title": str(job.get("title") or job.get("kind") or "Background task"),
            }
        )
    for job in MODEL_INSTALL_MANAGER.active_snapshot():
        blockers.append(
            {
                "kind": "model_install",
                "id": str(job.get("job_id") or ""),
                "title": str(job.get("display_name") or "Model installation"),
            }
        )
    return blockers

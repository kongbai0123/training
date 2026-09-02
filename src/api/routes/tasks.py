"""Status and WebSocket endpoints for shared background tasks."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from src.task_jobs import TERMINAL_STATUSES, TaskJobNotFound, task_job_manager


router = APIRouter()


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    job_id: str
    kind: str
    title: str
    project_id: str = ""
    status: str
    phase: str
    message: str = ""
    progress: float = 0
    retryable: bool = False
    retry_action: Optional[Dict[str, Any]] = None


@router.get("/api/tasks", response_model=List[TaskResponse])
def list_tasks(project_id: str = "", active_only: bool = False):
    tasks = task_job_manager.snapshot(active_only=active_only)
    if project_id:
        tasks = [task for task in tasks if task.get("project_id") == project_id]
    return tasks


@router.get("/api/tasks/{job_id}")
def get_task(job_id: str) -> TaskResponse:
    try:
        return task_job_manager.get(job_id)
    except TaskJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.post("/api/tasks/{job_id}/cancel")
def cancel_task(job_id: str) -> TaskResponse:
    try:
        return task_job_manager.cancel(job_id)
    except TaskJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.websocket("/api/tasks/{job_id}/ws")
async def monitor_task(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_updated = ""
    try:
        while True:
            try:
                task = task_job_manager.get(job_id)
            except TaskJobNotFound:
                await websocket.send_json({"job_id": job_id, "status": "failed", "error": "Task not found"})
                await websocket.close(code=4404)
                return
            if task.get("updated_at") != last_updated:
                await websocket.send_json(task)
                last_updated = str(task.get("updated_at") or "")
            if task.get("status") in TERMINAL_STATUSES:
                await websocket.close()
                return
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return

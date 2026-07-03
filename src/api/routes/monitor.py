import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.project_manager import ProjectManager
from src.training.dispatcher import TrainerDispatcher

router = APIRouter()


@router.websocket("/api/projects/{project_id}/monitor")
async def monitor_training(websocket: WebSocket, project_id: str):
    await websocket.accept()
    print(f"[WS] Client connected to monitor project {project_id}")
    try:
        while True:
            project = ProjectManager.get_project(project_id)
            status = TrainerDispatcher.get_status(project_id, project)
            await websocket.send_json(status)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from {project_id}")
    except Exception as e:
        print(f"[WS] Error in monitor loop: {e}")
        try:
            await websocket.close()
        except Exception:
            pass

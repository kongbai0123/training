from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from src.api.exceptions import VtsApiException
from src.project_manager import ProjectManager
from src.project_repository import ProjectRevisionConflict


router = APIRouter()


class ProjectCreate(BaseModel):
    project_name: str
    task_type: str
    class_names: List[str]


class ProjectTaskUpdate(BaseModel):
    task_type: str
    confirm: bool = False


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    project_id: str
    revision: int = 0
    project_name: Optional[str] = None
    task_type: Optional[str] = None
    dataset_path: Optional[str] = None

def _expected_revision(if_match: Optional[str]) -> Optional[int]:
    if not if_match:
        return None
    value = if_match.strip().removeprefix("W/").strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise VtsApiException("INVALID_IF_MATCH", "If-Match must contain a project revision.", status_code=400) from exc


def _set_etag(response: Response, project: Dict[str, Any]) -> None:
    response.headers["ETag"] = f'"{int(project.get("revision") or 0)}"'


@router.get("/api/projects")
def list_projects():
    return ProjectManager.get_all_projects()


@router.post("/api/projects", response_model=ProjectResponse)
def create_project(data: ProjectCreate, response: Response):
    try:
        project = ProjectManager.create_project(data.project_name, data.task_type, data.class_names)
        _set_etag(response, project)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, response: Response):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _set_etag(response, project)
    return project


@router.patch("/api/projects/{project_id}/task-type")
def update_project_task_type(
    project_id: str,
    data: ProjectTaskUpdate,
    response: Response,
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if str(project.get("task_type") or "").lower() != str(data.task_type or "").lower() and not data.confirm:
        raise HTTPException(status_code=409, detail="Changing the task type requires explicit confirmation")
    expected = _expected_revision(if_match)
    if expected is not None and expected != int(project.get("revision") or 0):
        raise VtsApiException("PROJECT_REVISION_CONFLICT", "Project was changed by another operation.", status_code=409)
    try:
        result = ProjectManager.update_task_type(project_id, data.task_type)
        _set_etag(response, result["project"])
        return result
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if message == "Project not found" else 400, detail=message) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/save", response_model=ProjectResponse)
def save_project_state(
    project_id: str,
    response: Response,
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    expected = _expected_revision(if_match)
    if expected is not None and expected != int(project.get("revision") or 0):
        raise VtsApiException("PROJECT_REVISION_CONFLICT", "Project was changed by another operation.", status_code=409)
    if not ProjectManager.save_project(project_id, project):
        raise VtsApiException("PROJECT_REVISION_CONFLICT", "Project was changed by another operation.", status_code=409)
    saved_project = ProjectManager.get_project(project_id)
    if not saved_project:
        raise HTTPException(status_code=500, detail="Unable to reload saved project")
    _set_etag(response, saved_project)
    return saved_project


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or unable to delete")
    return {"message": "Project deleted successfully"}

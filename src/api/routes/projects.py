from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.project_manager import ProjectManager


router = APIRouter()


class ProjectCreate(BaseModel):
    project_name: str
    task_type: str
    class_names: List[str]


@router.get("/api/projects")
def list_projects():
    return ProjectManager.get_all_projects()


@router.post("/api/projects")
def create_project(data: ProjectCreate):
    try:
        return ProjectManager.create_project(data.project_name, data.task_type, data.class_names)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/api/projects/{project_id}/save")
def save_project_state(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not ProjectManager.save_project(project_id, project):
        raise HTTPException(status_code=500, detail="Unable to save project")
    saved_project = ProjectManager.get_project(project_id)
    if not saved_project:
        raise HTTPException(status_code=500, detail="Unable to reload saved project")
    return saved_project


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or unable to delete")
    return {"message": "Project deleted successfully"}

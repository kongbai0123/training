from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.project_data_migration import ProjectDataMigrationTool
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.project_migrator import ProjectMigrator


router = APIRouter()


class ProjectDataMigrationRequest(BaseModel):
    project_ids: Optional[List[str]] = None
    delete_source: bool = False


@router.get("/api/projects/data-migration/scan")
def scan_project_data_migration():
    return ProjectDataMigrationTool.scan()


@router.post("/api/projects/data-migration/apply")
def apply_project_data_migration(request: ProjectDataMigrationRequest):
    return ProjectDataMigrationTool.migrate(
        project_ids=request.project_ids,
        delete_source=request.delete_source,
    )


@router.get("/api/projects/{project_id}/layout")
def get_project_layout(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectLayout.from_project(project).get_layout_report()


@router.post("/api/projects/{project_id}/layout/migration/dry-run")
def dry_run_layout_migration(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectMigrator.dry_run(project)


@router.post("/api/projects/{project_id}/layout/migration/apply")
def apply_layout_migration(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return ProjectMigrator.apply(project)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

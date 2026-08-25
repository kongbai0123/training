from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.api.dependencies import require_api_token
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.security_utils import safe_filename
from src.tabular_config import (
    active_tabular_config,
    get_tabular_workspace,
    import_tabular_csv,
    update_project_tabular_config,
)


router = APIRouter()
MAX_TABULAR_BATCH_BYTES = 256 * 1024 * 1024


class TabularConfigRequest(BaseModel):
    source_file: str = ""
    feature_columns: List[str] = Field(default_factory=list)
    target_column: str = ""
    id_column: str = ""
    split_column: str = ""
    task_head: str = "classification"
    seed: int = 42
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    missing_strategy: str = "median"


class TabularRowInferenceRequest(BaseModel):
    row: Dict[str, Any]
    run_id: Optional[str] = None
    model_id: Optional[str] = None


@router.get("/api/projects/{project_id}/tabular/workspace")
def get_tabular_project_workspace(project_id: str):
    project = _tabular_project(project_id)
    try:
        return get_tabular_workspace(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/tabular/config")
def save_tabular_project_config(project_id: str, request: TabularConfigRequest):
    project = _tabular_project(project_id)
    try:
        return update_project_tabular_config(project_id, project, request.dict())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/tabular/dataset/import")
def import_tabular_project_dataset(project_id: str, file: UploadFile = File(...)):
    project = _tabular_project(project_id)
    try:
        imported = import_tabular_csv(project, file)
        saved = update_project_tabular_config(project_id, project, imported["suggested_config"])
        return {"success": True, "dataset": imported, **saved}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/tabular/inference/row")
def infer_tabular_row(project_id: str, request: TabularRowInferenceRequest):
    project = _tabular_project(project_id)
    try:
        service, run_id = _inference_service(project, request.run_id, request.model_id)
        result = service.predict_one(request.row)
        return {"success": True, "run_id": run_id, **result}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/tabular/inference/batch")
def infer_tabular_batch(
    project_id: str,
    file: UploadFile = File(...),
    run_id: str = "",
    model_id: str = "",
):
    project = _tabular_project(project_id)
    layout = ProjectLayout.from_project(project)
    filename = safe_filename(Path(file.filename or "input.csv").name)
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Batch inference accepts CSV files only.")
    job_id = f"tabular_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    job_dir = layout.inference_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=False)
    input_path = job_dir / filename
    output_path = job_dir / "predictions.csv"
    try:
        copied = 0
        with input_path.open("wb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_TABULAR_BATCH_BYTES:
                    raise ValueError("Batch inference CSV exceeds the 256 MB limit.")
                handle.write(chunk)
        service, resolved_run_id = _inference_service(project, run_id, model_id)
        result = service.predict_csv(input_path, output_path, trusted_root=layout.project_dir)
        return {
            "success": True,
            "job_id": job_id,
            "run_id": resolved_run_id,
            "download_url": f"/api/projects/{project_id}/tabular/inference/jobs/{job_id}/download",
            **result,
        }
    except (ValueError, RuntimeError) as exc:
        _discard_failed_job(job_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}/tabular/inference/jobs/{job_id}/download")
def download_tabular_batch_result(project_id: str, job_id: str, _token=Depends(require_api_token)):
    project = _tabular_project(project_id)
    layout = ProjectLayout.from_project(project)
    job_dir = layout.inference_job_dir(job_id).resolve()
    if layout.inference_jobs_dir().resolve() not in job_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid inference job path.")
    path = job_dir / "predictions.csv"
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Prediction file not found.")
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}_predictions.csv")


def _tabular_project(project_id: str) -> Dict[str, Any]:
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not str(project.get("task_type") or "").lower().startswith("tabular_"):
        raise HTTPException(status_code=400, detail="This endpoint requires a Tabular project.")
    return project


def _discard_failed_job(job_dir: Path) -> None:
    """Remove only the just-created failed job; completed user results are untouched."""
    try:
        for child in job_dir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        job_dir.rmdir()
    except OSError:
        pass


def _inference_service(project: Dict[str, Any], run_id: Optional[str], model_id: Optional[str]):
    from src.model_registry import ModelRegistry
    from src.tabular_xgboost_inference import TabularXGBoostInferenceService

    layout = ProjectLayout.from_project(project)
    resolved_run_id = str(run_id or "").strip()
    if model_id:
        model = ModelRegistry.resolve_model(project, model_id)
        if str(model.get("architecture") or "").lower() != "tabular":
            raise ValueError("Selected model is not a Tabular model.")
        resolved_run_id = str(model.get("run_id") or "")
    if not resolved_run_id:
        completed = [
            item for item in project.get("training_runs") or []
            if isinstance(item, dict)
            and item.get("status") == "completed"
            and str(item.get("architecture") or "").lower() == "tabular"
        ]
        completed.sort(key=lambda item: item.get("completed_at") or "", reverse=True)
        resolved_run_id = str((completed[0] if completed else {}).get("run_id") or "")
    if not resolved_run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in resolved_run_id):
        raise ValueError("A valid completed Tabular run is required.")
    registered_runs = [
        item for item in project.get("training_runs") or []
        if isinstance(item, dict) and str(item.get("run_id") or "") == resolved_run_id
    ]
    if (
        not registered_runs
        or str(registered_runs[0].get("status") or "").lower() != "completed"
        or str(registered_runs[0].get("architecture") or "").lower() != "tabular"
    ):
        raise ValueError("A valid completed Tabular run is required.")
    run_dir = layout.training_run_dir(resolved_run_id).resolve()
    if layout.training_runs_dir().resolve() not in run_dir.parents:
        raise ValueError("Run path must stay inside the active project.")
    return TabularXGBoostInferenceService.load_from_run(run_dir, trusted_root=layout.project_dir), resolved_run_id

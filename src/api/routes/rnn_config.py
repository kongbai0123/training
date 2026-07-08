from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.training.rnn_readiness import build_rnn_readiness_report
from src.training.rnn_config import (
    active_rnn_config,
    build_suggested_config,
    build_window_summary,
    find_config_mismatches,
    import_sequence_dataset,
    inspect_sequence_csv_files,
    update_project_rnn_config,
    validate_rnn_config,
)

router = APIRouter()

class RNNConfigRequest(BaseModel):
    feature_columns: List[str] = []
    target_column: str = ""
    sequence_column: str = ""
    time_column: Optional[str] = ""
    sequence_length: int = 16
    stride: int = 8
    horizon: int = 1
    task_head: Optional[str] = "classification"



@router.get("/api/projects/{project_id}/rnn/readiness")
def get_rnn_readiness(
    project_id: str,
    sequence_length: int = 16,
    stride: int = 8,
    horizon: int = 1,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sequence_length = max(1, int(sequence_length or 16))
    stride = max(1, int(stride or 8))
    horizon = max(1, int(horizon or 1))
    return build_rnn_readiness_report(
        project,
        sequence_length=sequence_length,
        stride=stride,
        horizon=horizon,
    )


@router.get("/api/projects/{project_id}/rnn/config")
def get_rnn_config(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    csv_files = sorted(layout.sequences_dir().glob("*.csv")) if layout.sequences_dir().exists() else []
    inspection = inspect_sequence_csv_files(csv_files) if csv_files else {
        "files": [],
        "headers": [],
        "headers_match": True,
        "row_count": 0,
        "sequence_count": 0,
        "split_counts": {},
        "feature_columns": [],
        "feature_dim": 0,
        "preview_rows": [],
    }
    config = active_rnn_config(project)
    validation = validate_rnn_config(config, inspection)
    return {
        "config": config,
        "inspection": inspection,
        "recommendation": build_suggested_config(project, inspection),
        "validation": validation,
        "window": build_window_summary(config, inspection),
        "mismatches": find_config_mismatches(project),
    }


@router.post("/api/projects/{project_id}/rnn/config")
def save_rnn_config(project_id: str, request: RNNConfigRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return update_project_rnn_config(project_id, project, request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/rnn/dataset/import")
def import_rnn_sequence_dataset(project_id: str, file: UploadFile = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        result = import_sequence_dataset(project, file)
        config_result = update_project_rnn_config(project_id, project, result["suggested_config"])
        return {
            "success": True,
            "dataset": result,
            "config": config_result.get("config"),
            "recommendation": config_result.get("recommendation") or result.get("suggested_config"),
            "validation": config_result.get("validation"),
            "window": config_result.get("window"),
            "mismatches": config_result.get("mismatches", []),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))



import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import require_api_token
from src.feature_gate import require_feature
from src.project_manager import ProjectManager
from src.training.compare_service import CompareService, CompareServiceError
from src.training.export_service import ExportableModelNotFound, ExportService, ExportServiceError
from src.training.output_compare_service import CNNOutputCompareService, OutputCompareServiceError
from src.training.start_service import TrainingReadinessError, TrainingRunAlreadyExists, TrainingStartService

router = APIRouter()

LOCAL_TRUSTED_MODE = os.environ.get("LOCAL_TRUSTED_MODE", "false").lower() in ("true", "1", "yes")

class TrainConfigRequest(BaseModel):
    model: str
    epochs: int
    batch_size: int
    imgsz: int
    lr0: float
    device: str
    patience: Optional[int] = 20
    workers: Optional[int] = 4
    cache: Optional[bool] = False
    amp: Optional[bool] = True
    seed: Optional[int] = 42
    save_period: Optional[int] = 5
    close_mosaic: Optional[int] = 10
    optimizer: Optional[str] = "auto"
    run_id: Optional[str] = None
    backend: Optional[str] = None
    sequence_length: Optional[int] = None
    stride: Optional[int] = None
    horizon: Optional[int] = None
    task_head: Optional[str] = None
    hidden_size: Optional[int] = None
    num_layers: Optional[int] = None
    dropout: Optional[float] = None
    bidirectional: Optional[bool] = None
    gradient_clip_norm: Optional[float] = None
    early_stopping_patience: Optional[int] = None



class CompareRequest(BaseModel):
    architecture: str
    run_ids: List[str]
    baseline_run_id: Optional[str] = None



@router.post("/api/projects/{project_id}/train/start")
def start_training(project_id: str, config: TrainConfigRequest):
    require_feature("training")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return TrainingStartService.start(project_id, project, config)
    except TrainingRunAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except TrainingReadinessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.get("/api/projects/{project_id}/compare/runs")
def list_compare_runs(project_id: str, architecture: str = "cnn"):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.list_comparable_runs(project, architecture)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/compare")
def compare_project_runs(project_id: str, request: CompareRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.compare_runs(
            project=project,
            architecture=request.architecture,
            run_ids=request.run_ids,
            baseline_run_id=request.baseline_run_id,
        )
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/compare/report")
def export_compare_report(project_id: str, request: CompareRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.export_report(
            project=project,
            architecture=request.architecture,
            run_ids=request.run_ids,
            baseline_run_id=request.baseline_run_id,
        )
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects/{project_id}/compare/reports")
def list_compare_reports(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.list_reports(project)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/api/projects/{project_id}/compare/reports/{report_id}")
def delete_compare_report(project_id: str, report_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.delete_report(project, report_id)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects/{project_id}/compare/reports/{report_id}/download/{filename}")
def download_compare_report_file(project_id: str, report_id: str, filename: str, _token=Depends(require_api_token)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        file_path, media_type = CompareService.resolve_report_file(project, report_id, filename)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(str(file_path), filename=filename, media_type=media_type)


@router.post("/api/projects/{project_id}/compare/output-image")
async def compare_project_image_outputs(
    project_id: str,
    run_ids_json: str = Form(...),
    conf: float = Form(0.25),
    iou: float = Form(0.7),
    imgsz: int = Form(640),
    device: str = Form("cpu"),
    mask_opacity: float = Form(0.45),
    show_mask: bool = Form(True),
    show_bbox: bool = Form(True),
    class_filter: Optional[str] = Form(None),
    image_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    require_feature("inference")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        run_ids = CNNOutputCompareService.parse_run_ids(run_ids_json)
        input_path = CNNOutputCompareService.resolve_image_input(
            project,
            upload=file,
            image_path=image_path,
            local_trusted_mode=LOCAL_TRUSTED_MODE,
        )

        return CNNOutputCompareService.compare_image_outputs(
            project=project,
            run_ids=run_ids,
            input_path=input_path,
            settings={
                "conf": conf,
                "iou": iou,
                "imgsz": imgsz,
                "device": device,
                "mask_opacity": mask_opacity,
                "show_mask": show_mask,
                "show_bbox": show_bbox,
                "class_filter": class_filter,
                "original_filename": Path(file.filename).name if file and file.filename else (Path(image_path).name if image_path else ""),
            },
        )
    except OutputCompareServiceError as exc:
        status_code = 403 if "Local image path compare requires Local Trusted Mode" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))




# Export API.
@router.get("/api/projects/{project_id}/exports")
def list_exports(project_id: str, limit: int = 12):
    require_feature("export_onnx")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ExportService.list_project_exports(project, limit=limit)


@router.get("/api/projects/{project_id}/export")
def export_model(
    project_id: str,
    run_id: Optional[str] = None,
    model_id: Optional[str] = None,
    format: Optional[str] = None,
):
    require_feature("export_onnx")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return ExportService.export_project_model(
            project_id,
            project,
            run_id=run_id,
            model_id=model_id,
            export_format=format,
        )
    except ExportableModelNotFound as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExportServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc))




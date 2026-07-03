import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import require_api_token
from src.feature_gate import require_feature
from src.inference_engine import InferenceEngine
from src.inference_history import InferenceHistory
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.rnn_inference_engine import RNNSequenceInferenceEngine

router = APIRouter()

LOCAL_TRUSTED_MODE = os.environ.get("LOCAL_TRUSTED_MODE", "false").lower() in ("true", "1", "yes")


class DeleteInferenceJobsRequest(BaseModel):
    job_ids: List[str]
    confirm: bool = False


@router.post("/api/projects/{project_id}/inference/image")
async def run_image_inference(
    project_id: str,
    model_id: str = Form(...),
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
        model = ModelRegistry.resolve_model(project, model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    inference_dirs = ModelRegistry.ensure_inference_dirs(project)

    try:
        if file and file.filename:
            import uuid

            ext = Path(file.filename).suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                raise HTTPException(status_code=400, detail="Only image files are supported")
            safe_name = f"upload_{uuid.uuid4().hex}{ext}"
            input_path = inference_dirs["inputs_images"] / safe_name
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        elif image_path:
            if not LOCAL_TRUSTED_MODE:
                raise HTTPException(status_code=403, detail="image_path requires Local Trusted Mode.")
            try:
                from src.security_utils import safe_resolve_under

                project_base = ProjectLayout.from_project(project).project_dir.resolve()
                input_path = safe_resolve_under(project_base, Path(image_path))
            except ValueError as e:
                raise HTTPException(status_code=403, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail="Please provide an image file or image_path")

        return InferenceEngine.run_image_inference(
            project=project,
            model=model,
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
                "original_filename": Path(file.filename).name
                if file and file.filename
                else (Path(image_path).name if image_path else ""),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/projects/{project_id}/inference/sequence")
async def run_sequence_inference(
    project_id: str,
    model_id: str = Form(...),
    device: str = Form("cpu"),
    csv_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    require_feature("inference")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        model = ModelRegistry.resolve_model(project, model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    inference_dirs = ModelRegistry.ensure_inference_dirs(project)
    inputs_dir = inference_dirs["jobs"].parent / "inputs" / "sequences"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    try:
        if file and file.filename:
            import uuid

            ext = Path(file.filename).suffix.lower()
            if ext != ".csv":
                raise HTTPException(status_code=400, detail="Only CSV feature sequence files are supported")
            safe_name = f"upload_{uuid.uuid4().hex}{ext}"
            input_path = inputs_dir / safe_name
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        elif csv_path:
            if not LOCAL_TRUSTED_MODE:
                raise HTTPException(status_code=403, detail="Local CSV path inference requires Local Trusted Mode")
            try:
                from src.security_utils import safe_resolve_under

                project_base = ProjectLayout.from_project(project).project_dir.resolve()
                input_path = safe_resolve_under(project_base, Path(csv_path))
            except ValueError as e:
                raise HTTPException(status_code=403, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail="Please provide a CSV file or csv_path")

        return RNNSequenceInferenceEngine.run_csv_sequence_inference(
            project=project,
            model=model,
            input_path=input_path,
            settings={
                "device": device,
                "original_filename": Path(file.filename).name
                if file and file.filename
                else (Path(csv_path).name if csv_path else ""),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/projects/{project_id}/inference/jobs/{job_id}/files/{filename}")
def get_inference_job_file(project_id: str, job_id: str, filename: str, _token=Depends(require_api_token)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    layout = ProjectLayout.from_project(project)
    jobs_root = layout.inference_jobs_dir().resolve()
    job_dir = (jobs_root / job_id).resolve()
    if jobs_root not in job_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid job path")

    file_path = (job_dir / safe_filename).resolve()
    if job_dir not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Inference file not found")

    return FileResponse(str(file_path))


@router.get("/api/projects/{project_id}/inference/jobs")
def list_inference_jobs(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return InferenceHistory.list_jobs(project)


@router.post("/api/projects/{project_id}/inference/jobs/delete")
def delete_inference_jobs(project_id: str, request: DeleteInferenceJobsRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirmation")
    try:
        return InferenceHistory.delete_jobs(project, request.job_ids, confirm=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects/{project_id}/inference/jobs/{job_id}")
def get_inference_job(project_id: str, job_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return InferenceHistory.get_job(project, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Inference job not found")

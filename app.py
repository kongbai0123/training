import os
import json
import base64
import shutil
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import mimetypes

# MIME helper for browser static assets on Windows
mimetypes.add_type("application/javascript", ".js", strict=True)
mimetypes.add_type("text/css", ".css", strict=True)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect, Header, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from PIL import Image
from src.config import APP_ENV, APP_VERSION, BASE_DIR, PROJECTS_DIR, STATIC_DIR, VERSION_INFO, HAS_GPU, DEVICE_NAME
from src.project_manager import ProjectManager
from src.project_layout import ProjectLayout
from src.dataset_utils import DatasetUtils
from src.splitter import DataSplitter
from src.augmenter import ImageAugmenter
from src.trainer import YOLOTrainer
from src.training.compare_service import CompareService, CompareServiceError
from src.training.dispatcher import TrainerDispatcher
from src.training.output_compare_service import CNNOutputCompareService, OutputCompareServiceError
from src.training.rnn_readiness import build_rnn_readiness_report
from src.training.rnn_config import (
    active_rnn_config,
    build_window_summary,
    find_config_mismatches,
    import_sequence_dataset,
    inspect_sequence_csv_files,
    update_project_rnn_config,
    validate_rnn_config,
)
from src.labelme_adapter import LabelMeAdapter
from src.annotation_importer import AnnotationImporter
from src.model_registry import ModelRegistry
from src.model_store import ModelStore
from src.model_system import ModelCatalog
from src.inference_engine import InferenceEngine
from src.inference_history import InferenceHistory
from src.rnn_inference_engine import RNNSequenceInferenceEngine
from src.project_migrator import ProjectMigrator
from src.project_data_migration import ProjectDataMigrationTool
from src.local_session import current_bootstrap, validate_token
from src.feature_gate import require_feature
from src.license_manager import build_license_report
from src.diagnostics import generate_diagnostics_zip
from ultralytics import YOLO

APP_IS_PRODUCTION = APP_ENV in {"production", "prod"}
app = FastAPI(title="Vision Training Studio API")

if APP_IS_PRODUCTION:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

LOCAL_TRUSTED_MODE = os.environ.get("LOCAL_TRUSTED_MODE", "false").lower() in ("true", "1", "yes")
# ??? API ??????芰??賤??瞉?????

@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "API_ERROR",
                "message": exc.detail,
                "details": {}
            }
        }
    )


def require_api_token(token: str = Header(default="", alias="X-VTS-Token")) -> None:
    if not validate_token(token):
        raise HTTPException(
            status_code=401,
            detail=_build_error("AUTH_REQUIRED", "Missing or invalid local session token", 401),
        )

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors()
            }
        }
    )

@app.exception_handler(Exception)
def general_exception_handler(request, exc):
    if APP_IS_PRODUCTION:
        return JSONResponse(status_code=500, content=_build_error("INTERNAL_SERVER_ERROR", "Server error", 500))
    return JSONResponse(
        status_code=500,
        content=_build_error("INTERNAL_SERVER_ERROR", str(exc), 500),
    )


def _build_error(code: str, message, status_code: int = 500):
    safe_message = message if not APP_IS_PRODUCTION else "Server error" if status_code >= 500 else message
    return {
        "success": False,
        "error": {
            "code": code,
            "message": safe_message,
            "details": {},
        },
    }


@app.middleware("http")
async def protect_mutating_api(request: Request, call_next):
    if not APP_IS_PRODUCTION:
        return await call_next(request)

    method = request.method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)

    if path.startswith("/api/health") or path.startswith("/api/bootstrap") or path.startswith("/api/version"):
        return await call_next(request)

    token = request.headers.get("X-VTS-Token") or request.headers.get("x-vts-token")
    if not validate_token(token or ""):
        return JSONResponse(
            status_code=401,
            content=_build_error("AUTH_REQUIRED", "Missing or invalid local session token", 401),
        )

    return await call_next(request)

def find_labelme_executable() -> Optional[str]:
    executable = shutil.which("labelme")
    if executable:
        return executable

    scripts_dir = Path(sys.executable).parent
    candidates = []
    if os.name == "nt":
        candidates.extend([
            scripts_dir / "labelme.exe",
            Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "venv" / "Scripts" / "labelme.exe",
        ])
    else:
        candidates.extend([
            scripts_dir / "labelme",
            Path.home() / ".local" / "bin" / "labelme",
        ])

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None

def normalize_labelme_image_paths(images_dir: Path, labelme_dir: Path) -> int:
    if not labelme_dir.exists():
        return 0

    normalized = 0
    for json_path in labelme_dir.glob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        image_path = data.get("imagePath") or f"{json_path.stem}.jpg"
        image_name = Path(image_path).name
        source_image = images_dir / image_name
        if not source_image.exists():
            continue

        normalized_path = source_image.resolve().as_posix()
        if data.get("imagePath") == normalized_path:
            continue

        data["imagePath"] = normalized_path
        data["imageData"] = None
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        normalized += 1
    return normalized

# 1. ????祈???
# ?? static/ ??????梁????
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static")

# ?撖??隞?????index.html
@app.get("/")
def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return {"message": "Vision Training Studio backend is running. static/index.html not found."}
    return FileResponse(str(index_path))

@app.get("/api/version")
def get_version():
    return VERSION_INFO

@app.get("/api/bootstrap")
def bootstrap():
    return current_bootstrap(APP_VERSION, APP_ENV)

@app.get("/api/health")
def health_check():
    torch_version = "Not installed"
    has_gpu = False
    device_name = "CPU"
    memory = {
        "available_gb": None,
        "total_gb": None,
        "percent_used": None,
        "status": "unavailable",
    }
    try:
        import torch
        torch_version = torch.__version__
        has_gpu = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if has_gpu else "CPU"
    except Exception:
        pass
    try:
        import psutil
        ram = psutil.virtual_memory()
        memory = {
            "available_gb": round(ram.available / (1024 ** 3), 1),
            "total_gb": round(ram.total / (1024 ** 3), 1),
            "percent_used": round(ram.percent, 1),
            "status": "available",
        }
    except Exception:
        pass

    return {
        "status": "healthy",
        "mode": APP_ENV,
        "version": APP_VERSION,
        "local_trusted_mode": LOCAL_TRUSTED_MODE,
        "device": {
            "has_gpu": has_gpu,
            "device_name": device_name,
            "torch_version": torch_version,
        },
        "memory": memory,
        "directories": {
            "base_dir": str(BASE_DIR.resolve().as_posix()),
            "projects_dir": str(PROJECTS_DIR.resolve().as_posix()),
            "static_dir": str(STATIC_DIR.resolve().as_posix()),
        },
        "license": build_license_report()
    }


@app.get("/api/diagnostics/report")
def export_diagnostics_report(_token=Depends(require_api_token)):
    report_path = generate_diagnostics_zip()
    return FileResponse(str(report_path), filename=report_path.name, media_type="application/zip")

# --- Pydantic Models ---
class ProjectDataMigrationRequest(BaseModel):
    project_ids: Optional[List[str]] = None
    delete_source: bool = False

class ProjectCreate(BaseModel):
    project_name: str
    task_type: str
    class_names: List[str]

class AnnotationSave(BaseModel):
    filename: str
    status: str # annotated, flagged, skipped
    scene: Optional[str] = "unknown"
    source_video: Optional[str] = ""
    annotations: List[Dict[str, Any]]

class SplitRequest(BaseModel):
    method: str # basic, stratified, scene, group
    ratio: Dict[str, float] # e.g. {"train": 0.7, "val": 0.2, "test": 0.1}

class AugmentPreviewRequest(BaseModel):
    filename: str
    config: Dict[str, Any]

def normalize_augmentation_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config or {})
    camera_cfg = dict(normalized.get("camera", {}) or {})
    camera_cfg["perspective"] = 0
    normalized["camera"] = camera_cfg
    return normalized

def get_applied_augmentation_parameters(config: Dict[str, Any]) -> List[str]:
    params = []
    light_cfg = config.get("light", {}) or {}
    weather_cfg = config.get("weather", {}) or {}
    motion_cfg = config.get("motion", {}) or {}
    camera_cfg = config.get("camera", {}) or {}
    if float(light_cfg.get("brightness", 0) or 0) != 0:
        params.append("brightness")
    if float(light_cfg.get("contrast", 0) or 0) != 0:
        params.append("contrast")
    if bool(light_cfg.get("shadow", False)):
        params.append("shadow")
    if float(weather_cfg.get("rain", 0) or 0) > 0:
        params.append("rain")
    if float(weather_cfg.get("fog", 0) or 0) > 0:
        params.append("fog")
    if float(motion_cfg.get("motion_blur", 0) or 0) > 0:
        params.append("motion_blur")
    if float(camera_cfg.get("noise", 0) or 0) > 0:
        params.append("camera_noise")
    return params

def append_project_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

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


class RNNConfigRequest(BaseModel):
    feature_columns: List[str] = []
    target_column: str = ""
    sequence_column: str = ""
    time_column: Optional[str] = ""
    sequence_length: int = 16
    stride: int = 8
    horizon: int = 1
    task_head: Optional[str] = "classification"


class CompareRequest(BaseModel):
    architecture: str
    run_ids: List[str]
    baseline_run_id: Optional[str] = None


class DeleteModelWeightsRequest(BaseModel):
    model_ids: List[str]
    confirm: bool = False
# --- API Endpoints ---

# 1. ????? API
@app.get("/api/projects/data-migration/scan")
def scan_project_data_migration():
    return ProjectDataMigrationTool.scan()

@app.post("/api/projects/data-migration/apply")
def apply_project_data_migration(request: ProjectDataMigrationRequest):
    return ProjectDataMigrationTool.migrate(
        project_ids=request.project_ids,
        delete_source=request.delete_source,
    )

@app.get("/api/projects")
def list_projects():
    return ProjectManager.get_all_projects()

@app.post("/api/projects")
def create_project(data: ProjectCreate):
    try:
        project = ProjectManager.create_project(data.project_name, data.task_type, data.class_names)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@app.get("/api/projects/{project_id}/layout")
def get_project_layout(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectLayout.from_project(project).get_layout_report()

@app.post("/api/projects/{project_id}/layout/migration/dry-run")
def dry_run_layout_migration(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectMigrator.dry_run(project)

@app.post("/api/projects/{project_id}/layout/migration/apply")
def apply_layout_migration(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return ProjectMigrator.apply(project)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/save")
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

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or unable to delete")
    return {"message": "Project deleted successfully"}
@app.get("/api/projects/{project_id}/models")
def list_project_models(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ModelRegistry.list_models(project)


@app.post("/api/projects/{project_id}/models/weights/delete")
def delete_project_model_weights(project_id: str, request: DeleteModelWeightsRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation")

    model_ids = [str(model_id).strip() for model_id in request.model_ids if str(model_id).strip()]
    if not model_ids:
        raise HTTPException(status_code=400, detail="No model weights selected")
    if len(model_ids) > 50:
        raise HTTPException(status_code=400, detail="Too many model weights selected")

    layout = ProjectLayout.from_project(project)
    runs_dir = (layout.project_dir / "training" / "runs").resolve()
    deleted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for model_id in dict.fromkeys(model_ids):
        try:
            model = ModelRegistry.resolve_model(project, model_id)
            weight_type = str(model.get("weight_type") or "").lower()
            if weight_type not in {"best", "last"}:
                skipped.append({"model_id": model_id, "reason": "unsupported_weight_type"})
                continue

            weight_path = Path(model.get("internal_weight_path") or "").resolve()
            if runs_dir not in weight_path.parents:
                skipped.append({"model_id": model_id, "reason": "outside_training_runs"})
                continue
            if weight_path.name not in {"best.pt", "last.pt"}:
                skipped.append({"model_id": model_id, "reason": "unsupported_filename"})
                continue
            if not weight_path.exists() or not weight_path.is_file():
                skipped.append({"model_id": model_id, "reason": "missing_file"})
                continue

            file_size = weight_path.stat().st_size
            weight_path.unlink()
            deleted.append({
                "model_id": model_id,
                "run_id": model.get("run_id"),
                "weight_type": weight_type,
                "path": model.get("weight_path_display"),
                "file_size": file_size,
            })
        except ValueError:
            skipped.append({"model_id": model_id, "reason": "not_found"})
        except Exception as exc:
            skipped.append({"model_id": model_id, "reason": f"delete_failed: {exc}"})

    return {
        "success": True,
        "deleted": deleted,
        "skipped": skipped,
        "remaining_count": len(ModelRegistry.list_models(project)),
    }


@app.get("/api/projects/{project_id}/models/catalog")
def list_project_model_catalog(
    project_id: str,
    architecture: Optional[str] = Query(None),
    usage: str = Query("train"),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    task_family = project.get("task_type")
    if usage == "inference":
        models = ModelCatalog.list_inference_supported(project=project, task_family=task_family, architecture=architecture)
    elif usage == "all":
        models = ModelCatalog.list_all(project=project, architecture=architecture)
    else:
        models = ModelCatalog.list_trainable(project=project, task_family=task_family, architecture=architecture)
    return {
        "project_id": project_id,
        "architecture": architecture,
        "usage": usage,
        "task_family": task_family,
        "models": models,
    }


@app.post("/api/projects/{project_id}/models/import/yolo-pt")
def import_project_yolo_pt_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or not file.filename.lower().endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only YOLO .pt model files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_yolo_pt(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Model import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/projects/{project_id}/models/import/yolo-yaml")
def import_project_yolo_yaml_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(status_code=400, detail="Only YOLO model architecture .yaml / .yml files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_yolo_yaml(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Model YAML import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/projects/{project_id}/models/import/onnx")
def import_project_onnx_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".onnx":
        raise HTTPException(status_code=400, detail="Only .onnx model files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_onnx(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["ONNX import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/projects/{project_id}/models/import/rnn-package")
def import_project_rnn_package_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only .zip RNN model packages are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_rnn_package(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["RNN package import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/projects/{project_id}/models/import/custom-package")
def import_project_custom_package_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only .zip custom model packages are supported in Phase P1-A")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_custom_package(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Custom package validation failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/request")
def request_custom_package_dry_run(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.request_custom_package_dry_run(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package dry-run request failed"))
    return result


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/approval")
def approve_custom_package_dry_run(
    project_id: str,
    model_id: str,
    decision: str = Form(...),
    approved_by: str = Form("local_user"),
    note: str = Form(""),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = ModelCatalog.record_custom_package_dry_run_approval(
            project,
            model_id,
            decision=decision,
            approved_by=approved_by,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package dry-run approval failed"))
    return result


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/mock")
def run_custom_package_mock_dry_run(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.run_custom_package_mock_dry_run(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("dry_run", result.get("error", "Custom package mock dry-run failed")))
    return result


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/plan")
def build_custom_package_sandbox_plan(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.build_custom_package_sandbox_plan(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("plan", result.get("error", "Custom package sandbox plan failed")))
    return result


@app.get("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/audit")
def get_custom_package_sandbox_audit(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.get_custom_package_sandbox_audit(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package sandbox audit failed"))
    return result


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/enablement")
def evaluate_custom_package_enablement(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.evaluate_custom_package_enablement(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package enablement policy failed"))
    return result


@app.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/integration")
def build_custom_package_integration_contract(
    project_id: str,
    model_id: str,
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.build_custom_package_integration_contract(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package integration contract failed"))
    return result


@app.get("/api/models/weights")
def list_model_store_weights():
    models_dir = ModelStore.models_dir()
    weights = []
    for path in sorted(models_dir.rglob("*.pt")):
        if not path.is_file():
            continue
        try:
            resolved = ModelStore.validate_model_store_path(path)
            rel = resolved.relative_to(models_dir).as_posix()
            stat = resolved.stat()
            weights.append({
                "name": resolved.name,
                "path": rel,
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except ValueError:
            continue
    return {"models_dir": models_dir.as_posix(), "weights": weights}

@app.post("/api/projects/{project_id}/inference/image")
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
                raise HTTPException(status_code=403, detail="?蟡???????????(Local Trusted Mode ??)")
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
                "original_filename": Path(file.filename).name if file and file.filename else (Path(image_path).name if image_path else "")
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/projects/{project_id}/inference/sequence")
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
            settings={"device": device, "original_filename": Path(file.filename).name if file and file.filename else (Path(csv_path).name if csv_path else "")},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/projects/{project_id}/auto-labeling/status")
def get_auto_labeling_status(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layout = ProjectLayout.from_project(project)
    jobs_root = layout.project_dir / "auto_labeling" / "jobs"
    drafts_root = layout.project_dir / "annotations" / "drafts" / "auto_label"
    jobs = []
    if jobs_root.exists():
        for job_dir in sorted(jobs_root.iterdir(), reverse=True):
            if not job_dir.is_dir():
                continue
            summary = {"job_id": job_dir.name, "status": "draft"}
            summary_path = job_dir / "summary.json"
            if summary_path.exists():
                try:
                    summary.update(json.loads(summary_path.read_text(encoding="utf-8")))
                except Exception:
                    pass
            jobs.append(summary)
    return {"jobs": jobs, "jobs_dir": jobs_root.resolve().as_posix(), "drafts_dir": drafts_root.resolve().as_posix()}

@app.post("/api/projects/{project_id}/auto-labeling/jobs")
def create_auto_labeling_job(project_id: str, req: Dict[str, Any]):
    require_feature("auto_labeling")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layout = ProjectLayout.from_project(project)
    job_id = req.get("job_id") or f"al_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    job_dir = layout.auto_label_job_dir(job_id)
    draft_dir = layout.auto_label_draft_dir(job_id)
    for path in [
        job_dir / "inputs",
        job_dir / "previews",
        job_dir / "predictions",
        job_dir / "annotations" / "labelme",
        job_dir / "annotations" / "yolo",
        job_dir / "annotations" / "coco",
        job_dir / "review",
        draft_dir / "labelme",
        draft_dir / "yolo",
        draft_dir / "coco",
        draft_dir / "masks",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    config = {
        "job_id": job_id,
        "created_at": datetime.now().isoformat(),
        "model_id": req.get("model_id"),
        "mode": req.get("mode", "suggest"),
        "source": req.get("source", "dataset"),
        "status": "draft",
    }
    (job_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (job_dir / "summary.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"job_id": job_id, "status": "draft", "job_dir": job_dir.resolve().as_posix(), "draft_dir": draft_dir.resolve().as_posix()}

@app.post("/api/projects/{project_id}/auto-labeling/jobs/{job_id}/accept")
def accept_auto_labeling_job(project_id: str, job_id: str):
    require_feature("auto_labeling")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layout = ProjectLayout.from_project(project)
    draft_dir = layout.auto_label_draft_dir(job_id)
    if not draft_dir.exists():
        raise HTTPException(status_code=404, detail="Draft job not found")

    version_id = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}_auto_label_{job_id}"
    version_dir = layout.annotation_version_dir(version_id)
    copied = []
    for name, target_dir in [
        ("labelme", layout.resolve_current_labelme_dir().path),
        ("yolo", layout.resolve_current_yolo_labels_dir().path),
        ("coco", layout.project_dir / "annotations" / "current" / "coco"),
        ("masks", layout.resolve_current_masks_dir().path),
    ]:
        source_dir = draft_dir / name
        if not source_dir.exists():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        version_target = version_dir / name
        version_target.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, target_dir / item.name)
                shutil.copy2(item, version_target / item.name)
                copied.append(f"{name}/{item.name}")
    if "current" not in project:
        project["current"] = {}
    project["current"]["annotation_version"] = version_id
    ProjectManager.save_project(project_id, project)
    return {"accepted": True, "job_id": job_id, "annotation_version": version_id, "copied": copied}

@app.get("/api/projects/{project_id}/inference/jobs/{job_id}/files/{filename}")
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

@app.get("/api/projects/{project_id}/inference/jobs")
def list_inference_jobs(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return InferenceHistory.list_jobs(project)

@app.get("/api/projects/{project_id}/inference/jobs/{job_id}")
def get_inference_job(project_id: str, job_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return InferenceHistory.get_job(project, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Inference job not found")

# 2. ???????? API
@app.get("/api/projects/{project_id}/images/{filename}")
def get_project_image(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    img_path = layout.resolve_raw_images_dir().path / filename
    # ?鈭?raw ????????augmented_images ??(????皜??嚗???)
    if not img_path.exists():
        img_meta = next((img for img in project.get("images", []) if img.get("filename") == filename), {})
        aug_job_id = img_meta.get("augmentation_job_id") or img_meta.get("aug_job_id")
        if aug_job_id:
            img_path = layout.augmentation_outputs_dir(aug_job_id) / "images" / filename
        else:
            img_path = layout.resolve_legacy_augmented_images_dir().path / filename

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(img_path))

@app.post("/api/projects/{project_id}/import-local")
def import_local_folder(project_id: str, path: str = Form(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    import_path = Path(path)
    if not import_path.exists() or not import_path.is_dir():
        raise HTTPException(status_code=400, detail="Path does not exist or is not a folder")

    layout = ProjectLayout.from_project(project)
    dest_dir = layout.resolve_raw_images_dir().path
    dest_dir.mkdir(parents=True, exist_ok=True)
    imported = []

    # ???????
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    import hashlib

    for f in import_path.iterdir():
        if f.is_file() and f.suffix.lower() in valid_exts:
            dest_file = dest_dir / f.name
            shutil.copy(str(f), str(dest_file))
            try:
                sha = hashlib.sha256(dest_file.read_bytes()).hexdigest()
            except Exception:
                sha = ""
            imported.append((f.name, sha))

    # ?皝?project.json ??
    for fname, sha in imported:
        # ?頦????
        if any(img["filename"] == fname for img in project["images"]):
            continue

        project["images"].append({
            "filename": fname,
            "status": "unannotated",
            "scene": "unknown",
            "source_video": "",
            "annotations": [],
            "split": None,
            "quality": {},
            "sha256": sha
        })

    project["annotation_progress"]["total"] = len(project["images"])
    ProjectManager.save_project(project_id, project)

    return {"message": f"Imported {len(imported)} images.", "imported": [x[0] for x in imported]}

@app.post("/api/projects/{project_id}/import-video")
def import_video(project_id: str, video_path: str = Form(...), fps: int = Form(1)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    v_path = Path(video_path)
    if not v_path.exists() or not v_path.is_file():
        raise HTTPException(status_code=400, detail="Video file does not exist")

    layout = ProjectLayout.from_project(project)
    dest_dir = layout.resolve_raw_images_dir().path
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        filenames = DatasetUtils.extract_frames(str(v_path), str(dest_dir), fps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"?鞈??剜??: {str(e)}")

    import hashlib
    # ??蝞??? project.json ?????source_video
    for fname in filenames:
        if any(img["filename"] == fname for img in project["images"]):
            continue

        img_file = dest_dir / fname
        try:
            sha = hashlib.sha256(img_file.read_bytes()).hexdigest()
        except Exception:
            sha = ""

        project["images"].append({
            "filename": fname,
            "status": "unannotated",
            "scene": "unknown",
            "source_video": v_path.name, # ????? Group Split
            "annotations": [],
            "split": None,
            "quality": {},
            "sha256": sha
        })

    project["annotation_progress"]["total"] = len(project["images"])
    ProjectManager.save_project(project_id, project)

    return {"message": f"Extracted {len(filenames)} frames.", "imported_count": len(filenames)}

@app.post("/api/projects/{project_id}/upload-video")
def upload_video(project_id: str, file: UploadFile = File(...), fps: int = Form(1)):
    import uuid
    original_name = Path(file.filename or "upload.mp4").name
    suffix = Path(original_name).suffix.lower()

    if suffix not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = f"{uuid.uuid4().hex}{suffix}"
    temp_dir = Path(project["dataset_path"]) / ".tmp_video_upload"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_video_path = temp_dir / safe_filename

    try:
        # ????????
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        layout = ProjectLayout.from_project(project)
        dest_dir = layout.resolve_raw_images_dir().path
        dest_dir.mkdir(parents=True, exist_ok=True)
        filenames = DatasetUtils.extract_frames(str(temp_video_path), str(dest_dir), fps)

        # ??蝞??嗆?? project.json
        import hashlib
        for fname in filenames:
            if any(img["filename"] == fname for img in project["images"]):
                continue

            img_file = dest_dir / fname
            try:
                sha = hashlib.sha256(img_file.read_bytes()).hexdigest()
            except Exception:
                sha = ""

            project["images"].append({
                "filename": fname,
                "status": "unannotated",
                "scene": "unknown",
                "source_video": original_name,
                "annotations": [],
                "split": None,
                "quality": {},
                "sha256": sha
            })

        project["annotation_progress"]["total"] = len(project["images"])
        ProjectManager.save_project(project_id, project)

        return {
            "message": f"Uploaded video and extracted {len(filenames)} frames.",
            "imported_count": len(filenames)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"?嗆???鞈??剜??: {e}")
    finally:
        # ???????
        if temp_video_path.exists():
            os.remove(temp_video_path)
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            shutil.rmtree(temp_dir)


@app.post("/api/projects/{project_id}/upload-images")
def upload_images(
    project_id: str,
    files: List[UploadFile] = File(...),
    batch_id: Optional[str] = Form(None)
):
    import hashlib
    from datetime import datetime
    import uuid

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    image_dir = layout.resolve_raw_images_dir().path
    image_dir.mkdir(parents=True, exist_ok=True)

    image_exts = {".jpg", ".jpeg", ".png", ".bmp"}

    if not batch_id:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}"

    existing_sha256_map = {}  # sha256 -> filename
    existing_name_map = {}    # filename -> img_metadata
    modified_project_images = False

    # 1. ?皜??????????sha256 ??
    for img in project["images"]:
        filename = img["filename"]
        sha = img.get("sha256")
        if not sha:
            img_path = image_dir / filename
            if img_path.exists():
                try:
                    data_bytes = img_path.read_bytes()
                    sha = hashlib.sha256(data_bytes).hexdigest()
                    img["sha256"] = sha
                    modified_project_images = True
                except Exception:
                    sha = ""
            else:
                sha = ""

        if sha:
            existing_sha256_map[sha] = filename
        existing_name_map[filename] = img

    uploaded_count = 0
    duplicate_same_hash = 0
    renamed_same_name_diff_hash = 0
    invalid_count = 0
    skipped_count = 0

    uploaded_files_info = []

    # 2. ????
    for upload in files:
        original_name = Path(upload.filename or "").name
        if not original_name:
            invalid_count += 1
            continue

        ext = Path(original_name).suffix.lower()
        if ext not in image_exts:
            invalid_count += 1
            uploaded_files_info.append({
                "original_name": original_name,
                "stored_name": None,
                "sha256": None,
                "status": "invalid_format"
            })
            continue

        try:
            file_bytes = upload.file.read()
            sha256_val = hashlib.sha256(file_bytes).hexdigest()

            # ?? A: ????啣音??????(?? + ??SHA-256) -> ??
            if original_name in existing_name_map and existing_name_map[original_name].get("sha256") == sha256_val:
                duplicate_same_hash += 1
                skipped_count += 1
                uploaded_files_info.append({
                    "original_name": original_name,
                    "stored_name": original_name,
                    "sha256": sha256_val,
                    "status": "skipped_duplicate"
                })
                continue

            # ?? B: ???閰??踵憳???-> ?????鞈???怨翰?祉?
            stored_name = original_name
            if original_name in existing_name_map:
                prefix = sha256_val[:6]
                stem = Path(original_name).stem
                stored_name = f"{stem}__{prefix}{ext}"
                renamed_same_name_diff_hash += 1

            # ?? C: ?????踵憳???(??SHA-256) -> ??????桀?甇??
            if sha256_val in existing_sha256_map:
                duplicate_same_hash += 1
                skipped_count += 1
                uploaded_files_info.append({
                    "original_name": original_name,
                    "stored_name": existing_sha256_map[sha256_val],
                    "sha256": sha256_val,
                    "status": "skipped_hash_duplicate"
                })
                continue

            # ????
            dest_file_path = image_dir / stored_name
            dest_file_path.write_bytes(file_bytes)
            uploaded_count += 1

            # ????????
            project["images"].append({
                "filename": stored_name,
                "status": "unannotated",
                "scene": "unknown",
                "source_video": "",
                "annotations": [],
                "split": None,
                "quality": {},
                "sha256": sha256_val
            })
            modified_project_images = True

            # ?皝??????mapping
            existing_sha256_map[sha256_val] = stored_name
            existing_name_map[stored_name] = project["images"][-1]

            uploaded_files_info.append({
                "original_name": original_name,
                "stored_name": stored_name,
                "sha256": sha256_val,
                "status": "uploaded" if stored_name == original_name else "renamed"
            })

        except Exception as e:
            invalid_count += 1
            uploaded_files_info.append({
                "original_name": original_name,
                "stored_name": None,
                "sha256": None,
                "status": f"error: {str(e)}"
            })

    # 3. ?皝?????
    if modified_project_images:
        project["annotation_progress"]["total"] = len(project["images"])

    # 4. ??imports_history
    history_item = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "type": "images_upload",
        "uploaded_count": uploaded_count,
        "duplicate_same_hash": duplicate_same_hash,
        "renamed_same_name_diff_hash": renamed_same_name_diff_hash,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count
    }

    if "imports_history" not in project:
        project["imports_history"] = []
    project["imports_history"].append(history_item)

    ProjectManager.save_project(project_id, project)

    return {
        "success": True,
        "batch_id": batch_id,
        "uploaded_count": uploaded_count,
        "duplicate_same_hash": duplicate_same_hash,
        "renamed_same_name_diff_hash": renamed_same_name_diff_hash,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
        "files": uploaded_files_info,
        "errors": []
    }


@app.post("/api/projects/{project_id}/upload-dataset-files")
def upload_dataset_files(project_id: str, files: List[UploadFile] = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    image_dir = layout.resolve_raw_images_dir().path
    labelme_dir = layout.resolve_current_labelme_dir().path
    labels_dir = layout.resolve_current_yolo_labels_dir().path
    image_dir.mkdir(parents=True, exist_ok=True)
    labelme_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    image_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    imported_images = 0
    imported_jsons = 0
    imported_txts = 0
    skipped = 0

    for upload in files:
        filename = Path(upload.filename or "").name
        ext = Path(filename).suffix.lower()
        if not filename:
            skipped += 1
            continue

        if ext in image_exts:
            with open(image_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_images += 1

            if not any(img["filename"] == filename for img in project["images"]):
                project["images"].append({
                    "filename": filename,
                    "status": "unannotated",
                    "scene": "unknown",
                    "source_video": "",
                    "annotations": [],
                    "split": None,
                    "quality": {}
                })
        elif ext == ".json":
            with open(labelme_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_jsons += 1
        elif ext == ".txt":
            with open(labels_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_txts += 1
        else:
            skipped += 1

    if imported_txts > 0:
        LabelMeAdapter.convert_yolo_to_labelme(project)
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    project["annotation_progress"]["total"] = len(project["images"])
    ProjectManager.save_project(project_id, project)

    return {
        "message": "Dataset files uploaded.",
        "imported_images": imported_images,
        "imported_jsons": imported_jsons,
        "imported_txts": imported_txts,
        "skipped": skipped,
        "sync_status": sync_res
    }


@app.post("/api/projects/{project_id}/quality-check")
def trigger_quality_check(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    images_list = project.get("images", [])

    # 1. ????????????
    hashes = {}
    for img in images_list:
        fname = img["filename"]
        img_path = layout.resolve_raw_images_dir().path / fname
        if not img_path.exists():
            continue

        quality = DatasetUtils.analyze_image_quality(str(img_path))
        img["quality"] = quality

        # ?? dHash
        h = DatasetUtils.dhash(str(img_path))
        hashes[fname] = h

    # 2. ?????潘撓 (??????
    for fname, h in hashes.items():
        is_duplicate = False
        for other_fname, other_h in hashes.items():
            if fname == other_fname:
                continue
            if DatasetUtils.hamming_distance(h, other_h) <= 5:
                is_duplicate = True
                break

        # ?????metadata ?????
        for img in images_list:
            if img["filename"] == fname:
                img["quality"]["is_duplicate"] = is_duplicate
                if is_duplicate:
                    img["quality"]["status"] = "yellow"
                    duplicate_warning = "Possible duplicate image"
                    if duplicate_warning not in img["quality"]["warnings"]:
                        img["quality"]["warnings"].append(duplicate_warning)
                break

    # 3. ???皜?????函?瞍?鈭??唳???
    health_report = DatasetUtils.get_dataset_health(images_list)
    project["dataset_health"] = health_report

    ProjectManager.save_project(project_id, project)
    return health_report

# 3. ?? API
@app.post("/api/projects/{project_id}/annotations")
def save_annotations(project_id: str, data: AnnotationSave):
    import numpy as np
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)

    # ???????
    img_path = layout.resolve_raw_images_dir().path / data.filename
    w, h = 640, 640
    if img_path.exists():
        try:
            with Image.open(img_path) as pil_img:
                w, h = pil_img.size
        except Exception:
            pass

    # ?梁?? LabelMe JSON ??
    labelme_shapes = []
    for ann in data.annotations:
        label = ann.get("category")
        pts = ann.get("points")
        shape_type = ann.get("type", "bbox")

        if not pts:
            # bbox: [xc, yc, bw, bh] (normalized) -> points: [[x1,y1], [x2,y2]] (pixels)
            bbox = ann.get("bbox")
            if bbox and len(bbox) == 4:
                x1 = (bbox[0] - bbox[2]/2) * w
                y1 = (bbox[1] - bbox[3]/2) * h
                x2 = (bbox[0] + bbox[2]/2) * w
                y2 = (bbox[1] + bbox[3]/2) * h
                pts = [[float(x1), float(y1)], [float(x2), float(y2)]]
                shape_type = "rectangle"

        if pts:
            labelme_shapes.append({
                "label": label,
                "points": pts,
                "group_id": None,
                "shape_type": "rectangle" if shape_type == "bbox" or shape_type == "rectangle" else "polygon",
                "flags": {}
            })

    labelme_json = {
        "version": "5.0.1",
        "flags": {},
        "shapes": labelme_shapes,
        "imagePath": data.filename,
        "imageData": None,
        "imageHeight": h,
        "imageWidth": w
    }

    # ??json
    labelme_dir = layout.resolve_current_labelme_dir().path
    labelme_dir.mkdir(parents=True, exist_ok=True)
    json_path = labelme_dir / Path(data.filename).with_suffix(".json")

    try:
        with open(json_path, "w", encoding="utf-8") as json_f:
            json.dump(labelme_json, json_f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LabelMe JSON ???: {e}")

    # ??銵??????????
    found = False
    for img in project["images"]:
        if img["filename"] == data.filename:
            img["status"] = data.status
            img["scene"] = data.scene
            img["source_video"] = data.source_video
            img["width"] = w
            img["height"] = h
            # ??????notations ??? sync ??json ??
            # ?輸??∟?∠???????鈭???
            temp_anns = []
            for shape in labelme_shapes:
                # ??防???bbox
                pts_arr = np.array(shape["points"])
                x_min, y_min = np.min(pts_arr, axis=0)
                x_max, y_max = np.max(pts_arr, axis=0)
                bw = x_max - x_min
                bh = y_max - y_min
                xc = x_min + bw/2
                yc = y_min + bh/2
                temp_anns.append({
                    "category": shape["label"],
                    "type": "bbox" if shape["shape_type"] == "rectangle" else "polygon",
                    "bbox": [xc/w, yc/h, bw/w, bh/h],
                    "points": shape["points"]
                })
            img["annotations"] = temp_anns
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Image metadata not found in project")

    # ????????撞
    total = len(project["images"])
    annotated = sum(1 for img in project["images"] if img["status"] == "annotated")
    flagged = sum(1 for img in project["images"] if img["status"] == "flagged")
    skipped = sum(1 for img in project["images"] if img["status"] == "skipped")

    project["annotation_progress"] = {
        "total": total,
        "annotated": annotated,
        "flagged": flagged,
        "skipped": skipped
    }

    ProjectManager.save_project(project_id, project)
    return {"message": "???????", "progress": project["annotation_progress"]}


# --- ???LabelMe ???格?? / ZIP API ---

def should_auto_convert_yolo_to_labelme(project: Dict[str, Any]) -> bool:
    task_type = str(project.get("task_type", "")).lower()
    return task_type in {"object_detection", "detection"} or "segmentation" in task_type

def write_split_files(project: Dict[str, Any], splits: Dict[str, List[str]], method: str, ratio: Dict[str, float], quality_report: Dict[str, Any]) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    split_id = f"split_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    split_dir = layout.split_dir(split_id)
    split_dir.mkdir(parents=True, exist_ok=True)

    for name in ("train", "val", "test"):
        (split_dir / f"{name}.txt").write_text("\n".join(splits.get(name, [])) + ("\n" if splits.get(name) else ""), encoding="utf-8")

    manifest = {
        "split_id": split_id,
        "method": method,
        "ratio": ratio,
        "task_type": project.get("task_type"),
        "class_names": project.get("class_names", []),
        "source_annotation_version": (project.get("current") or {}).get("annotation_version"),
        "created_at": datetime.now().isoformat(),
        "counts": {name: len(splits.get(name, [])) for name in ("train", "val", "test")},
        "quality_report": quality_report,
        "yolo_data_yaml": (layout.yolo_split_dir(split_id) / "data.yaml").as_posix(),
    }
    layout.split_manifest_path(split_id).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    current = {
        "current_split_id": split_id,
        "source_annotation_version": manifest["source_annotation_version"],
        "task_type": project.get("task_type"),
        "created_at": manifest["created_at"],
        "split_manifest": layout.split_manifest_path(split_id).relative_to(layout.project_dir).as_posix(),
        "yolo_data_yaml": (layout.yolo_split_dir(split_id) / "data.yaml").relative_to(layout.project_dir).as_posix(),
    }
    layout.current_split_path.parent.mkdir(parents=True, exist_ok=True)
    layout.current_split_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

    if "current" not in project:
        project["current"] = {}
    project["current"]["split_id"] = split_id
    return manifest

@app.post("/api/projects/{project_id}/labelme/sync")
def sync_labelme(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        if should_auto_convert_yolo_to_labelme(project):
            LabelMeAdapter.convert_yolo_to_labelme(project)
        report = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"????: {e}")

@app.get("/api/projects/{project_id}/labelme/preview/{filename}")
def get_labelme_preview(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    shapes_data = LabelMeAdapter.get_labelme_shapes(project, filename)
    if not shapes_data:
        return {"shapes": [], "imageHeight": 640, "imageWidth": 640}
    return shapes_data

@app.post("/api/projects/{project_id}/labelme/open")
def open_labelme(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    images_dir = layout.resolve_raw_images_dir().path
    labelme_dir = layout.resolve_current_labelme_dir().path
    images_dir.mkdir(parents=True, exist_ok=True)
    labelme_dir.mkdir(parents=True, exist_ok=True)
    normalized_jsons = normalize_labelme_image_paths(images_dir, labelme_dir)

    executable = find_labelme_executable()
    if executable:
        command = [executable, str(images_dir), "--output", str(labelme_dir)]
    else:
        command = [sys.executable, "-m", "labelme", str(images_dir), "--output", str(labelme_dir)]

    class_names = project.get("class_names") or []
    if class_names:
        command.extend(["--labels", ",".join(class_names)])

    try:
        subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to launch LabelMe. Install it with `pip install labelme`, "
                "or make sure labelme.exe is available to the FastAPI server. "
                f"Original error: {e}"
            )
        )

    from datetime import datetime
    if "labelme_config" not in project:
        project["labelme_config"] = {
            "images_dir": "dataset/images/raw" if layout.is_v3_project() else "dataset/raw/images",
            "json_dir": "annotations/current/labelme" if layout.is_v3_project() else "dataset/raw/annotations/labelme",
            "command": "",
            "last_opened_at": None
        }
    project["labelme_config"]["last_opened_at"] = datetime.now().isoformat()
    project["labelme_config"]["command"] = " ".join(f'"{part}"' if " " in part else part for part in command)
    ProjectManager.save_project(project_id, project)

    return {
        "message": "LabelMe launched.",
        "command": " ".join(f'"{part}"' if " " in part else part for part in command),
        "images_folder": str(images_dir.resolve().as_posix()),
        "json_folder": str(labelme_dir.resolve().as_posix()),
        "normalized_jsons": normalized_jsons
    }

class ConvertRequest(BaseModel):
    export_type: str # yolo_detection, yolo_segmentation, coco, semantic_mask

@app.post("/api/projects/{project_id}/labelme/convert")
def convert_labelme_labels(project_id: str, req: ConvertRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        res = LabelMeAdapter.convert_labelme(project, req.export_type)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"???剜??: {e}")

@app.get("/api/projects/{project_id}/thumbnails/{filename}")
def get_image_thumbnail(project_id: str, filename: str):
    try:
        thumb_path = DatasetUtils.get_thumbnail(project_id, filename)
        return FileResponse(thumb_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/evaluation")
def get_evaluation_results(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    run_dir = _latest_completed_training_run_dir(project, layout)
    if not run_dir:
        return _empty_evaluation_payload()

    results = _read_evaluation_metrics(run_dir)
    available_plots = _list_evaluation_plots(run_dir)
    artifacts = _list_run_artifact_files(run_dir)

    if not results:
        payload = _empty_evaluation_payload()
        payload["run_id"] = run_dir.name
        payload["plots"] = available_plots
        payload["artifacts"] = artifacts
        return payload

    return {
        "success": True,
        "has_metrics": True,
        "run_id": run_dir.name,
        "metrics": results["metrics"],
        "epochs_completed": results["epochs_completed"],
        "plots": available_plots,
        "artifacts": artifacts
    }

@app.get("/api/projects/{project_id}/evaluation/plot/{filename}")
def get_evaluation_plot(project_id: str, filename: str, run_id: Optional[str] = None):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid plot filename")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id) if run_id else _latest_completed_training_run_dir(project, layout)
    if not run_dir:
        raise HTTPException(status_code=404, detail="No completed training run found")

    plot_path = (run_dir / safe_filename).resolve()
    try:
        plot_path.relative_to(run_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid plot path")

    if not plot_path.exists():
        raise HTTPException(status_code=404, detail=f"Plot file {filename} not found")

    return FileResponse(str(plot_path))


def _empty_evaluation_payload() -> Dict[str, Any]:
    return {
        "success": True,
        "has_metrics": False,
        "run_id": None,
        "metrics": {
            "map50": 0.0,
            "map50_95": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "box_loss": 0.0,
            "seg_loss": 0.0,
            "cls_loss": 0.0,
            "dfl_loss": 0.0,
        },
        "epochs_completed": 0,
        "plots": [],
        "artifacts": [],
    }


def _latest_completed_training_run_dir(project: Dict[str, Any], layout: ProjectLayout) -> Optional[Path]:
    runs = project.get("training_runs") or []
    candidate_ids: List[str] = []
    for run in sorted(runs, key=lambda item: item.get("completed_at") or item.get("created_at") or item.get("run_id") or "", reverse=True):
        run_id = run.get("run_id")
        if not run_id:
            continue
        if run.get("status") == "completed":
            candidate_ids.append(run_id)

    for run_id in candidate_ids:
        run_dir = layout.training_run_dir(run_id)
        if (run_dir / "results.csv").exists() or (run_dir / "metrics.json").exists():
            return run_dir

    runs_dir = layout.training_runs_dir()
    if not runs_dir.exists():
        return None
    candidates = [
        path for path in runs_dir.iterdir()
        if path.is_dir()
        and path.name.startswith("run_")
        and _read_run_summary(path).get("status") == "completed"
        and ((path / "results.csv").exists() or (path / "metrics.json").exists())
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _read_run_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "run_summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_evaluation_metrics(run_dir: Path) -> Optional[Dict[str, Any]]:
    metrics_file = run_dir / "metrics.json"
    if metrics_file.exists():
        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("raw") or {}
            epochs = data.get("epochs") or []
            if isinstance(raw, dict) and raw:
                metrics = _metrics_from_raw_series(raw)
                return {
                    "metrics": metrics,
                    "epochs_completed": len(epochs) or _series_length(raw),
                    "raw": raw,
                }
        except Exception:
            pass

    csv_results = YOLOTrainer.read_results_csv(run_dir)
    if not csv_results:
        return None
    metrics = dict(csv_results.get("metrics") or {})
    last_row = csv_results.get("last_row") or {}
    metrics.update(_metrics_from_last_row(last_row))
    return {
        "metrics": metrics,
        "epochs_completed": csv_results.get("epochs_completed", 0),
        "last_row": last_row,
    }


def _series_length(raw: Dict[str, Any]) -> int:
    lengths = [len(value) for value in raw.values() if isinstance(value, list)]
    return max(lengths) if lengths else 0


def _last_numeric(raw: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        values = raw.get(key)
        if not isinstance(values, list) or not values:
            continue
        for value in reversed(values):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _metrics_from_raw_series(raw: Dict[str, Any]) -> Dict[str, float]:
    precision = _last_numeric(raw, "metrics/precision(M)", "metrics/precision(B)")
    recall = _last_numeric(raw, "metrics/recall(M)", "metrics/recall(B)")
    return {
        "map50": _last_numeric(raw, "metrics/mAP50(M)", "metrics/mAP50(B)"),
        "map50_95": _last_numeric(raw, "metrics/mAP50-95(M)", "metrics/mAP50-95(B)"),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "box_loss": _last_numeric(raw, "val/box_loss", "train/box_loss"),
        "seg_loss": _last_numeric(raw, "val/seg_loss", "train/seg_loss"),
        "cls_loss": _last_numeric(raw, "val/cls_loss", "train/cls_loss"),
        "dfl_loss": _last_numeric(raw, "val/dfl_loss", "train/dfl_loss"),
    }


def _metrics_from_last_row(row: Dict[str, Any]) -> Dict[str, float]:
    raw = {key: [value] for key, value in row.items()}
    return _metrics_from_raw_series(raw)


def _f1_score(precision: float, recall: float) -> float:
    if precision <= 0 or recall <= 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _list_evaluation_plots(run_dir: Path) -> List[str]:
    preferred = [
        "results.png",
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "BoxF1_curve.png",
        "BoxPR_curve.png",
        "BoxP_curve.png",
        "BoxR_curve.png",
        "MaskF1_curve.png",
        "MaskPR_curve.png",
        "MaskP_curve.png",
        "MaskR_curve.png",
        "F1_curve.png",
        "PR_curve.png",
        "P_curve.png",
        "R_curve.png",
        "labels.jpg",
    ]
    return [name for name in preferred if (run_dir / name).exists()]


def _list_run_artifact_files(run_dir: Path) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []

    def scan_dir(path: Path, base: Path) -> None:
        for item in path.iterdir():
            if item.is_file():
                rel_path = item.relative_to(base).as_posix()
                artifacts.append({
                    "filename": item.name,
                    "rel_path": rel_path,
                    "size": item.stat().st_size,
                    "status": "Ready",
                })
            elif item.is_dir() and item.name != "__pycache__":
                scan_dir(item, base)

    if run_dir.exists():
        scan_dir(run_dir, run_dir)
    artifacts.sort(key=lambda item: item["rel_path"])
    return artifacts

@app.post("/api/projects/{project_id}/import-zip")
def import_zip_dataset(project_id: str, file: UploadFile = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ?????zip ??
    temp_zip_dir = Path(project["dataset_path"]) / ".tmp_zip_upload"
    temp_zip_dir.mkdir(parents=True, exist_ok=True)
    temp_zip_path = temp_zip_dir / "upload.zip"

    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        import_res = DatasetUtils.import_zip_package(project_id, str(temp_zip_path))

        updated_project = ProjectManager.get_project(project_id)
        if not updated_project:
            raise HTTPException(status_code=404, detail="Project not found after ZIP import")

        if should_auto_convert_yolo_to_labelme(updated_project):
            LabelMeAdapter.convert_yolo_to_labelme(updated_project)
        sync_res = LabelMeAdapter.sync_labelme_annotations(updated_project)
        ProjectManager.save_project(project_id, updated_project)

        return {
            "message": "ZIP dataset imported.",
            "imported_images": import_res["imported_images_count"],
            "imported_jsons": import_res["imported_jsons_count"],
            "imported_txts": import_res.get("imported_txts_count", 0),
            "sync_status": sync_res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZIP ??祆??: {e}")
    finally:
        # ????? zip
        if temp_zip_path.exists():
            os.remove(temp_zip_path)
        if temp_zip_dir.exists():
            shutil.rmtree(temp_zip_dir)

@app.post("/api/projects/{project_id}/import-annotations")
def import_annotations(
    project_id: str,
    files: List[UploadFile] = File(...),
    csv_mapping: Optional[str] = Form(None),
    auto_apply: bool = Form(True),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from src.security_utils import safe_filename, safe_resolve_under, validate_extension

    layout = ProjectLayout.from_project(project)
    import_id = AnnotationImporter.create_import_id()
    temp_dir = layout.tmp_dir / "annotation_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    staged_files: List[Path] = []
    parsed_csv_mapping: Optional[Dict[str, str]] = None
    if csv_mapping:
        try:
            parsed_csv_mapping = json.loads(csv_mapping)
            if not isinstance(parsed_csv_mapping, dict):
                raise ValueError("csv_mapping must be a JSON object")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid csv_mapping: {exc}")

    try:
        for file in files:
            original_name = file.filename
            if not original_name:
                continue
            
            try:
                validate_extension(original_name, {".json", ".txt", ".csv", ".xml", ".png", ".tif", ".tiff"})
                cleaned_name = safe_filename(original_name)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))

            try:
                target_path = safe_resolve_under(temp_dir, temp_dir / cleaned_name)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            staged_files.append(target_path)

        report = AnnotationImporter.import_files(project, staged_files, import_id=import_id, csv_mapping=parsed_csv_mapping)
        apply_result = None
        sync_report = None
        if auto_apply and report.get("converted", 0) > 0:
            apply_result = AnnotationImporter.apply_import(project, import_id)
            sync_report = LabelMeAdapter.sync_labelme_annotations(project)
            report = apply_result["report"]

        project["last_annotation_import"] = report
        ProjectManager.save_project(project_id, project)

        return {
            "message": "Annotation files imported as LabelMe draft.",
            "import_id": import_id,
            "imported_jsons": report.get("labelme_json", 0),
            "imported_txts": report.get("yolo_txt", 0),
            "imported_csv": report.get("csv", 0),
            "imported_xml": report.get("voc_xml", 0),
            "imported_coco_json": report.get("coco_json", 0),
            "imported_masks": report.get("mask_png", 0),
            "converted": report.get("converted", 0),
            "failed": report.get("failed", 0),
            "auto_applied": bool(apply_result),
            "applied_count": apply_result.get("applied_count", 0) if apply_result else 0,
            "skipped_duplicates": apply_result.get("skipped_duplicates", 0) if apply_result else 0,
            "sync_status": sync_report,
            "report": report,
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annotation import failed: {e}")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/projects/{project_id}/annotations/import/latest")
def get_latest_annotation_import(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return AnnotationImporter.latest_report(project) or {}


@app.get("/api/projects/{project_id}/annotations/import/{import_id}/summary")
def preview_annotation_import_apply(project_id: str, import_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return AnnotationImporter.preview_apply_import(project, import_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to preview annotation import: {e}")


@app.post("/api/projects/{project_id}/annotations/import/{import_id}/apply")
def apply_annotation_import(project_id: str, import_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = AnnotationImporter.apply_import(project, import_id)
        report = LabelMeAdapter.sync_labelme_annotations(project)
        project["last_annotation_import"] = result["report"]
        ProjectManager.save_project(project_id, project)
        return {"message": "Annotation import applied.", "apply": result, "sync_status": report}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply annotation import: {e}")


@app.delete("/api/projects/{project_id}/annotations/import/{import_id}/failed-source")
def delete_failed_annotation_import_source(project_id: str, import_id: str, file: str = Query(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = AnnotationImporter.delete_failed_source_file(project, import_id, file)
        project["last_annotation_import"] = result["report"]
        ProjectManager.save_project(project_id, project)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete failed annotation source: {e}")


class UpdateClassesRequest(BaseModel):
    class_names: List[str]

@app.post("/api/projects/{project_id}/classes")
def update_project_classes(project_id: str, req: UpdateClassesRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project["class_names"] = req.class_names
    ProjectManager.save_project(project_id, project)

    # ????????桅???漱??祈?????????
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    ProjectManager.save_project(project_id, project)

    return {
        "message": "????皝??",
        "class_names": project["class_names"],
        "sync_status": sync_res
    }


# 4. ???? API
@app.post("/api/projects/{project_id}/split")
def split_dataset(project_id: str, req: SplitRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ?????
    splits, quality_report = DataSplitter.split_dataset(
        images=project["images"],
        class_names=project["class_names"],
        method=req.method,
        ratio=req.ratio
    )

    # ?????蟡??project.json ???????? split ???
    for img in project["images"]:
        fname = img["filename"]
        if fname in splits["train"]:
            img["split"] = "train"
        elif fname in splits["val"]:
            img["split"] = "val"
        elif fname in splits["test"]:
            img["split"] = "test"
        else:
            img["split"] = None

    project["split_config"] = {
        "method": req.method,
        "ratio": req.ratio,
        "split_quality_score": quality_report["score"]
    }
    project["split_report"] = quality_report
    split_manifest = write_split_files(project, splits, req.method, req.ratio, quality_report)

    ProjectManager.save_project(project_id, project)
    return {"message": "Split completed.", "report": quality_report, "split": split_manifest}

# 5. ????皜? API
@app.post("/api/projects/{project_id}/augment-preview")
def preview_augmentation(project_id: str, req: AugmentPreviewRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    img_metadata = next((img for img in project["images"] if img["filename"] == req.filename), None)
    if not img_metadata:
        raise HTTPException(status_code=404, detail="Image metadata not found")

    layout = ProjectLayout.from_project(project)
    raw_img_path = layout.resolve_raw_images_dir().path / req.filename
    if not raw_img_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    config = normalize_augmentation_config(req.config)
    try:
        # ??皜?
        aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
            str(raw_img_path),
            img_metadata.get("annotations", []),
            config
        )

        preview_img = aug_img.copy()
        h, w, _ = preview_img.shape
        for ann in aug_bboxes:
            if ann.get("type") == "polygon" and ann.get("points"):
                pts = np.array(ann["points"], dtype=np.int32)
                if len(pts) >= 3:
                    cv2.polylines(preview_img, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
                    x1 = int(np.min(pts[:, 0]))
                    y1 = int(np.min(pts[:, 1]))
                    cv2.putText(preview_img, ann["category"], (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                continue

            bbox = ann.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            xc, yc, bw, bh = bbox[0]*w, bbox[1]*h, bbox[2]*w, bbox[3]*h
            x1 = int(xc - bw/2)
            y1 = int(yc - bh/2)
            x2 = int(xc + bw/2)
            y2 = int(yc + bh/2)
            cv2.rectangle(preview_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(preview_img, ann["category"], (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # ????Base64
        _, encoded_img = cv2.imencode(".jpg", preview_img)
        base64_str = base64.b64encode(encoded_img).decode("utf-8")

        return {
            "preview": f"data:image/jpeg;base64,{base64_str}",
            "bboxes": aug_bboxes,
            "applied_config": config,
            "applied_parameters": get_applied_augmentation_parameters(config),
            "source_filename": req.filename,
            "target_split": "train",
            "geometry": {"perspective": "disabled_phase_2"}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"?皜??瘙???剜??: {str(e)}")

@app.post("/api/projects/{project_id}/apply-augmentation")
def apply_augmentation(project_id: str, req: Dict[str, Any]):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    if layout.is_v3_project():
        aug_job_id = f"aug_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        aug_job_dir = layout.augmentation_job_dir(aug_job_id)
        aug_dir = layout.augmentation_outputs_dir(aug_job_id) / "images"
    else:
        aug_job_id = None
        aug_job_dir = None
        aug_dir = layout.resolve_legacy_augmented_images_dir().path
        if aug_dir.exists():
            shutil.rmtree(aug_dir)
    aug_dir.mkdir(parents=True, exist_ok=True)

    # ???蝞?????砂????"train" ? val ????
    # ??輯撒???????split (????train ??
    target_split = req.get("target_split", "train")
    if target_split != "train":
        raise HTTPException(status_code=400, detail="Augmentation can only be applied to Train split.")
    multiplier = int(req.get("multiplier", 1))
    if multiplier < 1 or multiplier > 5:
        raise HTTPException(status_code=400, detail="Multiplier must be between 1 and 5.")
    config = normalize_augmentation_config(req.get("config", {}))

    train_images = [
        img for img in project["images"]
        if img.get("split") == "train"
        and img.get("status") == "annotated"
        and not img.get("is_augmented", False)
    ]

    if len(train_images) == 0:
        raise HTTPException(status_code=400, detail="No annotated images found in target split for augmentation.")

    augmented_list = []
    failed_items = []
    skipped_missing = []
    # ??????? metadata
    original_images = [img for img in project["images"] if not img.get("is_augmented", False)]

    for img in train_images:
        fname = img["filename"]
        raw_img_path = layout.resolve_raw_images_dir().path / fname
        if not raw_img_path.exists():
            skipped_missing.append(fname)
            continue

        for i in range(multiplier):
            try:
                aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
                    str(raw_img_path),
                    img.get("annotations", []),
                    config
                )

                # ???????
                new_fname = f"aug_{i}_{fname}"
                dest_path = aug_dir / new_fname
                cv2.imwrite(str(dest_path.resolve()), aug_img)

                # ?梁???皜??????鞊??????????? split
                augmented_list.append({
                    "filename": new_fname,
                    "status": "annotated",
                    "scene": img.get("scene", "unknown"),
                    "source_video": img.get("source_video", ""),
                    "annotations": aug_bboxes,
                    "split": "train",
                    "is_augmented": True,
                    "augmentation_job_id": aug_job_id,
                    "quality": {"status": "green", "warnings": []}
                })
            except Exception as e:
                failed_items.append({"filename": fname, "message": str(e)})
                print(f"Failed to augment {fname}: {e}")

    # ??????? project.json
    project["images"] = original_images + augmented_list
    project["annotation_progress"]["total"] = len(project["images"])
    project["augmentation_config"] = config

    job_summary = {
        "job_id": aug_job_id or f"legacy_aug_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "type": "augmentation",
        "status": "completed" if len(failed_items) == 0 else "completed_with_errors",
        "created_at": datetime.now().isoformat(),
        "target_split": "train",
        "val_test_policy": "excluded",
        "source_train_count": len(train_images),
        "multiplier": multiplier,
        "generated_count": len(augmented_list),
        "skipped_missing_images": skipped_missing,
        "failed_items": failed_items,
        "applied_config": config,
        "applied_parameters": get_applied_augmentation_parameters(config),
        "geometry": {"perspective": "disabled_phase_2"},
        "outputs": {
            "images": (aug_dir.relative_to(layout.project_dir)).as_posix()
            if layout.is_v3_project()
            else str(aug_dir)
        }
    }

    if aug_job_id and aug_job_dir:
        aug_job_dir.mkdir(parents=True, exist_ok=True)
        (aug_job_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        (aug_job_dir / "summary.json").write_text(json.dumps(job_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    append_project_jsonl(layout.project_dir / "history" / "jobs.jsonl", job_summary)
    project.setdefault("augmentation_jobs", [])
    project["augmentation_jobs"].append(job_summary)

    ProjectManager.save_project(project_id, project)
    return {
        "message": "Augmentation completed.",
        "generated_count": len(augmented_list),
        "job_id": job_summary["job_id"],
        "summary": job_summary
    }

@app.get("/api/projects/{project_id}/augmentation/jobs")
def list_augmentation_jobs(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    jobs_by_id: Dict[str, Dict[str, Any]] = {}

    for job in project.get("augmentation_jobs", []):
        job_id = job.get("job_id")
        if job_id:
            jobs_by_id[job_id] = job

    history_path = layout.project_dir / "history" / "jobs.jsonl"
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "augmentation":
                continue
            job_id = record.get("job_id")
            if job_id and job_id not in jobs_by_id:
                jobs_by_id[job_id] = record

    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("created_at", ""),
        reverse=True
    )
    return {"jobs": jobs}

# 6. ?格? API
@app.post("/api/projects/{project_id}/train/start")
def start_training(project_id: str, config: TrainConfigRequest):
    require_feature("training")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ????箏????箸虜??喟???
    config_dict = config.dict() if hasattr(config, "dict") else config.__dict__
    backend = TrainerDispatcher.resolve_backend(project, config_dict)
    readiness_errors = backend.validate_readiness(project, config_dict)
    if readiness_errors:
        raise HTTPException(status_code=400, detail="?格??????喟??鈭???" + "\n".join(readiness_errors))

    from src.training.run_manager import RunManager
    run_id = config.run_id or RunManager.generate_run_id()

    # ???? run_id ??祆????????怨翰 Thread ????????
    layout = ProjectLayout.from_project(project)
    runs_dir = layout.training_runs_dir()
    run_dir = runs_dir / run_id
    if run_dir.exists():
        raise HTTPException(status_code=409, detail=f"Training run '{run_id}' already exists.")

    # ?皝瘥?桀??
    project["training_config"] = {
        "model": config.model,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "imgsz": config.imgsz,
        "lr0": config.lr0,
        "device": config.device,
        "patience": config.patience,
        "workers": config.workers,
        "cache": config.cache,
        "amp": config.amp,
        "seed": config.seed,
        "save_period": config.save_period,
        "close_mosaic": config.close_mosaic,
        "optimizer": config.optimizer,
        "run_id": run_id
    }
    if config.backend:
        project["training_config"]["backend"] = config.backend
    for key in ("sequence_length", "stride", "horizon", "task_head", "hidden_size", "num_layers", "dropout", "bidirectional"):
        value = getattr(config, key, None)
        if value is not None:
            project["training_config"][key] = value
    ProjectManager.save_project(project_id, project)

    # ????格?
    TrainerDispatcher.start_training(project)
    return {"status": "started", "message": "Training started.", "run_id": run_id}

@app.get("/api/projects/{project_id}/train/recommend")
def recommend_config(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    vram_mb = 0
    try:
        if HAS_NVML:
            handle = nvmlDeviceGetHandleByIndex(0)
            mem_info = nvmlDeviceGetMemoryInfo(handle)
            vram_mb = int(mem_info.total / (1024 ** 2))
    except Exception:
        pass

    if vram_mb == 0:
        import torch
        if torch.cuda.is_available():
            try:
                vram_mb = int(torch.cuda.get_device_properties(0).total_memory / (1024 ** 2))
            except Exception:
                vram_mb = 8000
        else:
            vram_mb = 2000

    dataset_size = len([img for img in project.get("images", []) if not img.get("is_augmented", False)])
    task_type = project.get("task_type", "detection")

    from src.training.config_recommender import ConfigRecommender
    return ConfigRecommender.recommend(task_type, vram_mb, dataset_size)

@app.get("/api/projects/{project_id}/rnn/readiness")
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


@app.get("/api/projects/{project_id}/rnn/config")
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
        "validation": validation,
        "window": build_window_summary(config, inspection),
        "mismatches": find_config_mismatches(project),
    }


@app.post("/api/projects/{project_id}/rnn/config")
def save_rnn_config(project_id: str, request: RNNConfigRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return update_project_rnn_config(project_id, project, request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/projects/{project_id}/rnn/dataset/import")
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
            "validation": config_result.get("validation"),
            "window": config_result.get("window"),
            "mismatches": config_result.get("mismatches", []),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/projects/{project_id}/compare/runs")
def list_compare_runs(project_id: str, architecture: str = "cnn"):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.list_comparable_runs(project, architecture)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/projects/{project_id}/compare")
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


@app.post("/api/projects/{project_id}/compare/report")
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


@app.get("/api/projects/{project_id}/compare/reports")
def list_compare_reports(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.list_reports(project)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/projects/{project_id}/compare/reports/{report_id}")
def delete_compare_report(project_id: str, report_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return CompareService.delete_report(project, report_id)
    except CompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/projects/{project_id}/compare/reports/{report_id}/download/{filename}")
def download_compare_report_file(project_id: str, report_id: str, filename: str, _token=Depends(require_api_token)):
    import re

    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", report_id):
        raise HTTPException(status_code=400, detail="Invalid report_id")
    if filename not in {"report.json", "report.md", "summary.csv", "report.pdf"}:
        raise HTTPException(status_code=400, detail="Invalid report filename")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    reports_root = (ProjectLayout.from_project(project).project_dir / "exports" / "compare_reports").resolve()
    file_path = (reports_root / report_id / filename).resolve()
    try:
        file_path.relative_to(reports_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid report path")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Compare report file not found")

    media_type = {
        ".json": "application/json",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
    }.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(file_path), filename=filename, media_type=media_type)


@app.post("/api/projects/{project_id}/compare/output-image")
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
        run_ids = json.loads(run_ids_json)
        if not isinstance(run_ids, list):
            raise ValueError("run_ids_json must be a JSON array")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid run_ids_json: {exc}")

    inference_dirs = ModelRegistry.ensure_inference_dirs(project)

    try:
        if file and file.filename:
            import uuid
            ext = Path(file.filename).suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                raise HTTPException(status_code=400, detail="Only image files are supported")
            safe_name = f"compare_upload_{uuid.uuid4().hex}{ext}"
            input_path = inference_dirs["inputs_images"] / safe_name
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        elif image_path:
            if not LOCAL_TRUSTED_MODE:
                raise HTTPException(status_code=403, detail="Local image path compare requires Local Trusted Mode")
            try:
                from src.security_utils import safe_resolve_under
                project_base = ProjectLayout.from_project(project).project_dir.resolve()
                input_path = safe_resolve_under(project_base, Path(image_path))
            except ValueError as exc:
                raise HTTPException(status_code=403, detail=str(exc))
        else:
            raise HTTPException(status_code=400, detail="Please provide an image file or image_path")

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
    except HTTPException:
        raise
    except OutputCompareServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/projects/{project_id}/train/runs")
def list_runs(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    runs_dir = layout.training_runs_dir()
    from src.training.run_manager import RunManager
    return RunManager.list_project_runs(runs_dir)

@app.get("/api/projects/{project_id}/train/runs/{run_id}/metrics")
def get_run_metrics(project_id: str, run_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    metrics_file = layout.training_run_dir(run_id) / "metrics.json"
    if not metrics_file.exists():
        raise HTTPException(status_code=404, detail="Metrics file not found for this run")

    try:
        with open(metrics_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/train/runs/{run_id}/artifacts")
def get_run_artifacts(project_id: str, run_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory not found")

    artifacts = []
    def scan_dir(p: Path, base: Path):
        for item in p.iterdir():
            if item.is_file():
                rel_path = item.relative_to(base).as_posix()
                artifacts.append({
                    "filename": item.name,
                    "rel_path": rel_path,
                    "size": item.stat().st_size,
                    "status": "Ready"
                })
            elif item.is_dir() and item.name != "__pycache__":
                scan_dir(item, base)
    scan_dir(run_dir, run_dir)
    return artifacts

@app.get("/api/projects/{project_id}/train/runs/{run_id}/artifacts/download/{filename}")
def download_run_artifact(project_id: str, run_id: str, filename: str, path: Optional[str] = None, _token=Depends(require_api_token)):
    # 1. ?? run_id ?瞉?
    import re
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Sanitize filename ?璆?
    safe_filename = Path(filename).name
    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id).resolve()
    
    if path:
        file_path = (run_dir / path).resolve()
    else:
        file_path = (run_dir / safe_filename).resolve()

    # 3. ???? file_path ??run_dir ???撩璆敹賡??
    try:
        file_path.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid path")

    if not file_path.exists():
        # ????????撗??weights ??
        file_path_w = (run_dir / "weights" / safe_filename).resolve()
        try:
            file_path_w.relative_to(run_dir)
            if file_path_w.exists():
                file_path = file_path_w
            else:
                raise HTTPException(status_code=404, detail=f"Artifact file not found: {filename}")
        except ValueError:
            raise HTTPException(status_code=400, detail="Access denied: invalid path")

    return FileResponse(str(file_path), filename=safe_filename)

@app.post("/api/projects/{project_id}/train/runs/{run_id}/export-onnx")
def export_run_onnx(project_id: str, run_id: str):
    require_feature("export_onnx")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id)
    best_pt = run_dir / "weights" / "best.pt"
    if not best_pt.exists():
        raise HTTPException(status_code=400, detail="best.pt not found; cannot export ONNX.")

    try:
        model = YOLO(str(best_pt.resolve()))
        model.export(format="onnx")
        best_onnx = run_dir / "weights" / "best.onnx"
        if best_onnx.exists():
            export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            export_dir = layout.export_dir(export_id)
            export_onnx_dir = export_dir / "onnx"
            export_onnx_dir.mkdir(parents=True, exist_ok=True)
            export_pt = export_onnx_dir / "best.pt"
            export_onnx = export_onnx_dir / "best.onnx"
            shutil.copy(str(best_pt), str(export_pt))
            shutil.copy(str(best_onnx), str(export_onnx))
            summary = {
                "export_id": export_id,
                "run_id": run_id,
                "created_at": datetime.now().isoformat(),
                "pt_path": export_pt.relative_to(layout.project_dir).as_posix(),
                "onnx_path": export_onnx.relative_to(layout.project_dir).as_posix(),
            }
            (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            if "current" not in project:
                project["current"] = {}
            project["current"]["export_id"] = export_id
            ProjectManager.save_project(project_id, project)
            return {"success": True, "export_id": export_id, "onnx_path": str(export_onnx.resolve().as_posix())}
        else:
            raise Exception("ONNX generation failed.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/train/stop")
def stop_training(project_id: str):
    project = ProjectManager.get_project(project_id)
    TrainerDispatcher.stop_training(project_id, project)
    return {"status": "stopped", "message": "?格???餈恍???????格??.."}

@app.get("/api/projects/{project_id}/train/status")
def get_train_status(project_id: str):
    project = ProjectManager.get_project(project_id)
    return TrainerDispatcher.get_status(project_id, project)

# --- WebSocket ????? ---
@app.websocket("/api/projects/{project_id}/monitor")
async def monitor_training(websocket: WebSocket, project_id: str):
    await websocket.accept()
    print(f"[WS] Client connected to monitor project {project_id}")
    try:
        while True:
            # ???????????格????撞??GPU/CPU telemetry
            project = ProjectManager.get_project(project_id)
            status = TrainerDispatcher.get_status(project_id, project)
            await websocket.send_json(status)

            # ?鈭??箸虜甇????嚗??蝎孵??漲??箸??箸?????????????箸??亙??
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from {project_id}")
    except Exception as e:
        print(f"[WS] Error in monitor loop: {e}")
        try:
            await websocket.close()
        except:
            pass

# 7. ??????API
@app.get("/api/projects/{project_id}/export")
def export_model(project_id: str, run_id: Optional[str] = None, model_id: Optional[str] = None):
    require_feature("export_onnx")()
    # Export a trained YOLO model to deployment artifacts.
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    project_dir = layout.project_dir
    runs_dir = layout.training_runs_dir()

    best_pt = None

    # 1. ????輯撒????run_id
    if run_id:
        from src.security_utils import sanitize_run_id
        try:
            safe_run_id = sanitize_run_id(run_id)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        candidate_dir = runs_dir / safe_run_id
        candidate_pt = candidate_dir / "weights" / "best.pt"
        if candidate_pt.exists():
            best_pt = candidate_pt

    # 2. ????輯撒????model_id (?????run_id)
    if not best_pt and model_id:
        parts = model_id.split("::")
        if len(parts) >= 2:
            safe_run_id = parts[1]
            candidate_dir = runs_dir / safe_run_id
            weight_type = parts[2] if len(parts) >= 3 else "best"
            candidate_pt = candidate_dir / "weights" / f"{weight_type}.pt"
            if candidate_pt.exists():
                best_pt = candidate_pt

    # 3. ????project["best_model"]
    if not best_pt and project.get("best_model"):
        candidate_pt = Path(project["best_model"])
        if candidate_pt.exists():
            best_pt = candidate_pt

    # 4. ?瘣駁???????completed ??training_run
    if not best_pt and project.get("training_runs"):
        completed_runs = [r for r in project["training_runs"] if r.get("status") == "completed"]
        completed_runs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        for r in completed_runs:
            safe_run_id = r.get("run_id")
            if safe_run_id:
                candidate_dir = runs_dir / safe_run_id
                candidate_pt = candidate_dir / "weights" / "best.pt"
                if candidate_pt.exists():
                    best_pt = candidate_pt
                    break

    # 5. ????ModelRegistry ???best.pt
    if not best_pt:
        try:
            models_list = ModelRegistry.list_models(project)
            best_models = [m for m in models_list if m.get("weight_type") == "best"]
            if best_models:
                candidate_pt = Path(best_models[0]["internal_weight_path"])
                if candidate_pt.exists():
                    best_pt = candidate_pt
        except Exception:
            pass

    # 6. Fallback???蟡? runs/train
    if not best_pt:
        legacy_dir = runs_dir / "train"
        legacy_pt = legacy_dir / "weights" / "best.pt"
        if legacy_pt.exists():
            best_pt = legacy_pt

    if not best_pt or not best_pt.exists():
        raise HTTPException(status_code=400, detail="No exportable model found.")

    # ???蝞?ONNX ?瞉?
    try:
        model_obj = YOLO(str(best_pt.resolve()))
        model_obj.export(format="onnx")
        # YOLO.export ? weights ???剜???best.onnx (??best.pt ?????獢?)
        best_onnx = best_pt.parent / "best.onnx"

        export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        exports_onnx_dir = export_dir / "onnx"
        exports_onnx_dir.mkdir(parents=True, exist_ok=True)

        # ?森?????export ?獢???
        export_pt = exports_onnx_dir / "best.pt"
        export_onnx = exports_onnx_dir / "best.onnx"

        shutil.copy(str(best_pt), str(export_pt))
        if best_onnx.exists():
            shutil.copy(str(best_onnx), str(export_onnx))

        summary = {
            "export_id": export_id,
            "created_at": datetime.now().isoformat(),
            "source_weight": str(best_pt.resolve().as_posix()),
            "pt_path": export_pt.relative_to(project_dir).as_posix(),
            "onnx_path": export_onnx.relative_to(project_dir).as_posix() if best_onnx.exists() else "",
        }
        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        if "current" not in project:
            project["current"] = {}
        project["current"]["export_id"] = export_id
        ProjectManager.save_project(project_id, project)

        return {
            "success": True,
            "export_id": export_id,
            "pt_path": str(export_pt.resolve().as_posix()),
            "onnx_path": str(export_onnx.resolve().as_posix() if best_onnx.exists() else "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"????祆??: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print(f"Starting Vision Training Studio Server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)


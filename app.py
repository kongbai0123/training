import os
import json
import base64
import shutil
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import mimetypes

# 撘瑕??Windows 銝? .js ??.css ??MIME 憿?閮餃??箸迤蝣箸撘??脩? text/plain ?餅?
mimetypes.add_type("application/javascript", ".js", strict=True)
mimetypes.add_type("text/css", ".css", strict=True)

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from PIL import Image
from src.config import BASE_DIR, PROJECTS_DIR, STATIC_DIR, HAS_GPU, DEVICE_NAME
from src.project_manager import ProjectManager
from src.project_layout import ProjectLayout
from src.dataset_utils import DatasetUtils
from src.splitter import DataSplitter
from src.augmenter import ImageAugmenter
from src.trainer import YOLOTrainer
from src.labelme_adapter import LabelMeAdapter
from src.model_registry import ModelRegistry
from src.inference_engine import InferenceEngine
from src.project_migrator import ProjectMigrator
from ultralytics import YOLO

app = FastAPI(title="Vision Training Studio API")

LOCAL_TRUSTED_MODE = os.environ.get("LOCAL_TRUSTED_MODE", "false").lower() in ("true", "1", "yes")

# ?典? API ?啣虜?航炊靽∪??澆?????
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

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
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "details": {}
            }
        }
    )

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

# 1. 頛??蝬脤?鞈?
# 憒? static/ 銝??剁?撱箇?摰?
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static")

# ?寧??仿?摰???index.html
@app.get("/")
def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        # ??index.html ??撱箇?嚗??喟陛?格迭餈?
        return {"message": "Vision Training Studio backend is running. static/index.html not found."}
    return FileResponse(str(index_path))

@app.get("/api/health")
def health_check():
    torch_version = "Not installed"
    has_gpu = False
    device_name = "CPU"
    try:
        import torch
        torch_version = torch.__version__
        has_gpu = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if has_gpu else "CPU"
    except Exception:
        pass

    return {
        "status": "healthy",
        "local_trusted_mode": LOCAL_TRUSTED_MODE,
        "device": {
            "has_gpu": has_gpu,
            "device_name": device_name,
            "torch_version": torch_version
        },
        "directories": {
            "base_dir": str(BASE_DIR.resolve().as_posix()),
            "projects_dir": str(PROJECTS_DIR.resolve().as_posix()),
            "static_dir": str(STATIC_DIR.resolve().as_posix())
        }
    }

# --- Pydantic Models ---
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
# --- API Endpoints ---

# 1. 撠?蝞∠? API
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
                raise HTTPException(status_code=403, detail="?祆?頝臬??刻??撌脣???(Local Trusted Mode ??)")
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
def get_inference_job_file(project_id: str, job_id: str, filename: str):
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

# 2. 鞈?????摮? API
@app.get("/api/projects/{project_id}/images/{filename}")
def get_project_image(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    img_path = layout.resolve_raw_images_dir().path / filename
    # ?亙 raw ?曆??堆???augmented_images ??(?拍??游??Ｙ???)
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

    # ?舀?舀???
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

    # ?湔 project.json 蝯?
    for fname, sha in imported:
        # ?踹????
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
        raise HTTPException(status_code=500, detail=f"?賢?憭望?: {str(e)}")

    import hashlib
    # 撠?箇?撟? project.json 撟嗉???source_video
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
            "source_video": v_path.name, # ?其?敺? Group Split
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
        # ?脣?銝?蔣??
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        layout = ProjectLayout.from_project(project)
        dest_dir = layout.resolve_raw_images_dir().path
        dest_dir.mkdir(parents=True, exist_ok=True)
        filenames = DatasetUtils.extract_frames(str(temp_video_path), str(dest_dir), fps)

        # 撠?箇?敶望? project.json
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
        raise HTTPException(status_code=500, detail=f"敶梁??賢?憭望?: {e}")
    finally:
        # 皜??怠?瑼?
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

    # 1. ?渡??暹???嚗?朣?sha256 甈?
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

    # 2. ??銝瑼?
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

            # ?? A: 瑼??摰孵??其???(?? + ??SHA-256) -> 頝喲?
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

            # ?? B: 瑼??詨?雿摰嫣???-> ?芸???賢??脫迫閬神
            stored_name = original_name
            if original_name in existing_name_map:
                prefix = sha256_val[:6]
                stem = Path(original_name).stem
                stored_name = f"{stem}__{prefix}{ext}"
                renamed_same_name_diff_hash += 1

            # ?? C: 銝?瑼?雿摰嫣???(??SHA-256) -> 閬??嚗?閮剛歲??
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

            # 甇?虜摮?
            dest_file_path = image_dir / stored_name
            dest_file_path.write_bytes(file_bytes)
            uploaded_count += 1

            # ?啣??????
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

            # ?湔撅?冽?撠?mapping
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

    # 3. ?湔撠????
    if modified_project_images:
        project["annotation_progress"]["total"] = len(project["images"])

    # 4. 撖怠 imports_history
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

    # 1. ?脰??????鞈芣???
    hashes = {}
    for img in images_list:
        fname = img["filename"]
        img_path = layout.resolve_raw_images_dir().path / fname
        if not img_path.exists():
            continue

        quality = DatasetUtils.analyze_image_quality(str(img_path))
        img["quality"] = quality

        # 閮? dHash
        h = DatasetUtils.dhash(str(img_path))
        hashes[fname] = h

    # 2. ????瑼Ｘ (瘥?????
    for fname, h in hashes.items():
        is_duplicate = False
        for other_fname, other_h in hashes.items():
            if fname == other_fname:
                continue
            if DatasetUtils.hamming_distance(h, other_h) <= 5:
                is_duplicate = True
                break

        # 撠撠???metadata 銝行?閮?
        for img in images_list:
            if img["filename"] == fname:
                img["quality"]["is_duplicate"] = is_duplicate
                if is_duplicate:
                    img["quality"]["status"] = "yellow"
                    duplicate_warning = "Possible duplicate image"
                    if duplicate_warning not in img["quality"]["warnings"]:
                        img["quality"]["warnings"].append(duplicate_warning)
                break

    # 3. 閮??游????摨瑕漲?亙熒閰摯?勗?
    health_report = DatasetUtils.get_dataset_health(images_list)
    project["dataset_health"] = health_report

    ProjectManager.save_project(project_id, project)
    return health_report

# 3. 璅酉 API
@app.post("/api/projects/{project_id}/annotations")
def save_annotations(project_id: str, data: AnnotationSave):
    import numpy as np
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)

    # 霈????撖?
    img_path = layout.resolve_raw_images_dir().path / data.filename
    w, h = 640, 640
    if img_path.exists():
        try:
            with Image.open(img_path) as pil_img:
                w, h = pil_img.size
        except Exception:
            pass

    # 撱箇? LabelMe JSON 瑼?
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

    # 撖怠 json
    labelme_dir = layout.resolve_current_labelme_dir().path
    labelme_dir.mkdir(parents=True, exist_ok=True)
    json_path = labelme_dir / Path(data.filename).with_suffix(".json")

    try:
        with open(json_path, "w", encoding="utf-8") as json_f:
            json.dump(labelme_json, json_f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LabelMe JSON 撖怠憭望?: {e}")

    # 撠銝行?啣????????
    found = False
    for img in project["images"]:
        if img["filename"] == data.filename:
            img["status"] = data.status
            img["scene"] = data.scene
            img["source_video"] = data.source_video
            img["width"] = w
            img["height"] = h
            # 撠????嚗nnotations ?敺? sync 敺?json 頛
            # 雿鈭?蝡航蝡皜脫?嚗ㄐ銋?交?啣?
            temp_anns = []
            for shape in labelme_shapes:
                # ?甇訾???bbox
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

    # ?閮?璅酉?脣漲
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
    return {"message": "璅酉?脣???", "progress": project["annotation_progress"]}


# --- ?冽 LabelMe ??蝮桀? / ZIP API ---

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
        raise HTTPException(status_code=500, detail=f"?郊憭望?: {e}")

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
        raise HTTPException(status_code=500, detail=f"頧?憭望?: {e}")

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

    dataset_path = Path(project["dataset_path"])
    runs_dir = dataset_path.parent / "training" / "runs" / "train"

    results = YOLOTrainer.read_results_csv(runs_dir)

    available_plots = []
    for plot_name in ["confusion_matrix.png", "results.png", "F1_curve.png", "PR_curve.png"]:
        plot_path = runs_dir / plot_name
        if plot_path.exists():
            available_plots.append(plot_name)

    if not results:
        return {
            "success": True,
            "has_metrics": False,
            "metrics": {
                "map50": 0.0,
                "map50_95": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "box_loss": 0.0,
                "seg_loss": 0.0
            },
            "epochs_completed": 0,
            "plots": []
        }

    return {
        "success": True,
        "has_metrics": True,
        "metrics": results["metrics"],
        "epochs_completed": results["epochs_completed"],
        "plots": available_plots
    }

@app.get("/api/projects/{project_id}/evaluation/plot/{filename}")
def get_evaluation_plot(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    dataset_path = Path(project["dataset_path"])
    plot_path = dataset_path.parent / "training" / "runs" / "train" / filename
    if not plot_path.exists():
        raise HTTPException(status_code=404, detail=f"Plot file {filename} not found")

    return FileResponse(str(plot_path))

@app.post("/api/projects/{project_id}/import-zip")
def import_zip_dataset(project_id: str, file: UploadFile = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 靽?銝??zip 瑼?
    temp_zip_dir = Path(project["dataset_path"]) / ".tmp_zip_upload"
    temp_zip_dir.mkdir(parents=True, exist_ok=True)
    temp_zip_path = temp_zip_dir / "upload.zip"

    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ?瑁?閫??蝮株???撠
        import_res = DatasetUtils.import_zip_package(project_id, str(temp_zip_path))

        if should_auto_convert_yolo_to_labelme(project):
            LabelMeAdapter.convert_yolo_to_labelme(project)
        sync_res = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)

        return {
            "message": "ZIP dataset imported.",
            "imported_images": import_res["imported_images_count"],
            "imported_jsons": import_res["imported_jsons_count"],
            "imported_txts": import_res.get("imported_txts_count", 0),
            "sync_status": sync_res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZIP ?臬憭望?: {e}")
    finally:
        # 皜??怠? zip
        if temp_zip_path.exists():
            os.remove(temp_zip_path)
        if temp_zip_dir.exists():
            shutil.rmtree(temp_zip_dir)

@app.post("/api/projects/{project_id}/import-annotations")
def import_annotations(project_id: str, files: List[UploadFile] = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    labelme_dir = layout.resolve_current_labelme_dir().path
    labels_dir = layout.resolve_current_yolo_labels_dir().path

    labelme_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    imported_jsons = 0
    imported_txts = 0

    from src.security_utils import safe_filename, safe_resolve_under, validate_extension

    try:
        for file in files:
            original_name = file.filename
            if not original_name:
                continue
            
            try:
                suffix = validate_extension(original_name, {".json", ".txt"})
                cleaned_name = safe_filename(original_name)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))

            if suffix == ".json":
                try:
                    target_path = safe_resolve_under(labelme_dir, labelme_dir / cleaned_name)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                with open(target_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                imported_jsons += 1
            elif suffix == ".txt":
                try:
                    target_path = safe_resolve_under(labels_dir, labels_dir / cleaned_name)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                with open(target_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                imported_txts += 1

        # Detection projects can import legacy YOLO bbox txt. Segmentation projects
        # should keep LabelMe polygon JSON as the source of truth.
        if should_auto_convert_yolo_to_labelme(project):
            LabelMeAdapter.convert_yolo_to_labelme(project)
        sync_res = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)

        return {
            "message": f"???臬 {imported_jsons} ??JSON 瑼???{imported_txts} ??TXT 瑼?",
            "imported_jsons": imported_jsons,
            "imported_txts": imported_txts,
            "sync_status": sync_res
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"璅酉瑼??臬憭望?: {e}")


class UpdateClassesRequest(BaseModel):
    class_names: List[str]

@app.post("/api/projects/{project_id}/classes")
def update_project_classes(project_id: str, req: UpdateClassesRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project["class_names"] = req.class_names
    ProjectManager.save_project(project_id, project)

    # ?瑁?銝甈⊥?閮餃?甇交?唬誑撠???圈???
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    ProjectManager.save_project(project_id, project)

    return {
        "message": "撠?憿?湔??",
        "class_names": project["class_names"],
        "sync_status": sync_res
    }


# 4. 鞈??? API
@app.post("/api/projects/{project_id}/split")
def split_dataset(project_id: str, req: SplitRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ?瑁???
    splits, quality_report = DataSplitter.split_dataset(
        images=project["images"],
        class_names=project["class_names"],
        method=req.method,
        ratio=req.ratio
    )

    # 撠????神??project.json 銝剜?撘萄??? split 撅祆?
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

# 5. ?拍??游? API
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

    try:
        # 憟?游?
        aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
            str(raw_img_path),
            img_metadata.get("annotations", []),
            req.config
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

        # 頧???Base64
        _, encoded_img = cv2.imencode(".jpg", preview_img)
        base64_str = base64.b64encode(encoded_img).decode("utf-8")

        return {"preview": f"data:image/jpeg;base64,{base64_str}", "bboxes": aug_bboxes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"?游??汗??憭望?: {str(e)}")

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

    # ?蕪?箏??砍歇蝬◤????"train" ? val ????
    # ?雿輻??摰?憟??split (?虜??train ??
    target_split = req.get("target_split", "train")
    multiplier = int(req.get("multiplier", 1)) # 瘥撐????憭?撘菜???
    config = req.get("config", {})

    train_images = [img for img in project["images"] if img.get("split") == target_split and img.get("status") == "annotated"]

    if len(train_images) == 0:
        raise HTTPException(status_code=400, detail="No annotated images found in target split for augmentation.")

    augmented_list = []
    # 靽?????? metadata
    original_images = [img for img in project["images"] if not img.get("is_augmented", False)]

    for img in train_images:
        fname = img["filename"]
        raw_img_path = layout.resolve_raw_images_dir().path / fname
        if not raw_img_path.exists():
            continue

        for i in range(multiplier):
            try:
                aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
                    str(raw_img_path),
                    img.get("annotations", []),
                    config
                )

                # ???唳???
                new_fname = f"aug_{i}_{fname}"
                dest_path = aug_dir / new_fname
                cv2.imwrite(str(dest_path.resolve()), aug_img)

                # 撱箇??游??????豢?嚗蒂甇賊??典??? split
                augmented_list.append({
                    "filename": new_fname,
                    "status": "annotated",
                    "scene": img.get("scene", "unknown"),
                    "source_video": img.get("source_video", ""),
                    "annotations": aug_bboxes,
                    "split": target_split,
                    "is_augmented": True,
                    "augmentation_job_id": aug_job_id,
                    "quality": {"status": "green", "warnings": []}
                })
            except Exception as e:
                print(f"Failed to augment {fname}: {e}")

    # 撠???酉?? project.json
    project["images"] = original_images + augmented_list
    project["annotation_progress"]["total"] = len(project["images"])
    project["augmentation_config"] = config

    if aug_job_id and aug_job_dir:
        aug_job_dir.mkdir(parents=True, exist_ok=True)
        (aug_job_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        (aug_job_dir / "summary.json").write_text(json.dumps({
            "job_id": aug_job_id,
            "created_at": datetime.now().isoformat(),
            "target_split": target_split,
            "multiplier": multiplier,
            "generated_count": len(augmented_list),
            "outputs": {"images": (aug_dir.relative_to(layout.project_dir)).as_posix()},
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    ProjectManager.save_project(project_id, project)
    return {"message": "Augmentation completed.", "generated_count": len(augmented_list), "job_id": aug_job_id}

# 6. 閮毀 API
@app.post("/api/projects/{project_id}/train/start")
def start_training(project_id: str, config: TrainConfigRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ?脰?敺垢摰??蝺游停蝺扳炎??
    from src.training.readiness import validate_training_readiness
    config_dict = config.dict() if hasattr(config, "dict") else config.__dict__
    readiness_errors = validate_training_readiness(project, config_dict)
    if readiness_errors:
        raise HTTPException(status_code=400, detail="閮毀撠梁??扳炎?交??嚗n" + "\n".join(readiness_errors))

    from src.training.run_manager import RunManager
    run_id = config.run_id or RunManager.generate_run_id()

    # ???菜葫 run_id ?臬撌脣??剁??脫迫 Thread ??敺?撏拇蔑
    layout = ProjectLayout.from_project(project)
    runs_dir = layout.training_runs_dir()
    run_dir = runs_dir / run_id
    if run_dir.exists():
        raise HTTPException(status_code=409, detail=f"Training run '{run_id}' already exists.")

    # ?湔閮毀閮剖?
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
    ProjectManager.save_project(project_id, project)

    # ???閮毀
    YOLOTrainer.start_training(project)
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
def download_run_artifact(project_id: str, run_id: str, filename: str, path: Optional[str] = None):
    # 1. 撽? run_id ?澆?
    import re
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Sanitize filename ?楝敺?
    safe_filename = Path(filename).name
    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id).resolve()
    
    if path:
        file_path = (run_dir / path).resolve()
    else:
        file_path = (run_dir / safe_filename).resolve()

    # 3. 蝣箔? file_path 雿 run_dir 銋嚗甇Ｚ楝敺忽頞?
    try:
        file_path.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid path")

    if not file_path.exists():
        # 憒?銝??剁??岫??weights 摨?
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
    YOLOTrainer.stop_training(project_id)
    return {"status": "stopped", "message": "閮毀銝剜迫銝哨?甇??閮擃?.."}

@app.get("/api/projects/{project_id}/train/status")
def get_train_status(project_id: str):
    return YOLOTrainer.get_status(project_id)

# --- WebSocket ????? ---
@app.websocket("/api/projects/{project_id}/monitor")
async def monitor_training(websocket: WebSocket, project_id: str):
    await websocket.accept()
    print(f"[WS] Client connected to monitor project {project_id}")
    try:
        while True:
            # 瘥?霈??甈⊥??啁?閮毀?脣漲??GPU/CPU telemetry
            status = YOLOTrainer.get_status(project_id)
            await websocket.send_json(status)

            # ?亥?蝺游歇蝯??葉甇Ｘ??粹嚗隞亦?敺格?蝺拇??雿?蝥??????敺恥?嗥垢??
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from {project_id}")
    except Exception as e:
        print(f"[WS] Error in monitor loop: {e}")
        try:
            await websocket.close()
        except:
            pass

# 7. 璅∪?????API
@app.get("/api/projects/{project_id}/export")
def export_model(project_id: str, run_id: Optional[str] = None, model_id: Optional[str] = None):
    # Export a trained YOLO model to deployment artifacts.
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    project_dir = layout.project_dir
    runs_dir = layout.training_runs_dir()

    best_pt = None

    # 1. ?芸?雿輻?喳??run_id
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

    # 2. 甈∟?雿輻?喳??model_id (閫????run_id)
    if not best_pt and model_id:
        parts = model_id.split("::")
        if len(parts) >= 2:
            safe_run_id = parts[1]
            candidate_dir = runs_dir / safe_run_id
            weight_type = parts[2] if len(parts) >= 3 else "best"
            candidate_pt = candidate_dir / "weights" / f"{weight_type}.pt"
            if candidate_pt.exists():
                best_pt = candidate_pt

    # 3. ?蝙??project["best_model"]
    if not best_pt and project.get("best_model"):
        candidate_pt = Path(project["best_model"])
        if candidate_pt.exists():
            best_pt = candidate_pt

    # 4. ?活銋蝙?冽???completed ??training_run
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

    # 5. ?蝙??ModelRegistry ???best.pt
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

    # 6. Fallback嚗??祉? runs/train
    if not best_pt:
        legacy_dir = runs_dir / "train"
        legacy_pt = legacy_dir / "weights" / "best.pt"
        if legacy_pt.exists():
            best_pt = legacy_pt

    if not best_pt or not best_pt.exists():
        raise HTTPException(status_code=400, detail="No exportable model found.")

    # 銝雿萄?箇 ONNX ?澆?
    try:
        model_obj = YOLO(str(best_pt.resolve()))
        model_obj.export(format="onnx")
        # YOLO.export ? weights 鞈?憭曄??best.onnx (??best.pt ?典?銝?桅?)
        best_onnx = best_pt.parent / "best.onnx"

        export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        exports_onnx_dir = export_dir / "onnx"
        exports_onnx_dir.mkdir(parents=True, exist_ok=True)

        # 銴ˊ?啣?獢?export ?桅?銝?
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
        raise HTTPException(status_code=500, detail=f"璅∪??臬憭望?: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print(f"Starting Vision Training Studio Server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)

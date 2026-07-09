import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.annotation_helpers import should_auto_convert_yolo_to_labelme
from src.dataset_helpers import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    add_project_images,
    file_sha256,
    import_zip_upload,
    process_image_upload_batch,
    process_mixed_dataset_files_upload,
    resolve_project_image_path,
    run_dataset_quality_check,
)
from src.dataset_quality_report import build_dataset_quality_report
from src.dataset_utils import DatasetUtils
from src.labelme_adapter import LabelMeAdapter
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager

router = APIRouter()


@router.get("/api/projects/{project_id}/images/{filename}")
def get_project_image(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    img_path = resolve_project_image_path(layout, project, filename)
    if not img_path:
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(img_path))

@router.post("/api/projects/{project_id}/import-local")
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

    for f in import_path.iterdir():
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            dest_file = dest_dir / f.name
            shutil.copy(str(f), str(dest_file))
            imported.append((f.name, file_sha256(dest_file)))

    add_project_images(project, imported)
    ProjectManager.save_project(project_id, project)

    return {"message": f"Imported {len(imported)} images.", "imported": [x[0] for x in imported]}

@router.post("/api/projects/{project_id}/import-video")
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
        raise HTTPException(status_code=500, detail=f"Failed to extract video frames: {e}")

    add_project_images(project, [(fname, file_sha256(dest_dir / fname)) for fname in filenames], source_video=v_path.name)
    ProjectManager.save_project(project_id, project)

    return {"message": f"Extracted {len(filenames)} frames.", "imported_count": len(filenames)}

@router.post("/api/projects/{project_id}/upload-video")
def upload_video(project_id: str, file: UploadFile = File(...), fps: int = Form(1)):
    import uuid
    original_name = Path(file.filename or "upload.mp4").name
    suffix = Path(original_name).suffix.lower()

    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = f"{uuid.uuid4().hex}{suffix}"
    temp_dir = Path(project["dataset_path"]) / ".tmp_video_upload"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_video_path = temp_dir / safe_filename

    try:
        # Save uploaded video to a temporary file.
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        layout = ProjectLayout.from_project(project)
        dest_dir = layout.resolve_raw_images_dir().path
        dest_dir.mkdir(parents=True, exist_ok=True)
        filenames = DatasetUtils.extract_frames(str(temp_video_path), str(dest_dir), fps)

        # Update project image metadata after extracting frames.
        add_project_images(project, [(fname, file_sha256(dest_dir / fname)) for fname in filenames], source_video=original_name)
        ProjectManager.save_project(project_id, project)

        return {
            "message": f"Uploaded video and extracted {len(filenames)} frames.",
            "imported_count": len(filenames)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {e}")
    finally:
        # Clean up temporary upload files.
        if temp_video_path.exists():
            os.remove(temp_video_path)
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            shutil.rmtree(temp_dir)


@router.post("/api/projects/{project_id}/upload-images")
def upload_images(
    project_id: str,
    files: List[UploadFile] = File(...),
    batch_id: Optional[str] = Form(None)
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    image_dir = layout.resolve_raw_images_dir().path
    result = process_image_upload_batch(project, image_dir, files, batch_id=batch_id)
    ProjectManager.save_project(project_id, project)
    return result


@router.post("/api/projects/{project_id}/upload-dataset-files")
def upload_dataset_files(project_id: str, files: List[UploadFile] = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    result = process_mixed_dataset_files_upload(project, layout, files)
    if result["imported_txts"] > 0:
        LabelMeAdapter.convert_yolo_to_labelme(project)
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    ProjectManager.save_project(project_id, project)

    return {**result, "sync_status": sync_res}


@router.post("/api/projects/{project_id}/quality-check")
def trigger_quality_check(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    health_report = run_dataset_quality_check(project, layout)
    ProjectManager.save_project(project_id, project)
    return health_report


@router.get("/api/projects/{project_id}/dataset/quality-report")
def get_dataset_quality_report(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return build_dataset_quality_report(project)

@router.get("/api/projects/{project_id}/thumbnails/{filename}")
def get_image_thumbnail(project_id: str, filename: str):
    try:
        thumb_path = DatasetUtils.get_thumbnail(project_id, filename)
        return FileResponse(thumb_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/projects/{project_id}/import-zip")
def import_zip_dataset(project_id: str, file: UploadFile = File(...)):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        import_res = import_zip_upload(project_id, project, file)

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
        raise HTTPException(status_code=500, detail=f"Failed to import ZIP dataset: {e}")


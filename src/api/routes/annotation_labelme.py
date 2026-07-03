import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from PIL import Image

from src.annotation_importer import AnnotationImporter
from src.annotation_helpers import (
    build_labelme_annotation_payload,
    find_labelme_executable,
    normalize_labelme_image_paths,
    should_auto_convert_yolo_to_labelme,
    update_project_image_annotation_state,
)
from src.config import BASE_DIR
from src.labelme_adapter import LabelMeAdapter
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager

router = APIRouter()

class AnnotationSave(BaseModel):
    filename: str
    status: str # annotated, flagged, skipped
    scene: Optional[str] = "unknown"
    source_video: Optional[str] = ""
    annotations: List[Dict[str, Any]]


# Annotation API.
@router.post("/api/projects/{project_id}/annotations")
def save_annotations(project_id: str, data: AnnotationSave):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)

    # Load image dimensions when available.
    img_path = layout.resolve_raw_images_dir().path / data.filename
    w, h = 640, 640
    if img_path.exists():
        try:
            with Image.open(img_path) as pil_img:
                w, h = pil_img.size
        except Exception:
            pass

    labelme_json, labelme_shapes = build_labelme_annotation_payload(data.filename, data.annotations, w, h)

    # Write LabelMe JSON.
    labelme_dir = layout.resolve_current_labelme_dir().path
    labelme_dir.mkdir(parents=True, exist_ok=True)
    json_path = labelme_dir / Path(data.filename).with_suffix(".json")

    try:
        with open(json_path, "w", encoding="utf-8") as json_f:
            json.dump(labelme_json, json_f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write LabelMe JSON: {e}")

    try:
        progress = update_project_image_annotation_state(
            project,
            data.filename,
            data.status,
            data.scene,
            data.source_video,
            w,
            h,
            labelme_shapes,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Image metadata not found in project")

    ProjectManager.save_project(project_id, project)
    return {"message": "Annotations saved.", "progress": progress}


# --- LabelMe and annotation import APIs ---

@router.post("/api/projects/{project_id}/labelme/sync")
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
        raise HTTPException(status_code=500, detail=f"Failed to sync LabelMe annotations: {e}")

@router.get("/api/projects/{project_id}/labelme/preview/{filename}")
def get_labelme_preview(project_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    shapes_data = LabelMeAdapter.get_labelme_shapes(project, filename)
    if not shapes_data:
        return {"shapes": [], "imageHeight": 640, "imageWidth": 640}
    return shapes_data

@router.post("/api/projects/{project_id}/labelme/open")
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
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform.startswith("win") else 0
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

@router.post("/api/projects/{project_id}/labelme/convert")
def convert_labelme_labels(project_id: str, req: ConvertRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        res = LabelMeAdapter.convert_labelme(project, req.export_type)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert LabelMe labels: {e}")





@router.post("/api/projects/{project_id}/import-annotations")
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


@router.get("/api/projects/{project_id}/annotations/import/latest")
def get_latest_annotation_import(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return AnnotationImporter.latest_report(project) or {}


@router.get("/api/projects/{project_id}/annotations/import/{import_id}/summary")
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


@router.post("/api/projects/{project_id}/annotations/import/{import_id}/apply")
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


@router.delete("/api/projects/{project_id}/annotations/import/{import_id}/failed-source")
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

@router.post("/api/projects/{project_id}/classes")
def update_project_classes(project_id: str, req: UpdateClassesRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project["class_names"] = req.class_names
    ProjectManager.save_project(project_id, project)

    # Keep LabelMe annotations synchronized with class names.
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    ProjectManager.save_project(project_id, project)

    return {
        "message": "Classes updated.",
        "class_names": project["class_names"],
        "sync_status": sync_res
    }





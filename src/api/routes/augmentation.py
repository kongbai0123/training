import base64
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.augmenter import ImageAugmenter
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager

router = APIRouter()

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


# Augmentation preview API.
@router.post("/api/projects/{project_id}/augment-preview")
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
        # Generate augmented preview image and annotations.
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

        # Encode preview as base64 for the frontend.
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
        raise HTTPException(status_code=500, detail=f"Failed to generate augmentation preview: {str(e)}")

@router.post("/api/projects/{project_id}/apply-augmentation")
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

    # Augmentation only applies to annotated train split images.
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
    # Keep original images and replace generated augmentation entries.
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

                # Write augmented image.
                new_fname = f"aug_{i}_{fname}"
                dest_path = aug_dir / new_fname
                cv2.imwrite(str(dest_path.resolve()), aug_img)

                # Add augmented metadata to the train split.
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

    # Persist updated project metadata.
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

@router.get("/api/projects/{project_id}/augmentation/jobs")
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


import base64
import hashlib
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
from src.task_jobs import task_job_manager

router = APIRouter()

class AugmentPreviewRequest(BaseModel):
    filename: str
    config: Dict[str, Any]

def normalize_augmentation_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config or {})
    light_cfg = dict(normalized.get("light", {}) or {})
    for key, lower, upper in (("brightness", -0.5, 0.5), ("contrast", -0.5, 0.5), ("temperature", -1.0, 1.0)):
        try:
            light_cfg[key] = max(lower, min(upper, float(light_cfg.get(key, 0) or 0)))
        except (TypeError, ValueError):
            light_cfg[key] = 0.0
    light_cfg["shadow"] = bool(light_cfg.get("shadow", False))
    normalized["light"] = light_cfg

    camera_cfg = dict(normalized.get("camera", {}) or {})
    for key, upper in (("noise", 1.0), ("compression", 1.0), ("lens_droplets", 1.0), ("perspective", 0.08)):
        try:
            camera_cfg[key] = max(0.0, min(upper, float(camera_cfg.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            camera_cfg[key] = 0.0
    normalized["camera"] = camera_cfg
    weather_cfg = dict(normalized.get("weather", {}) or {})
    for key in (
        "overcast", "rain", "fog", "sun_suppression",
        "wet_surface", "puddle", "splash",
    ):
        try:
            weather_cfg[key] = max(0.0, min(1.0, float(weather_cfg.get(key, 0) or 0)))
        except (TypeError, ValueError):
            weather_cfg[key] = 0.0
    weather_cfg["visibility_protection"] = bool(weather_cfg.get("visibility_protection", True))
    try:
        weather_cfg["wind_angle"] = max(-45.0, min(45.0, float(weather_cfg.get("wind_angle", -12.0))))
    except (TypeError, ValueError):
        weather_cfg["wind_angle"] = -12.0
    try:
        weather_cfg["max_occlusion"] = max(
            0.05,
            min(0.35, float(weather_cfg.get("max_occlusion", 0.15) or 0.15)),
        )
    except (TypeError, ValueError):
        weather_cfg["max_occlusion"] = 0.15
    normalized["weather"] = weather_cfg
    motion_cfg = dict(normalized.get("motion", {}) or {})
    for key in ("motion_blur", "gaussian_blur"):
        try:
            motion_cfg[key] = max(0.0, min(1.0, float(motion_cfg.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            motion_cfg[key] = 0.0
    normalized["motion"] = motion_cfg

    geometry_cfg = dict(normalized.get("geometry", {}) or {})
    for key, upper in (("rotation", 20.0), ("scale", 0.2), ("random_crop", 0.2)):
        try:
            geometry_cfg[key] = max(0.0, min(upper, float(geometry_cfg.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            geometry_cfg[key] = 0.0
    geometry_cfg["horizontal_flip"] = bool(geometry_cfg.get("horizontal_flip", False))
    geometry_cfg["vertical_flip"] = bool(geometry_cfg.get("vertical_flip", False))
    normalized["geometry"] = geometry_cfg

    occlusion_cfg = dict(normalized.get("occlusion", {}) or {})
    try:
        occlusion_cfg["intensity"] = max(0.0, min(0.5, float(occlusion_cfg.get("intensity", 0.0) or 0.0)))
    except (TypeError, ValueError):
        occlusion_cfg["intensity"] = 0.0
    normalized["occlusion"] = occlusion_cfg

    color_cfg = dict(normalized.get("color", {}) or {})
    for key, lower, upper in (("saturation", -1.0, 1.0), ("hue", -0.5, 0.5), ("sharpness", 0.0, 1.0)):
        try:
            color_cfg[key] = max(lower, min(upper, float(color_cfg.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            color_cfg[key] = 0.0
    normalized["color"] = color_cfg
    return normalized

def get_applied_augmentation_parameters(config: Dict[str, Any]) -> List[str]:
    params = []
    light_cfg = config.get("light", {}) or {}
    weather_cfg = config.get("weather", {}) or {}
    motion_cfg = config.get("motion", {}) or {}
    camera_cfg = config.get("camera", {}) or {}
    geometry_cfg = config.get("geometry", {}) or {}
    occlusion_cfg = config.get("occlusion", {}) or {}
    color_cfg = config.get("color", {}) or {}
    if float(light_cfg.get("brightness", 0) or 0) != 0:
        params.append("brightness")
    if float(light_cfg.get("contrast", 0) or 0) != 0:
        params.append("contrast")
    if bool(light_cfg.get("shadow", False)):
        params.append("shadow")
    if float(light_cfg.get("temperature", 0) or 0) != 0:
        params.append("color_temperature")
    if float(weather_cfg.get("overcast", 0) or 0) > 0:
        params.append("overcast_grade")
    if float(weather_cfg.get("sun_suppression", 0) or 0) > 0:
        params.append("sunny_cue_suppression")
    if float(weather_cfg.get("rain", 0) or 0) > 0:
        params.append("three_layer_rain")
    if float(weather_cfg.get("fog", 0) or 0) > 0:
        params.append("depth_fog")
    if float(weather_cfg.get("wet_surface", 0) or 0) > 0:
        params.append("wet_surface")
    if float(weather_cfg.get("puddle", 0) or 0) > 0:
        params.append("puddles")
    if float(weather_cfg.get("splash", 0) or 0) > 0:
        params.append("ground_splashes")
    if bool(weather_cfg.get("visibility_protection", True)) and (
        float(weather_cfg.get("rain", 0) or 0) > 0
        or float(weather_cfg.get("fog", 0) or 0) > 0
    ):
        params.append("annotation_visibility_protection")
    if float(motion_cfg.get("motion_blur", 0) or 0) > 0:
        params.append("motion_blur")
    if float(motion_cfg.get("gaussian_blur", 0) or 0) > 0:
        params.append("gaussian_blur")
    if float(camera_cfg.get("noise", 0) or 0) > 0:
        params.append("camera_noise")
    if float(camera_cfg.get("lens_droplets", 0) or 0) > 0:
        params.append("lens_droplets")
    if float(camera_cfg.get("compression", 0) or 0) > 0:
        params.append("compression_noise")
    if float(camera_cfg.get("perspective", 0) or 0) > 0:
        params.append("perspective")
    for key in ("rotation", "scale", "random_crop"):
        if float(geometry_cfg.get(key, 0) or 0) > 0:
            params.append(key)
    for key in ("horizontal_flip", "vertical_flip"):
        if bool(geometry_cfg.get(key, False)):
            params.append(key)
    if float(occlusion_cfg.get("intensity", 0) or 0) > 0:
        params.append("random_occlusion")
    if float(color_cfg.get("saturation", 0) or 0) != 0:
        params.append("saturation")
    if float(color_cfg.get("hue", 0) or 0) != 0:
        params.append("hue_shift")
    if float(color_cfg.get("sharpness", 0) or 0) > 0:
        params.append("sharpness")
    return params


def config_for_augmentation_sample(
    config: Dict[str, Any],
    filename: str,
    copy_index: int = 0,
) -> Dict[str, Any]:
    """Derive a stable per-image seed so preview and generated copy 0 match."""
    sample_config = dict(config)
    weather_cfg = dict(sample_config.get("weather", {}) or {})
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{filename}:{copy_index}:{canonical}".encode("utf-8")).digest()
    weather_cfg["seed"] = int.from_bytes(digest[:4], "big")
    sample_config["weather"] = weather_cfg
    return sample_config

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
        aug_img, aug_bboxes, augmentation_metadata = ImageAugmenter.augment_single_image(
            str(raw_img_path),
            img_metadata.get("annotations", []),
            config_for_augmentation_sample(config, req.filename, 0),
            return_metadata=True,
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

        # PNG preserves fine rain/droplet detail. Return clean and annotated
        # variants so the UI can inspect weather without green overlays.
        ok_clean, encoded_clean = cv2.imencode(".png", aug_img)
        ok_annotated, encoded_annotated = cv2.imencode(".png", preview_img)
        if not ok_clean or not ok_annotated:
            raise ValueError("Failed to encode augmentation preview")
        clean_base64 = base64.b64encode(encoded_clean).decode("utf-8")
        annotated_base64 = base64.b64encode(encoded_annotated).decode("utf-8")

        return {
            "preview": f"data:image/png;base64,{clean_base64}",
            "preview_annotated": f"data:image/png;base64,{annotated_base64}",
            "preview_mime": "image/png",
            "bboxes": aug_bboxes,
            "applied_config": config,
            "applied_parameters": get_applied_augmentation_parameters(config),
            "source_filename": req.filename,
            "target_split": "train",
            "geometry": augmentation_metadata,
            "weather": augmentation_metadata,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate augmentation preview: {str(e)}")

@router.post("/api/projects/{project_id}/apply-augmentation")
def apply_augmentation(project_id: str, req: Dict[str, Any]):
    reporter = req.get("__task_reporter")
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
    augmentation_metadata = None
    failed_items = []
    skipped_missing = []
    # Keep original images and replace generated augmentation entries.
    original_images = [img for img in project["images"] if not img.get("is_augmented", False)]
    total_units = len(train_images) * multiplier
    completed_units = 0

    for img in train_images:
        fname = img["filename"]
        raw_img_path = layout.resolve_raw_images_dir().path / fname
        if not raw_img_path.exists():
            skipped_missing.append(fname)
            completed_units += multiplier
            if reporter:
                reporter.update(
                    phase="augmenting",
                    message=f"Skipped missing image {fname}",
                    progress=20 + (70 * completed_units / max(1, total_units)),
                    indeterminate=False,
                    current=completed_units,
                    total=total_units,
                )
            continue

        for i in range(multiplier):
            try:
                aug_img, aug_bboxes, item_metadata = ImageAugmenter.augment_single_image(
                    str(raw_img_path),
                    img.get("annotations", []),
                    config_for_augmentation_sample(config, fname, i),
                    return_metadata=True,
                )
                augmentation_metadata = item_metadata

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
                    "augmentation": item_metadata,
                    "quality": {"status": "green", "warnings": []}
                })
            except Exception as e:
                failed_items.append({"filename": fname, "message": str(e)})
                print(f"Failed to augment {fname}: {e}")
            finally:
                completed_units += 1
                if reporter:
                    reporter.update(
                        phase="augmenting",
                        message=f"Generated {completed_units} of {total_units} augmented images",
                        progress=20 + (70 * completed_units / max(1, total_units)),
                        indeterminate=False,
                        current=completed_units,
                        total=total_units,
                    )

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
        "weather": augmentation_metadata or {
            "weather_engine": ImageAugmenter.WEATHER_ENGINE_VERSION,
            "visibility_protection": bool(config.get("weather", {}).get("visibility_protection", True)),
        },
        "geometry": {"annotation_remap": "enabled"},
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


@router.post("/api/projects/{project_id}/apply-augmentation/jobs")
def start_augmentation_job(project_id: str, req: Dict[str, Any]):
    if not ProjectManager.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    def run_augmentation(reporter):
        reporter.update(phase="validating", message="Validating augmentation policy", progress=10, indeterminate=False)
        reporter.update(phase="augmenting", message="Generating augmented training images", progress=25, indeterminate=True)
        task_request = dict(req)
        task_request["__task_reporter"] = reporter
        result = apply_augmentation(project_id, task_request)
        reporter.update(phase="writing", message="Writing augmentation job manifest", progress=95, indeterminate=False)
        return result

    task = task_job_manager.submit(
        kind="augmentation",
        title="Apply augmentation",
        project_id=project_id,
        message="Augmentation queued",
        handler=run_augmentation,
    )
    return {"job_id": task["job_id"], "task": task}

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


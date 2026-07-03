import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import hashlib

from src.dataset_utils import DatasetUtils
import uuid
from datetime import datetime


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def new_image_metadata(filename: str, *, source_video: str = "", sha256: str = "") -> Dict[str, Any]:
    return {
        "filename": filename,
        "status": "unannotated",
        "scene": "unknown",
        "source_video": source_video,
        "annotations": [],
        "split": None,
        "quality": {},
        "sha256": sha256,
    }


def add_project_images(
    project: Dict[str, Any],
    files: Iterable[Tuple[str, str]],
    *,
    source_video: str = "",
) -> List[str]:
    project.setdefault("images", [])
    existing = {image.get("filename") for image in project.get("images", [])}
    added: List[str] = []
    for filename, sha256 in files:
        if filename in existing:
            continue
        project["images"].append(new_image_metadata(filename, source_video=source_video, sha256=sha256))
        existing.add(filename)
        added.append(filename)

    project.setdefault("annotation_progress", {})
    project["annotation_progress"]["total"] = len(project.get("images", []))
    return added


def resolve_project_image_path(layout, project: Dict[str, Any], filename: str) -> Optional[Path]:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        return None

    image_path = layout.resolve_raw_images_dir().path / safe_name
    if image_path.exists():
        return image_path

    image_metadata = next((image for image in project.get("images", []) if image.get("filename") == safe_name), {})
    augmentation_job_id = image_metadata.get("augmentation_job_id") or image_metadata.get("aug_job_id")
    if augmentation_job_id:
        image_path = layout.augmentation_outputs_dir(augmentation_job_id) / "images" / safe_name
    else:
        image_path = layout.resolve_legacy_augmented_images_dir().path / safe_name

    return image_path if image_path.exists() else None


def process_image_upload_batch(
    project: Dict[str, Any],
    image_dir: Path,
    uploads: Iterable[Any],
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    image_dir.mkdir(parents=True, exist_ok=True)
    batch_id = batch_id or f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}"

    existing_sha256_map: Dict[str, str] = {}
    existing_name_map: Dict[str, Dict[str, Any]] = {}
    modified_project_images = False

    project.setdefault("images", [])
    for image in project["images"]:
        filename = image.get("filename")
        if not filename:
            continue
        sha = image.get("sha256")
        if not sha:
            image_path = image_dir / filename
            sha = file_sha256(image_path) if image_path.exists() else ""
            if sha:
                image["sha256"] = sha
                modified_project_images = True

        if sha:
            existing_sha256_map[sha] = filename
        existing_name_map[filename] = image

    uploaded_count = 0
    duplicate_same_hash = 0
    renamed_same_name_diff_hash = 0
    invalid_count = 0
    skipped_count = 0
    uploaded_files_info = []

    for upload in uploads:
        original_name = Path(getattr(upload, "filename", "") or "").name
        if not original_name:
            invalid_count += 1
            continue

        extension = Path(original_name).suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            invalid_count += 1
            uploaded_files_info.append(
                {
                    "original_name": original_name,
                    "stored_name": None,
                    "sha256": None,
                    "status": "invalid_format",
                }
            )
            continue

        try:
            file_bytes = upload.file.read()
            sha256_value = hashlib.sha256(file_bytes).hexdigest()

            if original_name in existing_name_map and existing_name_map[original_name].get("sha256") == sha256_value:
                duplicate_same_hash += 1
                skipped_count += 1
                uploaded_files_info.append(
                    {
                        "original_name": original_name,
                        "stored_name": original_name,
                        "sha256": sha256_value,
                        "status": "skipped_duplicate",
                    }
                )
                continue

            stored_name = original_name
            if original_name in existing_name_map:
                prefix = sha256_value[:6]
                stored_name = f"{Path(original_name).stem}__{prefix}{extension}"
                renamed_same_name_diff_hash += 1

            if sha256_value in existing_sha256_map:
                duplicate_same_hash += 1
                skipped_count += 1
                uploaded_files_info.append(
                    {
                        "original_name": original_name,
                        "stored_name": existing_sha256_map[sha256_value],
                        "sha256": sha256_value,
                        "status": "skipped_hash_duplicate",
                    }
                )
                continue

            (image_dir / stored_name).write_bytes(file_bytes)
            uploaded_count += 1
            project["images"].append(new_image_metadata(stored_name, sha256=sha256_value))
            modified_project_images = True
            existing_sha256_map[sha256_value] = stored_name
            existing_name_map[stored_name] = project["images"][-1]
            uploaded_files_info.append(
                {
                    "original_name": original_name,
                    "stored_name": stored_name,
                    "sha256": sha256_value,
                    "status": "uploaded" if stored_name == original_name else "renamed",
                }
            )
        except Exception as exc:
            invalid_count += 1
            uploaded_files_info.append(
                {
                    "original_name": original_name,
                    "stored_name": None,
                    "sha256": None,
                    "status": f"error: {str(exc)}",
                }
            )

    if modified_project_images:
        project.setdefault("annotation_progress", {})
        project["annotation_progress"]["total"] = len(project["images"])

    history_item = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "type": "images_upload",
        "uploaded_count": uploaded_count,
        "duplicate_same_hash": duplicate_same_hash,
        "renamed_same_name_diff_hash": renamed_same_name_diff_hash,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
    }
    project.setdefault("imports_history", []).append(history_item)

    return {
        "success": True,
        "batch_id": batch_id,
        "uploaded_count": uploaded_count,
        "duplicate_same_hash": duplicate_same_hash,
        "renamed_same_name_diff_hash": renamed_same_name_diff_hash,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
        "files": uploaded_files_info,
        "errors": [],
    }


def run_dataset_quality_check(project: Dict[str, Any], layout) -> Dict[str, Any]:
    images = project.get("images", [])
    hashes = {}
    raw_images_dir = layout.resolve_raw_images_dir().path

    for image in images:
        filename = image.get("filename")
        if not filename:
            continue
        image_path = raw_images_dir / filename
        if not image_path.exists():
            continue

        image["quality"] = DatasetUtils.analyze_image_quality(str(image_path))
        hashes[filename] = DatasetUtils.dhash(str(image_path))

    for filename, image_hash in hashes.items():
        is_duplicate = any(
            other_filename != filename and DatasetUtils.hamming_distance(image_hash, other_hash) <= 5
            for other_filename, other_hash in hashes.items()
        )
        for image in images:
            if image.get("filename") != filename:
                continue
            image.setdefault("quality", {})
            image["quality"]["is_duplicate"] = is_duplicate
            if is_duplicate:
                image["quality"]["status"] = "yellow"
                warnings = image["quality"].setdefault("warnings", [])
                duplicate_warning = "Possible duplicate image"
                if duplicate_warning not in warnings:
                    warnings.append(duplicate_warning)
            break

    health_report = DatasetUtils.get_dataset_health(images)
    project["dataset_health"] = health_report
    return health_report


def process_mixed_dataset_files_upload(project: Dict[str, Any], layout, uploads: Iterable[Any]) -> Dict[str, Any]:
    image_dir = layout.resolve_raw_images_dir().path
    labelme_dir = layout.resolve_current_labelme_dir().path
    labels_dir = layout.resolve_current_yolo_labels_dir().path
    image_dir.mkdir(parents=True, exist_ok=True)
    labelme_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    imported_images = 0
    imported_jsons = 0
    imported_txts = 0
    skipped = 0
    image_files = []

    for upload in uploads:
        filename = Path(getattr(upload, "filename", "") or "").name
        extension = Path(filename).suffix.lower()
        if not filename:
            skipped += 1
            continue

        if extension in IMAGE_EXTENSIONS:
            with open(image_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_images += 1
            image_files.append((filename, file_sha256(image_dir / filename)))
        elif extension == ".json":
            with open(labelme_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_jsons += 1
        elif extension == ".txt":
            with open(labels_dir / filename, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            imported_txts += 1
        else:
            skipped += 1

    add_project_images(project, image_files)
    return {
        "message": "Dataset files uploaded.",
        "imported_images": imported_images,
        "imported_jsons": imported_jsons,
        "imported_txts": imported_txts,
        "skipped": skipped,
    }


def import_zip_upload(project_id: str, project: Dict[str, Any], upload: Any) -> Dict[str, Any]:
    temp_zip_dir = Path(project["dataset_path"]) / ".tmp_zip_upload"
    temp_zip_dir.mkdir(parents=True, exist_ok=True)
    temp_zip_path = temp_zip_dir / "upload.zip"

    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        return DatasetUtils.import_zip_package(project_id, str(temp_zip_path))
    finally:
        if temp_zip_path.exists():
            os.remove(temp_zip_path)
        if temp_zip_dir.exists():
            shutil.rmtree(temp_zip_dir)

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def should_auto_convert_yolo_to_labelme(project: Dict[str, Any]) -> bool:
    task_type = str(project.get("task_type", "")).lower()
    return task_type in {"object_detection", "detection"} or "segmentation" in task_type


def find_labelme_executable() -> Optional[str]:
    executable = shutil.which("labelme")
    if executable:
        return executable

    scripts_dir = Path(sys.executable).parent
    candidates = []
    if os.name == "nt":
        candidates.extend(
            [
                scripts_dir / "labelme.exe",
                Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "venv" / "Scripts" / "labelme.exe",
            ]
        )
    else:
        candidates.extend(
            [
                scripts_dir / "labelme",
                Path.home() / ".local" / "bin" / "labelme",
            ]
        )

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


def build_labelme_annotation_payload(
    filename: str,
    annotations: List[Dict[str, Any]],
    width: int,
    height: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    shapes: List[Dict[str, Any]] = []
    for annotation in annotations:
        label = annotation.get("category")
        points = annotation.get("points")
        shape_type = annotation.get("type", "bbox")

        if not points:
            bbox = annotation.get("bbox")
            if bbox and len(bbox) == 4:
                x1 = (bbox[0] - bbox[2] / 2) * width
                y1 = (bbox[1] - bbox[3] / 2) * height
                x2 = (bbox[0] + bbox[2] / 2) * width
                y2 = (bbox[1] + bbox[3] / 2) * height
                points = [[float(x1), float(y1)], [float(x2), float(y2)]]
                shape_type = "rectangle"

        if points:
            shapes.append(
                {
                    "label": label,
                    "points": points,
                    "group_id": None,
                    "shape_type": "rectangle" if shape_type in {"bbox", "rectangle"} else "polygon",
                    "flags": {},
                }
            )

    return (
        {
            "version": "5.0.1",
            "flags": {},
            "shapes": shapes,
            "imagePath": filename,
            "imageData": None,
            "imageHeight": height,
            "imageWidth": width,
        },
        shapes,
    )


def labelme_shapes_to_project_annotations(
    shapes: List[Dict[str, Any]],
    width: int,
    height: int,
) -> List[Dict[str, Any]]:
    annotations = []
    for shape in shapes:
        points = shape.get("points") or []
        if not points:
            continue
        points_array = np.array(points)
        x_min, y_min = np.min(points_array, axis=0)
        x_max, y_max = np.max(points_array, axis=0)
        box_width = x_max - x_min
        box_height = y_max - y_min
        x_center = x_min + box_width / 2
        y_center = y_min + box_height / 2
        annotations.append(
            {
                "category": shape.get("label"),
                "type": "bbox" if shape.get("shape_type") == "rectangle" else "polygon",
                "bbox": [x_center / width, y_center / height, box_width / width, box_height / height],
                "points": points,
            }
        )
    return annotations


def update_project_image_annotation_state(
    project: Dict[str, Any],
    filename: str,
    status: str,
    scene: Optional[str],
    source_video: Optional[str],
    width: int,
    height: int,
    shapes: List[Dict[str, Any]],
) -> Dict[str, int]:
    images = project.get("images") or []
    found = False
    for image in images:
        if image.get("filename") == filename:
            image["status"] = status
            image["scene"] = scene
            image["source_video"] = source_video
            image["width"] = width
            image["height"] = height
            image["annotations"] = labelme_shapes_to_project_annotations(shapes, width, height)
            found = True
            break

    if not found:
        raise ValueError("Image metadata not found in project")

    progress = {
        "total": len(images),
        "annotated": sum(1 for image in images if image.get("status") == "annotated"),
        "flagged": sum(1 for image in images if image.get("status") == "flagged"),
        "skipped": sum(1 for image in images if image.get("status") == "skipped"),
    }
    project["annotation_progress"] = progress
    return progress

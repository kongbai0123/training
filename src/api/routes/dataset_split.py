import json
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.splitter import DataSplitter

router = APIRouter()

class SplitRequest(BaseModel):
    method: str # basic, stratified, scene, group
    ratio: Dict[str, float] # e.g. {"train": 0.7, "val": 0.2, "test": 0.1}

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

# Dataset split API.
@router.post("/api/projects/{project_id}/split")
def split_dataset(project_id: str, req: SplitRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build split assignments.
    splits, quality_report = DataSplitter.split_dataset(
        images=project["images"],
        class_names=project["class_names"],
        method=req.method,
        ratio=req.ratio
    )

    # Persist split assignment back to project metadata.
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


import json
import shutil
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.feature_gate import require_feature
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager

router = APIRouter()

@router.get("/api/projects/{project_id}/auto-labeling/status")
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

@router.post("/api/projects/{project_id}/auto-labeling/jobs")
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

@router.post("/api/projects/{project_id}/auto-labeling/jobs/{job_id}/accept")
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


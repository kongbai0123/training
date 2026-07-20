import json
import shutil
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.auto_labeling_service import AutoLabelingService, AutoLabelingServiceError
from src.feature_gate import require_feature
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.task_jobs import task_job_manager

router = APIRouter()


def _safe_child_name(value: str, suffix: str = "") -> str:
    name = str(value or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    if suffix and not name.lower().endswith(suffix):
        raise HTTPException(status_code=400, detail=f"Expected {suffix} file")
    return name


def _safe_job_id(job_id: str) -> str:
    safe = "".join(ch for ch in str(job_id or "") if ch.isalnum() or ch in {"_", "-"})
    if not safe or safe != job_id:
        raise HTTPException(status_code=400, detail="Invalid job_id")
    return safe

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
            summary_path = job_dir / "summary.json"
            if not summary_path.exists():
                continue
            summary = {"job_id": job_dir.name, "status": "draft"}
            try:
                summary.update(json.loads(summary_path.read_text(encoding="utf-8")))
            except Exception:
                summary["status"] = "unreadable"
            jobs.append(summary)
    return {"jobs": jobs, "jobs_dir": jobs_root.resolve().as_posix(), "drafts_dir": drafts_root.resolve().as_posix()}


@router.get("/api/projects/{project_id}/auto-labeling/jobs/{job_id}")
def get_auto_labeling_job(project_id: str, job_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layout = ProjectLayout.from_project(project)
    summary_path = layout.auto_label_job_dir(_safe_job_id(job_id)) / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Auto-label job not found")
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read auto-label job: {exc}")


@router.get("/api/projects/{project_id}/auto-labeling/jobs/{job_id}/drafts/labelme/{filename}")
def get_auto_labeling_draft_labelme(project_id: str, job_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    layout = ProjectLayout.from_project(project)
    draft_file = layout.auto_label_draft_dir(_safe_job_id(job_id)) / "labelme" / _safe_child_name(filename, ".json")
    if not draft_file.exists() or not draft_file.is_file():
        raise HTTPException(status_code=404, detail="Draft LabelMe JSON not found")
    try:
        return JSONResponse(content=json.loads(draft_file.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read Draft LabelMe JSON: {exc}")


@router.get("/api/projects/{project_id}/auto-labeling/jobs/{job_id}/previews/{filename}")
def get_auto_labeling_preview(project_id: str, job_id: str, filename: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    safe_name = _safe_child_name(filename)
    if not safe_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        raise HTTPException(status_code=400, detail="Expected image preview file")
    layout = ProjectLayout.from_project(project)
    preview_file = layout.auto_label_job_dir(_safe_job_id(job_id)) / "previews" / safe_name
    if not preview_file.exists() or not preview_file.is_file():
        raise HTTPException(status_code=404, detail="Auto-label preview not found")
    return FileResponse(str(preview_file), filename=preview_file.name)

@router.post("/api/projects/{project_id}/auto-labeling/jobs")
def create_auto_labeling_job(project_id: str, req: Dict[str, Any]):
    require_feature("auto_labeling")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        summary = AutoLabelingService.create_draft_job(project, req)
    except AutoLabelingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto-labeling job failed: {exc}")
    return summary


@router.post("/api/projects/{project_id}/auto-labeling/tasks")
def start_auto_labeling_task(project_id: str, req: Dict[str, Any]):
    require_feature("auto_labeling")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    def run_auto_label(reporter):
        current_project = ProjectManager.get_project(project_id)
        if not current_project:
            raise RuntimeError("Project not found")
        reporter.update(phase="loading_model", message="Loading auto-label model", progress=10, indeterminate=True)

        def on_progress(current, total, filename):
            reporter.update(
                phase="labeling",
                message=f"Generating draft for {filename}",
                progress=15 + (75 * current / max(1, total)),
                indeterminate=False,
                current=current,
                total=total,
            )

        summary = AutoLabelingService.create_draft_job(current_project, req, progress_callback=on_progress)
        reporter.update(phase="writing", message="Writing draft review queue", progress=95, indeterminate=False)
        return summary

    task = task_job_manager.submit(
        kind="auto_label",
        title="Generate annotation drafts",
        project_id=project_id,
        message="Auto-labeling queued",
        handler=run_auto_label,
    )
    return {"job_id": task["job_id"], "task": task}


@router.post("/api/projects/{project_id}/auto-labeling/jobs/{job_id}/review")
def review_auto_labeling_item(project_id: str, job_id: str, req: Dict[str, Any]):
    require_feature("auto_labeling")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = AutoLabelingService.review_draft_item(
            project=project,
            job_id=_safe_job_id(job_id),
            filename=_safe_child_name(str(req.get("filename") or "")),
            action=str(req.get("action") or ""),
        )
    except AutoLabelingServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto-label review failed: {exc}")
    ProjectManager.save_project(project_id, project)
    return result

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


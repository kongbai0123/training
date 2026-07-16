import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import require_api_token
from src.feature_gate import require_feature
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.run_filters import TEST_RUN_MARKERS, is_test_run
from src.training.dispatcher import TrainerDispatcher
from src.training.export_service import ExportableModelNotFound, ExportService, ExportServiceError
from src.training.run_registry import ExperimentRunRegistry
from src.training.state_store import TrainingStateStore


router = APIRouter()


class CleanupTrainingRunsRequest(BaseModel):
    run_ids: List[str]
    confirm: bool = False


def _is_cleanup_candidate_run(run_id: str, run: Optional[Dict[str, Any]] = None) -> bool:
    return is_test_run(run_id, run)


def _training_run_cleanup_card(project: Dict[str, Any], run: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    run_id = str(run.get("run_id") or "").strip()
    if not run_id:
        return None
    layout = ProjectLayout.from_project(project)
    run_dir = (layout.training_runs_dir() / run_id).resolve()
    project_dir = layout.project_dir.resolve()
    if project_dir not in run_dir.parents:
        return None

    def _file_info(path: Path) -> Dict[str, Any]:
        return {
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() and path.is_file() else 0,
            "path": path.relative_to(project_dir).as_posix() if project_dir in path.resolve().parents else path.name,
        }

    best = run_dir / "weights" / "best.pt"
    last = run_dir / "weights" / "last.pt"
    return {
        "run_id": run_id,
        "status": run.get("status"),
        "model": run.get("model") or run.get("model_name"),
        "task_type": run.get("task_type") or project.get("task_type"),
        "created_at": run.get("created_at") or run.get("timestamp"),
        "completed_at": run.get("completed_at"),
        "candidate_reason": "name_matches_test_marker",
        "run_dir_exists": run_dir.exists() and run_dir.is_dir(),
        "run_dir": run_dir.relative_to(project_dir).as_posix() if run_dir.exists() else f"training/runs/{run_id}",
        "best": _file_info(best),
        "last": _file_info(last),
        "artifact_count": sum(1 for item in run_dir.rglob("*") if item.is_file()) if run_dir.exists() else 0,
    }


@router.get("/api/projects/{project_id}/runs/cleanup-candidates")
def list_training_run_cleanup_candidates(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    candidates: List[Dict[str, Any]] = []
    for run in project.get("training_runs") or []:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("run_id") or "").strip()
        if not run_id or not _is_cleanup_candidate_run(run_id, run):
            continue
        card = _training_run_cleanup_card(project, run)
        if card:
            candidates.append(card)

    candidates.sort(key=lambda item: item.get("completed_at") or item.get("created_at") or item.get("run_id") or "", reverse=True)
    return {
        "project_id": project_id,
        "candidates": candidates,
        "count": len(candidates),
        "markers": list(TEST_RUN_MARKERS),
    }


@router.post("/api/projects/{project_id}/runs/cleanup")
def cleanup_training_runs(project_id: str, request: CleanupTrainingRunsRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Run cleanup requires explicit confirmation")

    requested_run_ids = [str(run_id).strip() for run_id in request.run_ids if str(run_id).strip()]
    if not requested_run_ids:
        raise HTTPException(status_code=400, detail="No run_ids selected")
    if len(requested_run_ids) > 50:
        raise HTTPException(status_code=400, detail="Too many run_ids selected")

    requested_run_ids = list(dict.fromkeys(requested_run_ids))
    layout = ProjectLayout.from_project(project)
    project_dir = layout.project_dir.resolve()
    runs_dir = layout.training_runs_dir().resolve()

    existing_runs = [run for run in project.get("training_runs") or [] if isinstance(run, dict)]
    run_by_id = {str(run.get("run_id") or "").strip(): run for run in existing_runs if str(run.get("run_id") or "").strip()}
    deleted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    removed_ids: set[str] = set()

    for run_id in requested_run_ids:
        run = run_by_id.get(run_id)
        if not run:
            skipped.append({"run_id": run_id, "reason": "not_registered"})
            continue
        if not _is_cleanup_candidate_run(run_id, run):
            skipped.append({"run_id": run_id, "reason": "not_test_candidate"})
            continue

        run_dir = (runs_dir / run_id).resolve()
        if project_dir not in run_dir.parents or runs_dir not in run_dir.parents:
            skipped.append({"run_id": run_id, "reason": "outside_project_runs"})
            continue

        file_count = 0
        bytes_removed = 0
        if run_dir.exists():
            try:
                for item in run_dir.rglob("*"):
                    if item.is_file():
                        file_count += 1
                        bytes_removed += item.stat().st_size
                shutil.rmtree(run_dir)
            except Exception as exc:
                skipped.append({"run_id": run_id, "reason": f"delete_failed: {exc}"})
                continue

        removed_ids.add(run_id)
        deleted.append({
            "run_id": run_id,
            "run_dir": run_dir.relative_to(project_dir).as_posix(),
            "files_removed": file_count,
            "bytes_removed": bytes_removed,
            "project_record_removed": True,
        })

    if removed_ids:
        project["training_runs"] = [
            run for run in existing_runs
            if str(run.get("run_id") or "").strip() not in removed_ids
        ]
        current = project.get("current") if isinstance(project.get("current"), dict) else {}
        for key in ("training_run_id", "best_model_id"):
            value = str(current.get(key) or "")
            if any(run_id in value for run_id in removed_ids):
                current[key] = None
        project["current"] = current
        if not ProjectManager.save_project(project_id, project):
            raise HTTPException(status_code=500, detail="Failed to save project after cleanup")

    refreshed_project = ProjectManager.get_project(project_id) or project
    return {
        "success": True,
        "deleted": deleted,
        "skipped": skipped,
        "remaining_training_runs": len(refreshed_project.get("training_runs") or []),
        "remaining_model_weights": len(ModelRegistry.list_models(refreshed_project)),
    }


@router.get("/api/projects/{project_id}/train/runs")
def list_runs(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    runs_dir = layout.training_runs_dir()
    from src.training.run_manager import RunManager

    return RunManager.list_project_runs(runs_dir)


@router.get("/api/projects/{project_id}/train/runs/registry")
def get_run_registry(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ExperimentRunRegistry.build(project)


@router.get("/api/projects/{project_id}/train/runs/{run_id}/metrics")
def get_run_metrics(project_id: str, run_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id)
    metrics_file = run_dir / "metrics.json"
    if not metrics_file.exists():
        raise HTTPException(status_code=404, detail="Metrics file not found for this run")

    try:
        with open(metrics_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            payload.setdefault("run_id", run_id)
            config_file = run_dir / "train_config.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config_payload = json.load(f)
                    if isinstance(config_payload, dict):
                        payload.setdefault("train_config", config_payload)
                        configured_epochs = config_payload.get("epochs") or config_payload.get("total_epochs")
                        if "total_epochs" not in payload and configured_epochs is not None:
                            payload["total_epochs"] = int(configured_epochs)
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
            summary_file = run_dir / "run_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_payload = json.load(f)
                    if isinstance(summary_payload, dict):
                        payload.setdefault("run_summary", summary_payload)
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
        schema_file = run_dir / "metric_schema.json"
        if schema_file.exists() and isinstance(payload, dict):
            with open(schema_file, "r", encoding="utf-8") as f:
                payload.setdefault("metric_schema", json.load(f))
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}/train/runs/{run_id}/artifacts")
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
                    "status": "Ready",
                })
            elif item.is_dir() and item.name != "__pycache__":
                scan_dir(item, base)

    scan_dir(run_dir, run_dir)
    return artifacts


@router.get("/api/projects/{project_id}/train/runs/{run_id}/artifacts/download/{filename}")
def download_run_artifact(project_id: str, run_id: str, filename: str, path: Optional[str] = None, _token=Depends(require_api_token)):
    import re

    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")

    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(filename).name
    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id).resolve()

    if path:
        file_path = (run_dir / path).resolve()
    else:
        file_path = (run_dir / safe_filename).resolve()

    try:
        file_path.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid path")

    if not file_path.exists():
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


@router.post("/api/projects/{project_id}/train/runs/{run_id}/export-onnx")
def export_run_onnx(project_id: str, run_id: str):
    require_feature("export_onnx")()
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return ExportService.export_run_onnx(project_id, project, run_id)
    except ExportableModelNotFound as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExportServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/projects/{project_id}/train/stop")
def stop_training(project_id: str):
    project = ProjectManager.get_project(project_id)
    TrainerDispatcher.stop_training(project_id, project)
    return {"status": "stopping", "message": "Stop request sent."}


@router.post("/api/projects/{project_id}/train/abort")
def abort_training(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        TrainerDispatcher.stop_training(project_id, project)
    except Exception:
        pass
    state = TrainingStateStore.mark_stopped(project_id, error="User aborted training.")
    return {"status": "stopped", "message": "Training abort requested.", "state": state}


@router.get("/api/projects/{project_id}/train/status")
def get_train_status(project_id: str):
    project = ProjectManager.get_project(project_id)
    return TrainerDispatcher.get_status(project_id, project)

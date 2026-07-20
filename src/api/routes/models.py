import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.model_registry import ModelRegistry
from src.model_store import ModelStore
from src.model_system import ModelCatalog
from src.model_system.catalog import normalize_task_family
from src.model_install_manager import MODEL_INSTALL_MANAGER
from src.model_recommendation import annotate_hardware_fit, rank_models_for_project
from src.model_system.research_gate import evaluate_research_candidates
from src.model_sources import list_model_sources
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.system_capabilities import get_system_capabilities


router = APIRouter()


class DeleteModelWeightsRequest(BaseModel):
    model_ids: List[str]
    confirm: bool = False


class InstallModelRequest(BaseModel):
    model_id: str
    confirm: bool = False


@router.get("/api/models/catalog")
def list_system_model_catalog(
    architecture: Optional[str] = Query(None),
    usage: str = Query("all"),
):
    if usage == "inference":
        models = ModelCatalog.list_inference_supported(project=None, architecture=architecture)
    elif usage == "train":
        models = ModelCatalog.list_trainable(project=None, architecture=architecture)
    else:
        models = ModelCatalog.list_all(project=None, architecture=architecture)
    capabilities = get_system_capabilities()
    models = annotate_hardware_fit(models, capabilities)
    return {
        "architecture": architecture,
        "usage": usage,
        "models": models,
        "sources": list_model_sources(),
        "hardware": capabilities,
        "summary": {
            "total": len(models),
            "installed": sum(1 for model in models if model.get("installed")),
            "usable": sum(1 for model in models if model.get("usable")),
            "not_installed": sum(1 for model in models if model.get("install_state") == "not_installed"),
        },
    }


@router.get("/api/models/sources")
def get_system_model_sources():
    return {"sources": list_model_sources()}


@router.post("/api/models/install")
def install_system_model(request: InstallModelRequest):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Model installation requires explicit confirmation")
    model = ModelCatalog.get_model(None, request.model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if not model.get("installation_required"):
        raise HTTPException(status_code=400, detail="This model does not require installation")
    try:
        return MODEL_INSTALL_MANAGER.start(model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/models/install/jobs/{job_id}")
def get_model_install_job(job_id: str):
    try:
        return MODEL_INSTALL_MANAGER.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model install job not found") from exc


@router.websocket("/api/models/install/jobs/{job_id}/ws")
async def monitor_model_install_job(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_updated = ""
    try:
        while True:
            try:
                job = MODEL_INSTALL_MANAGER.get(job_id)
            except KeyError:
                await websocket.send_json({"job_id": job_id, "status": "failed", "error": "Model install job not found"})
                await websocket.close(code=4404)
                return
            updated = str(job.get("updated_at") or "")
            if updated != last_updated:
                await websocket.send_json(job)
                last_updated = updated
            if str(job.get("status") or "").lower() in {"completed", "failed", "cancelled"}:
                await websocket.close()
                return
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return


@router.post("/api/models/install/jobs/{job_id}/cancel")
def cancel_model_install_job(job_id: str):
    try:
        return MODEL_INSTALL_MANAGER.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model install job not found") from exc


@router.post("/api/models/install/jobs/{job_id}/retry")
def retry_model_install_job(job_id: str):
    try:
        return MODEL_INSTALL_MANAGER.retry(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model install job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}/models")
def list_project_models(project_id: str, scope: str = Query("deployable")):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    normalized_scope = (scope or "deployable").strip().lower()
    if normalized_scope in {"all", "history", "manage", "manager"}:
        return ModelRegistry.list_models(project)
    if normalized_scope in {"best", "deployable", "runtime", "selector"}:
        return ModelRegistry.list_deployable_models(project)
    return ModelRegistry.list_models(project)


@router.post("/api/projects/{project_id}/models/weights/delete")
def delete_project_model_weights(project_id: str, request: DeleteModelWeightsRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation")

    model_ids = [str(model_id).strip() for model_id in request.model_ids if str(model_id).strip()]
    if not model_ids:
        raise HTTPException(status_code=400, detail="No model weights selected")
    if len(model_ids) > 50:
        raise HTTPException(status_code=400, detail="Too many model weights selected")

    layout = ProjectLayout.from_project(project)
    runs_dir = (layout.project_dir / "training" / "runs").resolve()
    deleted: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for model_id in dict.fromkeys(model_ids):
        try:
            model = ModelRegistry.resolve_model(project, model_id)
            weight_type = str(model.get("weight_type") or "").lower()
            if weight_type not in {"best", "last"}:
                skipped.append({"model_id": model_id, "reason": "unsupported_weight_type"})
                continue

            weight_path = Path(model.get("internal_weight_path") or "").resolve()
            if runs_dir not in weight_path.parents:
                skipped.append({"model_id": model_id, "reason": "outside_training_runs"})
                continue
            if weight_path.name not in {"best.pt", "last.pt"}:
                skipped.append({"model_id": model_id, "reason": "unsupported_filename"})
                continue
            if not weight_path.exists() or not weight_path.is_file():
                skipped.append({"model_id": model_id, "reason": "missing_file"})
                continue

            file_size = weight_path.stat().st_size
            weight_path.unlink()
            deleted.append({
                "model_id": model_id,
                "run_id": model.get("run_id"),
                "weight_type": weight_type,
                "path": model.get("weight_path_display"),
                "file_size": file_size,
            })
        except ValueError:
            skipped.append({"model_id": model_id, "reason": "not_found"})
        except Exception as exc:
            skipped.append({"model_id": model_id, "reason": f"delete_failed: {exc}"})

    return {
        "success": True,
        "deleted": deleted,
        "skipped": skipped,
        "remaining_count": len(ModelRegistry.list_models(project)),
    }


@router.get("/api/projects/{project_id}/models/catalog")
def list_project_model_catalog(
    project_id: str,
    architecture: Optional[str] = Query(None),
    usage: str = Query("train"),
    objective: str = Query("balanced"),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    task_family = project.get("task_type")
    if usage == "inference":
        models = ModelCatalog.list_inference_supported(project=project, task_family=task_family, architecture=architecture)
    elif usage == "guide":
        normalized_task = normalize_task_family(task_family)
        models = [
            model for model in ModelCatalog.list_all(project=project, architecture=architecture)
            if normalize_task_family(model.get("task_family")) == normalized_task
        ]
    elif usage == "all":
        models = ModelCatalog.list_all(project=project, architecture=architecture)
    else:
        models = ModelCatalog.list_trainable(project=project, task_family=task_family, architecture=architecture)
    capabilities = get_system_capabilities()
    models = annotate_hardware_fit(models, capabilities)
    models = rank_models_for_project(models, capabilities, project, objective)
    return {
        "project_id": project_id,
        "architecture": architecture,
        "usage": usage,
        "task_family": task_family,
        "objective": objective if objective in {"balanced", "speed", "accuracy"} else "balanced",
        "models": models,
        "hardware": capabilities,
        "decision_summary": {
            "sample_count": (models[0].get("decision_context") or {}).get("sample_count", 0) if models else 0,
            "recommended": [model.get("model_id") for model in models if model.get("recommended_for_project")],
        },
    }


@router.get("/api/models/research")
def list_model_research_candidates():
    return evaluate_research_candidates()


@router.post("/api/projects/{project_id}/models/import/yolo-pt")
def import_project_yolo_pt_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or not file.filename.lower().endswith(".pt"):
        raise HTTPException(status_code=400, detail="Only YOLO .pt model files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_yolo_pt(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Model import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/models/import/yolo-yaml")
def import_project_yolo_yaml_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(status_code=400, detail="Only YOLO model architecture .yaml / .yml files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_yolo_yaml(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Model YAML import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/models/import/onnx")
def import_project_onnx_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".onnx":
        raise HTTPException(status_code=400, detail="Only .onnx model files are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_onnx(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["ONNX import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/models/import/rnn-package")
def import_project_rnn_package_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only .zip RNN model packages are supported in this phase")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_rnn_package(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["RNN package import failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/models/import/custom-package")
def import_project_custom_package_model(
    project_id: str,
    display_name: str = Form(...),
    task_family: str = Form(...),
    file: UploadFile = File(...),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only .zip custom model packages are supported in Phase P1-A")

    from src.security_utils import safe_filename

    layout = ProjectLayout.from_project(project)
    import_id = f"model_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir = layout.tmp_dir / "model_import_uploads" / import_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_filename(file.filename)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = ModelCatalog.import_custom_package(
            project=project,
            source_path=temp_path,
            display_name=display_name.strip(),
            task_family=task_family,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("validation", {}).get("errors", ["Custom package validation failed"]))
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/request")
def request_custom_package_dry_run(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.request_custom_package_dry_run(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package dry-run request failed"))
    return result


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/approval")
def approve_custom_package_dry_run(
    project_id: str,
    model_id: str,
    decision: str = Form(...),
    approved_by: str = Form("local_user"),
    note: str = Form(""),
):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = ModelCatalog.record_custom_package_dry_run_approval(
            project,
            model_id,
            decision=decision,
            approved_by=approved_by,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package dry-run approval failed"))
    return result


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/mock")
def run_custom_package_mock_dry_run(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.run_custom_package_mock_dry_run(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("dry_run", result.get("error", "Custom package mock dry-run failed")))
    return result


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/plan")
def build_custom_package_sandbox_plan(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.build_custom_package_sandbox_plan(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("plan", result.get("error", "Custom package sandbox plan failed")))
    return result


@router.get("/api/projects/{project_id}/models/import/custom-package/{model_id}/dry-run/audit")
def get_custom_package_sandbox_audit(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.get_custom_package_sandbox_audit(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package sandbox audit failed"))
    return result


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/enablement")
def evaluate_custom_package_enablement(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.evaluate_custom_package_enablement(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package enablement policy failed"))
    return result


@router.post("/api/projects/{project_id}/models/import/custom-package/{model_id}/integration")
def build_custom_package_integration_contract(project_id: str, model_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = ModelCatalog.build_custom_package_integration_contract(project, model_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Custom package integration contract failed"))
    return result


@router.get("/api/models/weights")
def list_model_store_weights():
    models_dir = ModelStore.models_dir()
    weights = []
    for path in sorted(models_dir.rglob("*.pt")):
        if not path.is_file():
            continue
        try:
            resolved = ModelStore.validate_model_store_path(path)
            rel = resolved.relative_to(models_dir).as_posix()
            stat = resolved.stat()
            weights.append({
                "name": resolved.name,
                "path": rel,
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except ValueError:
            continue
    return {"models_dir": models_dir.as_posix(), "weights": weights}

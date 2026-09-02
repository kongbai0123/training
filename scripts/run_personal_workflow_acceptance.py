"""Run real CNN, RNN, and Tabular workflows in an isolated user-data root."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TERMINAL = {"completed", "failed", "stopped", "cancelled", "interrupted"}


def _wait_for_run(project_id: str, run_id: str, timeout: int = 1200) -> dict:
    from src.project_manager import ProjectManager
    from src.training.state_store import TrainingStateStore

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = TrainingStateStore.get_state(project_id)
        if str(state.get("status") or "").lower() in TERMINAL:
            project = ProjectManager.get_project(project_id) or {}
            record = next(
                (item for item in project.get("training_runs", []) if item.get("run_id") == run_id),
                {},
            )
            status = str(record.get("status") or state.get("status") or "").lower()
            if status != "completed":
                raise RuntimeError(f"{project_id}/{run_id} ended as {status}: {record.get('error') or state.get('error')}")
            return record
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {project_id}/{run_id}")


def _evaluation(project_id: str, run_id: str) -> dict:
    from src.api.routes.evaluation import get_evaluation_results

    payload = get_evaluation_results(project_id)
    if not payload.get("success") or payload.get("run_id") != run_id:
        raise RuntimeError(f"Evaluation is unavailable for {project_id}/{run_id}: {payload}")
    return {
        "run_id": payload.get("run_id"),
        "architecture": payload.get("architecture"),
        "metric_cards": len(payload.get("metric_cards") or []),
        "artifacts": len(payload.get("artifacts") or []),
    }


def _best_model(project: dict, run_id: str) -> dict:
    from src.model_registry import ModelRegistry

    models = [
        item for item in ModelRegistry.list_models(project)
        if item.get("run_id") == run_id and item.get("weight_type") == "best"
    ]
    if not models:
        raise RuntimeError(f"No best model registered for {run_id}")
    return models[0]


def _train(project_id: str, config: dict) -> tuple[dict, dict]:
    from src.project_manager import ProjectManager
    from src.training.readiness_service import TrainingReadinessService
    from src.training.start_service import TrainingStartService

    project = ProjectManager.get_project(project_id)
    readiness = TrainingReadinessService.check(project_id, project, config)
    if not readiness.get("ready"):
        raise RuntimeError(f"Readiness failed for {project_id}: {readiness.get('blockers')}")
    started = TrainingStartService.start(project_id, project, config)
    run_id = started["run_id"]
    run = _wait_for_run(project_id, run_id)
    return readiness, run


def _cnn(model_source: Path) -> dict:
    import cv2
    import numpy as np

    from src.app_paths import MODELS_DIR
    from src.inference_engine import InferenceEngine
    from src.project_layout import ProjectLayout
    from src.project_manager import ProjectManager
    from src.training.export_service import ExportService

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_target = MODELS_DIR / model_source.name
    shutil.copy2(model_source, model_target)

    project = ProjectManager.create_project("Acceptance CNN", "instance_segmentation", ["target"])
    layout = ProjectLayout.from_project(project)
    raw_images = layout.resolve_raw_images_dir().path
    raw_images.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(12):
        image = np.full((96, 96, 3), 32, dtype=np.uint8)
        offset = 14 + (index % 4) * 3
        cv2.rectangle(image, (offset, 20), (offset + 42, 72), (40, 210, 245), -1)
        filename = f"sample_{index:02d}.png"
        cv2.imwrite(str(raw_images / filename), image)
        split = "train" if index < 8 else ("val" if index < 10 else "test")
        records.append({
            "filename": filename,
            "width": 96,
            "height": 96,
            "split": split,
            "status": "annotated",
            "annotations": [{
                "category": "target",
                "shape_type": "polygon",
                "points": [[offset, 20], [offset + 42, 20], [offset + 42, 72], [offset, 72]],
            }],
        })
    project["images"] = records
    project["annotation_progress"] = {"total": 12, "annotated": 12, "flagged": 0, "skipped": 0}
    if not ProjectManager.save_project(project["project_id"], project):
        raise RuntimeError("Unable to save CNN fixture")

    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = "gpu"
    except Exception:
        pass
    run_id = "personal_cnn_5e"
    config = {
        "model": model_target.resolve().as_posix(),
        "backend": "ultralytics_yolo",
        "epochs": 5,
        "batch_size": 2,
        "imgsz": 96,
        "lr0": 0.01,
        "device": device,
        "patience": 5,
        "workers": 0,
        "workers_mode": "custom",
        "cache": False,
        "amp": device == "gpu",
        "seed": 42,
        "save_period": 5,
        "close_mosaic": 0,
        "optimizer": "auto",
        "run_id": run_id,
    }
    readiness, run = _train(project["project_id"], config)
    project = ProjectManager.get_project(project["project_id"])
    model = _best_model(project, run_id)
    prediction = InferenceEngine.run_image_inference(
        project, model, raw_images / "sample_10.png",
        {"conf": 0.01, "iou": 0.7, "imgsz": 96, "device": device, "show_mask": True, "show_bbox": True},
    )
    exported = ExportService.export_project_model(project["project_id"], project, run_id=run_id, export_format="pt")
    return {
        "project_id": project["project_id"], "run_id": run_id, "device": device,
        "readiness": readiness["ready"], "status": run["status"],
        "evaluation": _evaluation(project["project_id"], run_id),
        "prediction_count": len(prediction.get("predictions") or []),
        "inference_job": prediction["job_id"], "export": exported["pt_path"],
    }


def _rnn() -> dict:
    from fastapi import UploadFile

    from src.project_layout import ProjectLayout
    from src.project_manager import ProjectManager
    from src.rnn_inference_engine import RNNSequenceInferenceEngine
    from src.training.export_service import ExportService
    from src.training.rnn_config import import_sequence_dataset, update_project_rnn_config

    project = ProjectManager.create_project("Acceptance RNN", "sequence_classification", ["normal", "alarm"])
    rows = ["sequence_id,timestep,split,feature_1,feature_2,label"]
    for split, count in (("train", 8), ("val", 3), ("test", 2)):
        for sequence_index in range(count):
            label = "alarm" if sequence_index % 2 else "normal"
            sequence_id = f"{split}_{sequence_index:02d}"
            for step in range(12):
                base = 1.0 if label == "alarm" else 0.0
                rows.append(f"{sequence_id},{step},{split},{base + step * 0.03:.4f},{base + step * 0.02:.4f},{label}")
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    imported = import_sequence_dataset(project, UploadFile(filename="sequence.csv", file=io.BytesIO(csv_bytes)))
    result = update_project_rnn_config(project["project_id"], project, {
        "feature_columns": ["feature_1", "feature_2"], "target_column": "label",
        "sequence_column": "sequence_id", "time_column": "timestep",
        "sequence_length": 6, "stride": 3, "horizon": 1, "task_head": "classification",
    })
    if not result["validation"]["valid"]:
        raise RuntimeError(f"RNN configuration invalid: {result['validation']}")
    run_id = "personal_rnn_5e"
    config = {
        "model": "lstm", "backend": "pytorch_lstm", "epochs": 5, "batch_size": 8,
        "imgsz": 32, "lr0": 0.001, "device": "cpu", "workers": 0, "cache": False,
        "amp": False, "seed": 42, "run_id": run_id, "sequence_length": 6,
        "stride": 3, "horizon": 1, "task_head": "classification", "hidden_size": 16,
        "num_layers": 1, "dropout": 0.0, "bidirectional": False,
    }
    readiness, run = _train(project["project_id"], config)
    project = ProjectManager.get_project(project["project_id"])
    model = _best_model(project, run_id)
    source = ProjectLayout.from_project(project).project_dir / imported["imported_files"][0]
    prediction = RNNSequenceInferenceEngine.run_csv_sequence_inference(project, model, source, {"device": "cpu"})
    exported = ExportService.export_project_model(project["project_id"], project, run_id=run_id)
    return {
        "project_id": project["project_id"], "run_id": run_id,
        "readiness": readiness["ready"], "status": run["status"],
        "evaluation": _evaluation(project["project_id"], run_id),
        "prediction_count": len(prediction.get("predictions") or []),
        "inference_job": prediction["job_id"], "export": exported["package_path"],
    }


def _tabular() -> dict:
    from fastapi import UploadFile

    from src.project_layout import ProjectLayout
    from src.project_manager import ProjectManager
    from src.tabular_config import import_tabular_csv, update_project_tabular_config
    from src.tabular_xgboost_inference import TabularXGBoostInferenceService
    from src.training.export_service import ExportService

    project = ProjectManager.create_project("Acceptance Tabular", "tabular_classification", ["normal", "alarm"])
    rows = ["temperature,pressure,vibration,target"]
    for index in range(120):
        alarm = index % 3 == 0
        rows.append(f"{70 + index * 0.2:.3f},{100 + index * 0.1:.3f},{1.2 if alarm else 0.2:.3f},{'alarm' if alarm else 'normal'}")
    imported = import_tabular_csv(
        project,
        UploadFile(filename="quality.csv", file=io.BytesIO(("\n".join(rows) + "\n").encode("utf-8"))),
    )
    configured = update_project_tabular_config(project["project_id"], project, {
        **imported["suggested_config"], "task_head": "classification", "seed": 42,
        "train_ratio": 0.7, "val_ratio": 0.15, "test_ratio": 0.15,
    })
    if not configured["validation"]["valid"]:
        raise RuntimeError(f"Tabular configuration invalid: {configured['validation']}")
    run_id = "personal_tabular_5r"
    config = {
        "model": "xgboost_classifier", "backend": "xgboost_tabular", "epochs": 5,
        "batch_size": 1, "imgsz": 32, "lr0": 0.1, "device": "cpu", "workers": 1,
        "cache": False, "amp": False, "seed": 42, "run_id": run_id,
        "task_head": "classification", "learning_rate": 0.1, "max_depth": 3,
        "subsample": 1.0, "colsample_bytree": 1.0,
    }
    readiness, run = _train(project["project_id"], config)
    project = ProjectManager.get_project(project["project_id"])
    model = _best_model(project, run_id)
    service = TabularXGBoostInferenceService.load_from_run(
        Path(model["internal_weight_path"]).parent.parent,
        trusted_root=ProjectLayout.from_project(project).project_dir,
    )
    prediction = service.predict_one({"temperature": 91.0, "pressure": 112.0, "vibration": 1.2})
    exported = ExportService.export_project_model(project["project_id"], project, run_id=run_id)
    return {
        "project_id": project["project_id"], "run_id": run_id,
        "readiness": readiness["ready"], "status": run["status"],
        "evaluation": _evaluation(project["project_id"], run_id),
        "prediction": prediction.get("predicted_label"), "export": exported["package_path"],
    }


def _journal(root: Path) -> dict:
    from src.task_jobs import TaskJobManager

    journal = root / "tasks"
    job_dir = journal / "acceptance_interrupted"
    job_dir.mkdir(parents=True, exist_ok=True)
    job_dir.joinpath("job.json").write_text(json.dumps({
        "job_id": "acceptance_interrupted", "kind": "training", "title": "Acceptance restart",
        "project_id": "acceptance", "status": "running", "phase": "training",
        "message": "Training", "progress": 50, "history": [],
        "created_at": "2026-09-02T00:00:00+00:00", "updated_at": "2026-09-02T00:00:01+00:00",
        "retry_action": {"page": "training"},
    }), encoding="utf-8")
    restored = TaskJobManager(journal_dir=journal).get("acceptance_interrupted")
    if restored.get("status") != "interrupted" or restored.get("error_code") != "APP_RESTARTED":
        raise RuntimeError(f"Task journal restart state is invalid: {restored}")
    return {key: restored.get(key) for key in ("status", "error_code", "retryable", "retry_action")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--report", type=Path, default=Path("build/reports/personal_workflow_acceptance.json"))
    parser.add_argument("--model", type=Path)
    parser.add_argument("--keep-work-dir", action="store_true")
    args = parser.parse_args()
    root = args.work_dir or Path(tempfile.mkdtemp(prefix="vts-personal-acceptance-"))
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["VTS_USER_DATA_DIR"] = str(root)
    os.environ["LOCAL_TRUSTED_MODE"] = "true"
    os.environ["VTS_ENV"] = "test"

    model_source = args.model or Path(os.environ.get("LOCALAPPDATA", "")) / "VisionTrainingStudio" / "models" / "yolo26n-seg.pt"
    if not model_source.is_file():
        raise FileNotFoundError(f"Local segmentation model not found: {model_source}")

    started = time.time()
    report = {
        "positioning": "personal-local product-like AI training workflow",
        "isolated_user_data": str(root),
        "cnn": _cnn(model_source.resolve()),
        "rnn": _rnn(),
        "tabular": _tabular(),
        "task_restart": _journal(root),
        "elapsed_seconds": round(time.time() - started, 2),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not args.keep_work_dir and args.work_dir is None:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

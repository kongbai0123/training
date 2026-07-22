import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.trainer import YOLOTrainer
from src.system_downloads import copy_file_to_downloads

router = APIRouter()

@router.get("/api/projects/{project_id}/evaluation")
def get_evaluation_results(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    layout = ProjectLayout.from_project(project)
    run_dir = _latest_completed_training_run_dir(project, layout)
    if not run_dir:
        return _empty_evaluation_payload()

    results = _read_evaluation_metrics(run_dir)
    available_plots = _list_evaluation_plots(run_dir)
    plot_exports = _list_vector_plot_exports(run_dir, available_plots)
    artifacts = _list_run_artifact_files(run_dir)

    if not results:
        payload = _empty_evaluation_payload()
        payload["run_id"] = run_dir.name
        payload["plots"] = available_plots
        payload["plot_exports"] = plot_exports
        payload["artifacts"] = artifacts
        return payload

    return {
        "success": True,
        "has_metrics": True,
        "run_id": run_dir.name,
        "metrics": results["metrics"],
        "epochs_completed": results["epochs_completed"],
        "assessment": _build_smart_assessment(project, run_dir, results),
        "plots": available_plots,
        "plot_exports": plot_exports,
        "artifacts": artifacts
    }

@router.get("/api/projects/{project_id}/evaluation/plot/{filename}")
def get_evaluation_plot(project_id: str, filename: str, run_id: Optional[str] = None):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid plot filename")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id) if run_id else _latest_completed_training_run_dir(project, layout)
    if not run_dir:
        raise HTTPException(status_code=404, detail="No completed training run found")

    plot_path = (run_dir / safe_filename).resolve()
    try:
        plot_path.relative_to(run_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid plot path")

    if not plot_path.exists():
        raise HTTPException(status_code=404, detail=f"Plot file {filename} not found")

    return FileResponse(str(plot_path), filename=filename)


@router.post("/api/projects/{project_id}/evaluation/plot/{filename}/save-to-downloads")
def save_evaluation_plot_to_downloads(project_id: str, filename: str, run_id: Optional[str] = None):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid plot filename")
    if Path(safe_filename).suffix.lower() not in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported evaluation plot type")

    layout = ProjectLayout.from_project(project)
    run_dir = layout.training_run_dir(run_id) if run_id else _latest_completed_training_run_dir(project, layout)
    if not run_dir:
        raise HTTPException(status_code=404, detail="No completed training run found")

    plot_path = (run_dir / safe_filename).resolve()
    try:
        plot_path.relative_to(run_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Access denied: invalid plot path")
    if not plot_path.is_file():
        raise HTTPException(status_code=404, detail=f"Plot file {filename} not found")

    destination = copy_file_to_downloads(plot_path, safe_filename)
    return {"success": True, "filename": destination.name, "saved_path": str(destination)}


def _empty_evaluation_payload() -> Dict[str, Any]:
    return {
        "success": True,
        "has_metrics": False,
        "run_id": None,
        "metrics": {
            "map50": 0.0,
            "map50_95": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "box_loss": 0.0,
            "seg_loss": 0.0,
            "cls_loss": 0.0,
            "dfl_loss": 0.0,
        },
        "epochs_completed": 0,
        "plots": [],
        "plot_exports": {},
        "assessment": None,
        "artifacts": [],
    }


def _latest_completed_training_run_dir(project: Dict[str, Any], layout: ProjectLayout) -> Optional[Path]:
    runs = project.get("training_runs") or []
    candidate_ids: List[str] = []
    for run in sorted(runs, key=lambda item: item.get("completed_at") or item.get("created_at") or item.get("run_id") or "", reverse=True):
        run_id = run.get("run_id")
        if not run_id:
            continue
        if run.get("status") == "completed":
            candidate_ids.append(run_id)

    for run_id in candidate_ids:
        run_dir = layout.training_run_dir(run_id)
        if (run_dir / "results.csv").exists() or (run_dir / "metrics.json").exists():
            return run_dir

    runs_dir = layout.training_runs_dir()
    if not runs_dir.exists():
        return None
    candidates = [
        path for path in runs_dir.iterdir()
        if path.is_dir()
        and path.name.startswith("run_")
        and _read_run_summary(path).get("status") == "completed"
        and ((path / "results.csv").exists() or (path / "metrics.json").exists())
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _read_run_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "run_summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_evaluation_metrics(run_dir: Path) -> Optional[Dict[str, Any]]:
    metrics_file = run_dir / "metrics.json"
    if metrics_file.exists():
        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("raw") or {}
            epochs = data.get("epochs") or []
            if isinstance(raw, dict) and raw:
                metrics = _metrics_from_raw_series(raw)
                return {
                    "metrics": metrics,
                    "epochs_completed": len(epochs) or _series_length(raw),
                    "raw": raw,
                }
        except Exception:
            pass

    csv_results = YOLOTrainer.read_results_csv(run_dir)
    if not csv_results:
        return None
    metrics = dict(csv_results.get("metrics") or {})
    last_row = csv_results.get("last_row") or {}
    metrics.update(_metrics_from_last_row(last_row))
    return {
        "metrics": metrics,
        "epochs_completed": csv_results.get("epochs_completed", 0),
        "last_row": last_row,
    }


def _series_length(raw: Dict[str, Any]) -> int:
    lengths = [len(value) for value in raw.values() if isinstance(value, list)]
    return max(lengths) if lengths else 0


def _last_numeric(raw: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        values = raw.get(key)
        if not isinstance(values, list) or not values:
            continue
        for value in reversed(values):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _metrics_from_raw_series(raw: Dict[str, Any]) -> Dict[str, float]:
    precision = _last_numeric(raw, "metrics/precision(M)", "metrics/precision(B)")
    recall = _last_numeric(raw, "metrics/recall(M)", "metrics/recall(B)")
    return {
        "map50": _last_numeric(raw, "metrics/mAP50(M)", "metrics/mAP50(B)"),
        "map50_95": _last_numeric(raw, "metrics/mAP50-95(M)", "metrics/mAP50-95(B)"),
        "precision": precision,
        "recall": recall,
        "f1": _f1_score(precision, recall),
        "box_loss": _last_numeric(raw, "val/box_loss", "train/box_loss"),
        "seg_loss": _last_numeric(raw, "val/seg_loss", "train/seg_loss"),
        "cls_loss": _last_numeric(raw, "val/cls_loss", "train/cls_loss"),
        "dfl_loss": _last_numeric(raw, "val/dfl_loss", "train/dfl_loss"),
    }


def _metrics_from_last_row(row: Dict[str, Any]) -> Dict[str, float]:
    raw = {key: [value] for key, value in row.items()}
    return _metrics_from_raw_series(raw)


def _f1_score(precision: float, recall: float) -> float:
    if precision <= 0 or recall <= 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _list_evaluation_plots(run_dir: Path) -> List[str]:
    preferred = [
        "results.png",
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "BoxF1_curve.png",
        "BoxPR_curve.png",
        "BoxP_curve.png",
        "BoxR_curve.png",
        "MaskF1_curve.png",
        "MaskPR_curve.png",
        "MaskP_curve.png",
        "MaskR_curve.png",
        "F1_curve.png",
        "PR_curve.png",
        "P_curve.png",
        "R_curve.png",
        "labels.jpg",
    ]
    return [name for name in preferred if (run_dir / name).exists()]


def _list_vector_plot_exports(run_dir: Path, plots: List[str]) -> Dict[str, Optional[str]]:
    exports: Dict[str, Optional[str]] = {}
    for plot in plots:
        svg_name = f"{Path(plot).stem}.svg"
        exports[plot] = svg_name if (run_dir / svg_name).is_file() else None
    return exports


def _read_json_object(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _build_smart_assessment(project: Dict[str, Any], run_dir: Path, results: Dict[str, Any]) -> Dict[str, Any]:
    metrics = results.get("metrics") or {}
    raw = results.get("raw") or {}
    config = _read_json_object(run_dir / "train_config.json")
    summary = _read_json_object(run_dir / "run_summary.json")
    precision = float(metrics.get("precision") or 0.0)
    recall = float(metrics.get("recall") or 0.0)
    f1 = float(metrics.get("f1") or 0.0)
    map50 = float(metrics.get("map50") or 0.0)
    map50_95 = float(metrics.get("map50_95") or 0.0)
    quality_score = round(100 * max(0.0, min(1.0, (0.35 * map50_95) + (0.25 * f1) + (0.2 * precision) + (0.2 * recall))))
    signals: List[Dict[str, Any]] = []

    def add_signal(code: str, severity: str, **values: Any) -> None:
        signals.append({"code": code, "severity": severity, "values": values})

    if f1 < 0.5:
        add_signal("low_f1", "critical", f1=round(f1, 4))
    elif f1 < 0.75:
        add_signal("moderate_f1", "warning", f1=round(f1, 4))

    balance_gap = abs(precision - recall)
    if balance_gap >= 0.15:
        code = "precision_below_recall" if precision < recall else "recall_below_precision"
        add_signal(code, "warning", precision=round(precision, 4), recall=round(recall, 4), gap=round(balance_gap, 4))

    localization_gap = max(0.0, map50 - map50_95)
    if localization_gap >= 0.2:
        add_signal("localization_gap", "warning", map50=round(map50, 4), map50_95=round(map50_95, 4), gap=round(localization_gap, 4))

    configured_epochs = int(config.get("epochs") or results.get("epochs_completed") or 0)
    completed_epochs = int(results.get("epochs_completed") or 0)
    best_epoch = int(summary.get("best_epoch") or 0)
    if configured_epochs > 0 and best_epoch > 0:
        if best_epoch <= max(2, int(configured_epochs * 0.4)) and completed_epochs >= max(3, int(configured_epochs * 0.7)):
            add_signal("early_best_epoch", "warning", best_epoch=best_epoch, configured_epochs=configured_epochs)
        elif best_epoch >= int(configured_epochs * 0.9) and completed_epochs >= configured_epochs:
            add_signal("late_best_epoch", "info", best_epoch=best_epoch, configured_epochs=configured_epochs)

    total_images = int((project.get("annotation_progress") or {}).get("total") or len(project.get("images") or []))
    class_count = len(project.get("class_names") or [])
    if total_images and class_count and total_images / class_count < 40:
        add_signal("limited_class_coverage", "warning", total_images=total_images, class_count=class_count, images_per_class=round(total_images / class_count, 1))

    imgsz = int(config.get("imgsz") or 0)
    if imgsz and imgsz < 512 and str(project.get("task_type") or "").lower() in {"detection", "semantic_segmentation", "instance_segmentation"}:
        add_signal("low_input_resolution", "info", imgsz=imgsz)

    loss_values = [float(value) for value in (raw.get("val/box_loss") or raw.get("val/seg_loss") or []) if isinstance(value, (int, float))]
    if len(loss_values) >= 5 and min(loss_values) > 0 and loss_values[-1] >= min(loss_values) * 1.25:
        add_signal("validation_loss_rising", "warning", best_loss=round(min(loss_values), 4), last_loss=round(loss_values[-1], 4))

    if not signals:
        add_signal("healthy_balance", "positive", f1=round(f1, 4), map50_95=round(map50_95, 4))

    severity_penalty = sum({"critical": 15, "warning": 7, "info": 2, "positive": 0}.get(item["severity"], 0) for item in signals)
    score = max(0, min(100, quality_score - severity_penalty))
    verdict = "strong" if score >= 85 else "usable" if score >= 70 else "attention" if score >= 50 else "weak"
    return {
        "score": score,
        "verdict": verdict,
        "signals": signals[:6],
        "context": {
            "run_id": run_dir.name,
            "model": config.get("model") or summary.get("model") or "--",
            "task_type": project.get("task_type") or "--",
            "configured_epochs": configured_epochs,
            "completed_epochs": completed_epochs,
            "best_epoch": best_epoch,
            "batch_size": config.get("batch_size"),
            "imgsz": config.get("imgsz"),
            "patience": config.get("patience"),
            "device": config.get("device"),
            "total_images": total_images,
            "class_count": class_count,
        },
    }


def _list_run_artifact_files(run_dir: Path) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []

    def scan_dir(path: Path, base: Path) -> None:
        for item in path.iterdir():
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

    if run_dir.exists():
        scan_dir(run_dir, run_dir)
    artifacts.sort(key=lambda item: item["rel_path"])
    return artifacts




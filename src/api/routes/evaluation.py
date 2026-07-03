import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.trainer import YOLOTrainer

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
    artifacts = _list_run_artifact_files(run_dir)

    if not results:
        payload = _empty_evaluation_payload()
        payload["run_id"] = run_dir.name
        payload["plots"] = available_plots
        payload["artifacts"] = artifacts
        return payload

    return {
        "success": True,
        "has_metrics": True,
        "run_id": run_dir.name,
        "metrics": results["metrics"],
        "epochs_completed": results["epochs_completed"],
        "plots": available_plots,
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




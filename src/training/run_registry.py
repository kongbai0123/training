from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.project_layout import ProjectLayout
from src.run_filters import is_test_run
from src.training.compare_service import CompareService


class ExperimentRunRegistry:
    @classmethod
    def build(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        runs_dir = layout.training_runs_dir()
        runs: List[Dict[str, Any]] = []
        if runs_dir.exists():
            allowed = cls._project_run_ids(project)
            restrict = bool(project.get("training_runs"))
            for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
                if not run_dir.is_dir():
                    continue
                if restrict and run_dir.name not in allowed:
                    continue
                record = cls._project_run_record(project, run_dir.name)
                if is_test_run(run_dir.name, record):
                    continue
                runs.append(cls._run_record(project, run_dir, record))
        return {
            "project_id": project.get("project_id"),
            "run_count": len(runs),
            "runs": runs,
            "artifact_categories": ["config", "metrics", "model", "schema", "report", "diagnostics", "other"],
        }

    @classmethod
    def _run_record(cls, project: Dict[str, Any], run_dir: Path, project_record: Dict[str, Any]) -> Dict[str, Any]:
        manifest = _read_json(run_dir / "artifact_manifest.json")
        metrics = _read_json(run_dir / "metrics.json")
        summary = _read_json(run_dir / "run_summary.json")
        backend = _read_json(run_dir / "backend.json")
        metric_schema = _read_json(run_dir / "metric_schema.json")
        bundle = {
            "run_id": run_dir.name,
            "run_dir": run_dir,
            "metrics": metrics,
            "summary": summary,
            "backend_contract": backend,
            "config": _read_json(run_dir / "train_config.json"),
            "metric_schema": metric_schema,
            "artifact_manifest": manifest,
        }
        artifacts = cls._artifacts(run_dir, manifest)
        return {
            "run_id": run_dir.name,
            "architecture": CompareService.infer_architecture(bundle, project),
            "backend": backend.get("backend") or metrics.get("backend") or project_record.get("backend"),
            "task_type": metrics.get("task_type") or summary.get("task_type") or project_record.get("task_type") or project.get("task_type"),
            "status": summary.get("status") or project_record.get("status") or "unknown",
            "created_at": project_record.get("created_at") or project_record.get("timestamp") or _mtime_iso(run_dir),
            "completed_at": summary.get("completed_at") or project_record.get("completed_at"),
            "primary_metric": summary.get("primary_metric_name") or metrics.get("primary_metric"),
            "primary_value": summary.get("primary_metric_value") or _primary_metric_value(metrics),
            "config": _presence(run_dir, ["train_config.json", "backend.json"]),
            "metrics": _presence(run_dir, ["metrics.json", "results.csv", "metric_schema.json"]),
            "schema": _presence(run_dir, ["preprocess/feature_schema.json", "preprocess/normalization_stats.json", "preprocess/label_encoder.json"]),
            "model": _presence(run_dir, ["weights/best.pt", "weights/last.pt", "weights/best.json", "weights/last.json"]),
            "report": _presence(run_dir, ["run_summary.json"]),
            "diagnostics": cls._diagnostics_presence(metrics),
            "artifacts": artifacts,
            "artifact_counts": _category_counts(artifacts),
        }

    @staticmethod
    def _artifacts(run_dir: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(manifest.get("artifacts"), list) and manifest["artifacts"]:
            source = manifest["artifacts"]
        else:
            source = []
            for path in run_dir.rglob("*"):
                if path.is_file() and path.name != "artifact_manifest.json":
                    source.append({
                        "name": path.name,
                        "path": path.relative_to(run_dir).as_posix(),
                        "type": "",
                        "size_bytes": path.stat().st_size,
                    })
        artifacts = []
        for item in source:
            rel_path = str(item.get("path") or item.get("rel_path") or item.get("name") or "")
            artifacts.append({
                **item,
                "path": rel_path,
                "category": _artifact_category(rel_path, str(item.get("type") or ""), str(item.get("role") or "")),
            })
        return artifacts

    @staticmethod
    def _diagnostics_presence(metrics: Dict[str, Any]) -> Dict[str, Any]:
        keys = ["confusion_matrix", "confusion_labels", "residuals", "prediction_actual_samples"]
        present = [key for key in keys if key in metrics]
        return {
            "present": bool(present),
            "items": present,
        }

    @staticmethod
    def _project_run_ids(project: Dict[str, Any]) -> set[str]:
        return {str(run.get("run_id") or "").strip() for run in project.get("training_runs") or [] if isinstance(run, dict)}

    @staticmethod
    def _project_run_record(project: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        for run in project.get("training_runs") or []:
            if isinstance(run, dict) and str(run.get("run_id") or "").strip() == run_id:
                return run
        return {}


def _artifact_category(path: str, artifact_type: str, role: str) -> str:
    text = f"{path} {artifact_type} {role}".lower()
    if any(token in text for token in ("config", "backend", "contract")):
        return "config"
    if any(token in text for token in ("metrics", "results", "metric_schema")):
        return "metrics"
    if any(token in text for token in ("best.pt", "last.pt", "best.json", "last.json", "model_weight", "xgboost_model")):
        return "model"
    if any(token in text for token in ("feature_schema", "normalization", "label_encoder", "preprocess", "schema")):
        return "schema"
    if any(token in text for token in ("summary", "report")):
        return "report"
    if any(token in text for token in ("confusion", "residual", "prediction_actual", "diagnostic")):
        return "diagnostics"
    return "other"


def _presence(run_dir: Path, rel_paths: List[str]) -> Dict[str, Any]:
    files = []
    for rel_path in rel_paths:
        path = run_dir / rel_path
        if path.exists() and path.is_file():
            files.append({"path": rel_path, "size_bytes": path.stat().st_size})
    return {"present": bool(files), "files": files}


def _category_counts(artifacts: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in artifacts:
        category = str(item.get("category") or "other")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _primary_metric_value(metrics: Dict[str, Any]) -> Any:
    primary = metrics.get("primary_metric")
    best = metrics.get("best_metrics") if isinstance(metrics.get("best_metrics"), dict) else {}
    return best.get(primary) if primary else None


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _mtime_iso(path: Path) -> str:
    from datetime import datetime

    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except Exception:
        return ""

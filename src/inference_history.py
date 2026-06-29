from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.project_layout import ProjectLayout


class InferenceHistory:
    """Read image and sequence inference jobs from a project's inference/jobs folder."""

    @classmethod
    def list_jobs(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        jobs_dir = layout.inference_jobs_dir()
        jobs = []
        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    jobs.append(cls._build_job_record(project, job_dir))
        jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return {"jobs": jobs}

    @classmethod
    def get_job(cls, project: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        jobs_root = layout.inference_jobs_dir().resolve()
        job_dir = (jobs_root / Path(job_id).name).resolve()
        if jobs_root not in job_dir.parents or not job_dir.exists() or not job_dir.is_dir():
            raise FileNotFoundError("Inference job not found")
        record = cls._build_job_record(project, job_dir)
        prediction_path = job_dir / "prediction.json"
        if prediction_path.exists():
            record["prediction"] = cls._read_json(prediction_path)
            record["predictions"] = record["prediction"].get("predictions", []) if isinstance(record["prediction"], dict) else []
        else:
            record["prediction"] = {}
            record["predictions"] = []
        config_path = job_dir / "config.json"
        record["config"] = cls._read_json(config_path) if config_path.exists() else {}
        return record

    @classmethod
    def _build_job_record(cls, project: Dict[str, Any], job_dir: Path) -> Dict[str, Any]:
        summary = cls._read_json(job_dir / "summary.json")
        config = cls._read_json(job_dir / "config.json")
        job_id = job_dir.name
        architecture = str(summary.get("architecture") or "").lower()
        backend = str(summary.get("backend") or "").lower()
        is_rnn = architecture == "rnn" or backend == "pytorch_lstm" or job_id.startswith("seq_job_")
        created_at = summary.get("created_at") or cls._mtime_iso(job_dir)
        files = cls._list_files(project, job_dir)

        return {
            "job_id": job_id,
            "project_id": project.get("project_id"),
            "kind": "sequence" if is_rnn else "image",
            "mode": "rnn" if is_rnn else "cnn",
            "architecture": "rnn" if is_rnn else "cnn",
            "backend": summary.get("backend") or ("pytorch_lstm" if is_rnn else "ultralytics_yolo"),
            "status": "completed" if summary else "unknown",
            "created_at": created_at,
            "model_id": summary.get("model_id") or config.get("model_id"),
            "run_id": summary.get("run_id"),
            "task_type": summary.get("task_type"),
            "summary": summary,
            "files": files,
            "sequence_count": summary.get("sequence_count"),
            "prediction_count": summary.get("prediction_count"),
            "inference_time_ms": summary.get("inference_time_ms"),
        }

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _mtime_iso(path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        except OSError:
            return ""

    @staticmethod
    def _list_files(project: Dict[str, Any], job_dir: Path) -> List[Dict[str, Any]]:
        files = []
        project_id = project.get("project_id", "")
        for path in sorted(job_dir.iterdir()):
            if not path.is_file():
                continue
            files.append({
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "url": f"/api/projects/{project_id}/inference/jobs/{job_dir.name}/files/{path.name}",
            })
        return files

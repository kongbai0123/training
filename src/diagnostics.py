from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import platform
import zipfile
import sys
import hashlib

from src.app_paths import LOGS_DIR, TMP_DIR
from src.config import BASE_DIR, PROJECTS_DIR, STATIC_DIR, APP_VERSION, VERSION_INFO
from src.license_manager import build_license_report

SENSITIVE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".wmv",
    ".pt",
    ".pth",
    ".onnx",
    ".engine",
    ".trt",
    ".tflite",
    ".pkl",
    ".joblib",
}

MAX_LOG_BYTES = 80_000
MAX_PROJECTS_IN_SUMMARY = 200


def collect_basic_snapshot() -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "paths": {
            "base_dir": str(BASE_DIR),
            "projects_dir": str(PROJECTS_DIR),
            "static_dir": str(STATIC_DIR),
            "log_dir": str(LOGS_DIR),
            "tmp_dir": str(TMP_DIR),
        },
        "version": APP_VERSION,
        "version_info": VERSION_INFO,
        "license": build_license_report(),
        "diagnostics_policy": {
            "raw_images_included": False,
            "model_weights_included": False,
            "full_project_folders_included": False,
            "recent_logs_only": True,
            "max_log_bytes": MAX_LOG_BYTES,
        },
    }

    try:
        with open("requirements.txt", "r", encoding="utf-8") as f:
            data["requirements"] = [line.strip() for line in f if line.strip()]
    except Exception:
        data["requirements"] = []

    try:
        data["projects_count"] = len([p for p in PROJECTS_DIR.iterdir() if p.is_dir()])
    except Exception:
        data["projects_count"] = 0

    return data


def collect_health_payload() -> Dict[str, Any]:
    torch_version = "Not installed"
    has_gpu = False
    device_name = "CPU"
    memory: Dict[str, Any] = {
        "available_gb": None,
        "total_gb": None,
        "percent_used": None,
        "status": "unavailable",
    }

    try:
        import torch

        torch_version = torch.__version__
        has_gpu = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if has_gpu else "CPU"
    except Exception:
        pass

    try:
        import psutil

        ram = psutil.virtual_memory()
        memory = {
            "available_gb": round(ram.available / (1024**3), 1),
            "total_gb": round(ram.total / (1024**3), 1),
            "percent_used": round(ram.percent, 1),
            "status": "available",
        }
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": APP_VERSION,
        "device": {
            "has_gpu": has_gpu,
            "device_name": device_name,
            "torch_version": torch_version,
        },
        "memory": memory,
        "directories": {
            "base_dir": str(BASE_DIR.resolve().as_posix()),
            "projects_dir": str(PROJECTS_DIR.resolve().as_posix()),
            "static_dir": str(STATIC_DIR.resolve().as_posix()),
            "logs_dir": str(LOGS_DIR.resolve().as_posix()),
            "tmp_dir": str(TMP_DIR.resolve().as_posix()),
        },
    }


def collect_project_summary() -> Dict[str, Any]:
    projects: List[Dict[str, Any]] = []
    if not PROJECTS_DIR.exists():
        return {"projects_dir_exists": False, "project_count": 0, "projects": projects}

    for project_dir in sorted([p for p in PROJECTS_DIR.iterdir() if p.is_dir()], key=lambda p: p.name):
        if len(projects) >= MAX_PROJECTS_IN_SUMMARY:
            break

        project_json = project_dir / "project.json"
        if not project_json.exists():
            continue

        try:
            data = json.loads(project_json.read_text(encoding="utf-8"))
        except Exception as exc:
            projects.append(
                {
                    "project_id": project_dir.name,
                    "load_error": str(exc),
                }
            )
            continue

        file_summary = _build_project_file_counts(project_dir)
        projects.append(
            {
                "project_id": data.get("project_id") or project_dir.name,
                "project_name": data.get("project_name") or "",
                "task_type": data.get("task_type") or "",
                "schema_version": data.get("schema_version") or "",
                "layout_version": data.get("layout_version") or "",
                "created_at": data.get("created_at") or "",
                "updated_at": data.get("updated_at") or "",
                "class_count": len(data.get("class_names") or []),
                "training_runs_count": len(data.get("training_runs") or []),
                "annotation_progress": data.get("annotation_progress") or {},
                "current": data.get("current") or {},
                "file_summary": file_summary,
            }
        )

    return {
        "projects_dir_exists": True,
        "project_count": len(projects),
        "project_limit": MAX_PROJECTS_IN_SUMMARY,
        "projects": projects,
    }


def _build_project_file_counts(project_dir: Path) -> Dict[str, int]:
    buckets = {
        "images": {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"},
        "videos": {".mp4", ".avi", ".mov", ".mkv", ".wmv"},
        "labels": {".txt"},
        "json": {".json"},
        "csv": {".csv"},
        "weights": {".pt", ".pth", ".onnx", ".engine", ".trt", ".tflite"},
    }
    counts = {name: 0 for name in buckets}
    try:
        for item in project_dir.rglob("*"):
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            for name, suffixes in buckets.items():
                if suffix in suffixes:
                    counts[name] += 1
    except Exception:
        counts["scan_error"] = 1
    return counts


def _safe_path_for_report(value: Optional[str]) -> str:
    if not value:
        return ""
    marker = "\\Users\\"
    if marker in value:
        idx = value.index(marker)
        user_seg = value[idx:].split("\\", 3)
        if len(user_seg) > 1:
            return value[:idx] + "\\Users\\<user>" + ("\\" + "\\".join(user_seg[2:]) if len(user_seg) > 2 else "")
    return value


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_recent_log(log_file: Path, target: Path) -> None:
    try:
        with log_file.open("rb") as source:
            source.seek(0, 2)
            size = source.tell()
            source.seek(max(size - MAX_LOG_BYTES, 0), 0)
            payload = source.read()
        target.write_bytes(payload)
    except Exception as exc:
        target.write_text(f"Unable to read log: {exc}", encoding="utf-8")


def _is_sensitive_arcname(arcname: str) -> bool:
    return Path(arcname).suffix.lower() in SENSITIVE_EXTENSIONS


def generate_diagnostics_zip(output_dir: Path | None = None) -> Path:
    if output_dir is None:
        output_dir = TMP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot = collect_basic_snapshot()
    snapshot["static_index_exists"] = (STATIC_DIR / "index.html").exists()
    snapshot["snapshot_id"] = hashlib.sha256(datetime.now(timezone.utc).isoformat().encode("utf-8")).hexdigest()[:16]

    if "path" in snapshot.get("license", {}):
        snapshot["license"]["path"] = _safe_path_for_report(snapshot["license"].get("path", ""))

    work_dir = output_dir / f"diagnostics_work_{snapshot['snapshot_id']}"
    if work_dir.exists():
        for child in work_dir.rglob("*"):
            if child.is_file():
                child.unlink()
    work_dir.mkdir(parents=True, exist_ok=True)

    diagnostics_path = work_dir / "diagnostics.json"
    health_path = work_dir / "health.json"
    project_summary_path = work_dir / "project_summary.json"
    exclusions_path = work_dir / "exclusions.json"

    _write_json(diagnostics_path, snapshot)
    _write_json(health_path, collect_health_payload())
    _write_json(project_summary_path, collect_project_summary())
    _write_json(
        exclusions_path,
        {
            "excluded_by_default": sorted(SENSITIVE_EXTENSIONS),
            "policy": [
                "No raw images are included.",
                "No model weights are included.",
                "No full project folder is included.",
                "Only recent log tails are included.",
            ],
        },
    )

    logs_target = work_dir / "logs"
    logs_target.mkdir(parents=True, exist_ok=True)
    if LOGS_DIR.exists():
        for log_file in sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:10]:
            _write_recent_log(log_file, logs_target / log_file.name)

    zip_path = output_dir / f"diagnostics_report_{snapshot['snapshot_id']}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for report_file in work_dir.rglob("*"):
            if not report_file.is_file():
                continue
            arcname = report_file.relative_to(work_dir).as_posix()
            if _is_sensitive_arcname(arcname):
                continue
            zf.write(report_file, arcname=arcname)

        for rel in ["requirements.txt", "version.json"]:
            candidate = BASE_DIR / rel
            if candidate.exists() and not _is_sensitive_arcname(rel):
                zf.write(candidate, arcname=rel)
    return zip_path

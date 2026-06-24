from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json
import platform
import zipfile
import sys
import hashlib

from src.app_paths import LOGS_DIR, TMP_DIR
from src.config import BASE_DIR, PROJECTS_DIR, STATIC_DIR, APP_VERSION
from src.license_manager import build_license_report


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
        "license": build_license_report(),
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


def generate_diagnostics_zip(output_dir: Path | None = None) -> Path:
    if output_dir is None:
        output_dir = TMP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot = collect_basic_snapshot()
    snapshot["static_index_exists"] = (STATIC_DIR / "index.html").exists()
    snapshot["snapshot_id"] = hashlib.sha256(datetime.now(timezone.utc).isoformat().encode("utf-8")).hexdigest()[:16]

    if "path" in snapshot.get("license", {}):
        snapshot["license"]["path"] = _safe_path_for_report(snapshot["license"].get("path", ""))

    dump_path = output_dir / f"vts_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with dump_path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    zip_path = output_dir / f"diagnostics_report_{snapshot['snapshot_id']}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(dump_path, arcname="diagnostics.json")

        for rel in ["requirements.txt", "version.json"]:
            candidate = BASE_DIR / rel
            if candidate.exists():
                zf.write(candidate, arcname=rel)

        log_dir = LOGS_DIR
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                zf.write(log_file, arcname=f"logs/{log_file.name}")
    return zip_path

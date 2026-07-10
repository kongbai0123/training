from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from src.app_paths import MODELS_DIR
from src.model_system.constants import (
    MODEL_STATUS_AVAILABLE,
    MODEL_STATUS_CORRUPT,
    MODEL_STATUS_NOT_INSTALLED,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_builtin_install_state(
    entry: Dict[str, Any],
    *,
    models_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return a catalog entry with installation state derived from local files."""
    resolved = dict(entry)
    model_format = str(resolved.get("format") or "").lower()
    source = str(resolved.get("source") or "").lower()

    if model_format == "template" or source == "template":
        status = str(resolved.get("status") or MODEL_STATUS_AVAILABLE)
        ready = status == MODEL_STATUS_AVAILABLE and bool(resolved.get("training_enabled", resolved.get("trainable")))
        resolved.update({
            "installation_required": False,
            "installed": ready,
            "usable": ready,
            "install_state": "ready" if ready else status,
            "integrity": "not_applicable",
            "resolved_path": "",
            "file_size": 0,
        })
        return resolved

    if source != "builtin":
        return resolved

    root = Path(models_dir or MODELS_DIR).resolve()
    weight_value = str(resolved.get("weight_path") or resolved.get("weight") or "").strip()
    weight_path = Path(weight_value).expanduser() if weight_value else Path()
    candidate = weight_path.resolve() if weight_value and weight_path.is_absolute() else (root / weight_path).resolve()
    expected_sha = str(resolved.get("sha256") or resolved.get("checksum") or "").strip().lower()

    installed = bool(weight_value and candidate.exists() and candidate.is_file())
    integrity = "missing"
    actual_sha = ""
    status = MODEL_STATUS_NOT_INSTALLED
    usable = False

    if installed:
        if expected_sha:
            actual_sha = file_sha256(candidate)
            if actual_sha.lower() == expected_sha:
                integrity = "verified"
                status = MODEL_STATUS_AVAILABLE
                usable = True
            else:
                integrity = "checksum_mismatch"
                status = MODEL_STATUS_CORRUPT
        else:
            integrity = "unverified"
            status = MODEL_STATUS_AVAILABLE
            usable = True

    resolved.update({
        "status": status,
        "installation_required": True,
        "installed": installed,
        "usable": usable,
        "install_state": status,
        "integrity": integrity,
        "resolved_path": candidate.as_posix() if installed else "",
        "file_size": candidate.stat().st_size if installed else 0,
        "actual_sha256": actual_sha,
    })
    return resolved

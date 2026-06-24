from __future__ import annotations

from pathlib import Path
from typing import Set

from src.path_security import normalize_name, safe_join as _safe_join, safe_filename as _safe_filename, safe_resolve_under as _safe_resolve_under


def safe_filename(name: str) -> str:
    """Backward compatible filename sanitizer."""
    return _safe_filename(name)


def safe_resolve_under(base_dir: Path, target_path: Path) -> Path:
    """Backward compatible secure path resolver."""
    return _safe_resolve_under(base_dir, target_path)


def validate_extension(filename: str, allowed_extensions: Set[str]) -> str:
    return _safe_filename(filename, allowed_exts=allowed_extensions)


def sanitize_run_id(run_id: str) -> str:
    """Ensure run id contains only safe characters."""
    if not run_id:
        raise ValueError("Run ID is required")
    if not run_id.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ValueError(f"Invalid run_id: {run_id}")
    return run_id

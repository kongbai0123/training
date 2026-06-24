from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Set


def normalize_name(name: str) -> str:
    if not name:
        return "unnamed"
    base = Path(name).name
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    if not sanitized or sanitized in {".", ".."} or sanitized.startswith("."):
        sanitized = f"file_{sanitized or 'unnamed'}"
    return sanitized


def safe_resolve_under(base_dir: Path, target: Path) -> Path:
    base = base_dir.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError("Path traversal detected") from exc
    return resolved


def safe_filename(name: str, allowed_exts: Optional[Set[str]] = None) -> str:
    cleaned = normalize_name(name)
    if allowed_exts:
        suffix = Path(cleaned).suffix.lower()
        if suffix not in allowed_exts:
            raise ValueError(f"Invalid extension: {suffix}")
    return cleaned


def safe_join(base_dir: Path, relative_path: str) -> Path:
    candidate = (base_dir / relative_path)
    return safe_resolve_under(base_dir, candidate)

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Set


RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _reject_windows_reserved(name: str) -> None:
    stem = name.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"Reserved Windows name: {name}")


def validate_resource_id(value: str, *, label: str = "resource_id") -> str:
    candidate = str(value or "")
    if candidate in {".", ".."} or candidate.endswith((".", " ")) or not RESOURCE_ID_RE.fullmatch(candidate):
        raise ValueError(f"Invalid {label}")
    _reject_windows_reserved(candidate)
    return candidate


def validate_leaf_filename(name: str, allowed_exts: Optional[Set[str]] = None) -> str:
    candidate = str(name or "")
    if not candidate or len(candidate) > 180 or candidate in {".", ".."}:
        raise ValueError("Invalid filename")
    if candidate.endswith((".", " ")) or any(ch in candidate for ch in ("/", "\\")):
        raise ValueError("Invalid filename")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in candidate):
        raise ValueError("Invalid filename")
    _reject_windows_reserved(candidate)
    if allowed_exts and Path(candidate).suffix.lower() not in allowed_exts:
        raise ValueError(f"Invalid extension: {Path(candidate).suffix.lower()}")
    return candidate


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
    return validate_leaf_filename(name, allowed_exts)


def safe_join(base_dir: Path, relative_path: str) -> Path:
    candidate = (base_dir / relative_path)
    return safe_resolve_under(base_dir, candidate)

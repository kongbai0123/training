from __future__ import annotations

from pathlib import PurePosixPath


USER_DATA_ROOTS = frozenset(
    {
        "projects",
        "models",
        "logs",
        "config",
        "licenses",
        "cache",
        "tmp",
        "components",
        "exports",
        "runs",
        "project_assistant",
    }
)

APP_MUTABLE_FILES = frozenset(
    {
        "VisionTrainingStudio.exe",
        "_internal/version.json",
    }
)
APP_MUTABLE_PREFIXES = (
    "_internal/static/",
    "_internal/data/",
    "_internal/docs/",
)


def normalize_package_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Package path must be a string.")
    value = value.strip()
    if not value or "\x00" in value or "\\" in value:
        raise ValueError(f"Unsafe package path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe package path: {value!r}")
    if ":" in path.parts[0]:
        raise ValueError(f"Unsafe package path: {value!r}")
    normalized = path.as_posix()
    if path.parts[0].casefold() in USER_DATA_ROOTS:
        raise ValueError(f"Update packages cannot modify user data: {normalized}")
    return normalized


def is_app_mutable_path(value: str) -> bool:
    normalized = normalize_package_path(value)
    return normalized in APP_MUTABLE_FILES or normalized.startswith(APP_MUTABLE_PREFIXES)


def require_app_mutable_path(value: str) -> str:
    normalized = normalize_package_path(value)
    if not is_app_mutable_path(normalized):
        raise ValueError(f"Runtime file requires a full installer: {normalized}")
    return normalized

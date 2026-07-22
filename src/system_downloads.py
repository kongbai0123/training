from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional


_DOWNLOADS_FOLDER_ID = "{374DE290-123F-4565-9164-39C4925E467B}"
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def resolve_downloads_dir() -> Path:
    """Return the current user's real Downloads folder without using AppData."""
    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                raw, _ = winreg.QueryValueEx(key, _DOWNLOADS_FOLDER_ID)
            resolved = Path(os.path.expandvars(str(raw))).expanduser()
            if str(resolved).strip():
                return resolved
        except (OSError, ValueError):
            pass

    return Path.home() / "Downloads"


def safe_download_filename(filename: str, default: str = "download") -> str:
    name = Path(str(filename or "")).name.strip()
    name = _INVALID_FILENAME.sub("_", name).rstrip(". ")
    return name or default


def _available_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 10_000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Unable to allocate a unique filename in Downloads.")


def save_bytes_to_downloads(payload: bytes, filename: str) -> Path:
    directory = resolve_downloads_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = _available_path(directory, safe_download_filename(filename))
    destination.write_bytes(payload)
    return destination


def copy_file_to_downloads(source: Path, filename: Optional[str] = None) -> Path:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    directory = resolve_downloads_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = _available_path(directory, safe_download_filename(filename or source.name))
    shutil.copy2(source, destination)
    return destination

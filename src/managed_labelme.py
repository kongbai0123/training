from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from src.app_paths import APP_HOME, COMPONENTS_DIR, TMP_DIR


LABELME_COMPONENT_DIR = COMPONENTS_DIR / "labelme"
LABELME_MANIFEST = "component.json"
MAX_ARCHIVE_BYTES = 3 * 1024**3
MAX_FILE_BYTES = 1024**3


def _platform_id() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "x64" if machine in {"amd64", "x86_64"} else machine
    return f"{system}-{arch}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    normalized = PurePosixPath(str(value or "").replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
        raise ValueError("Component path is not safe")
    return Path(*normalized.parts)


def _read_manifest(root: Path) -> Dict[str, Any]:
    path = root / LABELME_MANIFEST
    if not path.is_file():
        raise ValueError("LabelMe component manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("component_id") != "labelme":
        raise ValueError("Component manifest is not for LabelMe")
    supported = manifest.get("platforms") or []
    if supported and _platform_id() not in supported:
        raise ValueError(f"LabelMe component does not support {_platform_id()}")
    entrypoint = _safe_relative(manifest.get("entrypoint", ""))
    executable = (root / entrypoint).resolve()
    if root.resolve() not in executable.parents or not executable.is_file():
        raise ValueError("LabelMe component entrypoint is missing")
    for relative, expected in (manifest.get("sha256") or {}).items():
        target = (root / _safe_relative(relative)).resolve()
        if root.resolve() not in target.parents or not target.is_file():
            raise ValueError(f"Component file is missing: {relative}")
        if _sha256(target).lower() != str(expected).lower():
            raise ValueError(f"Component checksum failed: {relative}")
    return manifest


def get_managed_labelme_executable() -> Optional[str]:
    try:
        manifest = _read_manifest(LABELME_COMPONENT_DIR)
        return str((LABELME_COMPONENT_DIR / _safe_relative(manifest["entrypoint"])).resolve())
    except Exception:
        return None


def get_labelme_component_status() -> Dict[str, Any]:
    managed = get_managed_labelme_executable()
    system_executable = shutil.which("labelme")
    manifest: Dict[str, Any] = {}
    if managed:
        manifest = _read_manifest(LABELME_COMPONENT_DIR)
    bundled = next((
        path for path in [
            APP_HOME / "components" / "labelme-runtime-windows-x64.zip",
            Path(os.environ.get("VTS_LABELME_COMPONENT_ARCHIVE", "")),
        ]
        if str(path) and path.is_file()
    ), None)
    return {
        "component_id": "labelme",
        "status": "installed" if managed else ("system_available" if system_executable else "not_installed"),
        "runtime_mode": "managed" if managed else ("system" if system_executable else "unavailable"),
        "offline_ready": bool(managed),
        "version": manifest.get("version", ""),
        "managed_executable": managed or "",
        "system_executable": system_executable or "",
        "bundled_archive_available": bool(bundled),
        "bundled_archive": bundled.as_posix() if bundled else "",
    }


def install_labelme_component_archive(archive_path: Path) -> Dict[str, Any]:
    archive_path = Path(archive_path).resolve()
    if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
        raise ValueError("LabelMe component must be a ZIP archive")
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("LabelMe component archive is too large")

    staging = (TMP_DIR / f"labelme_component_{uuid.uuid4().hex}").resolve()
    extracted = staging / "extracted"
    extracted.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            total_size = 0
            for info in archive.infolist():
                relative = _safe_relative(info.filename)
                if info.is_dir():
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Component archive cannot contain symbolic links")
                if info.file_size > MAX_FILE_BYTES:
                    raise ValueError("Component archive contains an oversized file")
                total_size += info.file_size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise ValueError("Expanded LabelMe component is too large")
                target = (extracted / relative).resolve()
                if extracted not in target.parents:
                    raise ValueError("Component archive contains an unsafe path")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        manifest = _read_manifest(extracted)
        destination = LABELME_COMPONENT_DIR.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = destination.with_name("labelme.backup")
        if backup.exists():
            shutil.rmtree(backup)
        try:
            if destination.exists():
                os.replace(destination, backup)
            os.replace(extracted, destination)
            _read_manifest(destination)
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            if backup.exists():
                os.replace(backup, destination)
            raise
        return get_labelme_component_status()
    finally:
        shutil.rmtree(staging, ignore_errors=True)

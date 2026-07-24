from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.update.paths import is_app_mutable_path, normalize_package_path
from src.update.security import sha256_file
from src.update.versioning import load_version_info


IGNORED_DIST_FILES = frozenset({"portable.mode", "portable_manifest.json"})


def scan_dist_files(dist: Path) -> dict[str, dict[str, Any]]:
    dist = dist.resolve()
    if not (dist / "VisionTrainingStudio.exe").is_file():
        raise FileNotFoundError(f"VisionTrainingStudio.exe not found in {dist}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        relative = normalize_package_path(path.relative_to(dist).as_posix())
        if relative in IGNORED_DIST_FILES:
            continue
        result[relative] = {
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "category": "app" if is_app_mutable_path(relative) else "runtime",
        }
    return result


def build_runtime_baseline(dist: Path, version_file: Path, output: Path) -> dict[str, Any]:
    version = load_version_info(version_file)
    files = scan_dist_files(dist)
    payload = {
        "schema_version": 1,
        "product": version.product,
        "app_version": str(version.app_version),
        "runtime_version": version.runtime_version,
        "package_format_version": version.package_format_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "runtime_file_count": sum(item["category"] == "runtime" for item in files.values()),
        "app_file_count": sum(item["category"] == "app" for item in files.values()),
        "files": files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_runtime_baseline(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported runtime baseline schema.")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("Runtime baseline is missing files.")
    for relative, item in files.items():
        normalize_package_path(relative)
        if not isinstance(item, dict) or item.get("category") not in {"app", "runtime"}:
            raise ValueError(f"Invalid baseline entry: {relative}")
    return payload

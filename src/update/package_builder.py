from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from src.update.baseline import load_runtime_baseline, scan_dist_files
from src.update.paths import is_app_mutable_path
from src.update.security import load_private_key, public_key_id, sign_manifest
from src.update.versioning import load_version_info


def build_update_package(
    dist: Path,
    baseline_path: Path,
    version_file: Path,
    private_key_path: Path,
    output: Path,
    release_notes_zh: str = "",
    release_notes_en: str = "",
) -> dict[str, Any]:
    dist = dist.resolve()
    baseline = load_runtime_baseline(baseline_path)
    target_version = load_version_info(version_file)
    if target_version.runtime_version != baseline.get("runtime_version"):
        raise ValueError("Target runtime differs from the baseline; build a full installer.")
    if target_version.package_format_version != baseline.get("package_format_version"):
        raise ValueError("Target update package format differs from the baseline.")
    if str(target_version.app_version) == baseline.get("app_version"):
        raise ValueError("Target app version must differ from the baseline version.")

    baseline_files: dict[str, dict[str, Any]] = baseline["files"]
    target_files = scan_dist_files(dist)
    runtime_changes: list[str] = []
    changed_app_files: list[str] = []
    removals: list[str] = []

    for relative, target in target_files.items():
        before = baseline_files.get(relative)
        if before == target:
            continue
        if not is_app_mutable_path(relative):
            runtime_changes.append(relative)
        else:
            changed_app_files.append(relative)
    for relative, before in baseline_files.items():
        if relative in target_files:
            continue
        if before.get("category") == "runtime":
            runtime_changes.append(relative)
        else:
            removals.append(relative)
    if runtime_changes:
        preview = ", ".join(sorted(runtime_changes)[:5])
        raise ValueError(f"Runtime changed and requires a full installer: {preview}")
    if not changed_app_files and not removals:
        raise ValueError("No application changes were found for the update package.")

    private_key = load_private_key(private_key_path)
    entries = [
        {
            "path": relative,
            "size": target_files[relative]["size"],
            "sha256": target_files[relative]["sha256"],
        }
        for relative in sorted(changed_app_files)
    ]
    manifest = {
        "format_version": 1,
        "product": target_version.product,
        "package_type": "application-update",
        "target_app_version": str(target_version.app_version),
        "runtime_version": target_version.runtime_version,
        "supported_from": [str(baseline["app_version"])],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requires_restart": True,
        "signing_algorithm": "ed25519",
        "signing_key_id": public_key_id(private_key.public_key()),
        "files": entries,
        "remove": sorted(removals),
        "user_data_policy": "preserve",
    }
    signature = sign_manifest(manifest, private_key)

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".part", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            archive.writestr("manifest.sig", signature + "\n")
            archive.writestr("release_notes/zh-TW.md", release_notes_zh)
            archive.writestr("release_notes/en.md", release_notes_en)
            for entry in entries:
                archive.write(dist / Path(entry["path"]), f"payload/{entry['path']}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "archive": output.as_posix(),
        "archive_bytes": output.stat().st_size,
        "target_app_version": str(target_version.app_version),
        "runtime_version": target_version.runtime_version,
        "changed_file_count": len(entries),
        "removed_file_count": len(removals),
    }

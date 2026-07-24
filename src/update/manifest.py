from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import stat
from typing import Any
import zipfile

from src.update.paths import require_app_mutable_path
from src.update.security import load_public_key, public_key_id, sha256_file, verify_manifest_signature
from src.update.versioning import ProductVersion


MAX_UPDATE_FILES = 20_000
MAX_UPDATE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
METADATA_MEMBERS = frozenset(
    {
        "manifest.json",
        "manifest.sig",
        "release_notes/zh-TW.md",
        "release_notes/en.md",
    }
)


@dataclass(frozen=True)
class VerifiedUpdate:
    manifest: dict[str, Any]
    archive_sha256: str
    archive_bytes: int


def validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Update manifest must be an object.")
    if payload.get("format_version") != 1:
        raise ValueError("Unsupported update package format.")
    if payload.get("product") != "Vision Training Studio":
        raise ValueError("Update package belongs to a different product.")
    if payload.get("package_type") != "application-update":
        raise ValueError("Unsupported update package type.")
    ProductVersion.parse(str(payload.get("target_app_version", "")))
    runtime = payload.get("runtime_version")
    if not isinstance(runtime, str) or not runtime.startswith("r"):
        raise ValueError("Update manifest has an invalid runtime version.")
    supported = payload.get("supported_from")
    if not isinstance(supported, list) or not supported:
        raise ValueError("Update manifest must declare supported_from versions.")
    for version in supported:
        ProductVersion.parse(str(version))

    files = payload.get("files")
    removals = payload.get("remove", [])
    if not isinstance(files, list) or not files:
        raise ValueError("Update manifest must contain at least one payload file.")
    if not isinstance(removals, list):
        raise ValueError("Update manifest remove must be a list.")
    if len(files) > MAX_UPDATE_FILES:
        raise ValueError("Update package contains too many files.")

    seen: set[str] = set()
    total = 0
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("Update manifest file entries must be objects.")
        path = require_app_mutable_path(str(entry.get("path", "")))
        folded = path.casefold()
        if folded in seen:
            raise ValueError(f"Duplicate update path: {path}")
        seen.add(folded)
        size = entry.get("size")
        digest = entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"Invalid update file size: {path}")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"Invalid update file digest: {path}")
        int(digest, 16)
        total += size
    if total > MAX_UPDATE_UNCOMPRESSED_BYTES:
        raise ValueError("Update package exceeds the allowed uncompressed size.")

    for value in removals:
        path = require_app_mutable_path(str(value))
        if path.casefold() in seen:
            raise ValueError(f"Path cannot be replaced and removed: {path}")
        seen.add(path.casefold())
    return payload


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def verify_update_archive(archive: Path, public_key_path: Path) -> VerifiedUpdate:
    archive = archive.resolve()
    public_key = load_public_key(public_key_path)
    with zipfile.ZipFile(archive, "r") as package:
        infos = package.infolist()
        folded_names: set[str] = set()
        for info in infos:
            if info.is_dir():
                continue
            if _is_zip_symlink(info):
                raise ValueError(f"Update package contains a symbolic link: {info.filename}")
            folded = info.filename.casefold()
            if folded in folded_names:
                raise ValueError(f"Update package contains a duplicate entry: {info.filename}")
            folded_names.add(folded)
        try:
            manifest = json.loads(package.read("manifest.json").decode("utf-8"))
            signature = package.read("manifest.sig").decode("ascii").strip()
        except KeyError as exc:
            raise ValueError("Update package is missing signed metadata.") from exc
        validate_manifest(manifest)
        expected_key = manifest.get("signing_key_id")
        if expected_key != public_key_id(public_key):
            raise ValueError("Update package was signed by an unknown key.")
        verify_manifest_signature(manifest, signature, public_key)

        declared = {entry["path"]: entry for entry in manifest["files"]}
        payload_members = {
            info.filename.removeprefix("payload/"): info
            for info in infos
            if not info.is_dir() and info.filename.startswith("payload/")
        }
        if set(payload_members) != set(declared):
            missing = sorted(set(declared) - set(payload_members))
            extra = sorted(set(payload_members) - set(declared))
            raise ValueError(f"Update payload mismatch; missing={missing[:1]}, extra={extra[:1]}")
        allowed_members = METADATA_MEMBERS | {f"payload/{path}" for path in declared}
        unexpected = sorted(
            info.filename for info in infos if not info.is_dir() and info.filename not in allowed_members
        )
        if unexpected:
            raise ValueError(f"Update package contains an undeclared file: {unexpected[0]}")

        for relative, entry in declared.items():
            info = payload_members[relative]
            if info.file_size != entry["size"]:
                raise ValueError(f"Update payload size mismatch: {relative}")
            import hashlib

            digest = hashlib.sha256()
            with package.open(info, "r") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"Update payload digest mismatch: {relative}")
        if package.testzip():
            raise ValueError("Update package CRC verification failed.")
    return VerifiedUpdate(
        manifest=manifest,
        archive_sha256=sha256_file(archive),
        archive_bytes=archive.stat().st_size,
    )

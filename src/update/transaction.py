from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any
import uuid
import zipfile

from src.update.manifest import VerifiedUpdate, verify_update_archive
from src.update.paths import require_app_mutable_path
from src.update.security import sha256_file
from src.update.versioning import VersionInfo, ensure_update_compatible, load_version_info


TERMINAL_STATES = frozenset({"completed", "rolled_back"})
RECOVERABLE_STATES = frozenset({"applying", "validating", "rollback_required"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _safe_install_path(root: Path, relative: str) -> Path:
    normalized = require_app_mutable_path(relative)
    root = root.resolve()
    destination = root.joinpath(*normalized.split("/"))
    resolved = destination.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Update destination escapes the installation directory: {relative}") from exc
    current = root
    for part in normalized.split("/")[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"Update destination traverses a symbolic link: {relative}")
    return destination


class UpdateJournal:
    def __init__(self, path: Path):
        self.path = path.resolve()

    def read(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("Unsupported update journal.")
        return payload

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_payload = dict(payload)
        next_payload["updated_at"] = _utc_now()
        _atomic_write_json(self.path, next_payload)
        return next_payload

    def transition(self, state: str, **values: Any) -> dict[str, Any]:
        payload = self.read()
        payload.update(values)
        payload["state"] = state
        payload.setdefault("history", []).append({"state": state, "at": _utc_now()})
        return self.write(payload)


def prepare_update(
    archive: Path,
    install_dir: Path,
    current_version_file: Path,
    public_key_path: Path,
    update_root: Path,
) -> UpdateJournal:
    verified: VerifiedUpdate = verify_update_archive(archive, public_key_path)
    current = load_version_info(current_version_file)
    target = VersionInfo.from_mapping(
        {
            "product": verified.manifest["product"],
            "app_version": verified.manifest["target_app_version"],
            "runtime_version": verified.manifest["runtime_version"],
            "package_format_version": verified.manifest["format_version"],
            "update_channel": current.update_channel,
        }
    )
    ensure_update_compatible(current, target, list(verified.manifest["supported_from"]))

    transaction_id = f"update_{target.app_version}_{uuid.uuid4().hex[:12]}"
    update_root = update_root.resolve()
    staging_dir = update_root / "staging" / transaction_id
    backup_dir = update_root / "backups" / transaction_id
    journal = UpdateJournal(update_root / "journals" / f"{transaction_id}.json")
    staging_dir.mkdir(parents=True, exist_ok=False)
    backup_dir.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(archive, "r") as package:
        for entry in verified.manifest["files"]:
            relative = require_app_mutable_path(entry["path"])
            destination = staging_dir.joinpath(*relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(f"payload/{relative}", "r") as source, destination.open("wb") as target_stream:
                shutil.copyfileobj(source, target_stream, length=1024 * 1024)
            if destination.stat().st_size != entry["size"] or sha256_file(destination) != entry["sha256"]:
                raise ValueError(f"Staged update file verification failed: {relative}")

    payload = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "state": "staged",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "history": [{"state": "staged", "at": _utc_now()}],
        "archive": archive.resolve().as_posix(),
        "archive_sha256": verified.archive_sha256,
        "install_dir": install_dir.resolve().as_posix(),
        "staging_dir": staging_dir.as_posix(),
        "backup_dir": backup_dir.as_posix(),
        "source_app_version": str(current.app_version),
        "target_app_version": str(target.app_version),
        "runtime_version": target.runtime_version,
        "files": verified.manifest["files"],
        "remove": verified.manifest.get("remove", []),
        "backed_up": [],
        "missing_before": [],
        "applied": [],
        "error": "",
    }
    journal.write(payload)
    return journal


def apply_update(journal: UpdateJournal) -> dict[str, Any]:
    payload = journal.read()
    if payload["state"] not in {"staged", "pending"}:
        raise ValueError(f"Update cannot be applied from state {payload['state']}.")
    install_dir = Path(payload["install_dir"]).resolve()
    staging_dir = Path(payload["staging_dir"]).resolve()
    backup_dir = Path(payload["backup_dir"]).resolve()
    affected = [entry["path"] for entry in payload["files"]] + list(payload["remove"])

    try:
        backed_up: list[str] = []
        missing_before: list[str] = []
        for relative in affected:
            source = _safe_install_path(install_dir, relative)
            backup = backup_dir.joinpath(*require_app_mutable_path(relative).split("/"))
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise ValueError(f"Update target is not a regular file: {relative}")
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup)
                backed_up.append(relative)
            else:
                missing_before.append(relative)
        payload = journal.transition(
            "applying",
            backed_up=backed_up,
            missing_before=missing_before,
            applied=[],
        )

        applied: list[str] = []
        for entry in payload["files"]:
            relative = entry["path"]
            source = staging_dir.joinpath(*relative.split("/"))
            destination = _safe_install_path(install_dir, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + f".{payload['transaction_id']}.new")
            shutil.copy2(source, temporary)
            if temporary.stat().st_size != entry["size"] or sha256_file(temporary) != entry["sha256"]:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"Update file changed while applying: {relative}")
            os.replace(temporary, destination)
            applied.append(relative)
            payload = journal.transition("applying", applied=list(applied))

        for relative in payload["remove"]:
            destination = _safe_install_path(install_dir, relative)
            if destination.exists():
                destination.unlink()
            applied.append(relative)
            payload = journal.transition("applying", applied=list(applied))

        payload = journal.transition("validating")
        installed_version = load_version_info(install_dir / "_internal" / "version.json")
        if str(installed_version.app_version) != payload["target_app_version"]:
            raise ValueError("Installed version does not match the update target.")
        if installed_version.runtime_version != payload["runtime_version"]:
            raise ValueError("Installed runtime changed unexpectedly.")
        return journal.transition("completed", error="")
    except Exception as exc:
        journal.transition("rollback_required", error=str(exc))
        rollback_update(journal)
        raise


def rollback_update(journal: UpdateJournal) -> dict[str, Any]:
    payload = journal.read()
    if payload["state"] == "rolled_back":
        return payload
    install_dir = Path(payload["install_dir"]).resolve()
    backup_dir = Path(payload["backup_dir"]).resolve()
    backed_up = set(payload.get("backed_up", []))
    missing_before = set(payload.get("missing_before", []))
    affected = list(dict.fromkeys(payload.get("applied", []) + list(backed_up) + list(missing_before)))
    errors: list[str] = []
    for relative in reversed(affected):
        try:
            destination = _safe_install_path(install_dir, relative)
            backup = backup_dir.joinpath(*require_app_mutable_path(relative).split("/"))
            if relative in backed_up and backup.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + ".rollback")
                shutil.copy2(backup, temporary)
                os.replace(temporary, destination)
            elif relative in missing_before:
                destination.unlink(missing_ok=True)
        except Exception as exc:
            errors.append(f"{relative}: {exc}")
    if errors:
        return journal.transition("rollback_required", rollback_errors=errors)
    return journal.transition("rolled_back", rollback_errors=[])


def recover_incomplete_update(journal: UpdateJournal) -> dict[str, Any]:
    payload = journal.read()
    if payload["state"] in RECOVERABLE_STATES:
        return rollback_update(journal)
    return payload

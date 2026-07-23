from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.update.paths import require_app_mutable_path
from src.update.security import sha256_file
from src.update.transaction import (
    apply_update,
    prepare_update,
    recover_incomplete_update,
)


def _installed_path(root: Path, relative: str) -> Path:
    normalized = require_app_mutable_path(relative)
    destination = root.joinpath(*normalized.split("/")).resolve(strict=False)
    destination.relative_to(root)
    return destination


def _snapshot(root: Path, relatives: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative in relatives:
        path = _installed_path(root, relative)
        result[relative] = {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
            "sha256": sha256_file(path) if path.is_file() else "",
        }
    return result


def _assert_snapshot(
    expected: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
) -> None:
    if actual != expected:
        raise AssertionError(
            "Installed files were not restored exactly:\n"
            + json.dumps({"expected": expected, "actual": actual}, indent=2)
        )


def validate_automatic_rollback(
    archive: Path,
    install_dir: Path,
    version_file: Path,
    public_key: Path,
    update_root: Path,
) -> dict[str, Any]:
    journal = prepare_update(archive, install_dir, version_file, public_key, update_root)
    payload = journal.read()
    affected = [entry["path"] for entry in payload["files"]] + list(payload["remove"])
    before = _snapshot(install_dir, affected)
    staged_version = Path(payload["staging_dir"]) / "_internal" / "version.json"
    staged_version.unlink()
    try:
        apply_update(journal)
    except Exception as exc:
        error = str(exc)
    else:
        raise AssertionError("The deliberately damaged staged update unexpectedly succeeded.")
    final = journal.read()
    if final["state"] != "rolled_back":
        raise AssertionError(f"Expected rolled_back journal, got {final['state']}.")
    _assert_snapshot(before, _snapshot(install_dir, affected))
    return {
        "journal": journal.path.as_posix(),
        "state": final["state"],
        "restored_file_count": len(affected),
        "injected_error": error,
    }


def validate_interrupted_recovery(
    archive: Path,
    install_dir: Path,
    version_file: Path,
    public_key: Path,
    update_root: Path,
) -> dict[str, Any]:
    journal = prepare_update(archive, install_dir, version_file, public_key, update_root)
    payload = journal.read()
    affected = [entry["path"] for entry in payload["files"]] + list(payload["remove"])
    before = _snapshot(install_dir, affected)
    relative = "_internal/version.json"
    destination = _installed_path(install_dir, relative)
    backup = Path(payload["backup_dir"]) / "_internal" / "version.json"
    staged = Path(payload["staging_dir"]) / "_internal" / "version.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, backup)
    temporary = destination.with_name(destination.name + ".interrupted-acceptance")
    shutil.copy2(staged, temporary)
    os.replace(temporary, destination)
    journal.transition(
        "applying",
        backed_up=[relative],
        missing_before=[],
        applied=[relative],
    )
    recovered = recover_incomplete_update(journal)
    if recovered["state"] != "rolled_back":
        raise AssertionError(f"Expected rolled_back recovery, got {recovered['state']}.")
    _assert_snapshot(before, _snapshot(install_dir, affected))
    return {
        "journal": journal.path.as_posix(),
        "state": recovered["state"],
        "restored_file_count": len(affected),
        "interrupted_after": relative,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate rollback and interrupted-update recovery against an installed app."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--update-root", type=Path, required=True)
    args = parser.parse_args()
    install_dir = args.install_dir.resolve()
    version_file = install_dir / "_internal" / "version.json"
    result = {
        "automatic_rollback": validate_automatic_rollback(
            args.archive.resolve(),
            install_dir,
            version_file,
            args.public_key.resolve(),
            args.update_root.resolve() / "automatic",
        ),
        "interrupted_recovery": validate_interrupted_recovery(
            args.archive.resolve(),
            install_dir,
            version_file,
            args.public_key.resolve(),
            args.update_root.resolve() / "interrupted",
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

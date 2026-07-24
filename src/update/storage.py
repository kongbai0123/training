from __future__ import annotations

from pathlib import Path
import shutil
import time
from typing import Iterable


UPDATE_CACHE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
PART_FILE_MAX_AGE_SECONDS = 24 * 60 * 60
ROLLBACK_BACKUP_KEEP_COUNT = 1
JOURNAL_KEEP_COUNT = 10


def _path_size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
    except OSError:
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def update_storage_report(update_root: Path) -> dict[str, int | float]:
    root = update_root.resolve()
    downloads = root / "downloads"
    staging = root / "staging"
    backups = root / "backups"
    journals = root / "journals"
    download_bytes = _path_size(downloads)
    staging_bytes = _path_size(staging)
    backup_bytes = _path_size(backups)
    journal_bytes = _path_size(journals)
    cache_bytes = download_bytes + staging_bytes
    backup_count = sum(1 for path in backups.iterdir() if path.is_dir()) if backups.is_dir() else 0
    part_count = sum(1 for path in downloads.glob("*.part") if path.is_file()) if downloads.is_dir() else 0
    return {
        "downloads_bytes": download_bytes,
        "staging_bytes": staging_bytes,
        "cache_bytes": cache_bytes,
        "backups_bytes": backup_bytes,
        "journals_bytes": journal_bytes,
        "total_bytes": cache_bytes + backup_bytes + journal_bytes,
        "cache_limit_bytes": UPDATE_CACHE_LIMIT_BYTES,
        "cache_percent": round(cache_bytes * 100 / UPDATE_CACHE_LIMIT_BYTES, 2),
        "backup_count": backup_count,
        "part_file_count": part_count,
    }


def _remove(path: Path) -> int:
    size = _path_size(path)
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    return size


def cleanup_expired_parts(update_root: Path, *, now: float | None = None) -> int:
    downloads = update_root.resolve() / "downloads"
    if not downloads.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - PART_FILE_MAX_AGE_SECONDS
    freed = 0
    for path in downloads.glob("*.part"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                freed += _remove(path)
        except OSError:
            continue
    return freed


def _resolved_set(paths: Iterable[Path]) -> set[Path]:
    return {path.resolve() for path in paths}


def cleanup_update_storage(
    update_root: Path,
    *,
    preserve_downloads: Iterable[Path] = (),
    remove_all_backups: bool = False,
    keep_backup_count: int = ROLLBACK_BACKUP_KEEP_COUNT,
    keep_journal_count: int = JOURNAL_KEEP_COUNT,
) -> dict[str, int | float]:
    root = update_root.resolve()
    downloads = root / "downloads"
    staging = root / "staging"
    backups = root / "backups"
    journals = root / "journals"
    preserved = _resolved_set(preserve_downloads)
    freed = 0

    if downloads.is_dir():
        for path in downloads.iterdir():
            if path.resolve() not in preserved:
                freed += _remove(path)
    if staging.is_dir():
        for path in staging.iterdir():
            freed += _remove(path)

    backup_items = (
        sorted(backups.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        if backups.is_dir()
        else []
    )
    retained_backups = 0 if remove_all_backups else max(0, keep_backup_count)
    for path in backup_items[retained_backups:]:
        freed += _remove(path)

    journal_items = (
        sorted(journals.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        if journals.is_dir()
        else []
    )
    for path in journal_items[max(0, keep_journal_count):]:
        freed += _remove(path)

    report = update_storage_report(root)
    report["freed_bytes"] = freed
    return report


def projected_cache_bytes(update_root: Path, destination: Path, expected_bytes: int) -> int:
    report = update_storage_report(update_root)
    current = int(report["cache_bytes"])
    destination = destination.resolve()
    part = destination.with_name(destination.name + ".part")
    resumed_part = _path_size(part)
    return max(0, current - resumed_part) + max(0, int(expected_bytes))

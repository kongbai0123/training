"""Crash-safe project metadata repository.

Large datasets and model artifacts remain on disk.  This repository owns the
small ``project.json`` control document and is the only supported writer for it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar

from src.path_security import safe_resolve_under, validate_resource_id


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class ProjectRepositoryError(RuntimeError):
    code = "PROJECT_REPOSITORY_ERROR"


class ProjectRevisionConflict(ProjectRepositoryError):
    code = "PROJECT_REVISION_CONFLICT"


class ProjectReadOnlyRecovery(ProjectRepositoryError):
    code = "PROJECT_READ_ONLY_RECOVERY"


class _InterProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            if self.path.stat().st_size == 0:
                self.handle.write(b"0")
                self.handle.flush()
                self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.handle:
            return
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


class ProjectRepository:
    BACKUP_LIMIT = 5

    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir.resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def project_dir(self, project_id: str) -> Path:
        validate_resource_id(project_id, label="project_id")
        return safe_resolve_under(self.projects_dir, self.projects_dir / project_id)

    def _thread_lock(self, project_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(project_id, threading.RLock())

    @contextmanager
    def _locked(self, project_id: str) -> Iterator[Path]:
        project_dir = self.project_dir(project_id)
        with self._thread_lock(project_id):
            with _InterProcessLock(project_dir / "_meta" / "project.lock"):
                yield project_dir

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Project document must be a JSON object")
        return value

    def _latest_backup(self, project_dir: Path) -> Optional[Dict[str, Any]]:
        backup_dir = project_dir / "_meta" / "project-backups"
        candidates = sorted(
            backup_dir.glob("project.r*.json"),
            key=lambda path: int(re.search(r"\.r(\d+)\.json$", path.name).group(1)),
            reverse=True,
        ) if backup_dir.exists() else []
        for candidate in candidates:
            try:
                return self._load_json(candidate)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return None

    def _read_stored(self, project_dir: Path, *, recover: bool = True) -> Optional[Dict[str, Any]]:
        path = project_dir / "project.json"
        if not path.exists():
            return None
        try:
            return self._load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            backup = self._latest_backup(project_dir) if recover else None
            if backup is None:
                LOGGER.error("PROJECT_RECOVERY_FAILED project=%s error=%s", project_dir.name, exc)
                return {
                    "project_id": project_dir.name,
                    "revision": 0,
                    "read_only": True,
                    "recovery": {"code": "PROJECT_READ_ONLY_RECOVERY", "message": "Project metadata is damaged and no valid backup exists."},
                }
            self._atomic_replace(project_dir, backup, create_backup=False)
            LOGGER.warning("PROJECT_RECOVERED project=%s revision=%s", project_dir.name, backup.get("revision", 0))
            backup["recovery"] = {"code": "PROJECT_RECOVERED", "message": "Recovered from the latest valid backup."}
            return backup

    def _project_for_runtime(self, project_dir: Path, stored: Dict[str, Any]) -> Dict[str, Any]:
        data = deepcopy(stored)
        raw_dataset = str(data.get("dataset_path") or "dataset")
        candidate = Path(raw_dataset)
        if candidate.is_absolute():
            try:
                safe_resolve_under(project_dir, candidate)
            except ValueError:
                data["read_only"] = True
                data["recovery"] = {"code": "PROJECT_PATH_OUTSIDE_ROOT", "message": "dataset_path is outside the project root."}
                return data
        else:
            candidate = project_dir / candidate
        data["dataset_path"] = str(safe_resolve_under(project_dir, candidate))
        return data

    def _project_for_storage(self, project_dir: Path, runtime: Dict[str, Any]) -> Dict[str, Any]:
        data = deepcopy(runtime)
        for key in ("_layout_report", "auto_label_review_gate", "recovery", "read_only"):
            data.pop(key, None)
        raw_dataset = str(data.get("dataset_path") or "dataset")
        dataset = Path(raw_dataset)
        if not dataset.is_absolute():
            dataset = project_dir / dataset
        dataset = safe_resolve_under(project_dir, dataset)
        data["dataset_path"] = dataset.relative_to(project_dir).as_posix() or "dataset"
        return data

    def read(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._locked(project_id) as project_dir:
            stored = self._read_stored(project_dir)
        return self._project_for_runtime(project_dir, stored) if stored else None

    def mutate(
        self,
        project_id: str,
        callback: Callable[[Dict[str, Any]], T],
        *,
        expected_revision: Optional[int] = None,
        create: bool = False,
        initial: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], T]:
        with self._locked(project_id) as project_dir:
            stored = self._read_stored(project_dir)
            if stored and stored.get("read_only"):
                raise ProjectReadOnlyRecovery(project_id)
            if stored is None:
                if not create:
                    raise FileNotFoundError(project_id)
                stored = deepcopy(initial or {"project_id": project_id, "revision": 0})
            current_revision = int(stored.get("revision") or 0)
            if expected_revision is not None and int(expected_revision) != current_revision:
                raise ProjectRevisionConflict(
                    f"Expected project revision {expected_revision}, current revision is {current_revision}"
                )
            runtime = self._project_for_runtime(project_dir, stored)
            result = callback(runtime)
            if runtime.get("read_only"):
                raise ProjectReadOnlyRecovery(project_id)
            runtime["revision"] = current_revision + 1
            runtime["updated_at"] = datetime.now().isoformat()
            saved = self._project_for_storage(project_dir, runtime)
            self._atomic_replace(project_dir, saved, create_backup=True)
            return self._project_for_runtime(project_dir, saved), result

    def write(self, project_id: str, data: Dict[str, Any], *, expected_revision: Optional[int] = None) -> Dict[str, Any]:
        def replace(current: Dict[str, Any]) -> None:
            current.clear()
            current.update(deepcopy(data))

        saved, _ = self.mutate(
            project_id,
            replace,
            expected_revision=expected_revision,
            create=not (self.project_dir(project_id) / "project.json").exists(),
            initial=data,
        )
        return saved

    def _atomic_replace(self, project_dir: Path, data: Dict[str, Any], *, create_backup: bool) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        target = project_dir / "project.json"
        backup_dir = project_dir / "_meta" / "project-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        if create_backup and target.exists():
            previous = self._load_json(target)
            previous_revision = int(previous.get("revision") or 0)
            backup = backup_dir / f"project.r{previous_revision}.json"
            if not backup.exists():
                shutil.copy2(target, backup)
        fd, temp_name = tempfile.mkstemp(prefix=".project.", suffix=".tmp", dir=project_dir)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
            try:
                directory_fd = os.open(project_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if temp.exists():
                temp.unlink()
        backups = sorted(
            backup_dir.glob("project.r*.json"),
            key=lambda path: int(re.search(r"\.r(\d+)\.json$", path.name).group(1)),
            reverse=True,
        )
        for old in backups[self.BACKUP_LIMIT :]:
            old.unlink(missing_ok=True)

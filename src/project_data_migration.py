from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.config import PROJECTS_DIR


class ProjectDataMigrationTool:
    """Move legacy app-data projects into the current managed projects directory."""

    @staticmethod
    def legacy_projects_dir() -> Path:
        explicit = os.environ.get("VTS_LEGACY_PROJECTS_DIR")
        if explicit:
            return Path(explicit).expanduser().resolve()
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).expanduser().resolve() / "VisionTrainingStudio" / "projects"
        return Path.home() / "AppData" / "Local" / "VisionTrainingStudio" / "projects"

    @classmethod
    def scan(cls) -> Dict[str, Any]:
        source_root = cls.legacy_projects_dir()
        target_root = PROJECTS_DIR.resolve()
        candidates: List[Dict[str, Any]] = []

        if source_root.exists():
            for project_dir in sorted(source_root.iterdir()):
                if not project_dir.is_dir():
                    continue
                project_json = project_dir / "project.json"
                if not project_json.exists():
                    continue
                candidates.append(cls._build_candidate(project_dir, target_root))

        return {
            "source_root": source_root.as_posix(),
            "target_root": target_root.as_posix(),
            "source_exists": source_root.exists(),
            "same_root": source_root == target_root,
            "candidates": candidates,
        }

    @classmethod
    def migrate(cls, project_ids: List[str] | None = None, delete_source: bool = False) -> Dict[str, Any]:
        report = cls.scan()
        if report["same_root"]:
            return {**report, "migrated": [], "skipped": [], "deleted": [], "errors": ["Source and target project roots are the same."]}

        selected = set(project_ids or [])
        candidates = [
            item for item in report["candidates"]
            if not selected or item["project_id"] in selected
        ]
        migrated: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        deleted: List[str] = []
        errors: List[str] = []

        for item in candidates:
            source = Path(item["source_path"]).resolve()
            target = Path(item["target_path"]).resolve()
            if not cls._is_safe_legacy_source(source):
                errors.append(f"Unsafe source path skipped: {source.as_posix()}")
                continue
            if target.exists():
                if delete_source:
                    try:
                        cls._verify_copy(source, target)
                        shutil.rmtree(source)
                        deleted.append(item["project_id"])
                    except Exception as exc:
                        errors.append(f"{item['project_id']}: existing target verification failed before delete: {exc}")
                else:
                    skipped.append({**item, "reason": "target_exists"})
                continue

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target)
                cls._rewrite_project_paths(target)
                cls._write_migration_marker(target, source)
                cls._verify_copy(source, target)
                migrated.append({**item, "status": "migrated"})
                if delete_source:
                    shutil.rmtree(source)
                    deleted.append(item["project_id"])
            except Exception as exc:
                if target.exists() and not (target / "project.json").exists():
                    shutil.rmtree(target, ignore_errors=True)
                errors.append(f"{item['project_id']}: {exc}")

        return {
            **report,
            "migrated": migrated,
            "skipped": skipped,
            "deleted": deleted,
            "errors": errors,
            "delete_source": delete_source,
        }

    @staticmethod
    def _build_candidate(project_dir: Path, target_root: Path) -> Dict[str, Any]:
        project_id = project_dir.name
        project_json = project_dir / "project.json"
        try:
            data = json.loads(project_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                project_id = str(data.get("project_id") or project_id)
        except Exception:
            data = {}

        target_path = target_root / project_id
        return {
            "project_id": project_id,
            "project_name": data.get("project_name") or project_id,
            "task_type": data.get("task_type") or "--",
            "source_path": project_dir.resolve().as_posix(),
            "target_path": target_path.resolve().as_posix(),
            "target_exists": target_path.exists(),
            "size_bytes": ProjectDataMigrationTool._dir_size(project_dir),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            return total
        return total

    @staticmethod
    def _verify_copy(source: Path, target: Path) -> None:
        if not (target / "project.json").exists():
            raise RuntimeError("Copied project is missing project.json.")
        source_json = json.loads((source / "project.json").read_text(encoding="utf-8"))
        target_json = json.loads((target / "project.json").read_text(encoding="utf-8"))
        if source_json.get("project_id") != target_json.get("project_id"):
            raise RuntimeError("Copied project_id does not match source project_id.")
        dataset_path = Path(str(target_json.get("dataset_path") or "")).resolve()
        expected_dataset = (target / "dataset").resolve()
        if dataset_path != expected_dataset:
            raise RuntimeError("Copied project dataset_path was not rewritten to the target project folder.")

    @staticmethod
    def _rewrite_project_paths(target: Path) -> None:
        project_json = target / "project.json"
        data = json.loads(project_json.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Copied project.json is not a JSON object.")
        data["dataset_path"] = (target / "dataset").resolve().as_posix()
        data.setdefault("paths", {})
        if isinstance(data["paths"], dict):
            data["paths"]["project_root"] = "."
            data["paths"]["dataset"] = "dataset"
        data["data_root_migrated_at"] = datetime.now().isoformat()
        project_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _write_migration_marker(target: Path, source: Path) -> None:
        marker_dir = target / "_meta"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = {
            "migrated_at": datetime.now().isoformat(),
            "source_path": source.as_posix(),
            "target_path": target.as_posix(),
            "tool": "ProjectDataMigrationTool",
        }
        (marker_dir / "data_root_migration.json").write_text(json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def _is_safe_legacy_source(cls, source: Path) -> bool:
        legacy_root = cls.legacy_projects_dir().resolve()
        current_root = PROJECTS_DIR.resolve()
        if source == current_root or current_root in source.parents:
            return False
        return source.exists() and source.is_dir() and legacy_root in source.parents

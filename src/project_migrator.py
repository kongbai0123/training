from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager


class ProjectMigrator:
    """Dry-run and apply migration from legacy project layout to v3."""

    @staticmethod
    def dry_run(project: Dict[str, Any]) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        mappings = ProjectMigrator._mappings(layout)
        checks = []
        can_apply = True

        for source, target, label in mappings:
            source_exists = source.exists()
            target_exists = target.exists()
            conflict = target_exists and source_exists and ProjectMigrator._has_content(target)
            if conflict:
                can_apply = False
            checks.append({
                "label": label,
                "source": source.resolve().as_posix(),
                "target": target.resolve().as_posix(),
                "source_exists": source_exists,
                "target_exists": target_exists,
                "conflict": conflict,
                "action": "copy" if source_exists and not conflict else "skip",
            })

        labelme_check = ProjectMigrator._check_labelme_image_paths(layout)
        if labelme_check["missing_images"]:
            can_apply = False

        return {
            "project_id": project.get("project_id"),
            "mode": layout.mode,
            "can_apply": can_apply,
            "checked_at": datetime.now().isoformat(),
            "checks": checks,
            "labelme_image_path_check": labelme_check,
        }

    @staticmethod
    def apply(project: Dict[str, Any]) -> Dict[str, Any]:
        report = ProjectMigrator.dry_run(project)
        if not report["can_apply"]:
            raise ValueError("Migration dry-run failed; apply is blocked")

        layout = ProjectLayout.from_project(project)
        backup_dir = layout.project_dir / "migration_backup" / f"layout_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        layout.ensure_v3_tree()

        copied = []
        for source, target, label in ProjectMigrator._mappings(layout):
            if not source.exists():
                continue
            backup_target = backup_dir / label
            ProjectMigrator._copy_path(source, backup_target)
            ProjectMigrator._copy_path(source, target)
            copied.append({"label": label, "source": source.as_posix(), "target": target.as_posix()})

        project["schema_version"] = "3.0"
        project["layout_version"] = "v3"
        project["layout"] = {
            "version": "v3",
            "mode": "v3",
            "migrated_from": "legacy",
            "created_by": "project_migrator",
            "verified_at": datetime.now().isoformat(),
            "backup_dir": backup_dir.relative_to(layout.project_dir).as_posix(),
        }
        if "paths" not in project:
            project["paths"] = {
                "project_root": ".",
                "dataset": "dataset",
                "annotations": "annotations",
                "splits": "splits",
                "training": "training",
                "inference": "inference",
                "auto_labeling": "auto_labeling",
                "exports": "exports",
            }
        if "current" not in project:
            project["current"] = {}
        ProjectManager.save_project(project["project_id"], project)

        result = {
            "success": True,
            "project_id": project.get("project_id"),
            "backup_dir": backup_dir.resolve().as_posix(),
            "copied": copied,
            "applied_at": datetime.now().isoformat(),
        }
        (backup_dir / "migration_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    @staticmethod
    def _mappings(layout: ProjectLayout) -> List[Tuple[Path, Path, str]]:
        project_dir = layout.project_dir
        return [
            (project_dir / "dataset" / "raw" / "images", project_dir / "dataset" / "images" / "raw", "raw_images"),
            (project_dir / "dataset" / "raw" / "annotations" / "labelme", project_dir / "annotations" / "current" / "labelme", "labelme"),
            (project_dir / "dataset" / "raw" / "labels", project_dir / "annotations" / "current" / "yolo", "yolo_labels"),
            (project_dir / "dataset" / "raw" / "masks", project_dir / "annotations" / "current" / "masks", "masks"),
            (project_dir / "dataset" / "splits" / "yolo", project_dir / "splits" / "legacy_yolo" / "yolo", "legacy_yolo_split"),
            (project_dir / "dataset" / "augmentations" / "augmented_images", project_dir / "augmentations" / "jobs" / "_legacy" / "outputs" / "images", "legacy_augmented_images"),
        ]

    @staticmethod
    def _copy_path(source: Path, target: Path) -> None:
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                ProjectMigrator._copy_path(item, target / item.name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _has_content(path: Path) -> bool:
        if path.is_file():
            return True
        if path.is_dir():
            return any(path.iterdir())
        return False

    @staticmethod
    def _check_labelme_image_paths(layout: ProjectLayout) -> Dict[str, Any]:
        labelme_dir = layout.project_dir / "dataset" / "raw" / "annotations" / "labelme"
        image_dir = layout.project_dir / "dataset" / "raw" / "images"
        checked = 0
        missing_images = []
        absolute_paths = []

        if not labelme_dir.exists():
            return {"checked": 0, "missing_images": [], "absolute_paths": []}

        for json_path in labelme_dir.glob("*.json"):
            checked += 1
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            image_path = data.get("imagePath") or f"{json_path.stem}.jpg"
            if Path(image_path).is_absolute():
                absolute_paths.append(json_path.name)
            image_name = Path(image_path).name
            if not (image_dir / image_name).exists():
                missing_images.append({"json": json_path.name, "imagePath": image_path})

        return {
            "checked": checked,
            "missing_images": missing_images,
            "absolute_paths": absolute_paths,
        }

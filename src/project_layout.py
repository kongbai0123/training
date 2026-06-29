from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import PROJECTS_DIR


@dataclass(frozen=True)
class LayoutResolution:
    path: Path
    source: str
    exists: bool
    valid: bool
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path.resolve().as_posix(),
            "source": self.source,
            "exists": self.exists,
            "valid": self.valid,
            "reason": self.reason,
        }


class ProjectLayout:
    """Central path resolver for project storage layouts.

    Phase 1 is intentionally conservative:
    - v3 projects read/write v3 paths.
    - legacy projects read/write legacy paths.
    - mixed projects prefer explicit v3 paths only when the v3 tree is valid.
    """

    V3_VERSION = "v3"
    VALID_LAYOUT_MODES = {"legacy", "v3", "mixed", "migration_pending", "migration_failed"}

    def __init__(self, project_dir: Path, project_data: Optional[Dict[str, Any]] = None):
        self.project_dir = project_dir.resolve()
        self.project_data = project_data or {}

    @classmethod
    def from_project(cls, project_data: Dict[str, Any]) -> "ProjectLayout":
        dataset_path = project_data.get("dataset_path")
        if dataset_path:
            project_dir = Path(dataset_path).resolve().parent
        else:
            project_id = project_data.get("project_id", "")
            project_dir = PROJECTS_DIR / project_id
        return cls(project_dir, project_data)

    @property
    def project_json(self) -> Path:
        return self.project_dir / "project.json"

    @property
    def meta_dir(self) -> Path:
        return self.project_dir / "_meta"

    @property
    def layout_manifest_path(self) -> Path:
        return self.meta_dir / "layout_version.json"

    @property
    def mode(self) -> str:
        layout = self.project_data.get("layout") or {}
        mode = layout.get("mode")
        if mode in self.VALID_LAYOUT_MODES:
            return mode
        version = layout.get("version") or self.project_data.get("layout_version")
        return "v3" if version == self.V3_VERSION else "legacy"

    def is_v3_project(self) -> bool:
        return self.mode == "v3"

    def has_v3_tree(self) -> bool:
        required_dirs = [
            self.project_dir / "dataset" / "images" / "raw",
            self.project_dir / "annotations" / "current" / "labelme",
            self.project_dir / "annotations" / "current" / "yolo",
            self.project_dir / "splits",
            self.project_dir / "training" / "runs",
            self.project_dir / "inference" / "jobs",
        ]
        return self.layout_manifest_path.exists() and all(path.exists() for path in required_dirs)

    def _is_valid_dir(self, path: Path, require_content: bool = False) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        if require_content:
            return any(path.iterdir())
        return True

    def _resolve(self, new_path: Path, legacy_path: Path, label: str, require_content: bool = False) -> LayoutResolution:
        mode = self.mode
        has_v3 = self.has_v3_tree()

        if mode == "v3":
            valid = self._is_valid_dir(new_path, require_content=require_content)
            return LayoutResolution(
                path=new_path,
                source="v3" if valid else "missing",
                exists=new_path.exists(),
                valid=valid,
                reason=f"{label}: layout.mode is v3",
            )

        if mode == "mixed" and has_v3:
            valid = self._is_valid_dir(new_path, require_content=require_content)
            if valid:
                return LayoutResolution(new_path, "v3", True, True, f"{label}: mixed project with valid v3 path")

        valid = self._is_valid_dir(legacy_path, require_content=require_content)
        return LayoutResolution(
            path=legacy_path,
            source="legacy" if valid else "missing",
            exists=legacy_path.exists(),
            valid=valid,
            reason=f"{label}: layout.mode is {mode}, using legacy fallback",
        )

    def ensure_v3_tree(self) -> None:
        dirs = [
            self.meta_dir,
            self.project_dir / "dataset" / "images" / "raw",
            self.project_dir / "dataset" / "images" / "imported",
            self.project_dir / "dataset" / "images" / "rejected",
            self.project_dir / "dataset" / "videos" / "raw",
            self.project_dir / "dataset" / "videos" / "frames",
            self.project_dir / "dataset" / "metadata",
            self.project_dir / "annotations" / "current" / "labelme",
            self.project_dir / "annotations" / "current" / "yolo",
            self.project_dir / "annotations" / "current" / "coco",
            self.project_dir / "annotations" / "current" / "masks",
            self.project_dir / "annotations" / "drafts" / "manual",
            self.project_dir / "annotations" / "drafts" / "auto_label",
            self.project_dir / "annotations" / "versions",
            self.project_dir / "annotations" / "review",
            self.project_dir / "splits",
            self.project_dir / "augmentations" / "jobs",
            self.project_dir / "augmentations" / "profiles",
            self.project_dir / "training" / "runs",
            self.project_dir / "training" / "registry",
            self.project_dir / "sequences",
            self.project_dir / "auto_labeling" / "jobs",
            self.project_dir / "inference" / "jobs",
            self.project_dir / "inference" / "cache",
            self.project_dir / "exports",
            self.project_dir / "history",
            self.project_dir / "logs",
            self.project_dir / "tmp",
            self.project_dir / "cache",
        ]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)

        manifest = {
            "layout_version": self.V3_VERSION,
            "mode": "v3",
            "created_by": "ProjectLayout.ensure_v3_tree",
        }
        self.layout_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def resolve_raw_images_dir(self, require_content: bool = False) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "dataset" / "images" / "raw",
            self.project_dir / "dataset" / "raw" / "images",
            "raw_images",
            require_content=require_content,
        )

    def resolve_video_frames_dir(self) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "dataset" / "videos" / "frames",
            self.project_dir / "dataset" / "raw" / "images",
            "video_frames",
        )

    def resolve_current_labelme_dir(self, require_content: bool = False) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "annotations" / "current" / "labelme",
            self.project_dir / "dataset" / "raw" / "annotations" / "labelme",
            "current_labelme",
            require_content=require_content,
        )

    def resolve_current_yolo_labels_dir(self, require_content: bool = False) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "annotations" / "current" / "yolo",
            self.project_dir / "dataset" / "raw" / "labels",
            "current_yolo",
            require_content=require_content,
        )

    def resolve_current_masks_dir(self) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "annotations" / "current" / "masks",
            self.project_dir / "dataset" / "raw" / "masks",
            "current_masks",
        )

    def resolve_legacy_augmented_images_dir(self) -> LayoutResolution:
        return self._resolve(
            self.project_dir / "augmentations" / "jobs" / "_legacy" / "outputs" / "images",
            self.project_dir / "dataset" / "augmentations" / "augmented_images",
            "augmented_images",
        )

    def resolve_coco_path(self) -> Path:
        if self.is_v3_project():
            return self.project_dir / "annotations" / "current" / "coco" / "coco.json"
        return self.project_dir / "dataset" / "coco.json"

    @property
    def current_split_path(self) -> Path:
        return self.project_dir / "splits" / "current_split.json"

    def resolve_current_split(self) -> LayoutResolution:
        path = self.current_split_path
        legacy_path = self.project_dir / "dataset" / "splits" / "current_split.json"
        if self.is_v3_project():
            return LayoutResolution(path, "v3" if path.exists() else "missing", path.exists(), path.exists(), "current_split: layout.mode is v3")
        valid = legacy_path.exists()
        return LayoutResolution(legacy_path, "legacy" if valid else "missing", valid, valid, "current_split: legacy fallback")

    def split_dir(self, split_id: str) -> Path:
        if self.is_v3_project():
            return self.project_dir / "splits" / split_id
        return self.project_dir / "dataset" / "splits" / split_id

    def yolo_split_dir(self, split_id: Optional[str] = None) -> Path:
        if split_id:
            return self.split_dir(split_id) / "yolo"
        if self.is_v3_project():
            return self.project_dir / "splits" / "manual" / "yolo"
        return self.project_dir / "dataset" / "splits" / "yolo"

    def resolve_yolo_split_dir(self) -> LayoutResolution:
        split_id = self.current_split_id()
        if split_id:
            path = self.yolo_split_dir(split_id)
            return LayoutResolution(path, "v3" if self.is_v3_project() else "legacy", path.exists(), path.exists(), "yolo_split: current split")
        legacy_path = self.project_dir / "dataset" / "splits" / "yolo"
        path = self.yolo_split_dir()
        if self.is_v3_project():
            return LayoutResolution(path, "missing", path.exists(), path.exists(), "yolo_split: no current split")
        return LayoutResolution(legacy_path, "legacy" if legacy_path.exists() else "missing", legacy_path.exists(), legacy_path.exists(), "yolo_split: legacy fallback")

    def current_split_id(self) -> Optional[str]:
        layout_current = (self.project_data.get("current") or {}).get("split_id")
        if layout_current:
            return str(layout_current)
        if self.current_split_path.exists():
            try:
                data = json.loads(self.current_split_path.read_text(encoding="utf-8"))
                if data.get("current_split_id"):
                    return str(data["current_split_id"])
            except Exception:
                return None
        return None

    def split_manifest_path(self, split_id: str) -> Path:
        return self.split_dir(split_id) / "split_manifest.json"

    def training_run_dir(self, run_id: str) -> Path:
        return self.project_dir / "training" / "runs" / run_id

    def training_runs_dir(self) -> Path:
        return self.project_dir / "training" / "runs"

    def sequences_dir(self) -> Path:
        return self.project_dir / "sequences"

    def sequence_manifest_path(self) -> Path:
        return self.sequences_dir() / "sequence_manifest.json"

    def inference_job_dir(self, job_id: str) -> Path:
        return self.project_dir / "inference" / "jobs" / job_id

    def inference_jobs_dir(self) -> Path:
        return self.project_dir / "inference" / "jobs"

    def auto_label_job_dir(self, job_id: str) -> Path:
        return self.project_dir / "auto_labeling" / "jobs" / job_id

    def auto_label_draft_dir(self, job_id: str) -> Path:
        return self.project_dir / "annotations" / "drafts" / "auto_label" / job_id

    def annotation_version_dir(self, version_id: str) -> Path:
        return self.project_dir / "annotations" / "versions" / version_id

    def export_dir(self, export_id: str) -> Path:
        return self.project_dir / "exports" / export_id

    @property
    def latest_export_path(self) -> Path:
        return self.project_dir / "exports" / "latest_export.json"

    @property
    def tmp_dir(self) -> Path:
        return self.project_dir / "tmp"

    @property
    def cache_dir(self) -> Path:
        return self.project_dir / "cache"

    def augmentation_job_dir(self, job_id: str) -> Path:
        return self.project_dir / "augmentations" / "jobs" / job_id

    def augmentation_outputs_dir(self, job_id: str) -> Path:
        return self.augmentation_job_dir(job_id) / "outputs"

    def get_layout_report(self) -> Dict[str, Any]:
        return {
            "project_dir": self.project_dir.as_posix(),
            "mode": self.mode,
            "is_v3_project": self.is_v3_project(),
            "has_v3_tree": self.has_v3_tree(),
            "paths": {
                "raw_images": self.resolve_raw_images_dir().as_dict(),
                "current_labelme": self.resolve_current_labelme_dir().as_dict(),
                "current_yolo": self.resolve_current_yolo_labels_dir().as_dict(),
                "current_masks": self.resolve_current_masks_dir().as_dict(),
                "current_split": self.resolve_current_split().as_dict(),
                "yolo_split": self.resolve_yolo_split_dir().as_dict(),
                "augmented_images": self.resolve_legacy_augmented_images_dir().as_dict(),
                "training_runs": LayoutResolution(self.training_runs_dir(), "v3", self.training_runs_dir().exists(), self.training_runs_dir().exists(), "training_runs").as_dict(),
                "inference_jobs": LayoutResolution(self.inference_jobs_dir(), "v3", self.inference_jobs_dir().exists(), self.inference_jobs_dir().exists(), "inference_jobs").as_dict(),
                "exports": LayoutResolution(self.project_dir / "exports", "v3", (self.project_dir / "exports").exists(), (self.project_dir / "exports").exists(), "exports").as_dict(),
            },
        }

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.config import PROJECTS_DIR
from src.project_layout import ProjectLayout

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}

class ProjectManager:
    @staticmethod
    def _is_sequence_task(task_type: str) -> bool:
        normalized = str(task_type or "").lower()
        return any(token in normalized for token in ("sequence", "time_series", "timeseries", "rnn"))

    @staticmethod
    def _default_training_config(task_type: str) -> Dict[str, Any]:
        if ProjectManager._is_sequence_task(task_type):
            task_head = "regression" if "regression" in str(task_type or "").lower() else "classification"
            return {
                "backend": "pytorch_lstm",
                "architecture": "rnn",
                "model": "lstm",
                "epochs": 10,
                "batch_size": 16,
                "device": "cpu",
                "sequence_length": 16,
                "stride": 8,
                "horizon": 1,
                "task_head": task_head,
                "hidden_size": 128,
                "num_layers": 2,
                "dropout": 0.2,
                "bidirectional": False,
            }
        return {
            "backend": "ultralytics_yolo",
            "architecture": "cnn",
            "model": "yolov8n.pt" if "segmentation" not in str(task_type or "").lower() else "yolov8n-seg.pt",
            "epochs": 50,
            "batch_size": 8,
            "imgsz": 640,
            "lr0": 0.01,
            "device": "gpu",
        }

    @staticmethod
    def get_all_projects() -> List[Dict[str, Any]]:
        """列出 projects 目錄下所有專案"""
        projects = []
        if not PROJECTS_DIR.exists():
            return projects
            
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir():
                json_path = d / "project.json"
                if json_path.exists():
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            projects.append({
                                "project_id": data.get("project_id"),
                                "project_name": data.get("project_name"),
                                "task_type": data.get("task_type"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "class_names": data.get("class_names", []),
                                "annotation_progress": data.get("annotation_progress", {"total": 0, "annotated": 0}),
                                "path": str(d.resolve()),
                                "file_summary": ProjectManager.build_project_file_summary(d, data)
                            })
                    except Exception as e:
                        print(f"Error loading project {d.name}: {e}")
        # 依修改時間降序排序
        projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return projects

    @staticmethod
    def build_project_file_summary(project_dir: Path, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a lightweight project content summary for history/browser views."""
        data = data or {}

        def count_files(path: Path, suffixes: Optional[set] = None) -> int:
            if not path.exists():
                return 0
            try:
                if suffixes:
                    return sum(1 for item in path.rglob("*") if item.is_file() and item.suffix.lower() in suffixes)
                return sum(1 for item in path.rglob("*") if item.is_file())
            except Exception:
                return 0

        def latest_file_mtime(path: Path) -> Optional[str]:
            if not path.exists():
                return None
            latest = None
            try:
                for item in path.rglob("*"):
                    if not item.is_file():
                        continue
                    mtime = item.stat().st_mtime
                    latest = mtime if latest is None or mtime > latest else latest
            except Exception:
                return None
            return datetime.fromtimestamp(latest).isoformat() if latest else None

        layout = ProjectLayout(project_dir, data)
        raw_images = layout.resolve_raw_images_dir().path
        labelme_dir = layout.resolve_current_labelme_dir().path
        yolo_labels = layout.resolve_current_yolo_labels_dir().path
        training_runs = layout.training_runs_dir()
        inference_jobs = layout.inference_jobs_dir()
        exports_dir = project_dir / "exports"
        split_current = project_dir / "splits" / "current_split.json"
        videos_raw = project_dir / "dataset" / "videos" / "raw"
        sequences_dir = layout.sequences_dir()
        sequence_manifest = layout.sequence_manifest_path()

        best_weights = list(training_runs.rglob("weights/best.pt")) if training_runs.exists() else []
        last_weights = list(training_runs.rglob("weights/last.pt")) if training_runs.exists() else []

        return {
            "project_root": str(project_dir.resolve().as_posix()),
            "layout_mode": (data.get("layout") or {}).get("mode") or data.get("layout_version") or "legacy",
            "images": count_files(raw_images, IMAGE_EXTENSIONS),
            "videos": count_files(videos_raw, VIDEO_EXTENSIONS),
            "labelme_json": count_files(labelme_dir, {".json"}),
            "yolo_labels": count_files(yolo_labels, {".txt"}),
            "split_ready": split_current.exists(),
            "training_runs": count_files(training_runs, None) if training_runs.exists() else 0,
            "best_weights": len(best_weights),
            "last_weights": len(last_weights),
            "sequence_manifest": sequence_manifest.exists(),
            "sequence_csv_files": count_files(sequences_dir, {".csv"}) if sequences_dir.exists() else 0,
            "sequence_files": count_files(sequences_dir, None) if sequences_dir.exists() else 0,
            "inference_jobs": len([p for p in inference_jobs.iterdir() if p.is_dir()]) if inference_jobs.exists() else 0,
            "exports": len([p for p in exports_dir.iterdir() if p.is_dir()]) if exports_dir.exists() else 0,
            "latest_file_updated_at": latest_file_mtime(project_dir),
        }

    @staticmethod
    def create_project(project_name: str, task_type: str, class_names: List[str]) -> Dict[str, Any]:
        """建立全新專案與對應的資料夾結構"""
        project_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:8]}"
        project_dir = PROJECTS_DIR / project_id
        
        # 建立目錄結構
        layout = ProjectLayout(project_dir, {"layout": {"mode": "v3"}})
        layout.ensure_v3_tree()
            
        # 初始化 project.json
        now_str = datetime.now().isoformat()
        project_data = {
          "project_id": project_id,
          "project_name": project_name,
          "task_type": task_type,
          "schema_version": "3.0",
          "layout_version": "v3",
          "layout": {
            "version": "v3",
            "mode": "v3",
            "migrated_from": None,
            "created_by": "project_manager",
            "verified_at": None
          },
          "created_at": now_str,
          "updated_at": now_str,
          "dataset_path": str((project_dir / "dataset").resolve().as_posix()),
          "paths": {
            "project_root": ".",
            "dataset": "dataset",
            "annotations": "annotations",
            "splits": "splits",
            "training": "training",
            "inference": "inference",
            "auto_labeling": "auto_labeling",
            "exports": "exports"
          },
          "current": {
            "annotation_version": None,
            "split_id": None,
            "training_run_id": None,
            "best_model_id": None,
            "export_id": None
          },
          "class_names": class_names,
          "annotation_progress": {
            "total": 0,
            "annotated": 0,
            "flagged": 0,
            "skipped": 0
          },
          "images": [],
          "split_config": {
            "method": "stratified",
            "ratio": {"train": 0.7, "val": 0.2, "test": 0.1},
            "split_quality_score": 0
          },
          "augmentation_config": {
            "light": {"brightness": 0.0, "contrast": 0.0, "shadow": False},
            "weather": {"rain": 0.0, "fog": 0.0},
            "motion": {"motion_blur": 0.0},
            "camera": {"noise": 0.0}
          },
          "training_config": ProjectManager._default_training_config(task_type),
          "training_runs": []
        }
        
        ProjectManager.save_project(project_id, project_data)
        return project_data

    @staticmethod
    def get_project(project_id: str) -> Optional[Dict[str, Any]]:
        """讀取單一專案設定並進行自動延遲遷移 (Lazy Migration)"""
        project_dir = PROJECTS_DIR / project_id
        json_path = project_dir / "project.json"
        if not json_path.exists():
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Lazy Migration: 檢查並升級 Schema 至 2.0 版
            migrated = False
            if "schema_version" not in data:
                data["schema_version"] = "2.0"
                migrated = True

            if "layout" not in data:
                data["layout"] = {
                    "version": "legacy",
                    "mode": "legacy",
                    "migrated_from": None,
                    "created_by": "lazy_migration",
                    "verified_at": None
                }
                data["layout_version"] = "legacy"
                migrated = True
                
            if "labelme_config" not in data:
                is_v3_layout = (data.get("layout") or {}).get("mode") == "v3"
                data["labelme_config"] = {
                    "images_dir": "dataset/images/raw" if is_v3_layout else "dataset/raw/images",
                    "json_dir": "annotations/current/labelme" if is_v3_layout else "dataset/raw/annotations/labelme",
                    "command": "",
                    "last_opened_at": None
                }
                migrated = True
                
            if "labelme_progress" not in data:
                data["labelme_progress"] = {
                    "last_sync_at": None,
                    "json_count": 0,
                    "missing_json": 0,
                    "empty_json": 0,
                    "invalid_json": 0,
                    "unknown_labels": [],
                    "corrupted_jsons_list": [],
                    "empty_jsons_list": [],
                    "unknown_labels_detail": {}
                }
                migrated = True
                
            if "imports_history" not in data:
                data["imports_history"] = []
                migrated = True
                
            if "versions" not in data:
                data["versions"] = []
                migrated = True
                
            if "jobs" not in data:
                data["jobs"] = []
                migrated = True
                
            if migrated:
                ProjectManager.save_project(project_id, data)

            data["_layout_report"] = ProjectLayout.from_project(data).get_layout_report()
            return data
        except Exception as e:
            print(f"Error loading project {project_id}: {e}")
            return None

    @staticmethod
    def save_project(project_id: str, data: Dict[str, Any]) -> bool:
        """儲存專案設定至 project.json"""
        project_dir = PROJECTS_DIR / project_id
        if not project_dir.exists():
            project_dir.mkdir(parents=True, exist_ok=True)
            
        json_path = project_dir / "project.json"
        data["updated_at"] = datetime.now().isoformat()
        try:
            data_to_save = dict(data)
            data_to_save.pop("_layout_report", None)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving project {project_id}: {e}")
            return False

    @staticmethod
    def delete_project(project_id: str) -> bool:
        """刪除專案資料夾"""
        project_dir = PROJECTS_DIR / project_id
        if project_dir.exists():
            try:
                shutil.rmtree(project_dir)
                return True
            except Exception as e:
                print(f"Error deleting project {project_id}: {e}")
                return False
        return False

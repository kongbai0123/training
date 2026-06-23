import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.config import PROJECTS_DIR

class ProjectManager:
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
                                "path": str(d.resolve())
                            })
                    except Exception as e:
                        print(f"Error loading project {d.name}: {e}")
        # 依修改時間降序排序
        projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return projects

    @staticmethod
    def create_project(project_name: str, task_type: str, class_names: List[str]) -> Dict[str, Any]:
        """建立全新專案與對應的資料夾結構"""
        project_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:8]}"
        project_dir = PROJECTS_DIR / project_id
        
        # 建立目錄結構
        dirs = [
            project_dir / "dataset" / "raw" / "images",
            project_dir / "dataset" / "raw" / "labels",
            project_dir / "dataset" / "raw" / "annotations" / "labelme",
            project_dir / "dataset" / "splits",
            project_dir / "dataset" / "augmentations" / "augmented_images",
            project_dir / "training" / "runs",
            project_dir / "training" / "logs",
            project_dir / "exports" / "onnx",
            project_dir / "exports" / "reports"
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            
        # 初始化 project.json
        now_str = datetime.now().isoformat()
        project_data = {
          "project_id": project_id,
          "project_name": project_name,
          "task_type": task_type,
          "created_at": now_str,
          "updated_at": now_str,
          "dataset_path": str((project_dir / "dataset").resolve().as_posix()),
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
          "training_config": {
            "model": "yolov8n.pt" if "segmentation" not in task_type else "yolov8n-seg.pt",
            "epochs": 50,
            "batch_size": 8,
            "imgsz": 640,
            "lr0": 0.01,
            "device": "gpu"
          },
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
            if "schema_version" not in data or data.get("schema_version") != "2.0":
                data["schema_version"] = "2.0"
                migrated = True
                
            if "labelme_config" not in data:
                data["labelme_config"] = {
                    "images_dir": "dataset/raw/images",
                    "json_dir": "dataset/raw/annotations/labelme",
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
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
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

import os
import csv
import json
import time
import shutil
import threading
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from ultralytics import YOLO

# 嘗試載入 GPU 監控庫
try:
    from pynvml import *
    nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False

class YOLOTrainer:
    # 格式: { project_id: { "status": "idle/training/paused/stopped/completed/failed", "epoch": 0, "total_epochs": 0, "metrics": {...}, "error": "", "run_id": "" } }
    _global_states: Dict[str, Dict[str, Any]] = {}
    _stop_flags: Dict[str, bool] = {}
    _threads: Dict[str, threading.Thread] = {}

    @classmethod
    def get_status(cls, project_id: str) -> Dict[str, Any]:
        """獲取當前專案的訓練狀態與硬體資訊"""
        state = cls._global_states.get(project_id, {
            "status": "idle",
            "epoch": 0,
            "total_epochs": 0,
            "metrics": [],
            "error": "",
            "run_id": ""
        })
        
        # 讀取硬體監控數據
        hw_info = cls.get_hardware_info()
        return {**state, "hardware": hw_info}

    @classmethod
    def stop_training(cls, project_id: str):
        """設定終止旗標"""
        cls._stop_flags[project_id] = True
        if project_id in cls._global_states:
            cls._global_states[project_id]["status"] = "stopping"

    @staticmethod
    def get_hardware_info() -> Dict[str, Any]:
        """獲取 CPU, RAM 與 GPU 狀態"""
        cpu_usage = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        
        gpu_info = {"available": False, "name": "N/A", "usage": 0, "vram_used": 0, "vram_total": 0, "temp": 0}
        
        if HAS_NVML:
            try:
                device_count = nvmlDeviceGetCount()
                if device_count > 0:
                    handle = nvmlDeviceGetHandleByIndex(0)
                    gpu_info["available"] = True
                    gpu_info["name"] = nvmlDeviceGetName(handle)
                    
                    mem_info = nvmlDeviceGetMemoryInfo(handle)
                    gpu_info["vram_used"] = int(mem_info.used / (1024 ** 2)) # MB
                    gpu_info["vram_total"] = int(mem_info.total / (1024 ** 2)) # MB
                    
                    rates = nvmlDeviceGetUtilizationRates(handle)
                    gpu_info["usage"] = rates.gpu
                    gpu_info["temp"] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except Exception as e:
                print(f"Error reading NVML data: {e}")
                
        return {
            "cpu_usage": cpu_usage,
            "ram_used": int(ram.used / (1024 ** 2)), # MB
            "ram_total": int(ram.total / (1024 ** 2)), # MB
            "gpu": gpu_info
        }

    @classmethod
    def prepare_yolo_dataset(cls, project_data: Dict[str, Any]) -> str:
        """
        導出符合 YOLO 格式要求的資料集目錄結構並生成 data.yaml。
        加入嚴格的多邊形、正規化、座標數以及任務格式匹配檢查。
        """
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        task_type = project_data.get("task_type", "detection")
        is_seg_task = "segmentation" in task_type or "seg" in task_type
        
        # 1. 建立 splits 下的 YOLO 目錄結構
        yolo_dir = dataset_path / "splits" / "yolo"
        if yolo_dir.exists():
            try:
                shutil.rmtree(yolo_dir)
            except Exception:
                pass
            
        for split in ["train", "val", "test"]:
            (yolo_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (yolo_dir / split / "labels").mkdir(parents=True, exist_ok=True)
        images_list = project_data.get("images", [])
        class_names = project_data.get("class_names", [])
        class_to_idx = {name: idx for idx, name in enumerate(class_names)}
        
        # 1.5 全面標註格式與一致性校驗
        for img in images_list:
            split_name = img.get("split")
            if not split_name or split_name not in ["train", "val", "test"]:
                continue
            filename = img["filename"]
            annotations = img.get("annotations", [])
            for ann in annotations:
                cat = ann.get("category")
                if cat not in class_to_idx:
                    raise ValueError(f"圖片 {filename} 的標註類別 '{cat}' 不存在於專案類別清單中。")
                
                if is_seg_task:
                    points = ann.get("points")
                    if not points or len(points) < 3:
                        raise ValueError(
                            f"分割任務出錯！圖片 '{filename}' 的標註不符合分割格式（必須包含多邊形頂點且至少為 3 個點）。"
                            f"請在 LabelMe 中完成多邊形標註，或修正專案 Task Type。"
                        )
                        
        # 2. 複製圖片並配置 labels
        for img in images_list:
            split_name = img.get("split")
            if not split_name or split_name not in ["train", "val", "test"]:
                continue
                
            filename = img["filename"]
            is_aug = img.get("is_augmented", False)
            
            # 定義圖片源路徑
            if is_aug:
                img_src_path = dataset_path / "augmentations" / "augmented_images" / filename
            else:
                img_src_path = dataset_path / "raw" / "images" / filename
                
            if not img_src_path.exists():
                continue
                
            # 複製圖片
            shutil.copy(img_src_path, yolo_dir / split_name / "images" / filename)
            
            txt_filename = Path(filename).with_suffix(".txt")
            target_txt_path = yolo_dir / split_name / "labels" / txt_filename
            
            annotations = img.get("annotations", [])
            
            # 檢查與導出標註
            with open(target_txt_path, "w", encoding="utf-8") as f:
                for ann in annotations:
                    cat = ann.get("category")
                    if cat not in class_to_idx:
                        raise ValueError(f"圖片 {filename} 的標註類別 '{cat}' 不存在於專案類別清單中。")
                    idx = class_to_idx[cat]
                    
                    if is_seg_task:
                        points = ann.get("points")
                        if not points or len(points) < 3:
                            raise ValueError(
                                f"分割任務出錯！圖片 '{filename}' 的標註不符合分割格式（必須包含多邊形頂點且至少為 3 個點）。"
                                f"請在 LabelMe 中完成多邊形標註，或修正專案 Task Type。"
                            )
                        
                        img_w = img.get("width")
                        img_h = img.get("height")
                        if not img_w or not img_h:
                            try:
                                import cv2
                                temp_img = cv2.imread(str(img_src_path))
                                if temp_img is not None:
                                    img_h, img_w = temp_img.shape[:2]
                                else:
                                    img_w, img_h = 640, 640
                            except Exception:
                                img_w, img_h = 640, 640
                        
                        # 進行 0.0 ~ 1.0 的歸一化並 clip 到邊界
                        norm_pts = []
                        for pt in points:
                            if len(pt) < 2:
                                continue
                            xn = max(0.0, min(1.0, pt[0] / img_w))
                            yn = max(0.0, min(1.0, pt[1] / img_h))
                            norm_pts.append(f"{xn:.6f} {yn:.6f}")
                        
                        if len(norm_pts) < 3:
                            raise ValueError(f"圖片 {filename} 的多邊形頂點歸一化後有效點數少於 3。")
                            
                        pts_str = " ".join(norm_pts)
                        f.write(f"{idx} {pts_str}\n")
                    else:
                        # Detection 任務 (若只有 points 自動轉為 bbox 作為相容機制)
                        bbox = ann.get("bbox")
                        if (not bbox or len(bbox) != 4) and ann.get("points"):
                            pts = ann.get("points")
                            img_w = img.get("width", 640)
                            img_h = img.get("height", 640)
                            xs = [p[0] for p in pts]
                            ys = [p[1] for p in pts]
                            xmin, xmax = min(xs), max(xs)
                            ymin, ymax = min(ys), max(ys)
                            w = xmax - xmin
                            h = ymax - ymin
                            xc = xmin + w / 2
                            yc = ymin + h / 2
                            bbox = [xc / img_w, yc / img_h, w / img_w, h / img_h]
                            
                        if bbox and len(bbox) == 4:
                            xc = max(0.0, min(1.0, bbox[0]))
                            yc = max(0.0, min(1.0, bbox[1]))
                            bw = max(0.0, min(1.0, bbox[2]))
                            bh = max(0.0, min(1.0, bbox[3]))
                            f.write(f"{idx} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")

        # 3. 生成 data.yaml
        data_yaml_path = yolo_dir / "data.yaml"
        with open(data_yaml_path, "w", encoding="utf-8") as f:
            f.write(f"path: {yolo_dir.resolve().as_posix()}\n")
            f.write(f"train: train/images\n")
            f.write(f"val: val/images\n")
            f.write(f"test: test/images\n\n")
            f.write(f"names:\n")
            for idx, name in enumerate(class_names):
                f.write(f"  {idx}: {name}\n")
                
        return str(data_yaml_path.resolve().as_posix())

    @classmethod
    def start_training(cls, project_data: Dict[str, Any]):
        """在背景線程啟動 YOLO 訓練"""
        project_id = project_data["project_id"]
        
        # 避免重複啟動
        if project_id in cls._global_states and cls._global_states[project_id]["status"] == "training":
            return
            
        cls._stop_flags[project_id] = False
        
        thread = threading.Thread(target=cls._run_yolo, args=(project_data,))
        cls._threads[project_id] = thread
        thread.start()

    @classmethod
    def _run_yolo(cls, project_data: Dict[str, Any]):
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        train_config = project_data.get("training_config", {})
        task_type = project_data.get("task_type", "detection")
        
        from src.training.run_manager import RunManager
        run_id = train_config.get("run_id") or RunManager.generate_run_id()
        
        project_dir = dataset_path.parent
        runs_dir = project_dir / "training" / "runs"
        
        # 1. 檢查是否存在同名資料夾，若已存在則拒絕啟動
        actual_run_dir = Path(runs_dir / run_id).resolve()
        if actual_run_dir.exists():
            raise RuntimeError(f"訓練輸出目錄已存在，為防覆寫已拒絕啟動：{actual_run_dir}")
        
        cls._global_states[project_id] = {
            "status": "training",
            "epoch": 0,
            "total_epochs": train_config.get("epochs", 50),
            "metrics": [],
            "error": "",
            "run_id": run_id
        }
        
        error_msg = ""
        status = "completed"
        
        try:
            # 1. 準備資料集並進行嚴格標註檢查 (不符則會拋出 ValueError)
            data_yaml_path = cls.prepare_yolo_dataset(project_data)
            
            # 2. 初始化 YOLO 模型
            model_name = train_config.get("model", "yolov8n.pt")
            model = YOLO(model_name)
            
            # 3. 註冊 Callbacks
            def on_train_start(trainer):
                # 這是 Ultralytics 在實際建立 save_dir 之後觸發的 callback
                path_dir = Path(trainer.save_dir).resolve()
                RunManager.save_run_metadata(path_dir, train_config, project_data.get("images", []))
                
            def on_fit_epoch_end(trainer):
                if cls._stop_flags.get(project_id, False):
                    raise KeyboardInterrupt("訓練由使用者手動中止。")
                    
                epoch = trainer.epoch
                is_seg = "segmentation" in task_type or "seg" in task_type
                suffix = "M" if is_seg else "B"
                
                # 從 metrics 取值
                map50 = float(trainer.metrics.get(f"metrics/mAP50({suffix})") or trainer.metrics.get("metrics/mAP50(B)") or 0.0)
                map50_95 = float(trainer.metrics.get(f"metrics/mAP50-95({suffix})") or trainer.metrics.get("metrics/mAP50-95(B)") or 0.0)
                precision = float(trainer.metrics.get(f"metrics/precision({suffix})") or trainer.metrics.get("metrics/precision(B)") or 0.0)
                recall = float(trainer.metrics.get(f"metrics/recall({suffix})") or trainer.metrics.get("metrics/recall(B)") or 0.0)
                
                loss_val = 0.0
                if hasattr(trainer, 'loss_items') and len(trainer.loss_items) > 0:
                    loss_val = float(trainer.loss_items[0])
                
                metrics_data = {
                    "epoch": epoch + 1,
                    "loss": loss_val,
                    "map50": map50,
                    "map50_95": map50_95,
                    "precision": precision,
                    "recall": recall,
                    "timestamp": time.time()
                }
                
                state = cls._global_states[project_id]
                state["epoch"] = epoch + 1
                state["metrics"].append(metrics_data)
                
            model.add_callback("on_train_start", on_train_start)
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
            
            # 4. 開始訓練，使用獨立 run_id，不覆蓋舊結果
            epochs = int(train_config.get("epochs", 50))
            batch_size = int(train_config.get("batch_size", 8))
            imgsz = int(train_config.get("imgsz", 640))
            lr0 = float(train_config.get("lr0", 0.01))
            device = 0 if train_config.get("device") == "gpu" and HAS_NVML else "cpu"
            
            model.train(
                data=data_yaml_path,
                epochs=epochs,
                batch=batch_size,
                imgsz=imgsz,
                lr0=lr0,
                device=device,
                project=str(runs_dir.resolve().as_posix()),
                name=run_id,
                exist_ok=False,
                patience=int(train_config.get("patience", 20)),
                save=True,
                save_period=int(train_config.get("save_period", 5)),
                cache=train_config.get("cache", False),
                workers=int(train_config.get("workers", 4)),
                amp=bool(train_config.get("amp", True)),
                seed=int(train_config.get("seed", 42)),
                deterministic=False,
                close_mosaic=int(train_config.get("close_mosaic", 10)),
                plots=True,
                verbose=True
            )
            
            # 5. 獲取實際訓練輸出目錄（優先使用 trainer 的 save_dir，若未啟動/取不到則 fallback 到原定目錄）
            try:
                actual_run_dir = Path(model.trainer.save_dir).resolve()
            except Exception:
                actual_run_dir = Path(runs_dir / run_id).resolve()
                
            # 訓練順利完成
            state = cls._global_states[project_id]
            state["status"] = "completed"
            
            best_model_path = actual_run_dir / "weights" / "best.pt"
            if best_model_path.exists():
                state["best_model"] = str(best_model_path.resolve().as_posix())
                
        except KeyboardInterrupt:
            status = "stopped"
            cls._global_states[project_id]["status"] = "stopped"
            error_msg = "訓練由使用者手動中止。"
            print(f"[Trainer] Training {project_id} was stopped by user.")
        except Exception as e:
            status = "failed"
            cls._global_states[project_id]["status"] = "failed"
            cls._global_states[project_id]["error"] = str(e)
            error_msg = str(e)
            print(f"[Trainer] Error in training {project_id}: {e}")
        finally:
            # 確保有獲取到 actual_run_dir 變數，若例外在 train 啟動前發生則 fallback
            try:
                if 'actual_run_dir' not in locals() or not actual_run_dir:
                    actual_run_dir = Path(runs_dir / run_id).resolve()
            except Exception:
                actual_run_dir = Path(runs_dir / run_id).resolve()

            # 保存 artifacts、解析 CSV 並回寫摘要資訊至 project.json
            from src.project_manager import ProjectManager
            latest_project = ProjectManager.get_project(project_id)
            if latest_project:
                run_summary = RunManager.finalize_run(actual_run_dir, task_type, status, error_msg)
                
                # 摘要記錄
                run_record = {
                    "run_id": run_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": status,
                    "model": train_config.get("model"),
                    "epochs": int(train_config.get("epochs", 50)),
                    "batch_size": int(train_config.get("batch_size", 8)),
                    "imgsz": int(train_config.get("imgsz", 640)),
                    "lr0": float(train_config.get("lr0", 0.01)),
                    "device": train_config.get("device"),
                    "error": error_msg,
                    **run_summary
                }
                
                if "training_runs" not in latest_project:
                    latest_project["training_runs"] = []
                
                # 避免重複
                latest_project["training_runs"] = [r for r in latest_project["training_runs"] if r["run_id"] != run_id]
                latest_project["training_runs"].append(run_record)
                
                if status == "completed":
                    version_id = f"v{len(latest_project.get('versions', [])) + 1}"
                    best_model_path = actual_run_dir / "weights" / "best.pt"
                    best_onnx_path = actual_run_dir / "weights" / "best.onnx"
                    
                    version_record = {
                        "version_id": version_id,
                        "timestamp": datetime.now().isoformat(),
                        "model_name": train_config.get("model"),
                        "best_model_pt": str(best_model_path.resolve().as_posix()) if best_model_path.exists() else "",
                        "best_model_onnx": str(best_onnx_path.resolve().as_posix()) if best_onnx_path.exists() else "",
                        "platform_score": run_summary.get("platform_score", 0.0),
                        "best_mAP50": run_summary.get("best_mAP50", 0.0),
                        "best_mAP50_95": run_summary.get("best_mAP50_95", 0.0)
                    }
                    if "versions" not in latest_project:
                        latest_project["versions"] = []
                    latest_project["versions"].append(version_record)
                    latest_project["best_model"] = str(best_model_path.resolve().as_posix())
                
                ProjectManager.save_project(project_id, latest_project)
            
            # 釋放 GPU VRAM 資源與垃圾回收
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                    
            if project_id in cls._threads:
                del cls._threads[project_id]

    @staticmethod
    def read_results_csv(runs_dir: Path) -> Optional[Dict[str, Any]]:
        csv_path = runs_dir / "results.csv"
        if not csv_path.exists():
            return None
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if not rows:
                    return None
                last_row = rows[-1]
                cleaned_row = {k.strip(): v.strip() for k, v in last_row.items() if k is not None}
                
                metrics = {
                    "map50": float(cleaned_row.get("metrics/mAP50(B)") or cleaned_row.get("metrics/mAP50(M)") or 0.0),
                    "map50_95": float(cleaned_row.get("metrics/mAP50-95(B)") or cleaned_row.get("metrics/mAP50-95(M)") or 0.0),
                    "precision": float(cleaned_row.get("metrics/precision(B)") or cleaned_row.get("metrics/precision(M)") or 0.0),
                    "recall": float(cleaned_row.get("metrics/recall(B)") or cleaned_row.get("metrics/recall(M)") or 0.0),
                    "box_loss": float(cleaned_row.get("train/box_loss") or cleaned_row.get("val/box_loss") or 0.0),
                    "seg_loss": float(cleaned_row.get("train/seg_loss") or cleaned_row.get("val/seg_loss") or 0.0)
                }
                return {
                    "metrics": metrics,
                    "epochs_completed": len(rows),
                    "last_row": cleaned_row
                }
        except Exception as e:
            print(f"Error parsing results.csv: {e}")
            return None

import os
import csv
import json
import time
import shutil
import threading
import psutil
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
    # 追蹤全局訓練狀態的字典
    # 格式: { project_id: { "status": "idle/training/paused/stopped/completed", "epoch": 0, "total_epochs": 0, "metrics": {...}, "error": "" } }
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
            "error": ""
        })
        
        # 讀取硬體監控數據
        hw_info = cls.get_hardware_info()
        return {**state, "hardware": hw_info}

    @classmethod
    def stop_training(cls, project_id: str):
        """設定終止旗標"""
        cls._stop_flags[project_id] = True
        if project_id in cls._global_states:
            cls._global_states[project_id]["status"] = "stopped"

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
                    
                    # 記憶體資訊
                    mem_info = nvmlDeviceGetMemoryInfo(handle)
                    gpu_info["vram_used"] = int(mem_info.used / (1024 ** 2)) # MB
                    gpu_info["vram_total"] = int(mem_info.total / (1024 ** 2)) # MB
                    
                    # 使用率與溫度
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
        導出符合 YOLO 格式要求的資料集目錄結構並生成 data.yaml
        """
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        
        # 1. 建立 splits 下的 YOLO 目錄結構
        yolo_dir = dataset_path / "splits" / "yolo"
        if yolo_dir.exists():
            shutil.rmtree(yolo_dir)
            
        for split in ["train", "val", "test"]:
            (yolo_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (yolo_dir / split / "labels").mkdir(parents=True, exist_ok=True)

        # 2. 獲取 dataset_split 設定
        # 讀取 splits.json / 專案 json
        # 我們將用 splits_report.json 或是 images list 中的 split 來劃分
        images_list = project_data.get("images", [])
        
        # 統計各類別索引
        class_names = project_data.get("class_names", [])
        class_to_idx = {name: idx for idx, name in enumerate(class_names)}
        
        # 3. 複製圖片並配置 labels
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
            
            # 如果是原始圖片且有預先轉換好的 txt label 檔案，直接複製它
            preconverted_label_path = dataset_path / "raw" / "labels" / txt_filename
            if not is_aug and preconverted_label_path.exists():
                shutil.copy(preconverted_label_path, target_txt_path)
            else:
                # 否則 (擴充圖或未預轉換的圖)，自 project.json 元數據寫入
                with open(target_txt_path, "w", encoding="utf-8") as f:
                    for ann in img.get("annotations", []):
                        cat = ann.get("category")
                        if cat not in class_to_idx:
                            continue
                        idx = class_to_idx[cat]
                        
                        # 支援 YOLO Segmentation (多邊形點序列)
                        points = ann.get("points")
                        if points and len(points) >= 3:
                            img_w = img.get("width", 640)
                            img_h = img.get("height", 640)
                            pts_str = " ".join(f"{pt[0]/img_w:.6f} {pt[1]/img_h:.6f}" for pt in points)
                            f.write(f"{idx} {pts_str}\n")
                        else:
                            # 支援 YOLO Detection (bbox)
                            bbox = ann.get("bbox")
                            if bbox and len(bbox) == 4:
                                f.write(f"{idx} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}\n")

        # 4. 生成 data.yaml
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
        cls._global_states[project_id] = {
            "status": "training",
            "epoch": 0,
            "total_epochs": project_data.get("training_config", {}).get("epochs", 50),
            "metrics": [],
            "error": ""
        }
        
        thread = threading.Thread(target=cls._run_yolo, args=(project_data,))
        cls._threads[project_id] = thread
        thread.start()

    @classmethod
    def _run_yolo(cls, project_data: Dict[str, Any]):
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        train_config = project_data.get("training_config", {})
        
        try:
            # 1. 準備資料集並導出 YOLO 格式
            data_yaml_path = cls.prepare_yolo_dataset(project_data)
            
            # 2. 初始化 YOLO 模型
            model_name = train_config.get("model", "yolov8n.pt")
            model = YOLO(model_name)
            
            # 3. 註冊終止 Callbacks
            # 利用 Ultralytics callbacks 機制，當 _stop_flags 觸發時拋出 Exception 終止訓練
            def on_fit_epoch_end(trainer):
                if cls._stop_flags.get(project_id, False):
                    raise KeyboardInterrupt("訓練由使用者手動中止。")
                    
                # 讀取與更新狀態
                epoch = trainer.epoch
                total_epochs = trainer.epochs
                
                # 計算或解析 metrics
                # trainer.metrics 內含各種指標
                metrics_data = {
                    "epoch": epoch + 1,
                    "loss": float(trainer.loss_items[0]) if hasattr(trainer, 'loss_items') and len(trainer.loss_items) > 0 else 0.0,
                    "map50": float(trainer.metrics.get("metrics/mAP50(B)", 0.0)),
                    "map50_95": float(trainer.metrics.get("metrics/mAP50-95(B)", 0.0)),
                    "precision": float(trainer.metrics.get("metrics/precision(B)", 0.0)),
                    "recall": float(trainer.metrics.get("metrics/recall(B)", 0.0)),
                    "timestamp": time.time()
                }
                
                state = cls._global_states[project_id]
                state["epoch"] = epoch + 1
                state["metrics"].append(metrics_data)
                
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
            
            # 4. 開始訓練
            # 確保 training runs 目錄
            project_dir = dataset_path.parent
            runs_dir = project_dir / "training" / "runs"
            
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
                name="train",
                exist_ok=True,
                verbose=False
            )
            
            # 5. 訓練完成
            state = cls._global_states[project_id]
            state["status"] = "completed"
            
            # 將最後的最佳模型路徑寫入 metrics 報告中
            best_model_path = runs_dir / "train" / "weights" / "best.pt"
            if best_model_path.exists():
                state["best_model"] = str(best_model_path.resolve().as_posix())
                
        except KeyboardInterrupt:
            # 捕捉手動中斷
            cls._global_states[project_id]["status"] = "stopped"
            print(f"[Trainer] Training {project_id} was stopped by user.")
        except Exception as e:
            # 捕捉訓練錯誤
            cls._global_states[project_id]["status"] = "error"
            cls._global_states[project_id]["error"] = str(e)
            print(f"[Trainer] Error in training {project_id}: {e}")
        finally:
            from datetime import datetime
            from src.project_manager import ProjectManager
            latest_project = ProjectManager.get_project(project_id)
            if latest_project:
                final_state = cls._global_states.get(project_id, {"status": "unknown"})
                status = final_state.get("status", "unknown")
                last_metrics = final_state.get("metrics")[-1] if final_state.get("metrics") else {}
                
                run_record = {
                    "run_id": f"run_{int(time.time())}",
                    "timestamp": datetime.now().isoformat(),
                    "status": status,
                    "model": train_config.get("model"),
                    "epochs": int(train_config.get("epochs", 50)),
                    "batch_size": int(train_config.get("batch_size", 8)),
                    "imgsz": int(train_config.get("imgsz", 640)),
                    "lr0": float(train_config.get("lr0", 0.01)),
                    "device": train_config.get("device"),
                    "metrics": last_metrics,
                    "error": final_state.get("error", "")
                }
                
                if "training_runs" not in latest_project:
                    latest_project["training_runs"] = []
                latest_project["training_runs"].append(run_record)
                
                if status == "completed":
                    version_id = f"v{len(latest_project.get('versions', [])) + 1}"
                    best_model_path = runs_dir / "train" / "weights" / "best.pt"
                    best_onnx_path = runs_dir / "train" / "weights" / "best.onnx"
                    
                    version_record = {
                        "version_id": version_id,
                        "timestamp": datetime.now().isoformat(),
                        "model_name": train_config.get("model"),
                        "metrics": last_metrics,
                        "best_model_pt": str(best_model_path.resolve().as_posix()) if best_model_path.exists() else "",
                        "best_model_onnx": str(best_onnx_path.resolve().as_posix()) if best_onnx_path.exists() else ""
                    }
                    if "versions" not in latest_project:
                        latest_project["versions"] = []
                    latest_project["versions"].append(version_record)
                
                ProjectManager.save_project(project_id, latest_project)

            # GPU VRAM & memory release
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
            import csv
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


import os
import csv
import json
import time
import shutil
import psutil
import sys
import torch
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from ultralytics import RTDETR, YOLO
from src.model_store import ModelStore
from src.project_layout import ProjectLayout
from src.training.runners.thread_runner import DEFAULT_THREAD_TRAINING_RUNNER
from src.training.state_store import TrainingStateStore

# Optional NVIDIA GPU telemetry.
try:
    from pynvml import *
    nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False

class YOLOTrainer:
    # Legacy mirrored state kept for compatibility during state-store migration.
    _global_states: Dict[str, Dict[str, Any]] = {}
    _stop_flags: Dict[str, bool] = {}
    _threads: Dict[str, Any] = {}

    @staticmethod
    def _load_training_model(model_path: str, backend: str):
        if backend == "ultralytics_rtdetr":
            return RTDETR(model_path)
        return YOLO(model_path)

    @staticmethod
    def resolve_training_device(requested_device: str):
        return 0 if requested_device == "gpu" and torch.cuda.is_available() else "cpu"

    @classmethod
    def _mirror_state(cls, project_id: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or TrainingStateStore.get_state(project_id)
        cls._global_states[project_id] = dict(state)
        return cls._global_states[project_id]

    @classmethod
    def get_status(cls, project_id: str) -> Dict[str, Any]:
        """Return the current training status with hardware telemetry."""
        state = TrainingStateStore.get_state(project_id)
        if state.get("status") == "idle" and project_id in cls._global_states:
            state = cls._global_states.get(project_id, state)
        
        # Attach runtime hardware telemetry to the training state.
        hw_info = cls.get_hardware_info()
        return {**state, "hardware": hw_info}

    @classmethod
    def stop_training(cls, project_id: str):
        """Request training stop for a project."""
        cls._stop_flags[project_id] = True
        state = TrainingStateStore.mark_stopping(project_id)
        cls._mirror_state(project_id, state)

    @staticmethod
    def get_hardware_info() -> Dict[str, Any]:
        """Return CPU, RAM, and GPU runtime telemetry."""
        cpu_usage = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        
        cuda_available = bool(torch.cuda.is_available())
        gpu_info = {
            "available": cuda_available,
            "name": torch.cuda.get_device_name(0) if cuda_available else "N/A",
            "usage": 0,
            "vram_used": 0,
            "vram_total": 0,
            "temp": 0,
        }
        
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
        Prepare a YOLO dataset folder and data.yaml from project metadata.
        Supports detection and segmentation annotation formats.
        """
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        layout = ProjectLayout.from_project(project_data)
        task_type = project_data.get("task_type", "detection")
        is_seg_task = "segmentation" in task_type or "seg" in task_type
        
        # Create YOLO split folders.
        split_id = layout.current_split_id()
        yolo_dir = layout.yolo_split_dir(split_id)
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
        
        # Copy images and labels into split folders.
        for img in images_list:
            split_name = img.get("split")
            if not split_name or split_name not in ["train", "val", "test"]:
                continue
            filename = img["filename"]
            annotations = img.get("annotations", [])
            for ann in annotations:
                cat = ann.get("category")
                if cat not in class_to_idx:
                    raise ValueError(f"Image '{filename}' has unknown class '{cat}'.")
                
                if is_seg_task:
                    points = ann.get("points")
                    if not points or len(points) < 3:
                        raise ValueError(
                            f"Segmentation image '{filename}' needs at least 3 polygon points."
                        )
                        
        # Build YOLO labels.
        for img in images_list:
            split_name = img.get("split")
            if not split_name or split_name not in ["train", "val", "test"]:
                continue
                
            filename = img["filename"]
            is_aug = img.get("is_augmented", False)
            
            # Copy image file.
            if is_aug:
                aug_job_id = img.get("augmentation_job_id") or img.get("aug_job_id")
                if aug_job_id:
                    img_src_path = layout.augmentation_outputs_dir(aug_job_id) / "images" / filename
                else:
                    img_src_path = layout.resolve_legacy_augmented_images_dir().path / filename
            else:
                img_src_path = layout.resolve_raw_images_dir().path / filename
                
            if not img_src_path.exists():
                continue
                
            # Copy image into the YOLO split folder.
            shutil.copy(img_src_path, yolo_dir / split_name / "images" / filename)
            
            txt_filename = Path(filename).with_suffix(".txt")
            target_txt_path = yolo_dir / split_name / "labels" / txt_filename
            
            annotations = img.get("annotations", [])
            
            # Write normalized label rows.
            with open(target_txt_path, "w", encoding="utf-8") as f:
                for ann in annotations:
                    cat = ann.get("category")
                    if cat not in class_to_idx:
                        raise ValueError(f"Image '{filename}' has unknown class '{cat}'.")
                    idx = class_to_idx[cat]
                    
                    if is_seg_task:
                        points = ann.get("points")
                        if not points or len(points) < 3:
                            raise ValueError(
                                f"Segmentation image '{filename}' needs at least 3 polygon points."
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
                        
                        # Clamp normalized coordinates into the 0.0 to 1.0 range.
                        norm_pts = []
                        for pt in points:
                            if len(pt) < 2:
                                continue
                            xn = max(0.0, min(1.0, pt[0] / img_w))
                            yn = max(0.0, min(1.0, pt[1] / img_h))
                            norm_pts.append(f"{xn:.6f} {yn:.6f}")
                        
                        if len(norm_pts) < 3:
                            raise ValueError(f"Image '{filename}' has fewer than 3 valid polygon points.")
                            
                        pts_str = " ".join(norm_pts)
                        f.write(f"{idx} {pts_str}\n")
                    else:
                        # Detection labels use class plus normalized bounding box.
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

        # Write data.yaml for the generated YOLO split.
        data_yaml_path = yolo_dir / "data.yaml"
        with open(data_yaml_path, "w", encoding="utf-8") as f:
            f.write(f"path: {yolo_dir.resolve().as_posix()}\n")
            f.write(f"train: train/images\n")
            f.write(f"val: val/images\n")
            f.write(f"test: test/images\n\n")
            f.write(f"names:\n")
            for idx, name in enumerate(class_names):
                f.write(f"  {idx}: {name}\n")

        if split_id:
            manifest_path = layout.split_manifest_path(split_id)
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["yolo_data_yaml"] = data_yaml_path.relative_to(layout.project_dir).as_posix()
                    manifest["prepared_at"] = datetime.now().isoformat()
                    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

        return str(data_yaml_path.resolve().as_posix())

    @classmethod
    def start_training(cls, project_data: Dict[str, Any]):
        """Start YOLO training through the thread runner."""
        project_id = project_data["project_id"]
        train_config = project_data.get("training_config", {})
        run_id = train_config.get("run_id", "")
        
        # Thread runner is the lifecycle source of truth. StateStore-only training
        # means stale/inconsistent state, so do not silently start another run.
        if DEFAULT_THREAD_TRAINING_RUNNER.is_running(project_id):
            return
        if TrainingStateStore.is_training(project_id):
            return
            
        cls._stop_flags[project_id] = False
        state = TrainingStateStore.init_run(
            project_id=project_id,
            run_id=run_id,
            total_epochs=int(train_config.get("epochs", 50)),
            architecture="cnn",
            backend=str(train_config.get("backend") or "ultralytics_yolo"),
        )
        cls._mirror_state(project_id, state)
        
        result = DEFAULT_THREAD_TRAINING_RUNNER.start(
            project_id=project_id,
            run_id=run_id,
            target=cls._run_yolo,
            args=(project_data,),
            daemon=False,
        )
        if result.get("started"):
            cls._threads[project_id] = dict(result)
        else:
            state = TrainingStateStore.mark_failed(
                project_id,
                "Training runner did not start.",
                run_id=run_id,
            )
            cls._mirror_state(project_id, state)

    @classmethod
    def _run_yolo(cls, project_data: Dict[str, Any]):
        project_id = project_data["project_id"]
        dataset_path = Path(project_data["dataset_path"])
        layout = ProjectLayout.from_project(project_data)
        train_config = project_data.get("training_config", {})
        backend_name = str(train_config.get("backend") or "ultralytics_yolo")
        task_type = project_data.get("task_type", "detection")
        
        from src.training.run_manager import RunManager
        run_id = train_config.get("run_id") or RunManager.generate_run_id()
        
        project_dir = layout.project_dir
        runs_dir = layout.training_runs_dir()
        
        # Ensure the run directory is unique before training starts.
        actual_run_dir = Path(runs_dir / run_id).resolve()
        if actual_run_dir.exists():
            raise RuntimeError(f"Training run directory already exists: {actual_run_dir}")
        
        state = TrainingStateStore.get_state(project_id)
        if state.get("run_id") != run_id or state.get("status") != "training":
            state = TrainingStateStore.init_run(
                project_id=project_id,
                run_id=run_id,
                total_epochs=train_config.get("epochs", 50),
                architecture="cnn",
                backend=backend_name,
            )
        cls._mirror_state(project_id, state)
        
        error_msg = ""
        status = "completed"
        data_yaml_path = None
        
        try:
            # Prepare dataset and validate split files.
            data_yaml_path = cls.prepare_yolo_dataset(project_data)
            
            # Load training model.
            model_name = ModelStore.resolve_training_model(train_config.get("model", "yolov8n.pt"))
            model = cls._load_training_model(model_name, backend_name)
            
            # 3. 閮餃? Callbacks
            def on_train_start(trainer):
                # Use a fixed save_dir so callbacks and history can locate outputs.
                path_dir = Path(trainer.save_dir).resolve()
                RunManager.save_run_metadata(path_dir, train_config, project_data.get("images", []))
                
            def on_fit_epoch_end(trainer):
                if cls._stop_flags.get(project_id, False):
                    raise KeyboardInterrupt("Training was stopped by user.")
                    
                epoch = trainer.epoch
                is_seg = "segmentation" in task_type or "seg" in task_type
                suffix = "M" if is_seg else "B"
                
                # 敺?metrics ??
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
                
                state = TrainingStateStore.append_epoch_metrics(project_id, metrics_data, run_id=run_id)
                cls._mirror_state(project_id, state)
                
            model.add_callback("on_train_start", on_train_start)
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
            
            # Record run metadata after training starts.
            epochs = int(train_config.get("epochs", 50))
            batch_size = int(train_config.get("batch_size", 8))
            imgsz = int(train_config.get("imgsz", 640))
            lr0 = float(train_config.get("lr0", 0.01))
            device = cls.resolve_training_device(str(train_config.get("device") or "cpu"))
            workers = int(train_config.get("workers", 4))
            if getattr(sys, "frozen", False):
                # PyInstaller on Windows can deadlock when PyTorch dataloader
                # workers spawn child processes from the frozen executable.
                workers = 0
            from src.training.vector_plot_capture import capture_vector_plots

            with capture_vector_plots(runs_dir):
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
                    workers=workers,
                    amp=bool(train_config.get("amp", True)),
                    seed=int(train_config.get("seed", 42)),
                    deterministic=False,
                    close_mosaic=int(train_config.get("close_mosaic", 10)),
                    plots=True,
                    verbose=True
                )
            
            # Resolve actual run directory from trainer save_dir, with fallback.
            try:
                actual_run_dir = Path(model.trainer.save_dir).resolve()
            except Exception:
                actual_run_dir = Path(runs_dir / run_id).resolve()
                
            # Training completed.
            best_model_path = actual_run_dir / "weights" / "best.pt"
            best_model = str(best_model_path.resolve().as_posix()) if best_model_path.exists() else None
            latest_state = TrainingStateStore.get_state(project_id)
            completed_epochs = int(latest_state.get("epoch") or 0)
            termination_reason = "early_stopping" if 0 < completed_epochs < epochs else "completed"
            state = TrainingStateStore.mark_completed(
                project_id,
                best_model=best_model,
                run_id=run_id,
                termination_reason=termination_reason,
            )
            cls._mirror_state(project_id, state)
                
        except KeyboardInterrupt:
            status = "stopped"
            error_msg = "Training was stopped by user."
            state = TrainingStateStore.mark_stopped(project_id, error_msg, run_id=run_id)
            cls._mirror_state(project_id, state)
            print(f"[Trainer] Training {project_id} was stopped by user.")
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            state = TrainingStateStore.mark_failed(project_id, error_msg, run_id=run_id)
            cls._mirror_state(project_id, state)
            print(f"[Trainer] Error in training {project_id}: {e}")
        finally:
            # Save run artifacts using the resolved run directory.
            try:
                if 'actual_run_dir' not in locals() or not actual_run_dir:
                    actual_run_dir = Path(runs_dir / run_id).resolve()
            except Exception:
                actual_run_dir = Path(runs_dir / run_id).resolve()

            # Store data.yaml path as a Path when available.
            try:
                actual_data_yaml = Path(data_yaml_path) if ('data_yaml_path' in locals() and data_yaml_path) else None
            except Exception:
                actual_data_yaml = None

            # Write artifact manifest, metrics CSV, and project metadata.
            from src.project_manager import ProjectManager
            latest_project = ProjectManager.get_project(project_id)
            if latest_project:
                run_summary = RunManager.finalize_run(
                    run_dir=actual_run_dir,
                    task_type=task_type,
                    status=status,
                    error_msg=error_msg,
                    data_yaml_path=actual_data_yaml,
                    backend=backend_name,
                )
                
                # Mark cancellation in the state store.
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
                
                # Best-effort cleanup.
                latest_project["training_runs"] = [r for r in latest_project["training_runs"] if r["run_id"] != run_id]
                latest_project["training_runs"].append(run_record)
                if "current" not in latest_project:
                    latest_project["current"] = {}
                latest_project["current"]["training_run_id"] = run_id
                
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
                    latest_project["current"]["best_model_id"] = f"{project_id}::{run_id}::best"
                
                ProjectManager.save_project(project_id, latest_project)
            
            # Free GPU memory after training.
            import gc
            gc.collect()
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                    
            cls._threads.pop(project_id, None)

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

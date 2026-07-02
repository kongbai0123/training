import json
import shutil
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from ultralytics import YOLO

from src.model_registry import ModelRegistry


class InferenceEngine:
    """Single-image inference runner for registered YOLO weights."""

    _model_cache: "OrderedDict[str, YOLO]" = OrderedDict()
    _cache_limit = 2

    @staticmethod
    def _normalize_task_family(task: Any) -> str:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return "detection"
        if normalized == "segment" or "seg" in normalized:
            return "segmentation"
        if normalized in {"detect", "detection", "object_detection", "bbox"} or "detect" in normalized:
            return "detection"
        if normalized == "classify" or "class" in normalized:
            return "classification"
        if normalized in {"pose", "obb"}:
            return normalized
        return normalized

    @classmethod
    def run_image_inference(
        cls,
        project: Dict[str, Any],
        model: Dict[str, Any],
        input_path: Path,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        project_id = project["project_id"]
        cls._validate_input_image(input_path)

        dirs = ModelRegistry.ensure_inference_dirs(project)
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
        job_dir = dirs["jobs"] / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        input_copy = job_dir / f"input{input_path.suffix.lower()}"
        shutil.copy2(input_path, input_copy)

        conf = float(settings.get("conf", 0.25))
        iou = float(settings.get("iou", 0.7))
        imgsz = int(settings.get("imgsz", 640))
        raw_device = settings.get("device", "cpu")
        device = cls._normalize_device(raw_device)
        device_fallback = False
        if device == "0":
            try:
                import torch
                if not torch.cuda.is_available():
                    device = "cpu"
                    device_fallback = True
            except ImportError:
                device = "cpu"
                device_fallback = True
        mask_opacity = float(settings.get("mask_opacity", 0.45))
        show_mask = bool(settings.get("show_mask", True))
        show_bbox = bool(settings.get("show_bbox", True))
        class_filter = cls._parse_class_filter(settings.get("class_filter"))

        model_obj = cls._get_model(model["internal_weight_path"])
        
        # Validate the loaded YOLO task against the project task family.
        real_task = getattr(model_obj, "task", "detect")
        expected_task = project.get("task_type", "detection")
        normalized_real_task = "detection"
        if real_task == "segment":
            normalized_real_task = "segmentation"
        elif real_task == "classify":
            normalized_real_task = "classification"
        elif real_task in {"pose", "obb"}:
            normalized_real_task = real_task
            
        normalized_expected_task = cls._normalize_task_family(expected_task)
        if normalized_real_task != normalized_expected_task:
            raise ValueError(
                f"Model task type '{normalized_real_task}' is not compatible with project task type "
                f"'{normalized_expected_task}'. Prediction was rejected."
            )

        started = time.perf_counter()
        results = model_obj.predict(
            source=str(input_copy.resolve()),
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device=device,
            save=False,
            verbose=False
        )
        inference_time_ms = round((time.perf_counter() - started) * 1000, 2)
        if not results:
            raise RuntimeError("No inference result returned")

        result = results[0]
        original = cv2.imread(str(input_copy))
        if original is None:
            raise RuntimeError("Failed to read input image")

        predictions, overlay, mask_area_ratio = cls._render_predictions(
            original=original,
            result=result,
            class_names=getattr(model_obj, "names", {}) or {},
            mask_opacity=mask_opacity,
            show_mask=show_mask,
            show_bbox=show_bbox,
            class_filter=class_filter,
        )

        output_image = job_dir / "annotated.jpg"
        cv2.imwrite(str(output_image), overlay)

        summary = cls._build_summary(
            project_id=project_id,
            job_id=job_id,
            model=model,
            predictions=predictions,
            inference_time_ms=inference_time_ms,
            mask_area_ratio=mask_area_ratio,
            device_fallback=device_fallback,
        )

        prediction_json = job_dir / "prediction.json"
        summary_json = job_dir / "summary.json"
        config_json = job_dir / "config.json"
        prediction_json.write_text(json.dumps({"predictions": predictions}, indent=2, ensure_ascii=False), encoding="utf-8")
        summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        config_json.write_text(json.dumps({
            "model_id": model["model_id"],
            "settings": settings,
            "input": input_copy.name,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "job_id": job_id,
            "model": model,
            "summary": summary,
            "predictions": predictions,
            "paths": {
                "job_dir": job_dir.resolve().as_posix(),
                "input_image": input_copy.resolve().as_posix(),
                "annotated_image": output_image.resolve().as_posix(),
                "prediction_json": prediction_json.resolve().as_posix(),
                "summary_json": summary_json.resolve().as_posix(),
            },
            "urls": {
                "input_image": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{input_copy.name}",
                "annotated_image": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{output_image.name}",
                "prediction_json": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{prediction_json.name}",
                "summary_json": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{summary_json.name}",
            }
        }

    @classmethod
    def _get_model(cls, weight_path: str) -> YOLO:
        key = Path(weight_path).resolve().as_posix()
        if key in cls._model_cache:
            model = cls._model_cache.pop(key)
            cls._model_cache[key] = model
            return model

        model = YOLO(key)
        cls._model_cache[key] = model
        while len(cls._model_cache) > cls._cache_limit:
            cls._model_cache.popitem(last=False)
        return model

    @staticmethod
    def _validate_input_image(path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise ValueError("Input image does not exist")
        if resolved.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            raise ValueError("Only image files are supported")

    @staticmethod
    def _normalize_device(device: Any) -> str:
        text = str(device or "cpu").lower()
        if text in {"gpu", "cuda", "0"}:
            return "0"
        return "cpu"

    @staticmethod
    def _parse_class_filter(value: Any) -> Optional[set]:
        if value in (None, "", []):
            return None
        if isinstance(value, str):
            return {item.strip() for item in value.split(",") if item.strip()}
        if isinstance(value, list):
            return {str(item).strip() for item in value if str(item).strip()}
        return None

    @staticmethod
    def _render_predictions(
        original: np.ndarray,
        result: Any,
        class_names: Dict[int, str],
        mask_opacity: float,
        show_mask: bool,
        show_bbox: bool,
        class_filter: Optional[set],
    ) -> tuple:
        overlay = original.copy()
        predictions: List[Dict[str, Any]] = []
        combined_mask = np.zeros(original.shape[:2], dtype=np.uint8)

        boxes = result.boxes
        masks = result.masks
        box_count = len(boxes) if boxes is not None else 0

        for idx in range(box_count):
            cls_id = int(boxes.cls[idx].item()) if boxes.cls is not None else -1
            label = str(class_names.get(cls_id, cls_id))
            if class_filter and label not in class_filter:
                continue

            conf = float(boxes.conf[idx].item()) if boxes.conf is not None else 0.0
            xyxy = boxes.xyxy[idx].detach().cpu().numpy().tolist() if boxes.xyxy is not None else None
            color = InferenceEngine._color_for_label(label)
            mask_area = 0.0

            if masks is not None and masks.data is not None and idx < len(masks.data):
                mask = masks.data[idx].detach().cpu().numpy()
                mask = cv2.resize(mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_NEAREST)
                mask_bin = (mask > 0.5).astype(np.uint8)
                mask_area = float(mask_bin.sum() / mask_bin.size) if mask_bin.size else 0.0
                combined_mask = np.maximum(combined_mask, mask_bin)
                if show_mask:
                    color_layer = np.zeros_like(overlay)
                    color_layer[:, :] = color
                    overlay = np.where(
                        mask_bin[..., None].astype(bool),
                        cv2.addWeighted(overlay, 1 - mask_opacity, color_layer, mask_opacity, 0),
                        overlay
                    )

            if show_bbox and xyxy:
                x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    overlay,
                    f"{label} {conf:.2f}",
                    (x1, max(16, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                    cv2.LINE_AA
                )

            predictions.append({
                "class_id": cls_id,
                "class_name": label,
                "confidence": round(conf, 6),
                "bbox_xyxy": xyxy,
                "mask_area_ratio": round(mask_area, 6),
            })

        combined_ratio = float(combined_mask.sum() / combined_mask.size) if combined_mask.size and combined_mask.any() else 0.0
        return predictions, overlay, round(combined_ratio, 6)

    @staticmethod
    def _build_summary(
        project_id: str,
        job_id: str,
        model: Dict[str, Any],
        predictions: List[Dict[str, Any]],
        inference_time_ms: float,
        mask_area_ratio: float,
        device_fallback: bool = False,
    ) -> Dict[str, Any]:
        detected_classes = sorted({p["class_name"] for p in predictions})
        avg_conf = sum(p["confidence"] for p in predictions) / len(predictions) if predictions else 0.0
        dominant_class = "--"
        if predictions:
            dominant_class = max(predictions, key=lambda p: p.get("mask_area_ratio", 0) or p.get("confidence", 0)).get("class_name", "--")

        return {
            "project_id": project_id,
            "job_id": job_id,
            "model_id": model["model_id"],
            "run_id": model.get("run_id"),
            "weight_type": model.get("weight_type"),
            "task_type": model.get("task_type"),
            "prediction_count": len(predictions),
            "detected_classes": detected_classes,
            "detected_class_count": len(detected_classes),
            "dominant_class": dominant_class,
            "average_confidence": round(avg_conf, 6),
            "mask_area_ratio": mask_area_ratio,
            "inference_time_ms": inference_time_ms,
            "created_at": datetime.now().isoformat(),
            "device_fallback": device_fallback,
        }

    @staticmethod
    def _color_for_label(label: str) -> tuple:
        palette = [
            (37, 99, 235),
            (22, 163, 74),
            (220, 38, 38),
            (147, 51, 234),
            (234, 88, 12),
            (8, 145, 178),
        ]
        idx = sum(ord(ch) for ch in str(label)) % len(palette)
        return palette[idx]

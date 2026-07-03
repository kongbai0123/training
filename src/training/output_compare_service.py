from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.inference_engine import InferenceEngine
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.security_utils import safe_resolve_under


class OutputCompareServiceError(ValueError):
    pass


class CNNOutputCompareService:
    MIN_RUNS = 2
    MAX_RUNS = 4
    IMAGE_INPUT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    @classmethod
    def parse_run_ids(cls, run_ids_json: str) -> List[str]:
        try:
            run_ids = json.loads(run_ids_json)
        except Exception as exc:
            raise OutputCompareServiceError(f"Invalid run_ids_json: {exc}")
        if not isinstance(run_ids, list):
            raise OutputCompareServiceError("Invalid run_ids_json: run_ids_json must be a JSON array")
        return run_ids

    @classmethod
    def resolve_image_input(
        cls,
        project: Dict[str, Any],
        *,
        upload: Any = None,
        image_path: Optional[str] = None,
        local_trusted_mode: bool = False,
    ) -> Path:
        if upload is not None and getattr(upload, "filename", ""):
            return cls.stage_uploaded_image(project, upload)
        if image_path:
            return cls.resolve_local_image_path(project, image_path, local_trusted_mode=local_trusted_mode)
        raise OutputCompareServiceError("Please provide an image file or image_path")

    @classmethod
    def stage_uploaded_image(cls, project: Dict[str, Any], upload: Any) -> Path:
        filename = str(getattr(upload, "filename", "") or "")
        ext = Path(filename).suffix.lower()
        if ext not in cls.IMAGE_INPUT_EXTENSIONS:
            raise OutputCompareServiceError("Only image files are supported")

        inference_dirs = ModelRegistry.ensure_inference_dirs(project)
        safe_name = f"compare_upload_{uuid.uuid4().hex}{ext}"
        input_path = inference_dirs["inputs_images"] / safe_name
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        return input_path

    @staticmethod
    def resolve_local_image_path(project: Dict[str, Any], image_path: str, *, local_trusted_mode: bool = False) -> Path:
        if not local_trusted_mode:
            raise OutputCompareServiceError("Local image path compare requires Local Trusted Mode")
        project_base = ProjectLayout.from_project(project).project_dir.resolve()
        try:
            return safe_resolve_under(project_base, Path(image_path))
        except ValueError as exc:
            raise OutputCompareServiceError(str(exc))

    @classmethod
    def compare_image_outputs(
        cls,
        project: Dict[str, Any],
        run_ids: List[str],
        input_path: Path,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        settings = settings or {}
        run_ids = [str(run_id or "").strip() for run_id in run_ids or [] if str(run_id or "").strip()]
        if len(run_ids) < cls.MIN_RUNS:
            raise OutputCompareServiceError("Output comparison requires at least 2 run_ids.")
        if len(run_ids) > cls.MAX_RUNS:
            raise OutputCompareServiceError("Output comparison supports at most 4 run_ids.")
        if len(set(run_ids)) != len(run_ids):
            raise OutputCompareServiceError("Duplicate run_ids are not allowed.")

        models = cls._resolve_models_for_runs(project, run_ids)
        outputs = []
        warnings: List[str] = []

        for run_id in run_ids:
            model = models[run_id]
            result = InferenceEngine.run_image_inference(
                project=project,
                model=model,
                input_path=input_path,
                settings=settings,
            )
            summary = result.get("summary") or {}
            outputs.append({
                "run_id": run_id,
                "model_id": model.get("model_id"),
                "weight_type": model.get("weight_type"),
                "model_name": model.get("model_name"),
                "task_type": model.get("task_type"),
                "job_id": result.get("job_id"),
                "summary": summary,
                "predictions": result.get("predictions") or [],
                "urls": result.get("urls") or {},
                "paths": result.get("paths") or {},
            })

        return {
            "comparison_id": f"outcmp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "architecture": "cnn",
            "kind": "image_output",
            "selected_run_ids": run_ids,
            "input": {
                "name": Path(input_path).name,
            },
            "settings": settings,
            "outputs": outputs,
            "summary": cls._build_summary(outputs, warnings),
            "warnings": warnings,
        }

    @classmethod
    def _resolve_models_for_runs(cls, project: Dict[str, Any], run_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        registry = ModelRegistry.list_models(project)
        by_run: Dict[str, List[Dict[str, Any]]] = {}
        for model in registry:
            if model.get("run_id") in run_ids and cls._is_cnn_model(model):
                by_run.setdefault(model["run_id"], []).append(model)

        resolved: Dict[str, Dict[str, Any]] = {}
        missing = []
        for run_id in run_ids:
            candidates = by_run.get(run_id) or []
            if not candidates:
                missing.append(run_id)
                continue
            candidates.sort(key=lambda item: 0 if item.get("weight_type") == "best" else 1)
            resolved[run_id] = ModelRegistry.resolve_model(project, candidates[0]["model_id"])

        if missing:
            raise OutputCompareServiceError(f"No CNN model weights found for run_id(s): {', '.join(missing)}")
        return resolved

    @staticmethod
    def _is_cnn_model(model: Dict[str, Any]) -> bool:
        architecture = str(model.get("architecture") or "cnn").lower()
        backend = str(model.get("backend") or "ultralytics_yolo").lower()
        return architecture in {"", "cnn"} and backend in {"", "ultralytics_yolo"}

    @staticmethod
    def _build_summary(outputs: List[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
        prediction_count_by_run = {}
        latency_ms_by_run = {}
        classes_by_run = {}
        mask_area_by_run = {}

        for output in outputs:
            run_id = output.get("run_id")
            summary = output.get("summary") or {}
            prediction_count_by_run[run_id] = summary.get("prediction_count", 0)
            latency_ms_by_run[run_id] = summary.get("inference_time_ms")
            classes_by_run[run_id] = summary.get("detected_classes") or []
            mask_area_by_run[run_id] = summary.get("mask_area_ratio")

        all_classes = sorted({label for labels in classes_by_run.values() for label in labels})
        if not all_classes:
            warnings.append("No predicted classes were detected by the selected models.")

        return {
            "prediction_count_by_run": prediction_count_by_run,
            "latency_ms_by_run": latency_ms_by_run,
            "classes_by_run": classes_by_run,
            "mask_area_by_run": mask_area_by_run,
            "all_detected_classes": all_classes,
            "warnings": warnings,
        }

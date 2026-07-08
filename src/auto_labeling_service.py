import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from src.annotation_helpers import build_labelme_annotation_payload
from src.dataset_helpers import resolve_project_image_path
from src.inference_engine import InferenceEngine
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout


class AutoLabelingServiceError(ValueError):
    pass


class AutoLabelingService:
    DEFAULT_MAX_IMAGES = 20
    REVIEW_ACTIONS = {"accept", "reject", "skip", "hard_case"}

    @classmethod
    def create_draft_job(
        cls,
        project: Dict[str, Any],
        request: Dict[str, Any],
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        job_id = cls._safe_job_id(request.get("job_id"))
        job_dir = layout.auto_label_job_dir(job_id)
        draft_dir = layout.auto_label_draft_dir(job_id)

        model_id = str(request.get("model_id") or "").strip()
        if not model_id:
            raise AutoLabelingServiceError("model_id is required")
        try:
            model = ModelRegistry.resolve_model(project, model_id)
        except ValueError as exc:
            raise AutoLabelingServiceError(str(exc)) from exc

        source = str(request.get("source") or "unlabeled")
        max_images = cls._parse_max_images(request.get("max_images"))
        inputs = cls._select_input_images(project, layout, source, max_images)
        if not inputs:
            raise AutoLabelingServiceError("No eligible images found for auto-labeling")
        cls._ensure_job_dirs(job_dir, draft_dir)

        config = {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "model_id": model_id,
            "mode": request.get("mode", "draft"),
            "source": source,
            "status": "running",
            "max_images": max_images,
            "settings": cls._settings_from_request(request),
        }
        cls._write_json(job_dir / "config.json", config)

        processed: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for input_item in inputs:
            try:
                processed.append(cls._run_single_image(project, model, layout, job_dir, draft_dir, input_item, config["settings"]))
            except Exception as exc:
                errors.append({"filename": input_item["filename"], "error": str(exc)})

        status = "draft" if processed else "failed"
        summary = {
            **config,
            "status": status,
            "completed_at": datetime.now().isoformat(),
            "input_count": len(inputs),
            "processed_count": len(processed),
            "draft_count": len(processed),
            "error_count": len(errors),
            "draft_dir": draft_dir.resolve().as_posix(),
            "job_dir": job_dir.resolve().as_posix(),
            "items": processed,
            "errors": errors,
        }
        cls._write_json(job_dir / "summary.json", summary)
        cls._write_json(job_dir / "predictions" / "predictions.json", {"items": processed, "errors": errors})
        return summary

    @classmethod
    def review_draft_item(
        cls,
        project: Dict[str, Any],
        job_id: str,
        filename: str,
        action: str,
    ) -> Dict[str, Any]:
        action = str(action or "").strip().lower()
        if action not in cls.REVIEW_ACTIONS:
            raise AutoLabelingServiceError("Invalid review action")

        layout = ProjectLayout.from_project(project)
        safe_job_id = cls._safe_job_id(job_id)
        safe_filename = Path(str(filename or "")).name
        if not safe_filename or safe_filename != str(filename or ""):
            raise AutoLabelingServiceError("Invalid filename")

        job_dir = layout.auto_label_job_dir(safe_job_id)
        summary_path = job_dir / "summary.json"
        if not summary_path.exists():
            raise AutoLabelingServiceError("Auto-label job not found")

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        item = cls._find_summary_item(summary, safe_filename)
        draft_json = layout.auto_label_draft_dir(safe_job_id) / "labelme" / f"{Path(safe_filename).stem}.json"
        if not draft_json.exists():
            raise AutoLabelingServiceError("Draft LabelMe JSON not found")

        now = datetime.now().isoformat()
        review_status = {
            "action": action,
            "status": {
                "accept": "accepted",
                "reject": "rejected",
                "skip": "skipped",
                "hard_case": "hard_case",
            }[action],
            "filename": safe_filename,
            "job_id": safe_job_id,
            "reviewed_at": now,
        }

        copied: List[str] = []
        annotation_version: Optional[str] = None
        if action == "accept":
            annotation_version = cls._accept_single_labelme(project, layout, safe_job_id, draft_json, now)
            copied = [f"labelme/{draft_json.name}"]
            review_status["annotation_version"] = annotation_version

        cls._update_project_image_review_state(project, safe_filename, action, now)
        cls._update_summary_review_state(summary, item, review_status)
        cls._write_json(summary_path, summary)
        cls._write_json(job_dir / "review" / "item_status.json", cls._review_status_map(summary))
        cls._append_review_event(job_dir, review_status)

        return {
            "job_id": safe_job_id,
            "filename": safe_filename,
            "action": action,
            "review_status": review_status["status"],
            "annotation_version": annotation_version,
            "copied": copied,
            "summary": summary,
        }

    @staticmethod
    def _safe_job_id(raw: Any) -> str:
        candidate = str(raw or "").strip()
        if candidate:
            safe = "".join(ch for ch in candidate if ch.isalnum() or ch in {"_", "-"})
            if safe != candidate or not safe:
                raise AutoLabelingServiceError("Invalid job_id")
            return safe
        return f"al_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    def _find_summary_item(summary: Dict[str, Any], filename: str) -> Dict[str, Any]:
        for item in summary.get("items") or []:
            if item.get("filename") == filename:
                return item
        raise AutoLabelingServiceError("Draft item not found in job summary")

    @classmethod
    def _accept_single_labelme(
        cls,
        project: Dict[str, Any],
        layout: ProjectLayout,
        job_id: str,
        draft_json: Path,
        reviewed_at: str,
    ) -> str:
        payload = json.loads(draft_json.read_text(encoding="utf-8"))
        flags = payload.setdefault("flags", {})
        flags["requires_review"] = False
        flags["auto_label_review_status"] = "accepted"
        flags["auto_label_reviewed_at"] = reviewed_at

        version_id = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}_auto_label_{job_id}_{draft_json.stem}"
        current_labelme_dir = layout.resolve_current_labelme_dir().path
        current_labelme_dir.mkdir(parents=True, exist_ok=True)
        version_labelme_dir = layout.annotation_version_dir(version_id) / "labelme"
        version_labelme_dir.mkdir(parents=True, exist_ok=True)
        cls._write_json(current_labelme_dir / draft_json.name, payload)
        cls._write_json(version_labelme_dir / draft_json.name, payload)

        if "current" not in project:
            project["current"] = {}
        project["current"]["annotation_version"] = version_id
        return version_id

    @staticmethod
    def _update_project_image_review_state(project: Dict[str, Any], filename: str, action: str, reviewed_at: str) -> None:
        status_by_action = {
            "accept": "annotated",
            "reject": "flagged",
            "skip": "skipped",
            "hard_case": "flagged",
        }
        images = project.get("images") or []
        for image in images:
            if image.get("filename") != filename:
                continue
            image["status"] = status_by_action[action]
            image["auto_label_review"] = {
                "action": action,
                "reviewed_at": reviewed_at,
            }
            break
        project["annotation_progress"] = {
            "total": len(images),
            "annotated": sum(1 for image in images if image.get("status") == "annotated"),
            "flagged": sum(1 for image in images if image.get("status") == "flagged"),
            "skipped": sum(1 for image in images if image.get("status") == "skipped"),
        }

    @staticmethod
    def _update_summary_review_state(summary: Dict[str, Any], item: Dict[str, Any], review_status: Dict[str, Any]) -> None:
        item["review_status"] = review_status["status"]
        item["review_action"] = review_status["action"]
        item["reviewed_at"] = review_status["reviewed_at"]
        if review_status.get("annotation_version"):
            item["annotation_version"] = review_status["annotation_version"]

        items = summary.get("items") or []
        summary["accepted_count"] = sum(1 for row in items if row.get("review_status") == "accepted")
        summary["rejected_count"] = sum(1 for row in items if row.get("review_status") == "rejected")
        summary["skipped_count"] = sum(1 for row in items if row.get("review_status") == "skipped")
        summary["hard_case_count"] = sum(1 for row in items if row.get("review_status") == "hard_case")
        summary["reviewed_count"] = sum(1 for row in items if row.get("review_status"))
        summary["pending_review_count"] = max(0, len(items) - summary["reviewed_count"])

    @staticmethod
    def _review_status_map(summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            item.get("filename", ""): {
                "review_status": item.get("review_status"),
                "review_action": item.get("review_action"),
                "reviewed_at": item.get("reviewed_at"),
                "annotation_version": item.get("annotation_version"),
            }
            for item in summary.get("items") or []
            if item.get("filename")
        }

    @staticmethod
    def _append_review_event(job_dir: Path, event: Dict[str, Any]) -> None:
        review_dir = job_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        with (review_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _parse_max_images(raw: Any) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = AutoLabelingService.DEFAULT_MAX_IMAGES
        return max(1, min(value, 200))

    @staticmethod
    def _settings_from_request(request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "conf": float(request.get("conf", 0.35)),
            "iou": float(request.get("iou", 0.5)),
            "imgsz": int(request.get("imgsz", 640)),
            "max_det": int(request.get("max_det", 20)),
            "min_mask_area": int(request.get("min_mask_area", 400)),
            "output_mode": request.get("output_mode", "mask_polygon"),
            "device": request.get("device", "cpu"),
            "mask_opacity": float(request.get("mask_opacity", 0.45)),
            "show_mask": bool(request.get("show_mask", True)),
            "show_bbox": bool(request.get("show_bbox", True)),
            "class_filter": request.get("class_filter"),
        }

    @staticmethod
    def _ensure_job_dirs(job_dir: Path, draft_dir: Path) -> None:
        for path in [
            job_dir / "inputs",
            job_dir / "previews",
            job_dir / "predictions",
            job_dir / "annotations" / "labelme",
            job_dir / "review",
            draft_dir / "labelme",
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _select_input_images(
        cls,
        project: Dict[str, Any],
        layout: ProjectLayout,
        source: str,
        max_images: int,
    ) -> List[Dict[str, Any]]:
        current_labelme_dir = layout.resolve_current_labelme_dir().path
        selected: List[Dict[str, Any]] = []
        for image in project.get("images") or []:
            filename = Path(str(image.get("filename") or "")).name
            if not filename:
                continue
            image_path = resolve_project_image_path(layout, project, filename)
            if not image_path:
                continue
            if not cls._matches_source(image, current_labelme_dir / f"{Path(filename).stem}.json", source):
                continue
            selected.append({"filename": filename, "path": image_path, "metadata": image})
            if len(selected) >= max_images:
                break
        return selected

    @staticmethod
    def _matches_source(image: Dict[str, Any], labelme_path: Path, source: str) -> bool:
        status = str(image.get("status") or "").lower()
        if source == "invalid-json":
            if not labelme_path.exists():
                return True
            try:
                data = json.loads(labelme_path.read_text(encoding="utf-8"))
                return not isinstance(data.get("shapes"), list) or len(data.get("shapes") or []) == 0
            except Exception:
                return True
        return status not in {"annotated", "accepted"} and not labelme_path.exists()

    @classmethod
    def _run_single_image(
        cls,
        project: Dict[str, Any],
        model: Dict[str, Any],
        layout: ProjectLayout,
        job_dir: Path,
        draft_dir: Path,
        input_item: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        filename = input_item["filename"]
        image_path = Path(input_item["path"])
        staged_input = job_dir / "inputs" / filename
        shutil.copy2(image_path, staged_input)

        inference = InferenceEngine.run_image_inference(
            project=project,
            model=model,
            input_path=staged_input,
            settings={**settings, "original_filename": filename},
        )
        width, height = cls._read_image_size(image_path)
        annotations = cls._predictions_to_annotations(inference.get("predictions") or [], width, height)
        labelme_payload, shapes = build_labelme_annotation_payload(filename, annotations, width, height)
        labelme_payload["flags"] = {
            "auto_label": True,
            "auto_label_job_id": job_dir.name,
            "model_id": model.get("model_id"),
            "inference_job_id": inference.get("job_id"),
            "requires_review": True,
        }

        draft_labelme = draft_dir / "labelme" / f"{Path(filename).stem}.json"
        job_labelme = job_dir / "annotations" / "labelme" / draft_labelme.name
        cls._write_json(draft_labelme, labelme_payload)
        cls._write_json(job_labelme, labelme_payload)

        preview_url: Optional[str] = None
        preview_path = inference.get("paths", {}).get("annotated_image")
        if preview_path:
            source_preview = Path(preview_path)
            if source_preview.exists():
                preview_file = job_dir / "previews" / f"{Path(filename).stem}.jpg"
                shutil.copy2(source_preview, preview_file)
                preview_url = f"/api/projects/{project['project_id']}/auto-labeling/jobs/{job_dir.name}/previews/{preview_file.name}"

        return {
            "filename": filename,
            "draft_labelme": draft_labelme.resolve().as_posix(),
            "draft_labelme_url": f"/api/projects/{project['project_id']}/auto-labeling/jobs/{job_dir.name}/drafts/labelme/{draft_labelme.name}",
            "shape_count": len(shapes),
            "prediction_count": len(inference.get("predictions") or []),
            "inference_job_id": inference.get("job_id"),
            "inference_summary": inference.get("summary", {}),
            "preview_url": preview_url,
        }

    @staticmethod
    def _read_image_size(path: Path) -> tuple[int, int]:
        image = cv2.imread(str(path))
        if image is None:
            raise AutoLabelingServiceError(f"Unable to read image size: {path.name}")
        height, width = image.shape[:2]
        return int(width), int(height)

    @staticmethod
    def _predictions_to_annotations(predictions: List[Dict[str, Any]], width: int, height: int) -> List[Dict[str, Any]]:
        annotations: List[Dict[str, Any]] = []
        for prediction in predictions:
            label = prediction.get("class_name") or prediction.get("class_id") or "object"
            polygon = prediction.get("polygon_points") or prediction.get("points")
            if polygon and len(polygon) >= 3:
                annotations.append(
                    {
                        "category": label,
                        "type": "polygon",
                        "points": [[float(x), float(y)] for x, y in polygon],
                    }
                )
                continue

            bbox = prediction.get("bbox_xyxy")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [float(value) for value in bbox]
            box_w = max(0.0, x2 - x1)
            box_h = max(0.0, y2 - y1)
            if box_w <= 0 or box_h <= 0:
                continue
            annotations.append(
                {
                    "category": label,
                    "type": "bbox",
                    "bbox": [
                        (x1 + box_w / 2) / width,
                        (y1 + box_h / 2) / height,
                        box_w / width,
                        box_h / height,
                    ],
                }
            )
        return annotations

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

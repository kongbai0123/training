from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ultralytics import YOLO

from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.security_utils import sanitize_run_id


class ExportServiceError(RuntimeError):
    pass


class ExportableModelNotFound(ExportServiceError):
    pass


class ExportService:
    @classmethod
    def export_project_model(
        cls,
        project_id: str,
        project: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        best_pt = cls.resolve_exportable_weight(project, run_id=run_id, model_id=model_id)
        summary = cls.export_weight_to_onnx(project_id, project, layout, best_pt, run_id=run_id)
        return {
            "success": True,
            "export_id": summary["export_id"],
            "pt_path": summary["pt_abs_path"],
            "onnx_path": summary["onnx_abs_path"],
        }

    @classmethod
    def export_run_onnx(cls, project_id: str, project: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        safe_run_id = sanitize_run_id(run_id)
        layout = ProjectLayout.from_project(project)
        best_pt = layout.training_run_dir(safe_run_id) / "weights" / "best.pt"
        if not best_pt.exists():
            raise ExportableModelNotFound("best.pt not found; cannot export ONNX.")

        summary = cls.export_weight_to_onnx(project_id, project, layout, best_pt, run_id=safe_run_id)
        return {
            "success": True,
            "export_id": summary["export_id"],
            "onnx_path": summary["onnx_abs_path"],
        }

    @classmethod
    def resolve_exportable_weight(
        cls,
        project: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Path:
        layout = ProjectLayout.from_project(project)
        runs_dir = layout.training_runs_dir()
        best_pt: Optional[Path] = None

        if run_id:
            safe_run_id = sanitize_run_id(run_id)
            candidate_pt = runs_dir / safe_run_id / "weights" / "best.pt"
            if candidate_pt.exists():
                best_pt = candidate_pt

        if not best_pt and model_id:
            parts = model_id.split("::")
            if len(parts) >= 2:
                safe_run_id = sanitize_run_id(parts[1])
                weight_type = parts[2] if len(parts) >= 3 else "best"
                candidate_pt = runs_dir / safe_run_id / "weights" / f"{weight_type}.pt"
                if candidate_pt.exists():
                    best_pt = candidate_pt

        if not best_pt and project.get("best_model"):
            candidate_pt = Path(project["best_model"])
            if candidate_pt.exists():
                best_pt = candidate_pt

        if not best_pt and project.get("training_runs"):
            completed_runs = [run for run in project["training_runs"] if run.get("status") == "completed"]
            completed_runs.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
            for run in completed_runs:
                safe_run_id = str(run.get("run_id") or "").strip()
                if not safe_run_id:
                    continue
                candidate_pt = runs_dir / sanitize_run_id(safe_run_id) / "weights" / "best.pt"
                if candidate_pt.exists():
                    best_pt = candidate_pt
                    break

        if not best_pt:
            try:
                best_models = [model for model in ModelRegistry.list_models(project) if model.get("weight_type") == "best"]
                if best_models:
                    candidate_pt = Path(best_models[0]["internal_weight_path"])
                    if candidate_pt.exists():
                        best_pt = candidate_pt
            except Exception:
                pass

        if not best_pt:
            legacy_pt = runs_dir / "train" / "weights" / "best.pt"
            if legacy_pt.exists():
                best_pt = legacy_pt

        if not best_pt or not best_pt.exists():
            raise ExportableModelNotFound("No exportable model found.")
        return best_pt

    @classmethod
    def export_weight_to_onnx(
        cls,
        project_id: str,
        project: Dict[str, Any],
        layout: ProjectLayout,
        best_pt: Path,
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            model_obj = YOLO(str(best_pt.resolve()))
            model_obj.export(format="onnx")
        except Exception as exc:
            raise ExportServiceError(f"Failed to export ONNX model: {exc}")

        best_onnx = best_pt.parent / "best.onnx"
        if not best_onnx.exists():
            raise ExportServiceError("ONNX generation failed.")

        export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        exports_onnx_dir = export_dir / "onnx"
        exports_onnx_dir.mkdir(parents=True, exist_ok=True)

        export_pt = exports_onnx_dir / "best.pt"
        export_onnx = exports_onnx_dir / "best.onnx"
        shutil.copy(str(best_pt), str(export_pt))
        shutil.copy(str(best_onnx), str(export_onnx))

        summary = {
            "export_id": export_id,
            "created_at": datetime.now().isoformat(),
            "source_weight": str(best_pt.resolve().as_posix()),
            "pt_path": export_pt.relative_to(layout.project_dir).as_posix(),
            "onnx_path": export_onnx.relative_to(layout.project_dir).as_posix(),
            "pt_abs_path": str(export_pt.resolve().as_posix()),
            "onnx_abs_path": str(export_onnx.resolve().as_posix()),
        }
        if run_id:
            summary["run_id"] = run_id

        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        if "current" not in project:
            project["current"] = {}
        project["current"]["export_id"] = export_id
        ProjectManager.save_project(project_id, project)
        return summary

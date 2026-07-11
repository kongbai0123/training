from __future__ import annotations

import json
import shutil
import zipfile
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
    def list_project_exports(cls, project: Dict[str, Any], *, limit: int = 12) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        exports_root = layout.project_dir / "exports"
        if not exports_root.exists() or not exports_root.is_dir():
            return {"exports": []}

        artifacts = []
        for summary_path in exports_root.glob("*/summary.json"):
            summary = _read_json(summary_path)
            if not summary:
                continue
            artifacts.append(cls._normalize_export_summary(layout, summary_path, summary))

        artifacts.sort(key=lambda item: item.get("created_at") or item.get("modified_at") or "", reverse=True)
        safe_limit = max(1, int(limit or 12))
        return {"exports": artifacts[:safe_limit]}

    @classmethod
    def export_project_model(
        cls,
        project_id: str,
        project: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
        export_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        normalized_format = cls._normalize_export_format(export_format)
        is_rnn_export = cls._should_export_rnn_package(project, layout, run_id=run_id, model_id=model_id)

        if is_rnn_export:
            if normalized_format in {"auto", "rnn_package"}:
                summary = cls.export_rnn_package(project_id, project, layout, run_id=run_id, model_id=model_id)
                return {
                    "success": True,
                    "export_id": summary["export_id"],
                    "run_id": summary.get("run_id"),
                    "created_at": summary.get("created_at"),
                    "package_path": summary["package_abs_path"],
                    "summary_path": summary["summary_abs_path"],
                    "export_type": "rnn_model_package",
                }
            if normalized_format == "rnn_contract":
                summary = cls.export_rnn_contract(project_id, project, layout, run_id=run_id, model_id=model_id)
                return {
                    "success": True,
                    "export_id": summary["export_id"],
                    "run_id": summary.get("run_id"),
                    "created_at": summary.get("created_at"),
                    "contract_path": summary["contract_abs_path"],
                    "summary_path": summary["summary_abs_path"],
                    "export_type": "rnn_inference_contract",
                }
            if normalized_format == "rnn_schema_scaler":
                summary = cls.export_rnn_schema_scaler(project_id, project, layout, run_id=run_id, model_id=model_id)
                return {
                    "success": True,
                    "export_id": summary["export_id"],
                    "run_id": summary.get("run_id"),
                    "created_at": summary.get("created_at"),
                    "package_path": summary["package_abs_path"],
                    "summary_path": summary["summary_abs_path"],
                    "export_type": "rnn_schema_scaler_package",
                }
            raise ExportServiceError(f"Export format '{normalized_format}' is not supported for RNN projects.")

        if normalized_format in {"auto", "onnx"}:
            best_pt = cls.resolve_exportable_weight(project, run_id=run_id, model_id=model_id)
            summary = cls.export_weight_to_onnx(project_id, project, layout, best_pt, run_id=run_id)
            return {
                "success": True,
                "export_id": summary["export_id"],
                "run_id": summary.get("run_id"),
                "created_at": summary.get("created_at"),
                "pt_path": summary["pt_abs_path"],
                "onnx_path": summary["onnx_abs_path"],
                "summary_path": summary["summary_abs_path"],
                "export_type": "cnn_onnx",
                "validation": summary.get("validation", {}),
            }
        if normalized_format == "pt":
            best_pt = cls.resolve_exportable_weight(project, run_id=run_id, model_id=model_id)
            summary = cls.export_weight_copy(project_id, project, layout, best_pt, run_id=run_id)
            return {
                "success": True,
                "export_id": summary["export_id"],
                "run_id": summary.get("run_id"),
                "created_at": summary.get("created_at"),
                "pt_path": summary["pt_abs_path"],
                "summary_path": summary["summary_abs_path"],
                "export_type": "cnn_pt_copy",
            }
        raise ExportServiceError(f"Export format '{normalized_format}' is not supported for CNN projects.")

    @staticmethod
    def _normalize_export_format(export_format: Optional[str]) -> str:
        normalized = str(export_format or "auto").strip().lower().replace("-", "_")
        aliases = {
            "": "auto",
            "package": "rnn_package",
            "zip": "rnn_package",
            "model_package": "rnn_package",
            "contract": "rnn_contract",
            "inference_contract": "rnn_contract",
            "schema": "rnn_schema_scaler",
            "schema_scaler": "rnn_schema_scaler",
            "schema_and_scaler": "rnn_schema_scaler",
        }
        return aliases.get(normalized, normalized)

    @classmethod
    def export_weight_copy(
        cls,
        project_id: str,
        project: Dict[str, Any],
        layout: ProjectLayout,
        best_pt: Path,
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        export_id = f"export_pt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        exports_pt_dir = export_dir / "pt"
        exports_pt_dir.mkdir(parents=True, exist_ok=True)

        export_pt = exports_pt_dir / "best.pt"
        shutil.copy(str(best_pt), str(export_pt))

        summary = {
            "export_id": export_id,
            "export_type": "cnn_pt_copy",
            "created_at": datetime.now().isoformat(),
            "source_weight": str(best_pt.resolve().as_posix()),
            "pt_path": export_pt.relative_to(layout.project_dir).as_posix(),
            "pt_abs_path": str(export_pt.resolve().as_posix()),
            "summary_abs_path": str((export_dir / "summary.json").resolve().as_posix()),
        }
        if run_id:
            summary["run_id"] = run_id

        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        project.setdefault("current", {})["export_id"] = export_id
        ProjectManager.save_project(project_id, project)
        return summary

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
        cls._validate_onnx_graph(export_onnx)

        summary = {
            "export_id": export_id,
            "export_type": "cnn_onnx",
            "created_at": datetime.now().isoformat(),
            "source_weight": str(best_pt.resolve().as_posix()),
            "pt_path": export_pt.relative_to(layout.project_dir).as_posix(),
            "onnx_path": export_onnx.relative_to(layout.project_dir).as_posix(),
            "pt_abs_path": str(export_pt.resolve().as_posix()),
            "onnx_abs_path": str(export_onnx.resolve().as_posix()),
            "summary_abs_path": str((export_dir / "summary.json").resolve().as_posix()),
            "validation": {
                "graph_check": "passed",
                "precision": "fp32",
                "numerical_equivalence": "not_run",
            },
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

    @staticmethod
    def _validate_onnx_graph(onnx_path: Path) -> None:
        try:
            import onnx

            model = onnx.load(str(onnx_path))
            onnx.checker.check_model(model)
        except Exception as exc:
            raise ExportServiceError(f"Generated ONNX graph failed validation: {exc}") from exc

    @classmethod
    def export_rnn_package(
        cls,
        project_id: str,
        project: Dict[str, Any],
        layout: ProjectLayout,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_run_id = cls._resolve_rnn_run_id(project, layout, run_id=run_id, model_id=model_id)
        run_dir = layout.training_run_dir(safe_run_id)
        if not run_dir.exists():
            raise ExportableModelNotFound("RNN run directory not found; cannot export package.")

        export_id = f"export_rnn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        package_root = export_dir / "rnn_model_package"
        package_root.mkdir(parents=True, exist_ok=True)

        copied = []
        for rel_path in cls._rnn_package_candidate_paths(run_dir):
            source = run_dir / rel_path
            if not source.exists() or not source.is_file():
                continue
            target = package_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(source), str(target))
            copied.append({"path": rel_path, "size_bytes": target.stat().st_size})

        if not any(item["path"].startswith("weights/") for item in copied):
            raise ExportableModelNotFound("No RNN model artifact was found in this run.")

        contract = cls._build_rnn_inference_contract(project, run_dir, safe_run_id)
        (package_root / "inference_contract.json").write_text(
            json.dumps(contract, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        copied.append({"path": "inference_contract.json", "size_bytes": (package_root / "inference_contract.json").stat().st_size})

        zip_path = export_dir / "rnn_model_package.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in package_root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root).as_posix())

        summary = {
            "export_id": export_id,
            "export_type": "rnn_model_package",
            "created_at": datetime.now().isoformat(),
            "run_id": safe_run_id,
            "package_dir": package_root.relative_to(layout.project_dir).as_posix(),
            "package_path": zip_path.relative_to(layout.project_dir).as_posix(),
            "package_abs_path": str(zip_path.resolve().as_posix()),
            "summary_abs_path": str((export_dir / "summary.json").resolve().as_posix()),
            "files": copied,
            "inference_contract": contract,
        }
        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        project.setdefault("current", {})["export_id"] = export_id
        ProjectManager.save_project(project_id, project)
        return summary

    @classmethod
    def export_rnn_contract(
        cls,
        project_id: str,
        project: Dict[str, Any],
        layout: ProjectLayout,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_run_id = cls._resolve_rnn_run_id(project, layout, run_id=run_id, model_id=model_id)
        run_dir = layout.training_run_dir(safe_run_id)
        if not run_dir.exists():
            raise ExportableModelNotFound("RNN run directory not found; cannot export inference contract.")

        export_id = f"export_rnn_contract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        contract = cls._build_rnn_inference_contract(project, run_dir, safe_run_id)
        contract_path = export_dir / "inference_contract.json"
        contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
        summary = {
            "export_id": export_id,
            "export_type": "rnn_inference_contract",
            "created_at": datetime.now().isoformat(),
            "run_id": safe_run_id,
            "contract_path": contract_path.relative_to(layout.project_dir).as_posix(),
            "contract_abs_path": str(contract_path.resolve().as_posix()),
            "summary_abs_path": str((export_dir / "summary.json").resolve().as_posix()),
            "inference_contract": contract,
        }
        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        project.setdefault("current", {})["export_id"] = export_id
        ProjectManager.save_project(project_id, project)
        return summary

    @classmethod
    def export_rnn_schema_scaler(
        cls,
        project_id: str,
        project: Dict[str, Any],
        layout: ProjectLayout,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_run_id = cls._resolve_rnn_run_id(project, layout, run_id=run_id, model_id=model_id)
        run_dir = layout.training_run_dir(safe_run_id)
        if not run_dir.exists():
            raise ExportableModelNotFound("RNN run directory not found; cannot export schema and scaler.")

        export_id = f"export_rnn_schema_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir = layout.export_dir(export_id)
        package_root = export_dir / "schema_scaler"
        package_root.mkdir(parents=True, exist_ok=True)

        copied = []
        for rel_path in (
            "preprocess/feature_schema.json",
            "preprocess/normalization_stats.json",
            "preprocess/label_encoder.json",
        ):
            source = run_dir / rel_path
            if not source.exists() or not source.is_file():
                continue
            target = package_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(source), str(target))
            copied.append({"path": rel_path, "size_bytes": target.stat().st_size})

        if not copied:
            raise ExportableModelNotFound("No RNN schema or scaler artifacts were found in this run.")

        zip_path = export_dir / "rnn_schema_scaler.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in package_root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root).as_posix())

        summary = {
            "export_id": export_id,
            "export_type": "rnn_schema_scaler_package",
            "created_at": datetime.now().isoformat(),
            "run_id": safe_run_id,
            "package_dir": package_root.relative_to(layout.project_dir).as_posix(),
            "package_path": zip_path.relative_to(layout.project_dir).as_posix(),
            "package_abs_path": str(zip_path.resolve().as_posix()),
            "summary_abs_path": str((export_dir / "summary.json").resolve().as_posix()),
            "files": copied,
        }
        (export_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        layout.latest_export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        project.setdefault("current", {})["export_id"] = export_id
        ProjectManager.save_project(project_id, project)
        return summary

    @classmethod
    def _should_export_rnn_package(
        cls,
        project: Dict[str, Any],
        layout: ProjectLayout,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> bool:
        task_type = str(project.get("task_type") or "").lower()
        architecture = str(project.get("architecture") or project.get("mode") or "").lower()
        if architecture == "rnn" or task_type.startswith("sequence_"):
            return True
        try:
            safe_run_id = cls._resolve_rnn_run_id(project, layout, run_id=run_id, model_id=model_id, allow_missing=True)
            if safe_run_id:
                backend = _read_json(layout.training_run_dir(safe_run_id) / "backend.json")
                metrics = _read_json(layout.training_run_dir(safe_run_id) / "metrics.json")
                return (
                    str(backend.get("architecture") or "").lower() == "rnn"
                    or str(metrics.get("architecture") or "").lower() == "rnn"
                    or str(metrics.get("task_type") or "").lower().startswith("sequence_")
                )
        except Exception:
            return False
        return False

    @classmethod
    def _resolve_rnn_run_id(
        cls,
        project: Dict[str, Any],
        layout: ProjectLayout,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
        allow_missing: bool = False,
    ) -> str:
        if run_id:
            safe_run_id = sanitize_run_id(run_id)
            if allow_missing or layout.training_run_dir(safe_run_id).exists():
                return safe_run_id
        if model_id:
            parts = model_id.split("::")
            if len(parts) >= 2:
                safe_run_id = sanitize_run_id(parts[1])
                if allow_missing or layout.training_run_dir(safe_run_id).exists():
                    return safe_run_id
        completed_runs = [run for run in project.get("training_runs") or [] if str(run.get("status") or "").lower() == "completed"]
        completed_runs.sort(key=lambda item: item.get("completed_at") or item.get("timestamp") or item.get("created_at") or "", reverse=True)
        for run in completed_runs:
            candidate = sanitize_run_id(str(run.get("run_id") or ""))
            if not candidate:
                continue
            run_dir = layout.training_run_dir(candidate)
            if not run_dir.exists():
                continue
            backend = _read_json(run_dir / "backend.json")
            metrics = _read_json(run_dir / "metrics.json")
            if str(backend.get("architecture") or metrics.get("architecture") or "").lower() == "rnn":
                return candidate
        if allow_missing:
            return ""
        raise ExportableModelNotFound("No completed RNN run was found for package export.")

    @staticmethod
    def _rnn_package_candidate_paths(run_dir: Path) -> list[str]:
        candidates = [
            "weights/best.pt",
            "weights/last.pt",
            "weights/best.json",
            "weights/last.json",
            "weights/model_metadata.json",
            "preprocess/feature_schema.json",
            "preprocess/normalization_stats.json",
            "preprocess/label_encoder.json",
            "train_config.json",
            "metrics.json",
            "results.csv",
            "run_summary.json",
            "backend.json",
            "metric_schema.json",
            "artifact_manifest.json",
        ]
        diagnostics = []
        for path in run_dir.rglob("*"):
            if path.is_file() and any(token in path.name.lower() for token in ("diagnostic", "residual", "confusion")):
                diagnostics.append(path.relative_to(run_dir).as_posix())
        return candidates + sorted(set(diagnostics))

    @staticmethod
    def _build_rnn_inference_contract(project: Dict[str, Any], run_dir: Path, run_id: str) -> Dict[str, Any]:
        feature_schema = _read_json(run_dir / "preprocess" / "feature_schema.json")
        backend = _read_json(run_dir / "backend.json")
        metrics = _read_json(run_dir / "metrics.json")
        config = _read_json(run_dir / "train_config.json")
        sequence_length = (
            feature_schema.get("sequence_length")
            or config.get("sequence_length")
            or (metrics.get("dataset_summary") or {}).get("sequence_length")
            or project.get("rnn_config", {}).get("sequence_length")
        )
        return {
            "contract_version": "1.0",
            "architecture": "rnn",
            "run_id": run_id,
            "backend": backend.get("backend") or metrics.get("backend") or config.get("backend"),
            "task_type": metrics.get("task_type") or project.get("task_type"),
            "task_head": feature_schema.get("task_head") or project.get("rnn_config", {}).get("task_head"),
            "feature_columns": feature_schema.get("feature_columns") or project.get("rnn_config", {}).get("feature_columns") or [],
            "target_column": feature_schema.get("target_column") or project.get("rnn_config", {}).get("target_column") or "",
            "sequence_column": feature_schema.get("sequence_column") or project.get("rnn_config", {}).get("sequence_column") or "",
            "time_column": feature_schema.get("time_column") or project.get("rnn_config", {}).get("time_column") or "",
            "sequence_length": sequence_length,
            "stride": config.get("stride") or project.get("rnn_config", {}).get("stride"),
            "horizon": config.get("horizon") or project.get("rnn_config", {}).get("horizon"),
            "normalization": "preprocess/normalization_stats.json",
            "label_encoder": "preprocess/label_encoder.json" if (run_dir / "preprocess" / "label_encoder.json").exists() else None,
            "model_artifacts": [path for path in ("weights/best.pt", "weights/best.json", "weights/last.pt", "weights/last.json") if (run_dir / path).exists()],
        }

    @staticmethod
    def _normalize_export_summary(layout: ProjectLayout, summary_path: Path, summary: Dict[str, Any]) -> Dict[str, Any]:
        export_dir = summary_path.parent
        modified_at = datetime.fromtimestamp(summary_path.stat().st_mtime).isoformat()
        files = summary.get("files") if isinstance(summary.get("files"), list) else []
        return {
            "export_id": str(summary.get("export_id") or export_dir.name),
            "export_type": summary.get("export_type") or _infer_export_type(summary),
            "run_id": summary.get("run_id") or "",
            "created_at": summary.get("created_at") or modified_at,
            "modified_at": modified_at,
            "primary_path": _primary_export_path(summary),
            "primary_abs_path": _primary_export_abs_path(summary),
            "summary_path": _relative_to_project(layout, summary_path),
            "summary_abs_path": summary.get("summary_abs_path") or summary_path.resolve().as_posix(),
            "file_count": len(files),
            "files": files[:8],
            "validation": summary.get("validation") if isinstance(summary.get("validation"), dict) else {},
        }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _infer_export_type(summary: Dict[str, Any]) -> str:
    if summary.get("onnx_path") or summary.get("onnx_abs_path"):
        return "cnn_onnx"
    if summary.get("pt_path") or summary.get("pt_abs_path"):
        return "cnn_pt_copy"
    if summary.get("contract_path") or summary.get("contract_abs_path"):
        return "rnn_inference_contract"
    if summary.get("package_path") or summary.get("package_abs_path"):
        package_path = str(summary.get("package_path") or "").lower()
        return "rnn_schema_scaler_package" if "schema" in package_path else "rnn_model_package"
    return "export_artifact"


def _primary_export_path(summary: Dict[str, Any]) -> str:
    for key in ("package_path", "contract_path", "onnx_path", "pt_path", "summary_path"):
        value = summary.get(key)
        if value:
            return str(value)
    for key in ("package_abs_path", "contract_abs_path", "onnx_abs_path", "pt_abs_path", "summary_abs_path"):
        value = summary.get(key)
        if value:
            return str(value)
    return ""


def _primary_export_abs_path(summary: Dict[str, Any]) -> str:
    for key in ("package_abs_path", "contract_abs_path", "onnx_abs_path", "pt_abs_path", "summary_abs_path"):
        value = summary.get(key)
        if value:
            return str(value)
    return ""


def _relative_to_project(layout: ProjectLayout, path: Path) -> str:
    try:
        return path.resolve().relative_to(layout.project_dir).as_posix()
    except ValueError:
        return path.resolve().as_posix()

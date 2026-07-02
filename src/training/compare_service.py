from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.project_layout import ProjectLayout
from src.training.metric_schema import build_rnn_metric_schema, build_yolo_metric_schema


class CompareServiceError(ValueError):
    pass


class CompareService:
    MIN_RUNS = 2
    MAX_RUNS = 4

    @classmethod
    def list_comparable_runs(cls, project: Dict[str, Any], architecture: str) -> Dict[str, Any]:
        architecture = cls._normalize_architecture(architecture)
        layout = ProjectLayout.from_project(project)
        runs: List[Dict[str, Any]] = []
        warnings: List[str] = []
        allowed_run_ids = cls._completed_project_run_ids(project)
        restrict_to_project_runs = bool(project.get("training_runs"))

        runs_dir = layout.training_runs_dir()
        if runs_dir.exists():
            for run_dir in sorted(runs_dir.iterdir(), key=lambda p: p.name):
                if not run_dir.is_dir() or not cls._looks_like_training_run(run_dir):
                    continue
                if restrict_to_project_runs and run_dir.name not in allowed_run_ids:
                    continue
                bundle = cls.load_run_bundle(project, run_dir.name)
                run_architecture = cls.infer_architecture(bundle, project)
                if run_architecture != architecture:
                    continue
                if cls._status(bundle) != "completed":
                    continue
                runs.append(cls._run_card(bundle, project, warnings))

        message = None
        if architecture == "rnn" and not runs:
            message = "No completed RNN runs are available for comparison."

        payload: Dict[str, Any] = {
            "architecture": architecture,
            "runs": runs,
            "warnings": warnings,
        }
        if message:
            payload["message"] = message
        return payload

    @staticmethod
    def _completed_project_run_ids(project: Dict[str, Any]) -> set[str]:
        run_ids: set[str] = set()
        for run in project.get("training_runs") or []:
            if not isinstance(run, dict):
                continue
            if str(run.get("status") or "").lower() != "completed":
                continue
            run_id = str(run.get("run_id") or "").strip()
            if run_id:
                run_ids.add(run_id)
        return run_ids

    @classmethod
    def compare_runs(
        cls,
        project: Dict[str, Any],
        architecture: str,
        run_ids: List[str],
        baseline_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        architecture = cls._normalize_architecture(architecture)
        run_ids = [str(run_id or "").strip() for run_id in run_ids or [] if str(run_id or "").strip()]
        if len(run_ids) < cls.MIN_RUNS:
            raise CompareServiceError("Compare requires at least 2 run_ids.")
        if len(run_ids) > cls.MAX_RUNS:
            raise CompareServiceError("Compare supports at most 4 run_ids.")
        if len(set(run_ids)) != len(run_ids):
            raise CompareServiceError("Duplicate run_ids are not allowed.")

        allowed_run_ids = cls._completed_project_run_ids(project)
        if project.get("training_runs"):
            unknown = [run_id for run_id in run_ids if run_id not in allowed_run_ids]
            if unknown:
                raise CompareServiceError(f"Run is not registered as completed in this project: {', '.join(unknown)}")

        baseline_run_id = baseline_run_id or run_ids[0]
        if baseline_run_id not in run_ids:
            raise CompareServiceError("baseline_run_id must be one of selected run_ids.")

        warnings: List[str] = []
        bundles = [cls.load_run_bundle(project, run_id) for run_id in run_ids]

        architectures = {cls.infer_architecture(bundle, project) for bundle in bundles}
        if architectures != {architecture}:
            raise CompareServiceError("Selected runs have mixed or incompatible architecture.")

        statuses = {bundle["run_id"]: cls._status(bundle) for bundle in bundles}
        incomplete = [run_id for run_id, status in statuses.items() if status != "completed"]
        if incomplete:
            raise CompareServiceError(f"Only completed runs can be compared: {', '.join(incomplete)}")

        task_families = {cls.infer_task_family(bundle, project) for bundle in bundles}
        if len(task_families) != 1:
            raise CompareServiceError("Selected runs have incompatible task_family.")
        task_family = next(iter(task_families))

        metric_groups = cls.build_metric_groups(bundles[0], project)
        metric_defs = cls._metric_definitions(bundles[0], project, metric_groups)
        selected_runs = [cls._selected_run(bundle, project, warnings) for bundle in bundles]
        series = cls._build_series(bundles, metric_defs, warnings)
        summary = cls._build_summary(selected_runs, series, metric_defs, warnings)

        payload = {
            "comparison_id": "temp",
            "architecture": architecture,
            "task_family": task_family,
            "baseline_run_id": baseline_run_id,
            "selected_runs": selected_runs,
            "metric_groups": metric_groups,
            "series": series,
            "summary": summary,
            "recommendation": {},
        }
        payload["recommendation"] = cls.build_recommendation(payload)
        return payload

    @classmethod
    def export_report(
        cls,
        project: Dict[str, Any],
        architecture: str,
        run_ids: List[str],
        baseline_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = cls.compare_runs(project, architecture, run_ids, baseline_run_id)
        layout = ProjectLayout.from_project(project)
        reports_root = layout.project_dir / "exports" / "compare_reports"
        reports_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_architecture = cls._normalize_architecture(payload.get("architecture", architecture))
        run_part = "_".join(_safe_filename(run_id) for run_id in payload.get("baseline_run_id", "").split()) or "runs"
        report_id = f"compare_{safe_architecture}_{timestamp}_{run_part}"
        report_dir = reports_root / report_id
        suffix = 1
        while report_dir.exists():
            report_dir = reports_root / f"{report_id}_{suffix}"
            suffix += 1
        report_dir.mkdir(parents=True)
        report_id = report_dir.name

        json_path = report_dir / "report.json"
        markdown_path = report_dir / "report.md"
        csv_path = report_dir / "summary.csv"
        pdf_path = report_dir / "report.pdf"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(cls._build_markdown_report(payload), encoding="utf-8")
        csv_path.write_text(cls._build_summary_csv(payload), encoding="utf-8")
        pdf_path.write_bytes(cls._build_pdf_report(payload))

        files = []
        for path in (json_path, markdown_path, csv_path, pdf_path):
            files.append(
                {
                    "filename": path.name,
                    "path": path.relative_to(report_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "url": f"/api/projects/{project.get('project_id')}/compare/reports/{report_id}/download/{path.name}",
                }
            )

        return {
            "comparison_id": payload.get("comparison_id", "temp"),
            "report_id": report_id,
            "architecture": payload.get("architecture"),
            "task_family": payload.get("task_family"),
            "created_at": datetime.now().isoformat(),
            "report_dir": report_dir.as_posix(),
            "files": files,
        }

    @classmethod
    def list_reports(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        reports_root = layout.project_dir / "exports" / "compare_reports"
        reports: List[Dict[str, Any]] = []
        if reports_root.exists():
            for report_dir in sorted(reports_root.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
                if not report_dir.is_dir():
                    continue
                report_json = _read_json(report_dir / "report.json")
                files = []
                for filename in ("report.json", "report.md", "summary.csv", "report.pdf"):
                    path = report_dir / filename
                    if path.exists() and path.is_file():
                        files.append(
                            {
                                "filename": filename,
                                "path": filename,
                                "size_bytes": path.stat().st_size,
                                "url": f"/api/projects/{project.get('project_id')}/compare/reports/{report_dir.name}/download/{filename}",
                            }
                        )
                reports.append(
                    {
                        "report_id": report_dir.name,
                        "architecture": report_json.get("architecture"),
                        "task_family": report_json.get("task_family"),
                        "baseline_run_id": report_json.get("baseline_run_id"),
                        "selected_run_ids": [run.get("run_id") for run in report_json.get("selected_runs", []) if run.get("run_id")],
                        "recommendation": report_json.get("recommendation") or {},
                        "created_at": _mtime_iso(report_dir),
                        "files": files,
                    }
                )
        return {
            "reports": reports,
            "reports_dir": reports_root.as_posix(),
        }

    @classmethod
    def delete_report(cls, project: Dict[str, Any], report_id: str) -> Dict[str, Any]:
        import shutil

        if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", str(report_id or "")):
            raise CompareServiceError("Invalid report_id.")
        layout = ProjectLayout.from_project(project)
        reports_root = (layout.project_dir / "exports" / "compare_reports").resolve()
        report_dir = (reports_root / report_id).resolve()
        try:
            report_dir.relative_to(reports_root)
        except ValueError:
            raise CompareServiceError("Access denied: invalid report path.")
        if not report_dir.exists() or not report_dir.is_dir():
            raise CompareServiceError("Compare report not found.")
        shutil.rmtree(report_dir)
        return {"deleted": True, "report_id": report_id}

    @staticmethod
    def load_run_bundle(project: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        run_dir = layout.training_run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise CompareServiceError(f"Run not found: {run_id}")

        bundle = {
            "project": project,
            "run_id": run_id,
            "run_dir": run_dir,
            "metrics": _read_json(run_dir / "metrics.json"),
            "summary": _read_json(run_dir / "run_summary.json"),
            "config": _read_json(run_dir / "train_config.json"),
            "backend_contract": _read_json(run_dir / "backend.json"),
            "metric_schema": _read_json(run_dir / "metric_schema.json"),
            "artifact_manifest": _read_json(run_dir / "artifact_manifest.json"),
        }

        if not bundle["metrics"] and (run_dir / "results.csv").exists():
            bundle["metrics"] = _parse_results_csv(run_dir / "results.csv")
        return bundle

    @staticmethod
    def infer_architecture(bundle: Dict[str, Any], project: Dict[str, Any]) -> str:
        candidates = [
            bundle.get("backend_contract", {}).get("architecture"),
            bundle.get("metrics", {}).get("architecture"),
            bundle.get("config", {}).get("architecture"),
        ]
        for value in candidates:
            normalized = str(value or "").lower()
            if normalized in {"cnn", "rnn"}:
                return normalized

        backend = str(bundle.get("backend_contract", {}).get("backend") or bundle.get("config", {}).get("backend") or "").lower()
        if "lstm" in backend or "rnn" in backend:
            return "rnn"
        return "cnn"

    @staticmethod
    def infer_task_family(bundle: Dict[str, Any], project: Dict[str, Any]) -> str:
        task_type = (
            bundle.get("backend_contract", {}).get("task_type")
            or bundle.get("summary", {}).get("task_type")
            or bundle.get("metrics", {}).get("task_type")
            or bundle.get("config", {}).get("task_type")
            or project.get("task_type")
            or ""
        )
        normalized = str(task_type or "").lower()
        model = str(bundle.get("config", {}).get("model") or "").lower()
        if "sequence" in normalized or "rnn" in normalized:
            return "regression" if "regression" in normalized else "classification"
        if "segmentation" in normalized or "seg" in normalized or "-seg" in model or "_seg" in model:
            return "segmentation"
        if "detect" in normalized or "bbox" in normalized or "object" in normalized:
            return "detection"

        keys = set(_series_keys(bundle.get("metrics", {})))
        if any(key.endswith("(M)") for key in keys):
            return "segmentation"
        if any(key.endswith("(B)") for key in keys):
            return "detection"
        return "unknown"

    @staticmethod
    def load_metrics_series(bundle: Dict[str, Any]) -> Dict[str, Dict[str, List[float]]]:
        metrics = bundle.get("metrics") or {}
        series: Dict[str, Dict[str, List[float]]] = {}

        if isinstance(metrics.get("raw"), dict):
            epochs = _number_list(metrics.get("epochs") or [])
            for key, values in metrics["raw"].items():
                y = _number_list(values)
                x = epochs[: len(y)] if epochs else list(range(1, len(y) + 1))
                series[key] = {"x": x, "y": y}
            return series

        history = metrics.get("history")
        if isinstance(history, list):
            for index, row in enumerate(history):
                if not isinstance(row, dict):
                    continue
                epoch = _number(row.get("epoch"), index + 1)
                for key, value in row.items():
                    if key == "epoch":
                        continue
                    numeric = _maybe_number(value)
                    if numeric is None:
                        continue
                    series.setdefault(key, {"x": [], "y": []})
                    series[key]["x"].append(epoch)
                    series[key]["y"].append(numeric)
        return series

    @staticmethod
    def build_metric_groups(bundle: Dict[str, Any], project: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
        schema = bundle.get("metric_schema") or {}
        groups = schema.get("groups") if isinstance(schema, dict) else None
        if isinstance(groups, dict) and groups:
            result = {name: list(values or []) for name, values in groups.items()}
            primary = schema.get("primary_metric", {}).get("key")
            if primary:
                result.setdefault("primary", [])
                if primary not in result["primary"]:
                    result["primary"].insert(0, primary)
            return result

        project = project or bundle.get("project") or {}
        architecture = CompareService.infer_architecture(bundle, project)
        task_family = CompareService.infer_task_family(bundle, project)
        task_type = "sequence_regression" if architecture == "rnn" and task_family == "regression" else "sequence_classification" if architecture == "rnn" else task_family
        fallback_schema = build_rnn_metric_schema(task_type) if architecture == "rnn" else build_yolo_metric_schema(task_type)
        primary = fallback_schema.get("primary_metric", {}).get("key")
        quality = list(fallback_schema.get("groups", {}).get("quality", []))
        loss = list(fallback_schema.get("groups", {}).get("loss", []))
        return {
            "primary": [primary] + [key for key in quality if key != primary] if primary else quality,
            "quality": quality,
            "loss": loss,
        }

    @staticmethod
    def build_recommendation(payload: Dict[str, Any]) -> Dict[str, Any]:
        selected_runs = payload.get("selected_runs") or []
        primary_key = None
        for run in selected_runs:
            primary_key = run.get("summary", {}).get("primary_metric_key")
            if primary_key:
                break
        best = payload.get("summary", {}).get("best_by_metric", {}).get(primary_key or "")
        primary_series = payload.get("series", {}).get(primary_key or "", {})
        primary_goal = primary_series.get("goal") or "maximize"
        warnings = [
            "Inference latency is not available yet.",
            "Model size comparison is based on artifact file size only.",
        ]
        if not best:
            return {
                "best_overall": None,
                "confidence": "low",
                "reason": "Primary metric is not available for the selected runs.",
                "tradeoffs": [],
                "warnings": warnings,
            }
        return {
            "best_overall": best.get("run_id"),
            "confidence": "medium",
            "reason": (
                "Lowest primary metric among selected completed runs."
                if primary_goal == "minimize"
                else "Highest primary metric among selected completed runs."
            ),
            "tradeoffs": ["Inference latency is not available yet."],
            "warnings": warnings,
        }

    @staticmethod
    def _normalize_architecture(architecture: str) -> str:
        normalized = str(architecture or "").lower()
        if normalized not in {"cnn", "rnn"}:
            raise CompareServiceError("architecture must be cnn or rnn.")
        return normalized

    @staticmethod
    def _build_markdown_report(payload: Dict[str, Any]) -> str:
        recommendation = payload.get("recommendation") or {}
        selected_runs = payload.get("selected_runs") or []
        summary = payload.get("summary") or {}
        lines = [
            "# Model Compare Report",
            "",
            f"- Architecture: `{payload.get('architecture', '--')}`",
            f"- Task family: `{payload.get('task_family', '--')}`",
            f"- Baseline run: `{payload.get('baseline_run_id', '--')}`",
            f"- Generated at: `{datetime.now().isoformat()}`",
            "",
            "## Recommendation",
            "",
            f"- Best overall: `{recommendation.get('best_overall') or '--'}`",
            f"- Confidence: `{recommendation.get('confidence') or '--'}`",
            f"- Reason: {recommendation.get('reason') or '--'}",
            "",
            "## Selected Runs",
            "",
            "| Run ID | Model | Backend | Task | Primary Metric | Value |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for run in selected_runs:
            run_summary = run.get("summary") or {}
            lines.append(
                "| {run_id} | {model} | {backend} | {task} | {metric} | {value} |".format(
                    run_id=_md(run.get("run_id")),
                    model=_md(run.get("model")),
                    backend=_md(run.get("backend")),
                    task=_md(run.get("task_type") or run.get("task_family")),
                    metric=_md(run_summary.get("primary_metric_name")),
                    value=_md(_format_value(run_summary.get("primary_metric_value"))),
                )
            )

        lines.extend(["", "## Best By Metric", "", "| Metric | Best Run | Value |", "| --- | --- | --- |"])
        for key, item in (summary.get("best_by_metric") or {}).items():
            lines.append(f"| {_md(_display_name(key))} | {_md(item.get('run_id'))} | {_md(_format_value(item.get('value')))} |")

        lines.extend(["", "## Config Differences", ""])
        config_diff = summary.get("config_diff") or {}
        if config_diff:
            run_ids = [run.get("run_id", "--") for run in selected_runs]
            lines.append("| Config | " + " | ".join(_md(run_id) for run_id in run_ids) + " |")
            lines.append("| --- | " + " | ".join("---" for _ in run_ids) + " |")
            for key, values in config_diff.items():
                row = [_md(key)] + [_md(values.get(run_id, "--")) for run_id in run_ids]
                lines.append("| " + " | ".join(row) + " |")
        else:
            lines.append("No visible config differences in tracked fields.")

        warnings = list(dict.fromkeys((summary.get("warnings") or []) + (recommendation.get("warnings") or [])))
        if warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _build_summary_csv(payload: Dict[str, Any]) -> str:
        rows = [["section", "metric", "run_id", "value", "note"]]
        for run in payload.get("selected_runs") or []:
            run_summary = run.get("summary") or {}
            rows.append(
                [
                    "selected_run",
                    run_summary.get("primary_metric_name") or "",
                    run.get("run_id") or "",
                    _format_value(run_summary.get("primary_metric_value")),
                    run.get("model") or "",
                ]
            )
        for key, item in (payload.get("summary", {}).get("best_by_metric") or {}).items():
            rows.append(["best_by_metric", key, item.get("run_id") or "", _format_value(item.get("value")), ""])
        return "\n".join(",".join(_csv_cell(value) for value in row) for row in rows) + "\n"

    @staticmethod
    def _build_pdf_report(payload: Dict[str, Any]) -> bytes:
        lines = _pdf_report_lines(payload)
        return _simple_text_pdf(lines)

    @staticmethod
    def _status(bundle: Dict[str, Any]) -> str:
        status = str(
            bundle.get("backend_contract", {}).get("status")
            or bundle.get("summary", {}).get("status")
            or ""
        ).lower()
        if status:
            return status
        if bundle.get("metrics") or (bundle.get("run_dir") / "results.csv").exists():
            return "completed"
        return ""

    @staticmethod
    def _looks_like_training_run(run_dir: Path) -> bool:
        return any(
            (run_dir / filename).exists()
            for filename in (
                "metrics.json",
                "run_summary.json",
                "results.csv",
                "backend.json",
                "train_config.json",
            )
        )

    @classmethod
    def _run_card(cls, bundle: Dict[str, Any], project: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
        primary = cls._primary_metric(bundle, project, warnings)
        artifacts = cls._artifact_summary(bundle)
        return {
            "run_id": bundle["run_id"],
            "architecture": cls.infer_architecture(bundle, project),
            "backend": cls._backend(bundle),
            "task_type": cls._task_type(bundle, project),
            "task_family": cls.infer_task_family(bundle, project),
            "model": cls._model(bundle),
            "status": cls._status(bundle),
            "created_at": cls._created_at(bundle),
            "primary_metric": primary,
            "artifact_summary": artifacts,
        }

    @classmethod
    def _selected_run(cls, bundle: Dict[str, Any], project: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
        primary = cls._primary_metric(bundle, project, warnings)
        summary = bundle.get("summary") or {}
        return {
            "run_id": bundle["run_id"],
            "architecture": cls.infer_architecture(bundle, project),
            "backend": cls._backend(bundle),
            "task_type": cls._task_type(bundle, project),
            "task_family": cls.infer_task_family(bundle, project),
            "model": cls._model(bundle),
            "status": cls._status(bundle),
            "created_at": cls._created_at(bundle),
            "summary": {
                "best_epoch": summary.get("best_epoch", 0),
                "primary_metric_key": primary.get("key"),
                "primary_metric_name": primary.get("display_name"),
                "primary_metric_value": primary.get("value"),
                "platform_score": summary.get("platform_score", 0.0),
            },
            "config": bundle.get("config") or {},
            "artifacts": cls._artifacts(bundle),
            "evaluation_source": {
                "type": "training_run",
                "metrics_path": "metrics.json" if (bundle["run_dir"] / "metrics.json").exists() else None,
                "summary_path": "run_summary.json" if (bundle["run_dir"] / "run_summary.json").exists() else None,
                "evaluation_job_id": None,
                "inference_job_id": None,
            },
        }

    @classmethod
    def _primary_metric(cls, bundle: Dict[str, Any], project: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
        metric_defs = cls._metric_definitions(bundle, project, cls.build_metric_groups(bundle, project))
        primary_key = next(iter(metric_defs.keys()), None)
        if not primary_key:
            warnings.append(f"{bundle['run_id']}: primary metric is unavailable.")
            return {"key": None, "display_name": None, "value": None, "goal": "maximize"}
        value = cls._last_value(bundle, primary_key)
        if value is None:
            warnings.append(f"{bundle['run_id']}: selected metric is missing: {primary_key}")
        definition = metric_defs[primary_key]
        return {
            "key": primary_key,
            "display_name": definition["display_name"],
            "value": value,
            "goal": definition["goal"],
        }

    @classmethod
    def _metric_definitions(
        cls,
        bundle: Dict[str, Any],
        project: Dict[str, Any],
        metric_groups: Dict[str, List[str]],
    ) -> Dict[str, Dict[str, str]]:
        schema = bundle.get("metric_schema") or {}
        defs: Dict[str, Dict[str, str]] = {}
        primary = schema.get("primary_metric") if isinstance(schema, dict) else {}
        if isinstance(primary, dict) and primary.get("key"):
            defs[primary["key"]] = {
                "display_name": primary.get("display_name") or primary["key"],
                "goal": primary.get("goal") or _default_goal(primary["key"]),
            }

        for key in _flatten_metric_groups(metric_groups):
            defs.setdefault(key, {"display_name": _display_name(key), "goal": _default_goal(key)})

        available = set(_series_keys(bundle.get("metrics") or {}))
        if not defs and available:
            for key in sorted(available):
                defs[key] = {"display_name": _display_name(key), "goal": _default_goal(key)}
        return defs

    @classmethod
    def _build_series(
        cls,
        bundles: List[Dict[str, Any]],
        metric_defs: Dict[str, Dict[str, str]],
        warnings: List[str],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        run_series = {bundle["run_id"]: cls.load_metrics_series(bundle) for bundle in bundles}
        for key, definition in metric_defs.items():
            runs: Dict[str, Any] = {}
            for bundle in bundles:
                item = run_series[bundle["run_id"]].get(key)
                if item:
                    runs[bundle["run_id"]] = item
                else:
                    warnings.append(f"{bundle['run_id']}: metric series missing: {key}")
            result[key] = {
                "display_name": definition["display_name"],
                "goal": definition["goal"],
                "runs": runs,
            }
        return result

    @staticmethod
    def _build_summary(
        selected_runs: List[Dict[str, Any]],
        series: Dict[str, Any],
        metric_defs: Dict[str, Dict[str, str]],
        warnings: List[str],
    ) -> Dict[str, Any]:
        best_by_metric: Dict[str, Any] = {}
        for key, payload in series.items():
            goal = payload.get("goal") or metric_defs.get(key, {}).get("goal") or "maximize"
            best_run_id = None
            best_value = None
            for run_id, item in (payload.get("runs") or {}).items():
                values = item.get("y") or []
                if not values:
                    continue
                value = values[-1]
                if best_value is None or (value < best_value if goal == "minimize" else value > best_value):
                    best_value = value
                    best_run_id = run_id
            if best_run_id:
                best_by_metric[key] = {"run_id": best_run_id, "value": best_value}

        config_diff = _config_diff(selected_runs)
        summary_warnings = list(dict.fromkeys(warnings))
        if selected_runs:
            summary_warnings.append("Inference latency is not available.")
            summary_warnings.append("Model size is estimated from artifact file size.")
        return {
            "best_by_metric": best_by_metric,
            "config_diff": config_diff,
            "warnings": list(dict.fromkeys(summary_warnings)),
        }

    @staticmethod
    def _backend(bundle: Dict[str, Any]) -> str:
        return str(bundle.get("backend_contract", {}).get("backend") or bundle.get("metrics", {}).get("backend") or bundle.get("config", {}).get("backend") or "ultralytics_yolo")

    @staticmethod
    def _task_type(bundle: Dict[str, Any], project: Dict[str, Any]) -> str:
        return str(
            bundle.get("backend_contract", {}).get("task_type")
            or bundle.get("summary", {}).get("task_type")
            or bundle.get("metrics", {}).get("task_type")
            or bundle.get("config", {}).get("task_type")
            or project.get("task_type")
            or "unknown"
        )

    @staticmethod
    def _model(bundle: Dict[str, Any]) -> str:
        return str(bundle.get("config", {}).get("model") or bundle.get("metrics", {}).get("model") or "")

    @staticmethod
    def _created_at(bundle: Dict[str, Any]) -> str:
        return str(bundle.get("backend_contract", {}).get("created_at") or _mtime_iso(bundle["run_dir"]))

    @staticmethod
    def _artifacts(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        manifest = bundle.get("artifact_manifest") or {}
        artifacts = manifest.get("artifacts")
        if isinstance(artifacts, list):
            return artifacts
        return []

    @classmethod
    def _artifact_summary(cls, bundle: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = cls._artifacts(bundle)
        has_best_model = False
        has_onnx = False
        model_size_bytes = 0
        for artifact in artifacts:
            path = str(artifact.get("path") or "")
            role = str(artifact.get("role") or "")
            artifact_type = str(artifact.get("type") or "")
            if role == "best_model" or path.endswith("weights/best.pt"):
                has_best_model = True
                model_size_bytes = int(artifact.get("size_bytes") or model_size_bytes or 0)
            if artifact_type == "onnx_model" or path.endswith(".onnx"):
                has_onnx = True
        if not has_best_model:
            best = bundle["run_dir"] / "weights" / "best.pt"
            if best.exists():
                has_best_model = True
                model_size_bytes = best.stat().st_size
        return {"has_best_model": has_best_model, "has_onnx": has_onnx, "model_size_bytes": model_size_bytes}

    @classmethod
    def _last_value(cls, bundle: Dict[str, Any], key: str) -> Optional[float]:
        series = cls.load_metrics_series(bundle).get(key)
        if series and series.get("y"):
            return series["y"][-1]
        summary = bundle.get("summary") or {}
        best_metrics = summary.get("best_metrics") or {}
        value = _maybe_number(best_metrics.get(key))
        return value


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_results_csv(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except Exception:
        return {}
    if not rows:
        return {}
    epochs: List[float] = []
    raw: Dict[str, List[float]] = {}
    for index, row in enumerate(rows):
        epoch = _number(row.get("epoch"), index + 1)
        epochs.append(epoch)
        for key, value in row.items():
            if key == "epoch":
                continue
            numeric = _maybe_number(value)
            if numeric is None:
                continue
            raw.setdefault(key.strip(), []).append(numeric)
    return {"epochs": epochs, "raw": raw, "smooth": {}}


def _series_keys(metrics: Dict[str, Any]) -> Iterable[str]:
    if isinstance(metrics.get("raw"), dict):
        return metrics["raw"].keys()
    history = metrics.get("history")
    if isinstance(history, list):
        keys = set()
        for row in history:
            if isinstance(row, dict):
                keys.update(key for key in row.keys() if key != "epoch")
        return keys
    return []


def _flatten_metric_groups(groups: Dict[str, List[str]]) -> List[str]:
    result: List[str] = []
    for group_name in ("primary", "quality", "loss"):
        for key in groups.get(group_name, []) or []:
            if key and key not in result:
                result.append(key)
    return result


def _config_diff(selected_runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    keys = [
        "model",
        "epochs",
        "batch_size",
        "imgsz",
        "lr0",
        "optimizer",
        "device",
        "sequence_length",
        "stride",
        "horizon",
        "hidden_size",
        "num_layers",
        "dropout",
    ]
    diff: Dict[str, Dict[str, Any]] = {}
    for key in keys:
        values = {run["run_id"]: run.get("config", {}).get(key) for run in selected_runs if key in (run.get("config") or {})}
        if values and len(set(json.dumps(value, sort_keys=True) for value in values.values())) > 1:
            diff[key] = values
    return diff


def _number(value: Any, fallback: float) -> float:
    numeric = _maybe_number(value)
    return fallback if numeric is None else numeric


def _maybe_number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _number_list(values: Iterable[Any]) -> List[float]:
    result = []
    for value in values:
        numeric = _maybe_number(value)
        if numeric is not None:
            result.append(numeric)
    return result


def _display_name(key: str) -> str:
    if "mAP50-95" in key:
        return "mAP50-95"
    if "mAP50" in key:
        return "mAP50"
    return key.split("/")[-1].replace("_", " ").title()


def _default_goal(key: str) -> str:
    lowered = key.lower()
    if "loss" in lowered or "mae" in lowered or "rmse" in lowered:
        return "minimize"
    return "maximize"


def _mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except Exception:
        return ""


def _safe_filename(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "report"


def _md(value: Any) -> str:
    text = str(value if value is not None else "--")
    return text.replace("|", "\\|").replace("\n", " ")


def _format_value(value: Any) -> str:
    numeric = _maybe_number(value)
    if numeric is None:
        return "--" if value in {None, ""} else str(value)
    return f"{numeric:.6g}"


def _csv_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    if any(char in text for char in [",", "\"", "\n", "\r"]):
        return "\"" + text.replace("\"", "\"\"") + "\""
    return text


def _pdf_report_lines(payload: Dict[str, Any]) -> List[str]:
    recommendation = payload.get("recommendation") or {}
    summary = payload.get("summary") or {}
    selected_runs = payload.get("selected_runs") or []
    lines = [
        "Model Compare Report",
        f"Architecture: {payload.get('architecture', '--')}",
        f"Task family: {payload.get('task_family', '--')}",
        f"Baseline run: {payload.get('baseline_run_id', '--')}",
        f"Generated at: {datetime.now().isoformat()}",
        "",
        "Recommendation Summary",
        f"Best overall: {recommendation.get('best_overall') or '--'}",
        f"Confidence: {recommendation.get('confidence') or '--'}",
        f"Reason: {recommendation.get('reason') or '--'}",
        "",
        "Metric Table",
        "Run ID | Model | Backend | Task | Primary Metric | Value",
    ]
    for run in selected_runs:
        run_summary = run.get("summary") or {}
        lines.append(
            " | ".join(
                [
                    str(run.get("run_id") or "--"),
                    str(run.get("model") or "--"),
                    str(run.get("backend") or "--"),
                    str(run.get("task_type") or run.get("task_family") or "--"),
                    str(run_summary.get("primary_metric_name") or "--"),
                    _format_value(run_summary.get("primary_metric_value")),
                ]
            )
        )

    lines.extend(["", "Best By Metric"])
    best_by_metric = summary.get("best_by_metric") or {}
    if best_by_metric:
        for key, item in best_by_metric.items():
            lines.append(f"{_display_name(key)}: {item.get('run_id') or '--'} ({_format_value(item.get('value'))})")
    else:
        lines.append("No comparable metric winner is available.")

    lines.extend(["", "Config Diff"])
    config_diff = summary.get("config_diff") or {}
    if config_diff:
        run_ids = [run.get("run_id", "--") for run in selected_runs]
        lines.append("Config | " + " | ".join(str(run_id) for run_id in run_ids))
        for key, values in config_diff.items():
            row = [str(key)] + [str(values.get(run_id, "--")) for run_id in run_ids]
            lines.append(" | ".join(row))
    else:
        lines.append("No visible config differences in tracked fields.")

    warnings = list(dict.fromkeys((summary.get("warnings") or []) + (recommendation.get("warnings") or [])))
    if warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    return lines


def _simple_text_pdf(lines: List[str]) -> bytes:
    sanitized = [_pdf_text(line)[:110] for line in lines]
    pages = [sanitized[index : index + 42] for index in range(0, len(sanitized), 42)] or [[]]

    objects: List[bytes] = []
    page_object_ids: List[int] = []
    content_object_ids: List[int] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object(b"")
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_lines in pages:
        content_lines = ["BT", "/F1 10 Tf", "50 770 Td", "14 TL"]
        for line_index, line in enumerate(page_lines):
            prefix = "" if line_index == 0 else "T* "
            content_lines.append(f"{prefix}({_escape_pdf_text(line)}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", errors="replace")
        content_id = add_object(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        content_object_ids.append(content_id)
        page_object_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _pdf_text(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

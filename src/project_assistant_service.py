from __future__ import annotations

import json
import math
import re
import time
import uuid
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.app_paths import USER_DATA_DIR
from src.project_layout import ProjectLayout
from src.training.export_service import ExportService
from src.training.run_registry import ExperimentRunRegistry


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
ASSISTANT_MODES = {"disabled", "local_search_only", "local_gguf", "cloud_api"}
ASSISTANT_SCOPE_SOURCE_TYPES = {
    "dashboard": {"project_summary", "dataset_schema", "training_runs", "exports"},
    "dataset": {"dataset_schema", "project_summary"},
    "labelme": {"dataset_schema", "project_summary"},
    "split": {"dataset_schema", "project_summary"},
    "augmentation": {"dataset_schema", "training_runs", "project_summary"},
    "training": {"dataset_schema", "training_runs", "project_summary"},
    "evaluation": {"training_runs", "evaluation_report", "diagnostics", "project_summary"},
    "inference": {"training_runs", "evaluation_report", "exports", "project_summary"},
    "auto_labeling": {"dataset_schema", "training_runs", "project_summary"},
    "auto-labeling": {"dataset_schema", "training_runs", "project_summary"},
    "sequence_dataset": {"dataset_schema", "project_summary"},
    "features_labels": {"dataset_schema", "project_summary"},
    "windowing": {"dataset_schema", "project_summary"},
    "sequence_test": {"training_runs", "evaluation_report", "dataset_schema", "project_summary"},
    "model_compare": {"training_runs", "model_comparison", "project_summary"},
    "model-compare": {"training_runs", "model_comparison", "project_summary"},
    "export": {"exports", "training_runs", "dataset_schema"},
    "history": {"project_summary", "dataset_schema", "training_runs", "exports", "history", "error_logs"},
}


def resolve_assistant_project_context(project: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    project = project if isinstance(project, dict) else {}
    task_type = str(project.get("task_type") or project.get("task") or "").strip().lower()
    training_config = project.get("training_config") if isinstance(project.get("training_config"), dict) else {}
    explicit_architecture = str(
        project.get("architecture")
        or project.get("training_mode")
        or training_config.get("architecture")
        or ""
    ).strip().lower()
    if explicit_architecture not in {"cnn", "rnn"}:
        explicit_architecture = "rnn" if any(
            token in task_type for token in ("sequence", "time_series", "timeseries", "rnn")
        ) else "cnn"
    return {"architecture": explicit_architecture, "task_type": task_type}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in WORD_RE.findall(text or "") if token.strip()]


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return ""


class ProjectAssistantService:
    """Offline-first project assistant service.

    The service deliberately avoids external embedding providers so the assistant can run
    in a clean local environment. Retrieval is lexical TF-style scoring; the API contract
    can later swap in vector embeddings without changing the UI workflow.
    """

    ROOT = USER_DATA_DIR / "project_assistant"
    KB_DIR = ROOT / "knowledge_base"
    DOCS_DIR = KB_DIR / "documents"
    RUNS_DIR = ROOT / "runs"
    ARTIFACTS_DIR = ROOT / "artifacts"
    EXPORTS_DIR = ROOT / "exports"
    STATE_PATH = ROOT / "state.json"
    SANDBOX_PATH = ROOT / "sandbox.json"

    DEFAULT_SANDBOX_FILES = {
        "index.html": "<!doctype html>\n<html>\n<head><title>Project Assistant Artifact</title></head>\n<body>\n  <main id=\"app\">Project Assistant artifact preview</main>\n</body>\n</html>\n",
        "css/style.css": "body { font-family: system-ui, sans-serif; margin: 24px; }\n#app { padding: 16px; border: 1px solid #d0d7de; }\n",
        "js/app.js": "document.querySelector('#app')?.setAttribute('data-ready', 'true');\n",
        "README.md": "# Project Assistant Artifact\n\nGenerated inside the local project assistant sandbox.\n",
    }

    @classmethod
    def ensure(cls) -> None:
        for path in (cls.ROOT, cls.KB_DIR, cls.DOCS_DIR, cls.RUNS_DIR, cls.ARTIFACTS_DIR, cls.EXPORTS_DIR):
            path.mkdir(parents=True, exist_ok=True)
        if not cls.STATE_PATH.exists():
            cls._save_state(cls._empty_state())
        if not cls.SANDBOX_PATH.exists():
            cls._save_sandbox({"files": cls.DEFAULT_SANDBOX_FILES, "updated_at": _now()})

    @classmethod
    def _empty_state(cls) -> Dict[str, Any]:
        return {
            "schema_version": "project-assistant.1",
            "workspace": {
                "workspace_id": "local_project_assistant",
                "title": "Local Project Assistant",
                "model_state": "local_stub",
                "assistant_enabled": True,
                "index_state": "empty",
                "updated_at": _now(),
            },
            "documents": [],
            "chunks": [],
            "retrieval_profiles": [
                {"profile_id": "lexical_default", "name": "Lexical Default", "top_k": 5, "rerank": "none"},
                {"profile_id": "lexical_precise", "name": "Lexical Precise", "top_k": 3, "rerank": "length_penalty"},
            ],
            "agent_runs": [],
            "evaluation_reports": [],
            "golden_set": [],
            "bad_retrieval_marks": [],
            "assistant_settings": {
                "mode": "local_search_only",
                "local_model_path": "",
                "cloud_provider": "",
                "cloud_model": "",
                "allow_external_requests": False,
                "updated_at": _now(),
            },
        }

    @classmethod
    def _state(cls) -> Dict[str, Any]:
        cls.ensure()
        state = _read_json(cls.STATE_PATH, cls._empty_state())
        if not isinstance(state, dict):
            state = cls._empty_state()
        state.setdefault("assistant_settings", cls._empty_state()["assistant_settings"])
        return state

    @classmethod
    def _save_state(cls, state: Dict[str, Any]) -> None:
        state.setdefault("workspace", {})["updated_at"] = _now()
        _write_json(cls.STATE_PATH, state)

    @classmethod
    def _sandbox(cls) -> Dict[str, Any]:
        cls.ensure()
        sandbox = _read_json(cls.SANDBOX_PATH, {"files": cls.DEFAULT_SANDBOX_FILES, "updated_at": _now()})
        files = sandbox.get("files")
        if not isinstance(files, dict):
            sandbox["files"] = dict(cls.DEFAULT_SANDBOX_FILES)
        return sandbox

    @classmethod
    def _save_sandbox(cls, sandbox: Dict[str, Any]) -> None:
        sandbox["updated_at"] = _now()
        _write_json(cls.SANDBOX_PATH, sandbox)

    @staticmethod
    def _project_matches(metadata: Optional[Dict[str, Any]], project_id: Optional[str]) -> bool:
        if project_id is None:
            return True
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return False
        return str((metadata or {}).get("project_id") or "").strip() == normalized_project_id

    @classmethod
    def _project_documents(cls, state: Dict[str, Any], project_id: Optional[str]) -> List[Dict[str, Any]]:
        return [
            document
            for document in state.get("documents", [])
            if cls._project_matches(document.get("metadata") or {}, project_id)
        ]

    @classmethod
    def _project_chunks(cls, state: Dict[str, Any], project_id: Optional[str]) -> List[Dict[str, Any]]:
        return [
            chunk
            for chunk in state.get("chunks", [])
            if cls._project_matches(chunk.get("metadata") or {}, project_id)
        ]

    @classmethod
    def _project_agent_runs(cls, state: Dict[str, Any], project_id: Optional[str]) -> List[Dict[str, Any]]:
        if project_id is None:
            return state.get("agent_runs", [])
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return []
        return [
            run
            for run in state.get("agent_runs", [])
            if str((run.get("retrieval_config") or {}).get("filters", {}).get("project_id") or "").strip() == normalized_project_id
        ]

    @classmethod
    def status(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        state = cls._state()
        docs = cls._project_documents(state, project_id)
        chunks = cls._project_chunks(state, project_id)
        agent_runs = cls._project_agent_runs(state, project_id)
        indexed_chunks = [chunk for chunk in chunks if chunk.get("index_state") == "indexed"]
        index_state = "ready" if indexed_chunks else "empty"
        if docs and len(indexed_chunks) < len(chunks):
            index_state = "partial"
        if project_id is None:
            state["workspace"]["index_state"] = index_state
            cls._save_state(state)
        return {
            "workspace": state["workspace"],
            "navigation": ["chat", "knowledge-base", "retrieval", "agent-runs", "sandbox", "evaluation", "settings"],
            "knowledge_base": {
                "document_count": len(docs),
                "chunk_count": len(chunks),
                "indexed_chunk_count": len(indexed_chunks),
                "index_state": index_state,
            },
            "retrieval_profiles": state.get("retrieval_profiles", []),
            "agent_run_count": len(agent_runs),
            "evaluation_report_count": len(state.get("evaluation_reports", [])),
            "assistant_settings": cls.get_settings(),
            "guardrails": {
                "raw_thought_visible": False,
                "conversation_from_dom": False,
                "sandbox_os_isolation": False,
            },
        }

    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        state = cls._state()
        settings = state.setdefault("assistant_settings", cls._empty_state()["assistant_settings"])
        mode = str(settings.get("mode") or "local_search_only")
        if mode not in ASSISTANT_MODES:
            mode = "local_search_only"
        return {
            "mode": mode,
            "local_model_path": str(settings.get("local_model_path") or ""),
            "cloud_provider": str(settings.get("cloud_provider") or ""),
            "cloud_model": str(settings.get("cloud_model") or ""),
            "allow_external_requests": bool(settings.get("allow_external_requests", False)),
            "requires_llm": mode in {"local_gguf", "cloud_api"},
            "generation_enabled": mode != "disabled",
            "updated_at": settings.get("updated_at") or "",
        }

    @classmethod
    def update_settings(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = cls._state()
        current = state.setdefault("assistant_settings", cls._empty_state()["assistant_settings"])
        requested_mode = str(payload.get("mode") or current.get("mode") or "local_search_only")
        if requested_mode not in ASSISTANT_MODES:
            raise ValueError(f"Unsupported assistant mode: {requested_mode}")
        current.update({
            "mode": requested_mode,
            "local_model_path": str(payload.get("local_model_path", current.get("local_model_path", "")) or ""),
            "cloud_provider": str(payload.get("cloud_provider", current.get("cloud_provider", "")) or ""),
            "cloud_model": str(payload.get("cloud_model", current.get("cloud_model", "")) or ""),
            "allow_external_requests": bool(payload.get("allow_external_requests", current.get("allow_external_requests", False))),
            "updated_at": _now(),
        })
        state["assistant_settings"] = current
        cls._save_state(state)
        return cls.get_settings()

    @classmethod
    def ingest_document(cls, filename: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cls.ensure()
        state = cls._state()
        safe_name = Path(filename or "document.txt").name
        document_id = _safe_id("doc")
        document_path = cls.DOCS_DIR / f"{document_id}_{safe_name}"
        document_path.write_text(content or "", encoding="utf-8")

        stages = [
            {"stage": "upload", "state": "done", "message": "Document stored locally."},
            {"stage": "parse", "state": "done", "message": "Plain text parsed."},
            {"stage": "chunk", "state": "done", "message": "Document split into retrieval chunks."},
            {"stage": "embed", "state": "done", "message": "Local lexical token index prepared."},
            {"stage": "index", "state": "done", "message": "Chunks are searchable."},
        ]
        document_metadata = metadata or {}
        chunks = cls._chunk_document(document_id, safe_name, content or "", document_metadata)
        document = {
            "document_id": document_id,
            "filename": safe_name,
            "path": document_path.as_posix(),
            "size_chars": len(content or ""),
            "chunk_count": len(chunks),
            "metadata": document_metadata,
            "ingestion": stages,
            "index_state": "indexed" if chunks else "empty",
            "created_at": _now(),
        }
        state.setdefault("documents", []).append(document)
        state.setdefault("chunks", []).extend(chunks)
        state["workspace"]["index_state"] = "ready" if chunks else state["workspace"].get("index_state", "empty")
        cls._save_state(state)
        project_id = document_metadata.get("project_id") if document_metadata else None
        return {"document": document, "chunks": chunks, "status": cls.status(project_id=project_id)}

    @classmethod
    def ingest_file_bytes(cls, filename: str, payload: bytes, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in {".txt", ".md", ".markdown", ".csv", ".json", ".log"}:
            return cls.ingest_document(
                filename=f"{Path(filename or 'document').stem or 'document'}.txt",
                content=payload.decode("utf-8", errors="replace"),
                metadata={**(metadata or {}), "original_filename": filename, "parse_warning": "Parsed as UTF-8 text fallback."},
            )
        return cls.ingest_document(
            filename=filename,
            content=payload.decode("utf-8", errors="replace"),
            metadata=metadata or {},
        )

    @classmethod
    def sync_project_artifacts(cls, project: Dict[str, Any]) -> Dict[str, Any]:
        """Index deterministic artifacts for the active project.

        This is intentionally a project-scoped mirror of structured training evidence,
        not a global document crawler. Manual knowledge-base uploads are preserved; only
        previously auto-indexed documents for the same project are replaced.
        """
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            raise ValueError("project_id is required to sync project artifacts.")

        cls.ensure()
        removed = cls._clear_auto_documents(project_id)
        documents = cls._build_project_artifact_documents(project)
        project_context = resolve_assistant_project_context(project)
        results = []
        for item in documents:
            result = cls.ingest_document(
                filename=item["filename"],
                content=item["content"],
                metadata={
                    "project_id": project_id,
                    "project_name": str(project.get("project_name") or project.get("name") or ""),
                    **project_context,
                    "source_type": item["source_type"],
                    "auto_indexed": True,
                    "sync_key": item["sync_key"],
                },
            )
            results.append(result["document"])

        return {
            "project_id": project_id,
            "status": cls.status(project_id=project_id),
            "removed_auto_documents": removed,
            "documents": results,
            "document_count": len(results),
            "chunk_count": sum(int(document.get("chunk_count") or 0) for document in results),
        }

    @classmethod
    def _clear_auto_documents(cls, project_id: str) -> int:
        state = cls._state()
        normalized_project_id = str(project_id or "").strip()
        removed_documents = [
            document
            for document in state.get("documents", [])
            if cls._project_matches(document.get("metadata") or {}, normalized_project_id)
            and bool((document.get("metadata") or {}).get("auto_indexed"))
        ]
        if not removed_documents:
            return 0
        removed_ids = {document.get("document_id") for document in removed_documents}
        state["documents"] = [
            document
            for document in state.get("documents", [])
            if document.get("document_id") not in removed_ids
        ]
        state["chunks"] = [
            chunk
            for chunk in state.get("chunks", [])
            if chunk.get("document_id") not in removed_ids
        ]
        removed_paths = {Path(str(document.get("path") or "")).name for document in removed_documents}
        if cls.DOCS_DIR.exists():
            for item in cls.DOCS_DIR.iterdir():
                if item.is_file() and item.name in removed_paths:
                    item.unlink()
        cls._save_state(state)
        return len(removed_documents)

    @classmethod
    def _build_project_artifact_documents(cls, project: Dict[str, Any]) -> List[Dict[str, str]]:
        project_id = str(project.get("project_id") or "project").strip()
        layout = ProjectLayout.from_project(project)
        registry = cls._safe_call(lambda: ExperimentRunRegistry.build(project), {"runs": [], "run_count": 0})
        exports = cls._safe_call(lambda: ExportService.list_project_exports(project, limit=24), {"exports": []})
        docs = [
            {
                "filename": "project-summary.md",
                "source_type": "project_summary",
                "sync_key": f"{project_id}:project-summary",
                "content": cls._project_summary_markdown(project, registry, exports),
            },
            {
                "filename": "dataset-and-schema.md",
                "source_type": "dataset_schema",
                "sync_key": f"{project_id}:dataset-schema",
                "content": cls._dataset_schema_markdown(project, layout),
            },
            {
                "filename": "training-runs-and-metrics.md",
                "source_type": "training_runs",
                "sync_key": f"{project_id}:training-runs",
                "content": cls._training_runs_markdown(project, registry, layout),
            },
            {
                "filename": "evaluation-diagnostics.md",
                "source_type": "evaluation_report",
                "sync_key": f"{project_id}:evaluation-diagnostics",
                "content": cls._evaluation_diagnostics_markdown(project, registry, layout),
            },
            {
                "filename": "model-comparison-reports.md",
                "source_type": "model_comparison",
                "sync_key": f"{project_id}:model-comparison",
                "content": cls._model_comparison_markdown(project, registry, layout),
            },
            {
                "filename": "exports-and-contracts.md",
                "source_type": "exports",
                "sync_key": f"{project_id}:exports",
                "content": cls._exports_markdown(project, exports),
            },
            {
                "filename": "history-and-activity.md",
                "source_type": "history",
                "sync_key": f"{project_id}:history",
                "content": cls._history_markdown(project, layout),
            },
            {
                "filename": "error-logs.md",
                "source_type": "error_logs",
                "sync_key": f"{project_id}:error-logs",
                "content": cls._error_logs_markdown(project, registry, layout),
            },
        ]
        return [doc for doc in docs if doc["content"].strip()]

    @staticmethod
    def _safe_call(callback, fallback):
        try:
            return callback()
        except Exception:
            return fallback

    @classmethod
    def _project_summary_markdown(cls, project: Dict[str, Any], registry: Dict[str, Any], exports: Dict[str, Any]) -> str:
        file_summary = project.get("file_summary") if isinstance(project.get("file_summary"), dict) else {}
        current = project.get("current") if isinstance(project.get("current"), dict) else {}
        imports_history = project.get("imports_history") if isinstance(project.get("imports_history"), list) else []
        classes = project.get("class_names") if isinstance(project.get("class_names"), list) else []
        lines = [
            "# Project Summary",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Project name: {project.get('project_name') or project.get('name') or ''}",
            f"- Task type: {project.get('task_type') or ''}",
            f"- Created at: {project.get('created_at') or ''}",
            f"- Updated at: {project.get('updated_at') or ''}",
            f"- Current training run: {current.get('training_run_id') or ''}",
            f"- Current export: {current.get('export_id') or ''}",
            f"- Registered training runs: {registry.get('run_count') or 0}",
            f"- Export artifacts: {len(exports.get('exports') or [])}",
            "",
            "## File Summary",
            cls._compact_json(file_summary),
            "",
            "## Classes",
            ", ".join(str(item) for item in classes) if classes else "No class labels configured for this project.",
            "",
            "## Recent Imports",
            cls._compact_json(imports_history[-8:] if imports_history else []),
        ]
        return "\n".join(lines)

    @classmethod
    def _dataset_schema_markdown(cls, project: Dict[str, Any], layout: ProjectLayout) -> str:
        sequence_manifest = _read_json(layout.sequence_manifest_path(), {})
        split_manifest = _read_json(layout.current_split_path, {})
        rnn_config = project.get("rnn_config") if isinstance(project.get("rnn_config"), dict) else {}
        training_config = project.get("training_config") if isinstance(project.get("training_config"), dict) else {}
        split_config = project.get("split_config") if isinstance(project.get("split_config"), dict) else {}
        lines = [
            "# Dataset And Schema",
            "",
            f"- Task type: {project.get('task_type') or ''}",
            f"- Dataset path: {project.get('dataset_path') or ''}",
            f"- Sequence manifest exists: {layout.sequence_manifest_path().exists()}",
            f"- Current split exists: {layout.current_split_path.exists()}",
            "",
            "## RNN Schema Config",
            cls._compact_json(rnn_config),
            "",
            "## Training Config",
            cls._compact_json(training_config),
            "",
            "## Split Config",
            cls._compact_json(split_config),
            "",
            "## Sequence Manifest",
            cls._compact_json(sequence_manifest),
            "",
            "## Current Split Manifest",
            cls._compact_json(split_manifest),
        ]
        return "\n".join(lines)

    @classmethod
    def _training_runs_markdown(cls, project: Dict[str, Any], registry: Dict[str, Any], layout: ProjectLayout) -> str:
        lines = [
            "# Training Runs And Metrics",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Run count: {registry.get('run_count') or 0}",
            "",
        ]
        runs = registry.get("runs") if isinstance(registry.get("runs"), list) else []
        if not runs:
            lines.append("No registered training runs found.")
            return "\n".join(lines)
        for run in runs[:20]:
            run_id = str(run.get("run_id") or "")
            run_dir = layout.training_run_dir(run_id)
            metrics = _read_json(run_dir / "metrics.json", {})
            metric_schema = _read_json(run_dir / "metric_schema.json", {})
            summary = _read_json(run_dir / "run_summary.json", {})
            lines.extend([
                f"## Run {run_id}",
                f"- Status: {run.get('status') or ''}",
                f"- Architecture: {run.get('architecture') or ''}",
                f"- Backend: {run.get('backend') or ''}",
                f"- Task type: {run.get('task_type') or ''}",
                f"- Primary metric: {run.get('primary_metric') or ''}",
                f"- Primary value: {run.get('primary_value') if run.get('primary_value') is not None else ''}",
                f"- Diagnostics: {cls._compact_json(run.get('diagnostics') or {})}",
                f"- Artifact counts: {cls._compact_json(run.get('artifact_counts') or {})}",
                "",
                "### Metrics",
                cls._compact_json(metrics),
                "",
                "### Metric Schema",
                cls._compact_json(metric_schema),
                "",
                "### Run Summary",
                cls._compact_json(summary),
                "",
            ])
        return "\n".join(lines)

    @classmethod
    def _evaluation_diagnostics_markdown(cls, project: Dict[str, Any], registry: Dict[str, Any], layout: ProjectLayout) -> str:
        lines = [
            "# Evaluation Diagnostics",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Task type: {project.get('task_type') or ''}",
            "",
        ]
        runs = registry.get("runs") if isinstance(registry.get("runs"), list) else []
        completed = [run for run in runs if str(run.get("status") or "").lower() == "completed"]
        if not completed:
            lines.append("No completed training runs are available for evaluation.")
            return "\n".join(lines)
        for run in completed[:20]:
            run_id = str(run.get("run_id") or "")
            run_dir = layout.training_run_dir(run_id)
            metrics = _read_json(run_dir / "metrics.json", {})
            metric_schema = _read_json(run_dir / "metric_schema.json", {})
            diagnostics = {
                key: metrics.get(key)
                for key in ("confusion_matrix", "confusion_labels", "residuals", "prediction_actual_samples", "outliers")
                if key in metrics
            }
            best_metrics = metrics.get("best_metrics") if isinstance(metrics.get("best_metrics"), dict) else {}
            history = metrics.get("history") if isinstance(metrics.get("history"), list) else []
            lines.extend([
                f"## Evaluation Run {run_id}",
                f"- Architecture: {run.get('architecture') or ''}",
                f"- Backend: {run.get('backend') or ''}",
                f"- Task type: {run.get('task_type') or ''}",
                f"- Primary metric: {run.get('primary_metric') or ''}",
                f"- Primary value: {run.get('primary_value') if run.get('primary_value') is not None else ''}",
                "",
                "### Best Metrics",
                cls._compact_json(best_metrics),
                "",
                "### Metric Schema",
                cls._compact_json(metric_schema),
                "",
                "### Diagnostics",
                cls._compact_json(diagnostics or {"present": False, "message": "No task-specific diagnostic payload found."}),
                "",
                "### Recent Epoch History",
                cls._compact_json(history[-12:] if history else []),
                "",
            ])
        return "\n".join(lines)

    @classmethod
    def _model_comparison_markdown(cls, project: Dict[str, Any], registry: Dict[str, Any], layout: ProjectLayout) -> str:
        reports_root = layout.project_dir / "exports" / "compare_reports"
        reports: List[Dict[str, Any]] = []
        if reports_root.exists():
            for report_dir in sorted((path for path in reports_root.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
                report = _read_json(report_dir / "report.json", {})
                if report:
                    reports.append({
                        "report_id": report_dir.name,
                        "created_at": _mtime_iso(report_dir),
                        "report": report,
                    })
        lines = [
            "# Model Comparison Reports",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Report count: {len(reports)}",
            "",
        ]
        if reports:
            for item in reports[:12]:
                report = item.get("report") or {}
                lines.extend([
                    f"## Compare Report {item.get('report_id') or ''}",
                    f"- Created at: {item.get('created_at') or ''}",
                    f"- Architecture: {report.get('architecture') or ''}",
                    f"- Task family: {report.get('task_family') or ''}",
                    f"- Baseline run: {report.get('baseline_run_id') or ''}",
                    f"- Selected runs: {', '.join(str(run.get('run_id') or '') for run in report.get('selected_runs', []) if isinstance(run, dict))}",
                    "",
                    "### Recommendation",
                    cls._compact_json(report.get("recommendation") or {}),
                    "",
                    "### Summary",
                    cls._compact_json(report.get("summary") or {}),
                    "",
                ])
            return "\n".join(lines)

        completed_runs = [
            {
                "run_id": run.get("run_id"),
                "architecture": run.get("architecture"),
                "task_type": run.get("task_type"),
                "primary_metric": run.get("primary_metric"),
                "primary_value": run.get("primary_value"),
            }
            for run in (registry.get("runs") if isinstance(registry.get("runs"), list) else [])
            if str(run.get("status") or "").lower() == "completed"
        ]
        lines.extend([
            "No exported model comparison report found.",
            "",
            "## Comparable Completed Runs",
            cls._compact_json(completed_runs[:20]),
        ])
        return "\n".join(lines)

    @classmethod
    def _exports_markdown(cls, project: Dict[str, Any], exports: Dict[str, Any]) -> str:
        lines = [
            "# Exports And Contracts",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Export count: {len(exports.get('exports') or [])}",
            "",
        ]
        items = exports.get("exports") if isinstance(exports.get("exports"), list) else []
        if not items:
            lines.append("No export artifacts found.")
            return "\n".join(lines)
        for item in items[:24]:
            lines.extend([
                f"## Export {item.get('export_id') or ''}",
                f"- Type: {item.get('export_type') or ''}",
                f"- Run ID: {item.get('run_id') or ''}",
                f"- Created at: {item.get('created_at') or ''}",
                f"- Primary path: {item.get('primary_path') or ''}",
                f"- Summary path: {item.get('summary_path') or ''}",
                f"- Files: {cls._compact_json(item.get('files') or [])}",
                "",
            ])
        return "\n".join(lines)

    @classmethod
    def _history_markdown(cls, project: Dict[str, Any], layout: ProjectLayout) -> str:
        imports_history = project.get("imports_history") if isinstance(project.get("imports_history"), list) else []
        training_runs = project.get("training_runs") if isinstance(project.get("training_runs"), list) else []
        history_dir = layout.project_dir / "history"
        history_files = cls._read_small_text_files(history_dir, suffixes={".md", ".txt", ".json", ".log"}, limit=12)
        lines = [
            "# Project History And Activity",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Import records: {len(imports_history)}",
            f"- Training run records: {len(training_runs)}",
            f"- History files: {len(history_files)}",
            "",
            "## Recent Imports",
            cls._compact_json(imports_history[-12:] if imports_history else []),
            "",
            "## Training Run Records",
            cls._compact_json(training_runs[-20:] if training_runs else []),
            "",
            "## History Files",
            cls._compact_json(history_files),
        ]
        return "\n".join(lines)

    @classmethod
    def _error_logs_markdown(cls, project: Dict[str, Any], registry: Dict[str, Any], layout: ProjectLayout) -> str:
        project_logs = cls._read_small_text_files(layout.project_dir / "logs", suffixes={".log", ".txt", ".json"}, limit=12)
        run_errors: List[Dict[str, Any]] = []
        runs = registry.get("runs") if isinstance(registry.get("runs"), list) else []
        for run in runs[:30]:
            run_id = str(run.get("run_id") or "")
            run_dir = layout.training_run_dir(run_id)
            summary = _read_json(run_dir / "run_summary.json", {})
            error_log = run_dir / "error.log"
            if summary.get("error") or error_log.exists() or str(run.get("status") or "").lower() == "failed":
                run_errors.append({
                    "run_id": run_id,
                    "status": run.get("status"),
                    "summary_error": summary.get("error") or "",
                    "error_log": cls._read_text_excerpt(error_log),
                })
        lines = [
            "# Error Logs And Failures",
            "",
            f"- Project ID: {project.get('project_id') or ''}",
            f"- Project log files: {len(project_logs)}",
            f"- Runs with error evidence: {len(run_errors)}",
            "",
            "## Project Logs",
            cls._compact_json(project_logs),
            "",
            "## Run Error Evidence",
            cls._compact_json(run_errors),
        ]
        if not project_logs and not run_errors:
            lines.append("\nNo project error logs or failed run evidence found.")
        return "\n".join(lines)

    @classmethod
    def _read_small_text_files(cls, directory: Path, suffixes: set[str], limit: int = 12) -> List[Dict[str, Any]]:
        if not directory.exists() or not directory.is_dir():
            return []
        files: List[Dict[str, Any]] = []
        for path in sorted((item for item in directory.rglob("*") if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in suffixes:
                continue
            files.append({
                "path": path.relative_to(directory).as_posix(),
                "size_bytes": path.stat().st_size,
                "modified_at": _mtime_iso(path),
                "excerpt": cls._read_text_excerpt(path),
            })
            if len(files) >= limit:
                break
        return files

    @staticmethod
    def _read_text_excerpt(path: Path, limit: int = 2200) -> str:
        if not path.exists() or not path.is_file():
            return ""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
        text = text.strip()
        return text[:limit] + ("\n... truncated ..." if len(text) > limit else "")

    @staticmethod
    def _compact_json(payload: Any, limit: int = 5000) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except Exception:
            text = str(payload)
        if len(text) > limit:
            text = text[:limit] + "\n... truncated ..."
        return f"```json\n{text}\n```"

    @classmethod
    def _chunk_document(
        cls,
        document_id: str,
        filename: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 700,
        overlap: int = 120,
    ) -> List[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", content or "").strip()
        if not text:
            return []
        chunks: List[Dict[str, Any]] = []
        start = 0
        sequence = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            chunk_text = text[start:end].strip()
            token_counts = Counter(_tokens(chunk_text))
            chunks.append({
                "chunk_id": f"{document_id}_chunk_{sequence:04d}",
                "document_id": document_id,
                "source": filename,
                "section": f"chunk {sequence + 1}",
                "offset_start": start,
                "offset_end": end,
                "content": chunk_text,
                "token_count": sum(token_counts.values()),
                "token_index": dict(token_counts),
                "metadata": metadata or {},
                "index_state": "indexed",
            })
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
            sequence += 1
        return chunks

    @classmethod
    def list_documents(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        state = cls._state()
        documents = cls._project_documents(state, project_id)
        document_ids = {document.get("document_id") for document in documents}
        chunks = [
            chunk
            for chunk in cls._project_chunks(state, project_id)
            if chunk.get("document_id") in document_ids
        ]
        return {
            "documents": documents,
            "chunks": chunks,
            "status": cls.status(project_id=project_id),
        }

    @classmethod
    def clear_knowledge_base(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        state = cls._state()
        if project_id is None:
            removed_documents = state.get("documents", [])
            state["documents"] = []
            state["chunks"] = []
            state["bad_retrieval_marks"] = []
            state["workspace"]["index_state"] = "empty"
        else:
            removed_documents = cls._project_documents(state, project_id)
            removed_ids = {document.get("document_id") for document in removed_documents}
            state["documents"] = [
                document
                for document in state.get("documents", [])
                if document.get("document_id") not in removed_ids
            ]
            state["chunks"] = [
                chunk
                for chunk in state.get("chunks", [])
                if chunk.get("document_id") not in removed_ids
            ]
        if cls.DOCS_DIR.exists() and removed_documents:
            removed_paths = {Path(str(document.get("path") or "")).name for document in removed_documents}
            for item in cls.DOCS_DIR.iterdir():
                if item.is_file() and (project_id is None or item.name in removed_paths):
                    item.unlink()
        cls._save_state(state)
        return cls.status(project_id=project_id)

    @classmethod
    def reindex(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        state = cls._state()
        for chunk in state.get("chunks", []):
            if not cls._project_matches(chunk.get("metadata") or {}, project_id):
                continue
            chunk["token_index"] = dict(Counter(_tokens(chunk.get("content", ""))))
            chunk["index_state"] = "indexed"
        if project_id is None:
            state["workspace"]["index_state"] = "ready" if state.get("chunks") else "empty"
        cls._save_state(state)
        return cls.status(project_id=project_id)

    @classmethod
    def _normalize_retrieval_filters(cls, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized = dict(filters or {})
        scope = str(normalized.get("scope") or "").strip()
        if scope:
            normalized["scope"] = scope
        source_types = normalized.get("source_types")
        if source_types is None and scope:
            source_types = ASSISTANT_SCOPE_SOURCE_TYPES.get(scope, set())
        if isinstance(source_types, str):
            source_types = [source_types]
        normalized_source_types = {
            str(item or "").strip()
            for item in (source_types or [])
            if str(item or "").strip()
        }
        if normalized_source_types:
            normalized["source_types"] = sorted(normalized_source_types)
        else:
            normalized.pop("source_types", None)
        architecture = str(normalized.get("architecture") or "").strip().lower()
        if architecture in {"cnn", "rnn"}:
            normalized["architecture"] = architecture
        else:
            normalized.pop("architecture", None)
        task_type = str(normalized.get("task_type") or "").strip().lower()
        if task_type:
            normalized["task_type"] = task_type
        else:
            normalized.pop("task_type", None)
        return normalized

    @classmethod
    def retrieve(cls, query: str, top_k: int = 5, profile_id: str = "lexical_default", filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = cls._state()
        query_tokens = Counter(_tokens(query))
        filters = cls._normalize_retrieval_filters(filters)
        has_project_filter = "project_id" in filters
        project_id_filter = str(filters.get("project_id") or "").strip()
        source_type_filter = set(filters.get("source_types") or [])
        architecture_filter = str(filters.get("architecture") or "").strip().lower()
        task_type_filter = str(filters.get("task_type") or "").strip().lower()
        if not query_tokens:
            return {
                "query": query,
                "profile_id": profile_id,
                "filters": filters,
                "results": [],
                "diagnostic": {"reason": "empty_query"},
            }

        scored = []
        candidate_chunks = 0
        scoped_candidate_chunks = 0
        for chunk in state.get("chunks", []):
            if filters.get("document_id") and chunk.get("document_id") != filters["document_id"]:
                continue
            if has_project_filter and not cls._project_matches(chunk.get("metadata") or {}, project_id_filter):
                continue
            candidate_chunks += 1
            metadata = chunk.get("metadata") or {}
            source_type = str(metadata.get("source_type") or "").strip()
            if source_type_filter and source_type not in source_type_filter:
                continue
            if architecture_filter and str(metadata.get("architecture") or "").strip().lower() != architecture_filter:
                continue
            if task_type_filter and str(metadata.get("task_type") or "").strip().lower() != task_type_filter:
                continue
            scoped_candidate_chunks += 1
            token_index = chunk.get("token_index") or {}
            overlap = sum(min(query_tokens[token], int(token_index.get(token, 0))) for token in query_tokens)
            if not overlap:
                continue
            length_norm = math.sqrt(max(int(chunk.get("token_count") or 1), 1))
            score = overlap / length_norm
            if profile_id == "lexical_precise":
                score = score / max(math.log(max(int(chunk.get("token_count") or 2), 2)), 1)
            scored.append({**chunk, "score": round(score, 4), "rerank_score": round(score, 4)})

        scored.sort(key=lambda item: item["score"], reverse=True)
        safe_top_k = max(1, min(int(top_k or 5), 20))
        results = [
            {
                "chunk_id": item["chunk_id"],
                "document_id": item["document_id"],
                "source": item["source"],
                "section": item["section"],
                "score": item["score"],
                "rerank_score": item["rerank_score"],
                "content": item["content"],
                "source_type": (item.get("metadata") or {}).get("source_type", ""),
                "architecture": (item.get("metadata") or {}).get("architecture", ""),
                "task_type": (item.get("metadata") or {}).get("task_type", ""),
            }
            for item in scored[:safe_top_k]
        ]
        return {
            "query": query,
            "profile_id": profile_id,
            "top_k": safe_top_k,
            "filters": filters,
            "results": results,
            "diagnostic": {
                "query_tokens": list(query_tokens.keys()),
                "candidate_chunks": candidate_chunks,
                "scoped_candidate_chunks": scoped_candidate_chunks,
                "matched_chunks": len(scored),
                "scope": filters.get("scope", ""),
                "source_types": filters.get("source_types", []),
            },
        }

    @classmethod
    def mark_retrieval(cls, query: str, chunk_id: str, relevance: str, note: str = "") -> Dict[str, Any]:
        state = cls._state()
        mark = {
            "mark_id": _safe_id("mark"),
            "query": query,
            "chunk_id": chunk_id,
            "relevance": relevance if relevance in {"good", "bad", "irrelevant"} else "bad",
            "note": note,
            "created_at": _now(),
        }
        state.setdefault("bad_retrieval_marks", []).append(mark)
        cls._save_state(state)
        return mark

    @classmethod
    def chat(
        cls,
        message: str,
        conversation_state: Optional[List[Dict[str, Any]]] = None,
        profile_id: str = "lexical_default",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        settings = cls.get_settings()
        filters = cls._normalize_retrieval_filters(filters)
        if settings["mode"] == "disabled":
            sources = []
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            answer = "Project Assistant is disabled. Enable Local Search Only to search project reports and logs."
            run = {
                "run_id": _safe_id("assistant_run"),
                "query": message,
                "answer": answer,
                "sources": sources,
                "agent_trace": [
                    cls._agent_step("parse", "done", "Parsed user request."),
                    cls._agent_step("settings", "failed", "Assistant mode is disabled."),
                    cls._agent_step("final", "done", "Returned disabled-mode response."),
                ],
                "conversation_state": cls._clean_conversation(conversation_state or []) + [
                    {"role": "user", "content": message, "meta": {"source": "clean_state"}},
                    {"role": "assistant", "content": answer, "meta": {"source_count": 0}},
                ],
                "retrieval_config": {"profile_id": profile_id, "top_k": 0, "filters": filters, "mode": settings["mode"]},
                "metrics": cls._run_metrics(sources, latency_ms, "assistant_disabled"),
                "failure_type": "assistant_disabled",
                "created_at": _now(),
            }
            state = cls._state()
            state.setdefault("agent_runs", []).insert(0, run)
            state["agent_runs"] = state["agent_runs"][:100]
            cls._save_state(state)
            return run
        conversation = cls._clean_conversation(conversation_state or [])
        retrieval = cls.retrieve(message, top_k=5, profile_id=profile_id, filters=filters)
        sources = retrieval["results"]
        steps = [
            cls._agent_step("parse", "done", "Parsed user request."),
            cls._agent_step("retrieve", "done" if sources else "failed", f"Retrieved {len(sources)} source chunk(s)."),
            cls._agent_step("validate", "done" if sources else "failed", "Checked source availability."),
            cls._agent_step("final", "done", "Generated grounded response." if sources else "Generated no-source response."),
        ]
        if sources:
            source_lines = [f"- {item['source']} / {item['section']}: {item['content'][:220]}" for item in sources[:3]]
            answer = "According to the active project knowledge base, the most relevant sources are:\n" + "\n".join(source_lines)
            failure_type = ""
        else:
            answer = "No citable source was found in the active project knowledge base. Import project reports, run records, or error logs before asking again."
            failure_type = "no_sources"

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        run = {
            "run_id": _safe_id("assistant_run"),
            "query": message,
            "answer": answer,
            "sources": sources,
            "agent_trace": steps,
            "conversation_state": conversation + [
                {"role": "user", "content": message, "meta": {"source": "clean_state"}},
                {"role": "assistant", "content": answer, "meta": {"source_count": len(sources)}},
            ],
            "retrieval_config": {"profile_id": profile_id, "top_k": 5, "filters": retrieval.get("filters") or filters},
            "metrics": cls._run_metrics(sources, latency_ms, failure_type),
            "failure_type": failure_type,
            "created_at": _now(),
        }
        state = cls._state()
        state.setdefault("agent_runs", []).insert(0, run)
        state["agent_runs"] = state["agent_runs"][:100]
        cls._save_state(state)
        return run

    @classmethod
    def chat_stream_events(
        cls,
        message: str,
        conversation_state: Optional[List[Dict[str, Any]]] = None,
        profile_id: str = "lexical_default",
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        run = cls.chat(
            message=message,
            conversation_state=conversation_state or [],
            profile_id=profile_id,
            filters=filters or {},
        )
        return [
            {"event": "plan", "data": {"steps": run["agent_trace"]}},
            {"event": "sources", "data": {"sources": run["sources"]}},
            {"event": "final", "data": {"answer": run["answer"], "run_id": run["run_id"], "metrics": run["metrics"]}},
            {"event": "done", "data": {"run_id": run["run_id"]}},
        ]

    @classmethod
    def _clean_conversation(cls, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean = []
        for item in items:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant", "system"} or not isinstance(content, str):
                continue
            clean.append({"role": role, "content": content, "meta": item.get("meta") if isinstance(item.get("meta"), dict) else {}})
        return clean[-20:]

    @staticmethod
    def _agent_step(name: str, state: str, message: str) -> Dict[str, Any]:
        return {"step": name, "state": state, "message": message, "timestamp": _now()}

    @staticmethod
    def _run_metrics(sources: List[Dict[str, Any]], latency_ms: float, failure_type: str = "") -> Dict[str, Any]:
        return {
            "source_count": len(sources),
            "citation_coverage": 1.0 if sources else 0.0,
            "source_hit": bool(sources),
            "latency_ms": latency_ms,
            "failure_type": failure_type,
        }

    @classmethod
    def list_agent_runs(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        state = cls._state()
        return {"runs": cls._project_agent_runs(state, project_id)}

    @classmethod
    def get_sandbox(cls) -> Dict[str, Any]:
        sandbox = cls._sandbox()
        files = sandbox.get("files", {})
        return {
            "files": [{"path": path, "size": len(content or ""), "content": content or ""} for path, content in sorted(files.items())],
            "preview_html": cls.build_preview_html(files),
            "updated_at": sandbox.get("updated_at"),
            "policy": {"os_isolation": False, "network": "not_used", "write_scope": "project_assistant/artifacts"},
        }

    @classmethod
    def update_sandbox_file(cls, path: str, content: str) -> Dict[str, Any]:
        safe_path = str(path or "").replace("\\", "/").strip().lstrip("/")
        if not safe_path or ".." in Path(safe_path).parts:
            raise ValueError("Invalid sandbox file path.")
        sandbox = cls._sandbox()
        sandbox.setdefault("files", {})[safe_path] = content or ""
        cls._save_sandbox(sandbox)
        return cls.get_sandbox()

    @classmethod
    def build_preview_html(cls, files: Optional[Dict[str, str]] = None) -> str:
        files = files or cls._sandbox().get("files", {})
        html = files.get("index.html") or "<!doctype html><html><head></head><body></body></html>"
        css = files.get("css/style.css") or ""
        js = files.get("js/app.js") or ""
        style = f"<style data-rag-sandbox-style>\n{css}\n</style>"
        script = f"<script data-rag-sandbox-script>\n{js}\n</script>"
        output = html.replace("</head>", f"{style}\n</head>") if "</head>" in html else f"{style}\n{html}"
        output = output.replace("</body>", f"{script}\n</body>") if "</body>" in output else f"{output}\n{script}"
        return output

    @classmethod
    def export_sandbox(cls) -> Dict[str, Any]:
        sandbox = cls._sandbox()
        artifact_id = _safe_id("artifact")
        target = cls.ARTIFACTS_DIR / f"{artifact_id}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted((sandbox.get("files") or {}).items()):
                archive.writestr(path, content or "")
            archive.writestr("preview.html", cls.build_preview_html(sandbox.get("files") or {}))
        artifact = {
            "artifact_id": artifact_id,
            "type": "sandbox_project_zip",
            "path": target.as_posix(),
            "created_at": _now(),
            "size_bytes": target.stat().st_size,
        }
        state = cls._state()
        state.setdefault("artifacts", []).insert(0, artifact)
        cls._save_state(state)
        return artifact

    @classmethod
    def set_golden_set(cls, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = []
        for item in items:
            query = str(item.get("query") or "").strip()
            expected_source = str(item.get("expected_source") or "").strip()
            expected_answer = str(item.get("expected_answer") or "").strip()
            if not query:
                continue
            normalized.append({
                "case_id": item.get("case_id") or _safe_id("golden"),
                "query": query,
                "expected_source": expected_source,
                "expected_answer": expected_answer,
                "created_at": item.get("created_at") or _now(),
            })
        state = cls._state()
        state["golden_set"] = normalized
        cls._save_state(state)
        return {"golden_set": normalized, "count": len(normalized)}

    @classmethod
    def evaluation_report(cls, golden_set: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        state = cls._state()
        if golden_set is not None:
            state["golden_set"] = cls.set_golden_set(golden_set)["golden_set"]
            state = cls._state()
        runs = state.get("agent_runs", [])
        golden_items = state.get("golden_set", [])
        total = len(runs)
        source_hits = sum(1 for run in runs if run.get("metrics", {}).get("source_hit"))
        avg_latency = round(sum(float(run.get("metrics", {}).get("latency_ms") or 0) for run in runs) / total, 2) if total else 0
        failures = Counter(run.get("failure_type") or "none" for run in runs)
        golden_hits = cls._evaluate_golden_hits(runs, golden_items)
        report = {
            "report_id": _safe_id("rag_eval"),
            "run_count": total,
            "golden_case_count": len(golden_items),
            "golden_source_hits": golden_hits,
            "citation_coverage": round(source_hits / total, 4) if total else 0,
            "source_hit_rate": round(source_hits / total, 4) if total else 0,
            "average_latency_ms": avg_latency,
            "failure_types": dict(failures),
            "created_at": _now(),
        }
        markdown = (
            "# Project Assistant Evaluation Report\n\n"
            f"- Runs: {report['run_count']}\n"
            f"- Golden cases: {report['golden_case_count']}\n"
            f"- Golden source hits: {report['golden_source_hits']}\n"
            f"- Citation coverage: {report['citation_coverage']}\n"
            f"- Source hit rate: {report['source_hit_rate']}\n"
            f"- Average latency ms: {report['average_latency_ms']}\n"
            f"- Failure types: {json.dumps(report['failure_types'], ensure_ascii=False)}\n"
        )
        export_dir = cls.EXPORTS_DIR / report["report_id"]
        export_dir.mkdir(parents=True, exist_ok=True)
        report_path = export_dir / "report.md"
        report_path.write_text(markdown, encoding="utf-8")
        report["report_path"] = report_path.as_posix()
        state.setdefault("evaluation_reports", []).insert(0, report)
        cls._save_state(state)
        return report

    @staticmethod
    def _evaluate_golden_hits(runs: List[Dict[str, Any]], golden_items: List[Dict[str, Any]]) -> int:
        if not runs or not golden_items:
            return 0
        hits = 0
        for case in golden_items:
            query = str(case.get("query") or "").lower()
            expected_source = str(case.get("expected_source") or "").lower()
            for run in runs:
                if query and query not in str(run.get("query") or "").lower():
                    continue
                if not expected_source:
                    hits += 1
                    break
                if any(expected_source in str(src.get("source") or "").lower() for src in run.get("sources", [])):
                    hits += 1
                    break
        return hits

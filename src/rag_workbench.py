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


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
ASSISTANT_MODES = {"disabled", "local_search_only", "local_gguf", "cloud_api"}


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


class RagWorkbenchService:
    """Offline-first project assistant service.

    The service deliberately avoids external embedding providers so the assistant can run
    in a clean local environment. Retrieval is lexical TF-style scoring; the API contract
    can later swap in vector embeddings without changing the UI workflow.
    """

    ROOT = USER_DATA_DIR / "rag_workbench"
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
                "rag_enabled": True,
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

    @classmethod
    def status(cls) -> Dict[str, Any]:
        state = cls._state()
        docs = state.get("documents", [])
        chunks = state.get("chunks", [])
        indexed_chunks = [chunk for chunk in chunks if chunk.get("index_state") == "indexed"]
        index_state = "ready" if indexed_chunks else "empty"
        if docs and len(indexed_chunks) < len(chunks):
            index_state = "partial"
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
            "agent_run_count": len(state.get("agent_runs", [])),
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
        return {"document": document, "chunks": chunks, "status": cls.status()}

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
    def list_documents(cls) -> Dict[str, Any]:
        state = cls._state()
        return {
            "documents": state.get("documents", []),
            "chunks": state.get("chunks", []),
            "status": cls.status(),
        }

    @classmethod
    def clear_knowledge_base(cls) -> Dict[str, Any]:
        state = cls._state()
        state["documents"] = []
        state["chunks"] = []
        state["bad_retrieval_marks"] = []
        state["workspace"]["index_state"] = "empty"
        if cls.DOCS_DIR.exists():
            for item in cls.DOCS_DIR.iterdir():
                if item.is_file():
                    item.unlink()
        cls._save_state(state)
        return cls.status()

    @classmethod
    def reindex(cls) -> Dict[str, Any]:
        state = cls._state()
        for chunk in state.get("chunks", []):
            chunk["token_index"] = dict(Counter(_tokens(chunk.get("content", ""))))
            chunk["index_state"] = "indexed"
        state["workspace"]["index_state"] = "ready" if state.get("chunks") else "empty"
        cls._save_state(state)
        return cls.status()

    @classmethod
    def retrieve(cls, query: str, top_k: int = 5, profile_id: str = "lexical_default", filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = cls._state()
        query_tokens = Counter(_tokens(query))
        filters = filters or {}
        if not query_tokens:
            return {"query": query, "profile_id": profile_id, "results": [], "diagnostic": {"reason": "empty_query"}}

        scored = []
        for chunk in state.get("chunks", []):
            if filters.get("document_id") and chunk.get("document_id") != filters["document_id"]:
                continue
            if filters.get("project_id") and (chunk.get("metadata") or {}).get("project_id") != filters["project_id"]:
                continue
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
            }
            for item in scored[:safe_top_k]
        ]
        return {
            "query": query,
            "profile_id": profile_id,
            "top_k": safe_top_k,
            "results": results,
            "diagnostic": {
                "query_tokens": list(query_tokens.keys()),
                "candidate_chunks": len(state.get("chunks", [])),
                "matched_chunks": len(scored),
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
                "retrieval_config": {"profile_id": profile_id, "top_k": 0, "filters": filters or {}, "mode": settings["mode"]},
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
        retrieval = cls.retrieve(message, top_k=5, profile_id=profile_id, filters=filters or {})
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
            "retrieval_config": {"profile_id": profile_id, "top_k": 5, "filters": filters or {}},
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
    def list_agent_runs(cls) -> Dict[str, Any]:
        state = cls._state()
        return {"runs": state.get("agent_runs", [])}

    @classmethod
    def get_sandbox(cls) -> Dict[str, Any]:
        sandbox = cls._sandbox()
        files = sandbox.get("files", {})
        return {
            "files": [{"path": path, "size": len(content or ""), "content": content or ""} for path, content in sorted(files.items())],
            "preview_html": cls.build_preview_html(files),
            "updated_at": sandbox.get("updated_at"),
            "policy": {"os_isolation": False, "network": "not_used", "write_scope": "rag_workbench/artifacts"},
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

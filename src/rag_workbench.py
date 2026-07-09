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
    """Offline-first RAG Workbench MVP service.

    The service deliberately avoids external embedding providers so the workbench can run
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
        "index.html": "<!doctype html>\n<html>\n<head><title>RAG Artifact</title></head>\n<body>\n  <main id=\"app\">RAG Workbench artifact preview</main>\n</body>\n</html>\n",
        "css/style.css": "body { font-family: system-ui, sans-serif; margin: 24px; }\n#app { padding: 16px; border: 1px solid #d0d7de; }\n",
        "js/app.js": "document.querySelector('#app')?.setAttribute('data-ready', 'true');\n",
        "README.md": "# RAG Artifact\n\nGenerated inside the local RAG Workbench sandbox.\n",
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
            "schema_version": "rag-workbench.1",
            "workspace": {
                "workspace_id": "local_rag_workspace",
                "title": "Local RAG Workbench",
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
            "bad_retrieval_marks": [],
        }

    @classmethod
    def _state(cls) -> Dict[str, Any]:
        cls.ensure()
        state = _read_json(cls.STATE_PATH, cls._empty_state())
        if not isinstance(state, dict):
            state = cls._empty_state()
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
            "guardrails": {
                "raw_thought_visible": False,
                "conversation_from_dom": False,
                "sandbox_os_isolation": False,
            },
        }

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
        chunks = cls._chunk_document(document_id, safe_name, content or "")
        document = {
            "document_id": document_id,
            "filename": safe_name,
            "path": document_path.as_posix(),
            "size_chars": len(content or ""),
            "chunk_count": len(chunks),
            "metadata": metadata or {},
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
    def _chunk_document(cls, document_id: str, filename: str, content: str, chunk_size: int = 700, overlap: int = 120) -> List[Dict[str, Any]]:
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
    def chat(cls, message: str, conversation_state: Optional[List[Dict[str, Any]]] = None, profile_id: str = "lexical_default") -> Dict[str, Any]:
        start_time = time.perf_counter()
        conversation = cls._clean_conversation(conversation_state or [])
        retrieval = cls.retrieve(message, top_k=5, profile_id=profile_id)
        sources = retrieval["results"]
        steps = [
            cls._agent_step("parse", "done", "Parsed user request."),
            cls._agent_step("retrieve", "done" if sources else "failed", f"Retrieved {len(sources)} source chunk(s)."),
            cls._agent_step("validate", "done" if sources else "failed", "Checked source availability."),
            cls._agent_step("final", "done", "Generated grounded response." if sources else "Generated no-source response."),
        ]
        if sources:
            source_lines = [f"- {item['source']} / {item['section']}: {item['content'][:220]}" for item in sources[:3]]
            answer = "根據目前知識庫，最相關的內容如下：\n" + "\n".join(source_lines)
            failure_type = ""
        else:
            answer = "目前知識庫沒有找到足夠相關的來源。請先匯入文件、重新索引，或調整查詢。"
            failure_type = "no_sources"

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        run = {
            "run_id": _safe_id("rag_run"),
            "query": message,
            "answer": answer,
            "sources": sources,
            "agent_trace": steps,
            "conversation_state": conversation + [
                {"role": "user", "content": message, "meta": {"source": "clean_state"}},
                {"role": "assistant", "content": answer, "meta": {"source_count": len(sources)}},
            ],
            "retrieval_config": {"profile_id": profile_id, "top_k": 5},
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
    def evaluation_report(cls) -> Dict[str, Any]:
        state = cls._state()
        runs = state.get("agent_runs", [])
        total = len(runs)
        source_hits = sum(1 for run in runs if run.get("metrics", {}).get("source_hit"))
        avg_latency = round(sum(float(run.get("metrics", {}).get("latency_ms") or 0) for run in runs) / total, 2) if total else 0
        failures = Counter(run.get("failure_type") or "none" for run in runs)
        report = {
            "report_id": _safe_id("rag_eval"),
            "run_count": total,
            "citation_coverage": round(source_hits / total, 4) if total else 0,
            "source_hit_rate": round(source_hits / total, 4) if total else 0,
            "average_latency_ms": avg_latency,
            "failure_types": dict(failures),
            "created_at": _now(),
        }
        markdown = (
            "# RAG Workbench Evaluation Report\n\n"
            f"- Runs: {report['run_count']}\n"
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

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.rag_workbench import RagWorkbenchService

router = APIRouter()


class RagDocumentRequest(BaseModel):
    filename: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class RagRetrievalRequest(BaseModel):
    query: str
    top_k: int = 5
    profile_id: str = "lexical_default"
    filters: Optional[Dict[str, Any]] = None


class RagRetrievalMarkRequest(BaseModel):
    query: str
    chunk_id: str
    relevance: str
    note: str = ""


class RagChatRequest(BaseModel):
    message: str
    conversation_state: Optional[List[Dict[str, Any]]] = None
    profile_id: str = "lexical_default"


class RagSandboxFileRequest(BaseModel):
    path: str
    content: str


@router.get("/api/rag-workbench/status")
def rag_workbench_status():
    return RagWorkbenchService.status()


@router.get("/api/rag-workbench/knowledge-base")
def rag_knowledge_base():
    return RagWorkbenchService.list_documents()


@router.post("/api/rag-workbench/knowledge-base/documents")
def rag_ingest_document(request: RagDocumentRequest):
    return RagWorkbenchService.ingest_document(
        filename=request.filename,
        content=request.content,
        metadata=request.metadata or {},
    )


@router.post("/api/rag-workbench/knowledge-base/reindex")
def rag_reindex():
    return RagWorkbenchService.reindex()


@router.delete("/api/rag-workbench/knowledge-base")
def rag_clear_knowledge_base():
    return RagWorkbenchService.clear_knowledge_base()


@router.post("/api/rag-workbench/retrieval/query")
def rag_retrieval_query(request: RagRetrievalRequest):
    return RagWorkbenchService.retrieve(
        query=request.query,
        top_k=request.top_k,
        profile_id=request.profile_id,
        filters=request.filters or {},
    )


@router.post("/api/rag-workbench/retrieval/marks")
def rag_mark_retrieval(request: RagRetrievalMarkRequest):
    return RagWorkbenchService.mark_retrieval(
        query=request.query,
        chunk_id=request.chunk_id,
        relevance=request.relevance,
        note=request.note,
    )


@router.post("/api/rag-workbench/chat")
def rag_chat(request: RagChatRequest):
    return RagWorkbenchService.chat(
        message=request.message,
        conversation_state=request.conversation_state or [],
        profile_id=request.profile_id,
    )


@router.get("/api/rag-workbench/agent-runs")
def rag_agent_runs():
    return RagWorkbenchService.list_agent_runs()


@router.get("/api/rag-workbench/sandbox")
def rag_sandbox():
    return RagWorkbenchService.get_sandbox()


@router.post("/api/rag-workbench/sandbox/files")
def rag_update_sandbox_file(request: RagSandboxFileRequest):
    try:
        return RagWorkbenchService.update_sandbox_file(path=request.path, content=request.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/rag-workbench/sandbox/export")
def rag_export_sandbox():
    return RagWorkbenchService.export_sandbox()


@router.post("/api/rag-workbench/evaluation/report")
def rag_evaluation_report():
    return RagWorkbenchService.evaluation_report()


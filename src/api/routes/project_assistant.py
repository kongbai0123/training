from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.project_assistant import ProjectAssistantService

router = APIRouter()


class ProjectAssistantDocumentRequest(BaseModel):
    filename: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class ProjectAssistantRetrievalRequest(BaseModel):
    query: str
    top_k: int = 5
    profile_id: str = "lexical_default"
    filters: Optional[Dict[str, Any]] = None


class ProjectAssistantRetrievalMarkRequest(BaseModel):
    query: str
    chunk_id: str
    relevance: str
    note: str = ""


class ProjectAssistantChatRequest(BaseModel):
    message: str
    conversation_state: Optional[List[Dict[str, Any]]] = None
    profile_id: str = "lexical_default"


class ProjectAssistantSandboxFileRequest(BaseModel):
    path: str
    content: str


class ProjectAssistantGoldenSetRequest(BaseModel):
    items: List[Dict[str, Any]]


class ProjectAssistantSettingsRequest(BaseModel):
    mode: str
    local_model_path: str = ""
    cloud_provider: str = ""
    cloud_model: str = ""
    allow_external_requests: bool = False


def _project_metadata(project_id: str = "", project_name: str = "") -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if project_id:
        metadata["project_id"] = project_id
    if project_name:
        metadata["project_name"] = project_name
    return metadata


@router.get("/api/project-assistant/status")
@router.get("/api/rag-workbench/status")
def project_assistant_status(
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.status(project_id=project_id)


@router.get("/api/project-assistant/settings")
@router.get("/api/rag-workbench/settings")
def project_assistant_settings():
    return ProjectAssistantService.get_settings()


@router.post("/api/project-assistant/settings")
@router.post("/api/rag-workbench/settings")
def update_project_assistant_settings(request: ProjectAssistantSettingsRequest):
    try:
        return ProjectAssistantService.update_settings(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/project-assistant/knowledge-base")
@router.get("/api/rag-workbench/knowledge-base")
def project_assistant_knowledge_base(
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.list_documents(project_id=project_id)


@router.post("/api/project-assistant/knowledge-base/documents")
@router.post("/api/rag-workbench/knowledge-base/documents")
def project_assistant_ingest_document(
    request: ProjectAssistantDocumentRequest,
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
    project_name: str = Query("", description="Active project display name."),
):
    return ProjectAssistantService.ingest_document(
        filename=request.filename,
        content=request.content,
        metadata={**(request.metadata or {}), **_project_metadata(project_id, project_name)},
    )


@router.post("/api/project-assistant/knowledge-base/upload")
@router.post("/api/rag-workbench/knowledge-base/upload")
async def project_assistant_upload_document(
    file: UploadFile = File(...),
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
    project_name: str = Query("", description="Active project display name."),
):
    payload = await file.read()
    return ProjectAssistantService.ingest_file_bytes(
        filename=file.filename or "document.txt",
        payload=payload,
        metadata={"content_type": file.content_type or "", **_project_metadata(project_id, project_name)},
    )


@router.post("/api/project-assistant/knowledge-base/reindex")
@router.post("/api/rag-workbench/knowledge-base/reindex")
def project_assistant_reindex(
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.reindex(project_id=project_id)


@router.delete("/api/project-assistant/knowledge-base")
@router.delete("/api/rag-workbench/knowledge-base")
def project_assistant_clear_knowledge_base(
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.clear_knowledge_base(project_id=project_id)


@router.post("/api/project-assistant/retrieval/query")
@router.post("/api/rag-workbench/retrieval/query")
def project_assistant_retrieval_query(
    request: ProjectAssistantRetrievalRequest,
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    filters = request.filters or {}
    filters = {**filters, "project_id": project_id}
    return ProjectAssistantService.retrieve(
        query=request.query,
        top_k=request.top_k,
        profile_id=request.profile_id,
        filters=filters,
    )


@router.post("/api/project-assistant/retrieval/marks")
@router.post("/api/rag-workbench/retrieval/marks")
def project_assistant_mark_retrieval(request: ProjectAssistantRetrievalMarkRequest):
    return ProjectAssistantService.mark_retrieval(
        query=request.query,
        chunk_id=request.chunk_id,
        relevance=request.relevance,
        note=request.note,
    )


@router.post("/api/project-assistant/chat")
@router.post("/api/rag-workbench/chat")
def project_assistant_chat(
    request: ProjectAssistantChatRequest,
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.chat(
        message=request.message,
        conversation_state=request.conversation_state or [],
        profile_id=request.profile_id,
        filters={"project_id": project_id},
    )


@router.post("/api/project-assistant/chat/stream")
@router.post("/api/rag-workbench/chat/stream")
def project_assistant_chat_stream(
    request: ProjectAssistantChatRequest,
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    events = ProjectAssistantService.chat_stream_events(
        message=request.message,
        conversation_state=request.conversation_state or [],
        profile_id=request.profile_id,
        filters={"project_id": project_id},
    )

    def iter_events():
        for item in events:
            yield f"event: {item['event']}\n"
            yield f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(iter_events(), media_type="text/event-stream")


@router.get("/api/project-assistant/agent-runs")
@router.get("/api/rag-workbench/agent-runs")
def project_assistant_agent_runs(
    project_id: str = Query("", description="Active project id for project-scoped assistant knowledge."),
):
    return ProjectAssistantService.list_agent_runs(project_id=project_id)


@router.get("/api/project-assistant/sandbox")
@router.get("/api/rag-workbench/sandbox")
def project_assistant_sandbox():
    return ProjectAssistantService.get_sandbox()


@router.post("/api/project-assistant/sandbox/files")
@router.post("/api/rag-workbench/sandbox/files")
def project_assistant_update_sandbox_file(request: ProjectAssistantSandboxFileRequest):
    try:
        return ProjectAssistantService.update_sandbox_file(path=request.path, content=request.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/project-assistant/sandbox/export")
@router.post("/api/rag-workbench/sandbox/export")
def project_assistant_export_sandbox():
    return ProjectAssistantService.export_sandbox()


@router.post("/api/project-assistant/evaluation/report")
@router.post("/api/rag-workbench/evaluation/report")
def project_assistant_evaluation_report(request: Optional[ProjectAssistantGoldenSetRequest] = None):
    return ProjectAssistantService.evaluation_report(golden_set=request.items if request else None)


@router.post("/api/project-assistant/evaluation/golden-set")
@router.post("/api/rag-workbench/evaluation/golden-set")
def project_assistant_set_golden_set(request: ProjectAssistantGoldenSetRequest):
    return ProjectAssistantService.set_golden_set(request.items)

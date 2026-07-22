from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.system_downloads import save_bytes_to_downloads


router = APIRouter()
_ALLOWED_TEXT_EXTENSIONS = {".svg", ".csv", ".json", ".md", ".txt"}


class TextDownloadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content: str = Field(max_length=20_000_000)


@router.post("/api/downloads/text")
def save_text_download(request: TextDownloadRequest):
    suffix = request.filename.lower().rsplit(".", 1)
    extension = f".{suffix[-1]}" if len(suffix) > 1 else ""
    if extension not in _ALLOWED_TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported download file type.")
    destination = save_bytes_to_downloads(request.content.encode("utf-8"), request.filename)
    return {"success": True, "filename": destination.name, "saved_path": str(destination)}

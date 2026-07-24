from __future__ import annotations

import os
from pathlib import Path
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.app_paths import UPDATE_DOWNLOADS_DIR
from src.update.service import UPDATE_SERVICE


router = APIRouter()
class UpdateCleanupRequest(BaseModel):
    discard_ready: bool = False
    remove_backup: bool = False


@router.get("/api/updates/status")
def update_status():
    return UPDATE_SERVICE.status()


@router.post("/api/updates/check")
def check_updates():
    return UPDATE_SERVICE.start_check()


@router.post("/api/updates/download")
def download_update():
    try:
        return UPDATE_SERVICE.start_download()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/updates/download-latest")
def download_latest_update():
    try:
        return UPDATE_SERVICE.start_latest_download()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/updates/apply")
def apply_update():
    try:
        return UPDATE_SERVICE.launch_ready_update()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/updates/cleanup")
def cleanup_updates(request: UpdateCleanupRequest):
    return UPDATE_SERVICE.cleanup_storage(
        discard_ready=request.discard_ready,
        remove_backup=request.remove_backup,
    )


@router.post("/api/updates/import")
async def import_update(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".vtsupdate"):
        raise HTTPException(status_code=400, detail="Select a .vtsupdate package.")
    UPDATE_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=filename + ".",
        suffix=".part",
        dir=UPDATE_DOWNLOADS_DIR,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    destination = UPDATE_DOWNLOADS_DIR / filename
    import_budget = UPDATE_SERVICE.import_budget(filename)
    if import_budget <= 0:
        raise HTTPException(status_code=413, detail="The 2 GiB update cache limit is full.")
    total = 0
    try:
        with temporary.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > import_budget:
                    raise HTTPException(
                        status_code=413,
                        detail="The imported package would exceed the 2 GiB update cache limit.",
                    )
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return UPDATE_SERVICE.register_imported_package(destination)
    except HTTPException:
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Update package validation failed: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
        await file.close()

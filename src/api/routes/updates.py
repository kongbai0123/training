from __future__ import annotations

import os
from pathlib import Path
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.app_paths import UPDATE_DOWNLOADS_DIR
from src.update.service import UPDATE_SERVICE


router = APIRouter()
MAX_IMPORTED_UPDATE_BYTES = 1024 * 1024 * 1024


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


@router.post("/api/updates/apply")
def apply_update():
    try:
        return UPDATE_SERVICE.launch_ready_update()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    total = 0
    try:
        with temporary.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_IMPORTED_UPDATE_BYTES:
                    raise HTTPException(status_code=413, detail="Update package exceeds 1 GiB.")
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

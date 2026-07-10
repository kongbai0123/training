from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.app_paths import TMP_DIR
from src.managed_labelme import get_labelme_component_status, install_labelme_component_archive


router = APIRouter()


@router.get("/api/components/labelme")
def get_labelme_component():
    return get_labelme_component_status()


@router.post("/api/components/labelme/install")
def install_labelme_component(
    confirm: bool = Form(False),
    file: UploadFile = File(...),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="LabelMe component installation requires explicit confirmation")
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="LabelMe component must be a ZIP archive")
    upload_dir = TMP_DIR / f"labelme_upload_{uuid.uuid4().hex}"
    upload_dir.mkdir(parents=True, exist_ok=False)
    archive = upload_dir / "labelme-component.zip"
    try:
        with archive.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        try:
            return install_labelme_component_archive(archive)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)

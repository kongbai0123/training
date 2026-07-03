from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from src.api.dependencies import require_api_token
from src.diagnostics import generate_diagnostics_zip


router = APIRouter()


@router.get("/api/diagnostics/report")
def export_diagnostics_report(_token=Depends(require_api_token)):
    report_path = generate_diagnostics_zip()
    return FileResponse(str(report_path), filename=report_path.name, media_type="application/zip")

import mimetypes

# MIME helper for browser static assets on Windows
mimetypes.add_type("application/javascript", ".js", strict=True)
mimetypes.add_type("text/css", ".css", strict=True)

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import APP_ENV, STATIC_DIR
from src.local_session import validate_token
from src.api.dependencies import build_error as _build_error
from src.api.dependencies import normalize_error_response as _normalize_error_response
from src.api.routes.diagnostics import router as diagnostics_router
from src.api.routes.dataset_split import router as dataset_split_router
from src.api.routes.datasets import router as datasets_router
from src.api.routes.evaluation import router as evaluation_router
from src.api.routes.annotation_labelme import router as annotation_labelme_router
from src.api.routes.augmentation import router as augmentation_router
from src.api.routes.auto_labeling import router as auto_labeling_router
from src.api.routes.inference import router as inference_router
from src.api.routes.models import router as models_router
from src.api.routes.components import router as components_router
from src.api.routes.monitor import router as monitor_router
from src.api.routes.project_layout import router as project_layout_router
from src.api.routes.project_assistant import router as project_assistant_router
from src.api.routes.rnn_config import router as rnn_config_router
from src.api.routes.projects import router as projects_router
from src.api.routes.system import router as system_router
from src.api.routes.training_orchestration import router as training_orchestration_router
from src.api.routes.training_recommendation import router as training_recommendation_router
from src.api.routes.training_runs import router as training_runs_router

APP_IS_PRODUCTION = APP_ENV in {"production", "prod"}
app = FastAPI(title="Vision Training Studio API")
app.include_router(system_router)
app.include_router(diagnostics_router)
app.include_router(project_layout_router)
app.include_router(project_assistant_router)
app.include_router(projects_router)
app.include_router(rnn_config_router)
app.include_router(models_router)
app.include_router(components_router)
app.include_router(training_runs_router)
app.include_router(training_orchestration_router)
app.include_router(training_recommendation_router)
app.include_router(monitor_router)
app.include_router(inference_router)
app.include_router(datasets_router)
app.include_router(dataset_split_router)
app.include_router(evaluation_router)
app.include_router(annotation_labelme_router)
app.include_router(auto_labeling_router)
app.include_router(augmentation_router)

if APP_IS_PRODUCTION:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Local API error response handlers.

@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=_normalize_error_response(exc.detail, status_code=exc.status_code),
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
                "suggestion": "Check the request payload fields and retry.",
                "retryable": False,
                "field_errors": {},
                "severity": "error",
                "status": 422,
            }
        }
    )

@app.exception_handler(Exception)
def general_exception_handler(request, exc):
    if APP_IS_PRODUCTION:
        return JSONResponse(status_code=500, content=_build_error("INTERNAL_SERVER_ERROR", "Server error", 500))
    return JSONResponse(
        status_code=500,
        content=_build_error("INTERNAL_SERVER_ERROR", str(exc), 500),
    )


@app.middleware("http")
async def protect_mutating_api(request: Request, call_next):
    if not APP_IS_PRODUCTION:
        return await call_next(request)

    method = request.method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)

    if path.startswith("/api/health") or path.startswith("/api/bootstrap") or path.startswith("/api/version"):
        return await call_next(request)

    token = request.headers.get("X-VTS-Token") or request.headers.get("x-vts-token")
    if not validate_token(token or ""):
        return JSONResponse(
            status_code=401,
            content=_build_error("AUTH_REQUIRED", "Missing or invalid local session token", 401),
        )

    return await call_next(request)


@app.middleware("http")
async def prevent_frontend_asset_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path or ""
    if path in {"/", "/index.html"} or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response



# Static frontend files.
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static")

# Serve the application shell.
@app.get("/")
def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return {"message": "Vision Training Studio backend is running. static/index.html not found."}
    return FileResponse(str(index_path))

if __name__ == "__main__":
    import uvicorn
    print("Starting Vision Training Studio Server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)


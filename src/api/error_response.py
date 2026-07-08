from typing import Any, Dict, Mapping, Optional


DEFAULT_SUGGESTIONS = {
    "AUTH_REQUIRED": "Restart the app or refresh the browser session, then retry the action.",
    "VALIDATION_ERROR": "Check the highlighted input values and submit again.",
    "PROJECT_NOT_OPEN": "Open or create a project before running this action.",
    "DATASET_MISSING": "Import images or a dataset ZIP before continuing.",
    "SPLIT_NOT_READY": "Create a train / validation / test split before training.",
    "MODEL_NOT_FOUND": "Select an available model or import a valid model package.",
    "MODEL_TASK_MISMATCH": "Choose a model that matches the project task type.",
    "TRAINING_ALREADY_RUNNING": "Wait for the active run to finish, stop it, or abort it before starting another run.",
    "BACKEND_UNAVAILABLE": "Check the local runtime dependencies and retry after the backend is healthy.",
    "INTERNAL_SERVER_ERROR": "Check logs and retry after fixing the backend error.",
}


def build_error(
    code: str,
    message: Any,
    status_code: int = 500,
    *,
    details: Any = None,
    suggestion: str = "",
    retryable: bool = False,
    field_errors: Optional[Mapping[str, Any]] = None,
    severity: str = "error",
) -> Dict[str, Any]:
    normalized_code = str(code or "API_ERROR").strip().upper()
    safe_message = str(message or "Request failed")
    return {
        "success": False,
        "error": {
            "code": normalized_code,
            "message": safe_message,
            "details": details if details is not None else {},
            "suggestion": suggestion or DEFAULT_SUGGESTIONS.get(normalized_code, ""),
            "retryable": bool(retryable),
            "field_errors": dict(field_errors or {}),
            "severity": severity or "error",
            "status": int(status_code or 500),
        },
    }


def normalize_error_response(content: Any, *, status_code: int = 500, fallback_code: str = "API_ERROR") -> Dict[str, Any]:
    if isinstance(content, Mapping):
        if content.get("success") is False and isinstance(content.get("error"), Mapping):
            error = dict(content["error"])
            return build_error(
                error.get("code") or fallback_code,
                error.get("message") or "Request failed",
                status_code=error.get("status") or status_code,
                details=error.get("details") if "details" in error else {},
                suggestion=error.get("suggestion") or "",
                retryable=bool(error.get("retryable")),
                field_errors=error.get("field_errors") or {},
                severity=error.get("severity") or "error",
            )
        if isinstance(content.get("error"), Mapping):
            error = dict(content["error"])
            return build_error(
                error.get("code") or fallback_code,
                error.get("message") or content.get("message") or "Request failed",
                status_code=status_code,
                details=error.get("details") if "details" in error else {},
                suggestion=error.get("suggestion") or "",
                retryable=bool(error.get("retryable")),
                field_errors=error.get("field_errors") or {},
                severity=error.get("severity") or "error",
            )
        if "detail" in content:
            return normalize_error_response(content["detail"], status_code=status_code, fallback_code=fallback_code)
        return build_error(
            content.get("code") or fallback_code,
            content.get("message") or "Request failed",
            status_code=status_code,
            details=content.get("details") if "details" in content else content,
            suggestion=content.get("suggestion") or "",
            retryable=bool(content.get("retryable")),
            field_errors=content.get("field_errors") or {},
            severity=content.get("severity") or "error",
        )

    return build_error(fallback_code, content or f"HTTP {status_code}", status_code=status_code)

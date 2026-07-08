from fastapi import Header, HTTPException

from src.config import APP_ENV
from src.api.error_response import build_error as build_structured_error
from src.api.error_response import normalize_error_response
from src.local_session import validate_token


APP_IS_PRODUCTION = APP_ENV in {"production", "prod"}


def build_error(code: str, message, status_code: int = 500):
    safe_message = message if not APP_IS_PRODUCTION else "Server error" if status_code >= 500 else message
    return build_structured_error(code, safe_message, status_code)


def require_api_token(token: str = Header(default="", alias="X-VTS-Token")) -> None:
    if not validate_token(token):
        raise HTTPException(
            status_code=401,
            detail=build_error("AUTH_REQUIRED", "Missing or invalid local session token", 401),
        )

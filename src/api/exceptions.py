from typing import Any, Mapping, Optional


class VtsApiException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Any = None,
        suggestion: str = "",
        retryable: bool = False,
        field_errors: Optional[Mapping[str, Any]] = None,
        severity: str = "error",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details if details is not None else {}
        self.suggestion = suggestion
        self.retryable = retryable
        self.field_errors = dict(field_errors or {})
        self.severity = severity

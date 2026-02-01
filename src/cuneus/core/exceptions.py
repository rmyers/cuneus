"""
Exception handling with consistent API responses.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .extensions import BaseExtension
from .settings import Settings

log = structlog.get_logger()


class ErrorDetails(BaseModel):
    status: int
    code: str
    message: str
    request_id: str | None = None
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetails


class AppException(Exception):
    """
    Base exception for application errors.

    Subclass this for domain-specific errors.
    """

    status_code: int = 500
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self, request_id: str | None = None) -> ErrorResponse:
        error_detail = ErrorDetails(
            status=self.status_code,
            code=self.error_code,
            message=self.message,
            request_id=request_id,
            details=self.details,
        )
        return ErrorResponse(error=error_detail)


# === Common HTTP Exceptions ===


class BadRequest(AppException):
    status_code = 400
    error_code = "bad_request"
    message = "Invalid request"


class Unauthorized(AppException):
    status_code = 401
    error_code = "unauthorized"
    message = "Authentication required"


class Forbidden(AppException):
    status_code = 403
    error_code = "forbidden"
    message = "Access denied"


class NotFound(AppException):
    status_code = 404
    error_code = "not_found"
    message = "Resource not found"


class Conflict(AppException):
    status_code = 409
    error_code = "conflict"
    message = "Resource conflict"


class RateLimited(AppException):
    status_code = 429
    error_code = "rate_limited"
    message = "Too many requests"

    def __init__(self, retry_after: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retry_after = retry_after


class ServiceUnavailable(AppException):
    status_code = 503
    error_code = "service_unavailable"
    message = "Service temporarily unavailable"


# === Infrastructure Exceptions ===


class DatabaseError(AppException):
    status_code = 503
    error_code = "database_error"
    message = "Database operation failed"


class RedisError(AppException):
    status_code = 503
    error_code = "cache_error"
    message = "Cache operation failed"


class ExternalServiceError(AppException):
    status_code = 502
    error_code = "external_service_error"
    message = "External service request failed"


def error_responses(*excptions: AppException) -> dict[int, dict[str, Any]]:
    responses: dict[int, dict[str, Any]] = {}
    for exception in excptions:
        responses[exception.status_code] = {
            "model": ErrorResponse,
            "description": exception.message,
        }
    return responses


class ExceptionExtension(BaseExtension):
    """
    Exception handling extension.

    Catches AppException subclasses and converts to JSON responses.
    Catches unexpected exceptions and returns generic 500s.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def add_exception_handler(self, app: FastAPI) -> None:
        app.add_exception_handler(AppException, self._handle_app_exception)  # type: ignore[arg-type]
        app.add_exception_handler(Exception, self._handle_unexpected_exception)

    def _handle_app_exception(
        self, request: Request, exc: AppException
    ) -> JSONResponse:
        if exc.status_code >= 500 and self.settings.log_server_errors:
            log.exception("server_error", error_code=exc.error_code)
        else:
            log.warning("client_error", error_code=exc.error_code, message=exc.message)

        response = exc.to_response(getattr(request.state, "request_id", None))

        headers = {}
        if isinstance(exc, RateLimited) and exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(exclude_none=True, mode="json"),
            headers=headers,
        )

    def _handle_unexpected_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        log.exception("unexpected_error", exc_info=exc)
        response: dict[str, Any] = {
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        }

        if hasattr(request.state, "request_id"):  # pragma: no branch
            response["error"]["request_id"] = request.state.request_id

        if self.settings.debug:
            response["error"]["details"] = {
                "exception": type(exc).__name__,
                "message": str(exc),
            }

        return JSONResponse(status_code=500, content=response)

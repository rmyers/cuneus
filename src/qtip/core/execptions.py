"""
Exception handling with consistent API responses.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qtip.core.application import Extension

logger = logging.getLogger(__name__)


# === Base Exceptions ===


class AppException(Exception):
    """
    Base exception for application errors.

    Subclass this for domain-specific errors that should
    return structured API responses.
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

    def to_response(self) -> dict[str, Any]:
        """Convert to API response body."""
        response: dict[str, dict[str, Any]] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }
        if self.details:
            response["error"]["details"] = self.details
        return response


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

    def __init__(self, retry_after: int | None = None, **kwargs):
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


# === Exception Handler Extension ===


class ExceptionExtension(Extension):
    """
    Extension that adds consistent exception handling.

    Settings:
        debug_errors: bool = False  - Include stack traces in responses
        log_server_errors: bool = True - Log tracebacks for 5xx

    Catches AppException subclasses and converts to JSON responses.
    Catches unexpected exceptions and returns generic 500s.
    """

    name = "exceptions"
    settings_keys = ["debug_errors", "log_server_errors"]

    async def startup(self, app: FastAPI) -> None:
        app.add_exception_handler(AppException, self._handle_app_exception)  # type: ignore[arg-type]
        app.add_exception_handler(Exception, self._handle_unexpected_exception)

    async def _handle_app_exception(
        self, request: Request, exc: AppException
    ) -> JSONResponse:
        """Handle known application exceptions."""
        log_server_errors = self.get_setting("log_server_errors", True)

        if exc.status_code >= 500 and log_server_errors:
            logger.exception(f"Server error: {exc.error_code}", exc_info=exc)
        else:
            logger.warning(f"Client error: {exc.error_code} - {exc.message}")

        response = exc.to_response()

        if hasattr(request.state, "request_id"):
            response["error"]["request_id"] = request.state.request_id

        headers = {}
        if isinstance(exc, RateLimited) and exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            content=response,
            headers=headers,
        )

    async def _handle_unexpected_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception("Unexpected error", exc_info=exc)

        response: dict[str, Any] = {
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        }

        if hasattr(request.state, "request_id"):
            response["error"]["request_id"] = request.state.request_id

        debug_errors = self.get_setting("debug_errors", False)
        if debug_errors:
            response["error"]["details"] = {
                "exception": type(exc).__name__,
                "message": str(exc),
            }

        return JSONResponse(status_code=500, content=response)

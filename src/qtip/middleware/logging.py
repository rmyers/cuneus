"""
Logging configuration using starlette-context for request IDs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from qtip.core.application import Application, Settings

logger = logging.getLogger(__name__)


class LoggingSettings(Settings):
    """Settings for logging configuration."""

    log_level: str = "INFO"
    log_format: str = "%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s"
    log_requests: bool = True


class RequestContextFilter(logging.Filter):
    """Logging filter that injects request_id from starlette-context."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = context.get(HeaderKeys.request_id, "-")
        except Exception:
            record.request_id = "-"
        return True


def configure_logging(app: Application, settings: LoggingSettings) -> None:
    """
    Configure logging with request context.

    Uses starlette-context (already added by Application) for request IDs.
    Adds request/response logging middleware if enabled.

    Usage:
        from qtip.middleware.logging import configure_logging, LoggingSettings

        configure_logging(app, settings)
    """

    # Configure root logger
    logging.basicConfig(
        level=settings.log_level,
        format=settings.log_format,
    )

    # Add context filter to root logger
    root_logger = logging.getLogger()
    root_logger.addFilter(RequestContextFilter())

    # Add request logging middleware if enabled
    if settings.log_requests:
        app.add_middleware(Middleware(RequestLoggingMiddleware))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs requests and responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        # Get request ID from starlette-context
        request_id = context.get(HeaderKeys.request_id, "-")

        logger.info(f"{request.method} {request.url.path} started")

        try:
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"{request.method} {request.url.path} "
                f"completed {response.status_code} in {duration_ms:.1f}ms"
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                f"{request.method} {request.url.path} "
                f"failed after {duration_ms:.1f}ms: {e}"
            )
            raise


# === Convenience functions ===


def get_request_id() -> str:
    """Get current request ID from context."""
    try:
        return context.get(HeaderKeys.request_id, "-")
    except Exception:
        return "-"


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    try:
        return context.get(HeaderKeys.correlation_id, "-")
    except Exception:
        return "-"

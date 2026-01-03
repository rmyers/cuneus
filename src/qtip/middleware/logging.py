"""
Structured logging with structlog and request context.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware

from qtip.core.application import Application, Settings


class LoggingSettings(Settings):
    """Settings for logging configuration."""

    log_level: str = "INFO"
    log_json: bool = False  # Set True for production
    log_requests: bool = True


def configure_logging(app: Application, settings: LoggingSettings) -> None:
    """
    Configure structured logging with structlog.

    Uses structlog.contextvars for request-scoped context (request_id, etc).

    Usage:
        from qtip.middleware.logging import configure_logging, LoggingSettings, get_logger

        configure_logging(app, settings)

        # In your code:
        log = get_logger()
        log.info("something happened", user_id=123)
    """

    # Shared processors for all output
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if settings.log_json:
        # JSON output for production
        processors = shared_processors + [
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(settings.log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Add request logging middleware if enabled
    if settings.log_requests:
        app.add_middleware(Middleware(RequestLoggingMiddleware))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Generates request_id
    - Binds it to structlog context
    - Logs request start/end
    - Adds request_id to response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]

        # Clear any previous context and bind request info
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # Also store on request.state for access in routes
        request.state.request_id = request_id

        log = structlog.get_logger()
        start_time = time.perf_counter()

        log.info("request_started")

        try:
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            log.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log.exception(
                "request_failed",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()


# === Public API ===


def get_logger(**initial_context: Any) -> structlog.stdlib.BoundLogger:
    """
    Get a logger with optional initial context.

    Usage:
        log = get_logger()
        log.info("user logged in", user_id=123)

        # Or with initial context
        log = get_logger(service="payment")
        log.info("charge created", amount=100)
    """
    log = structlog.get_logger()
    if initial_context:
        log = log.bind(**initial_context)
    return log


def bind_contextvars(**context: Any) -> None:
    """
    Bind additional context that will appear in all subsequent logs.

    Useful for adding user_id after authentication, etc.

    Usage:
        # In auth middleware or dependency
        bind_contextvars(user_id=current_user.id, tenant="acme")
    """
    structlog.contextvars.bind_contextvars(**context)


def get_request_id(request: Request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, "request_id", "-")

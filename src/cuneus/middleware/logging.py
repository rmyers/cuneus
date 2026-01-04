"""
Structured logging with structlog and request context.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator

import structlog
import svcs
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from cuneus.core.application import BaseExtension, Settings


class LoggingExtension(BaseExtension):
    """
    Structured logging extension using structlog.

    Integrates with stdlib logging so uvicorn and other libraries
    also output through structlog.

    Usage:
        from qtip import build_app
        from qtip.middleware.logging import LoggingExtension, LoggingSettings

        app = build_app(
            settings,
            extensions=[LoggingExtension(settings)],
        )
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._configure_structlog()

    def _configure_structlog(self) -> None:
        settings = self.settings

        # Shared processors
        shared_processors: list[structlog.types.Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]

        if settings.log_json:
            renderer = structlog.processors.JSONRenderer()
        else:
            renderer = structlog.dev.ConsoleRenderer(colors=True)

        # Configure structlog
        structlog.configure(
            processors=shared_processors
            + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Create formatter for stdlib
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )

        # Configure root logger
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(settings.log_level.upper())

        # Quiet noisy loggers
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    async def startup(self, registry: svcs.Registry, app: FastAPI) -> dict[str, Any]:
        # app.add_middleware(RequestLoggingMiddleware)
        return {}


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Generates request_id
    - Binds it to structlog context
    - Logs request start/end
    - Adds request_id to response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        request.state.request_id = request_id

        log = structlog.get_logger()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            log.info(
                f"{request.method} {request.url.path} {response.status_code}",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception:
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
    """
    log = structlog.get_logger()
    if initial_context:
        log = log.bind(**initial_context)
    return log


def bind_contextvars(**context: Any) -> None:
    """
    Bind additional context that will appear in all subsequent logs.
    """
    structlog.contextvars.bind_contextvars(**context)


def get_request_id(request: Request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, "request_id", "-")

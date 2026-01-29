"""
Structured logging with structlog and request context.
"""

from __future__ import annotations

from contextvars import ContextVar
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, MutableMapping

import structlog
import svcs
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Scope, Send, Receive

from .extensions import BaseExtension
from .settings import Settings


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

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
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

        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
        if settings.log_json:
            renderer = structlog.processors.JSONRenderer()

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

    def middleware(self) -> list[Middleware]:
        return [
            Middleware(
                LoggingMiddleware,
                header_name=self.settings.request_id_header,
            ),
        ]


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Generates request_id
    - Binds it to structlog context
    - Logs request start/end
    - Adds request_id to response headers
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.header_name = header_name
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())[:8]

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

            response.headers[self.header_name] = request_id
            return response

        except Exception:
            raise
        finally:
            structlog.contextvars.clear_contextvars()


# Used by httpx for request ID propagation
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(
            self.header_name.lower().encode(), str(uuid.uuid4())[:8].encode()
        ).decode()

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Set contextvar for use in HTTP clients
        token = request_id_ctx.set(request_id)

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.header_name.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


# === Public API ===


def get_logger(**initial_context: Any) -> structlog.stdlib.BoundLogger:
    """
    Get a logger with optional initial context.

    Usage:
        log = get_logger()
        log.info("user logged in", user_id=123)
    """
    log = structlog.stdlib.get_logger()
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

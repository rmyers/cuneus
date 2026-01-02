"""
Request logging middleware with context propagation.

Optional settings:
    log_level: str = "INFO"
    log_format: str = "%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s"
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from qtip.core.application import Extension, SettingsProtocol

# Context variable for request ID - accessible anywhere in async context
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger(__name__)


class RequestContextFilter(logging.Filter):
    """Logging filter that injects request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class LoggingExtension(Extension):
    """
    Logging extension with request context.

    Auto-included by wrap_app() unless logging_enabled=False.

    Settings:
        log_level: str = "INFO"
        log_format: str = "%(asctime)s [%(request_id)s] ..."

    Adds to request.state:
        - request_id: str
    """

    name = "logging"
    settings_keys = ["log_level", "log_format"]

    DEFAULT_FORMAT = "%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s"

    async def startup(self, app: FastAPI) -> None:
        log_level = self.get_setting("log_level", "INFO")
        log_format = self.get_setting("log_format", self.DEFAULT_FORMAT)

        logging.basicConfig(level=log_level, format=log_format)

        root_logger = logging.getLogger()
        root_logger.addFilter(RequestContextFilter())

    def middleware(self) -> list[Middleware]:
        return [Middleware(RequestLoggingMiddleware)]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs requests and sets request ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4())[:8])

        request_id_ctx.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        logger.info(f"{request.method} {request.url.path} started")

        try:
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"{request.method} {request.url.path} "
                f"completed {response.status_code} in {duration_ms:.1f}ms"
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                f"{request.method} {request.url.path} "
                f"failed after {duration_ms:.1f}ms: {e}"
            )
            raise
        finally:
            request_id_ctx.set(None)


# Accessors
def get_request_id(request: Request) -> str:
    """Get the current request ID."""
    return request.state.request_id


def current_request_id() -> str | None:
    """Get request ID from context (works anywhere in async context)."""
    return request_id_ctx.get()

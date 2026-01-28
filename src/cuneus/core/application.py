"""
cuneus - The wedge stone that locks the arch together.

Lightweight lifespan management for FastAPI applications.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncContextManager, AsyncIterator, Protocol, runtime_checkable

import svcs
from fastapi import FastAPI, Request, middleware
from starlette.types import ASGIApp
from starlette.middleware import Middleware

from .settings import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class Extension(Protocol):
    """
    Protocol for extensions that hook into app lifecycle.

    Extensions can:
    - Register services with svcs
    - Add routes via app.include_router()
    - Add exception handlers via app.add_exception_handler()
    - Return state to merge into lifespan state
    """

    def register(
        self, registry: svcs.Registry, app: FastAPI
    ) -> AsyncContextManager[dict[str, Any]]:
        """
        Async context manager for lifecycle.

        - Enter: startup (register services, add routes, etc.)
        - Yield: dict of state to merge into lifespan state
        - Exit: shutdown (cleanup resources)
        """
        ...

    def middleware(self) -> list[Middleware]:
        """Return a list of middleware required by this Extension."""
        ...


class BaseExtension:
    """
    Base class for extensions with explicit startup/shutdown hooks.

    For simple extensions, override startup() and shutdown().
    For full control, override register() directly.
    """

    async def startup(self, registry: svcs.Registry, app: FastAPI) -> dict[str, Any]:
        """
        Override to setup resources during app startup.

        You can call app.include_router(), app.add_exception_handler(), etc.
        Returns a dict of state to merge into lifespan state.
        """
        return {}

    async def shutdown(self, app: FastAPI) -> None:
        """Override to cleanup resources during app shutdown."""
        pass

    def middleware(self) -> list[Middleware]:
        return []

    @asynccontextmanager
    async def register(
        self, registry: svcs.Registry, app: FastAPI
    ) -> AsyncIterator[dict[str, Any]]:
        """Wraps startup/shutdown into async context manager."""
        state = await self.startup(registry, app)
        try:
            yield state
        finally:
            await self.shutdown(app)


def build_app(
    *extensions: Extension,
    settings: Settings = Settings(),
    **fastapi_kwargs,
) -> tuple[FastAPI, Any]:
    """
    Build a FastAPI with extensions preconfigured.

    The returned lifespan has a `.registry` attribute for testing overrides.

    Usage:
        from cuneus import build_app, Settings, SettingsExtension
        from myapp.extensions import DatabaseExtension

        settings = Settings()
        app = build_app(
            SettingsExtension(settings),
            DatabaseExtension(settings),
            title="Args are passed to FastAPI",
        )

        app = FastAPI(lifespan=lifespan, title="My App")

    Testing:
        from myapp import app, lifespan

        def test_with_mock_db(client):
            mock_db = Mock(spec=Database)
            lifespan.registry.register_value(Database, mock_db)
    """
    if "lifespan" in fastapi_kwargs:
        raise AttributeError("cannot set lifespan with build_app")

    middleware = [
        # Always add the request id middleware as the first
        Middleware(RequestIDMiddleware, header_name=settings.request_id_header),
    ]

    @svcs.fastapi.lifespan
    @asynccontextmanager
    async def lifespan(
        app: FastAPI, registry: svcs.Registry
    ) -> AsyncIterator[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            state: dict[str, Any] = {}

            for ext in extensions:
                ext_state = await stack.enter_async_context(ext.register(registry, app))
                if ext_state:
                    if overlap := state.keys() & ext_state.keys():
                        raise ValueError(f"Extension state key collision: {overlap}")
                    state.update(ext_state)

            yield state

    app = FastAPI(**fastapi_kwargs, lifespan=lifespan)


class RequestIDMiddleware:
    """
    Middleware that adds a unique request_id to each request.

    Access via request.state.request_id
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check for existing request ID in headers, or generate new one
        headers = dict(scope.get("headers", []))
        request_id = headers.get(
            self.header_name.lower().encode(), str(uuid.uuid4())[:8].encode()
        ).decode()

        # Store in scope state
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Add request ID to response headers
        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.header_name.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def get_settings(request: Request) -> Settings:
    """Get settings from request state."""
    return request.state.settings


def get_request_id(request: Request) -> str:
    """Get the request ID from request state."""
    return request.state.request_id

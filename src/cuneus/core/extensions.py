from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    Protocol,
    runtime_checkable,
)

import svcs
from click import Group
from fastapi import FastAPI
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

    def __init__(self, settings: Settings | None = None) -> None: ...

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


@runtime_checkable
class HasMiddleware(Protocol):
    """Extension that provides middleware."""

    def middleware(self) -> list[Middleware]: ...


@runtime_checkable
class HasCLI(Protocol):
    """Extension that provides CLI commands."""

    def register_cli(self, cli_group: Group) -> None: ...


class BaseExtension:
    """
    Base class for extensions with explicit startup/shutdown hooks.

    For simple extensions, override startup() and shutdown().
    For full control, override register() directly.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

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

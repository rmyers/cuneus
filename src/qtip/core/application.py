"""
Core application factory built on svcs.
"""

from __future__ import annotations

import logging
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, TypeVar

import svcs
from fastapi import FastAPI, Request
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware import Middleware

if TYPE_CHECKING:
    from collections.abc import Sequence
    from starlette.routing import BaseRoute

logger = logging.getLogger(__name__)

T = TypeVar("T")
DEFAULT_TOOL_NAME = "qtip"


def load_pyproject_config(
    tool_name: str = DEFAULT_TOOL_NAME,
    path: Path | None = None,
) -> dict[str, Any]:
    """Load configuration from pyproject.toml under [tool.{tool_name}]."""
    if path is None:
        path = Path.cwd()

    for parent in [path, *path.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            return data.get("tool", {}).get(tool_name, {})

    return {}


class Settings(BaseSettings):
    """
    Base settings that loads from:
    1. pyproject.toml [tool.qtip] (lowest priority)
    2. .env file
    3. Environment variables (highest priority)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "app"
    app_module: str = "app.main:app"
    debug: bool = False
    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def load_from_pyproject(cls, data: dict[str, Any]) -> dict[str, Any]:
        pyproject_config = load_pyproject_config()
        return {**pyproject_config, **data}


class Application:
    """
    Application factory that wires FastAPI with svcs.

    Usage:
        settings = MySettings()
        app = Application(settings)

        # Register services with svcs
        app.register_factory(Database, create_database)
        app.register_factory(Redis, create_redis)

        fastapi_app = app.build()
    """

    def __init__(
        self,
        settings: Settings,
        *,
        title: str | None = None,
        version: str = "0.1.0",
        routes: Sequence[BaseRoute] | None = None,
    ) -> None:
        self.settings = settings
        self.title = title or settings.app_name
        self.version = version
        self.routes = list(routes) if routes else []
        self._registry = svcs.Registry()
        self._on_startup: list[Callable[[svcs.Registry], AsyncIterator[None]]] = []
        self._extra_middleware: list[Middleware] = []
        self._exception_handlers: dict[Any, Any] = {}
        self._routers: list[tuple[Any, str]] = []  # (router, prefix)

    def register_factory(
        self,
        svc_type: type[T],
        factory: Callable[..., T] | Callable[..., AsyncIterator[T]],
        *,
        ping: Callable[..., None] | None = None,
    ) -> None:
        """
        Register a service factory with svcs.

        The factory can be sync/async and can be a context manager for cleanup.
        """
        self._registry.register_factory(svc_type, factory, ping=ping)

    def register_value(self, svc_type: type[T], value: T) -> None:
        """Register a concrete value."""
        self._registry.register_value(svc_type, value)

    def add_middleware(self, middleware: Middleware) -> None:
        """Add custom middleware."""
        self._extra_middleware.append(middleware)

    def include_router(self, router: Any, *, prefix: str = "") -> None:
        """Add a router to be included when the app is built."""
        self._routers.append((router, prefix))

    def on_startup(
        self, func: Callable[[svcs.Registry], AsyncIterator[None]]
    ) -> Callable[[svcs.Registry], AsyncIterator[None]]:
        """
        Decorator to register startup/shutdown logic.

        @app.on_startup
        async def setup_something(registry: svcs.Registry):
            # startup code
            yield
            # shutdown code
        """
        self._on_startup.append(func)
        return func

    def _build_lifespan(self):
        registry = self._registry
        settings = self.settings
        startup_hooks = self._on_startup

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, Any]]:
            # Run custom startup hooks (they register services on the registry)
            cleanup_stack = []
            for hook in startup_hooks:
                gen = hook(registry)
                await gen.__anext__()
                cleanup_stack.append(gen)

            # Yield state with registry for svcs middleware
            yield {
                "svcs_registry": registry,
                "settings": settings,
            }

            # Cleanup in reverse order
            for gen in reversed(cleanup_stack):
                try:
                    await gen.__anext__()
                except StopAsyncIteration:
                    pass

            # Close the registry
            await registry.aclose()

        return lifespan

    def _collect_middleware(self) -> list[Middleware]:
        middleware = [
            # svcs container middleware
            Middleware(svcs.starlette.SVCSMiddleware),
        ]
        middleware.extend(self._extra_middleware)
        return middleware

    def build(self) -> FastAPI:
        """Build and return the configured FastAPI application."""
        app = FastAPI(
            title=self.title,
            version=self.version,
            debug=self.settings.debug,
            lifespan=self._build_lifespan(),
            middleware=self._collect_middleware(),
            routes=self.routes or None,
        )

        # Include registered routers
        for router, prefix in self._routers:
            app.include_router(router, prefix=prefix)

        # Register exception handlers if configured
        if hasattr(self, "_exception_handlers"):
            for exc_class, handler in self._exception_handlers.items():
                app.add_exception_handler(exc_class, handler)

        # Store references
        app.state.settings = self.settings
        app.state._application = self

        return app


# === Typed accessors using svcs ===


async def aget(request: Request, *svc_types: type) -> Any:
    """Get services from the request's svcs container."""
    return await svcs.fastapi.aget(request, *svc_types)  # type: ignore


def get(request: Request, *svc_types: type) -> Any:
    """Get sync services from the request's svcs container."""
    container = svcs.starlette.svcs_from(request)
    return container.get(*svc_types)


def get_settings(request: Request) -> Settings:
    """Get settings from request state."""
    return request.state.settings

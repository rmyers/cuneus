"""
Core application factory and base classes.
"""

from __future__ import annotations

import logging
import tomllib
from contextlib import asynccontextmanager, AbstractAsyncContextManager
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    TypeVar,
    Protocol,
    runtime_checkable,
)

from fastapi import FastAPI, Request
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from starlette.middleware import Middleware

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_TOOL_NAME = "qtip"


@runtime_checkable
class SettingsProtocol(Protocol):
    """Protocol for settings objects. Any object with attribute access works."""

    def __getattr__(self, name: str) -> Any: ...


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
    Optional pydantic-settings base class that loads from:
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

    # Built-in extension toggles
    logging_enabled: bool = True
    exception_handler_enabled: bool = True
    health_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def load_from_pyproject(cls, data: dict[str, Any]) -> dict[str, Any]:
        pyproject_config = load_pyproject_config()
        return {**pyproject_config, **data}


class Extension:
    """
    Base class for extensions that hook into app lifecycle.

    Extensions can be passed as classes or instances to wrap_app().
    If passed as a class, it will be instantiated with settings.
    """

    name: str = "extension"
    settings_keys: list[str] = []

    def __init__(self, settings: SettingsProtocol) -> None:
        self.settings = settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value, with optional default."""
        return getattr(self.settings, key, default)

    def require_setting(self, key: str) -> Any:
        """Get a setting value, raising if not present."""
        try:
            value = getattr(self.settings, key)
            if value is None:
                raise AttributeError
            return value
        except AttributeError:
            raise ValueError(
                f"Extension '{self.name}' requires setting '{key}'. "
                f"Add '{key}' to your settings."
            ) from None

    async def startup(self, app: FastAPI) -> None:
        """Called during app startup."""
        pass

    async def shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""
        pass

    def middleware(self) -> list[Middleware]:
        """Return middleware to add to the app."""
        return []


def wrap_app(
    app: FastAPI,
    settings: SettingsProtocol,
    extensions: list[type[Extension] | Extension] | None = None,
) -> FastAPI:
    """
    Wrap a FastAPI application with qtip extensions.

    Built-in extensions (logging, exceptions, health) are always included
    unless disabled via settings. User extensions are added after.

    Usage:
        from fastapi import FastAPI
        from qtip import wrap_app, Settings
        from qtip.ext.database import DatabaseExtension
        from qtip.ext.redis import RedisExtension

        app = FastAPI(title="My App")

        @app.get("/hello")
        def hello():
            return {"message": "world"}

        settings = Settings()
        app = wrap_app(app, settings, [
            DatabaseExtension,  # Just pass the class
            RedisExtension,
        ])

    Settings to disable built-ins:
        logging_enabled: bool = True
        exception_handler_enabled: bool = True
        health_enabled: bool = True
    """
    from qtip.middleware.logging import LoggingExtension
    from qtip.core.execptions import ExceptionExtension
    from qtip.ext.health import HealthExtension

    # Build extension instances
    all_extensions: list[Extension] = []

    # 1. Logging first (sets up request IDs for everything else)
    if getattr(settings, "logging_enabled", True):
        all_extensions.append(LoggingExtension(settings))

    # 2. Exception handler (catches errors from all subsequent middleware)
    if getattr(settings, "exception_handler_enabled", True):
        all_extensions.append(ExceptionExtension(settings))

    # 3. User extensions (database, redis, etc.)
    for ext in extensions or []:
        if isinstance(ext, type):
            all_extensions.append(ext(settings))
        else:
            all_extensions.append(ext)

    # 4. Health checks last (can check all infrastructure)
    if getattr(settings, "health_enabled", True):
        version = getattr(settings, "app_version", app.version)
        all_extensions.append(HealthExtension(settings, version=version))

    # Collect middleware from all extensions
    middleware_stack: list[Middleware] = []
    for ext in all_extensions:
        middleware_stack.extend(ext.middleware())

    # Build combined lifespan
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state._extensions = all_extensions

        for ext in all_extensions:
            logger.info(f"Starting extension: {ext.name}")
            await ext.startup(app)

        if original_lifespan is not None:
            async with original_lifespan(app):
                yield
        else:
            yield

        for ext in reversed(all_extensions):
            logger.info(f"Stopping extension: {ext.name}")
            await ext.shutdown(app)

    # Create wrapped app
    wrapped = FastAPI(
        title=app.title,
        description=app.description,
        version=app.version,
        openapi_url=app.openapi_url,
        docs_url=app.docs_url,
        redoc_url=app.redoc_url,
        debug=app.debug,
        lifespan=combined_lifespan,
        middleware=middleware_stack,
    )

    # Copy routes, exception handlers, event handlers
    for route in app.routes:
        wrapped.router.routes.append(route)

    for exc_class, handler in app.exception_handlers.items():
        wrapped.add_exception_handler(exc_class, handler)

    return wrapped


# Typed accessors
def get_state(request: Request, key: str, expected_type: type[T]) -> T:
    """Get a value from request.state with type checking."""
    value = getattr(request.state, key)
    if not isinstance(value, expected_type):
        raise TypeError(f"Expected {expected_type}, got {type(value)}")
    return value


def get_app_state(request: Request, key: str, expected_type: type[T]) -> T:
    """Get a value from app.state with type checking."""
    value = getattr(request.app.state, key)
    if not isinstance(value, expected_type):
        raise TypeError(f"Expected {expected_type}, got {type(value)}")
    return value

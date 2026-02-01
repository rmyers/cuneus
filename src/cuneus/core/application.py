"""
cuneus - The wedge stone that locks the arch together.

Lightweight lifespan management for FastAPI applications.
"""

from __future__ import annotations

import inspect
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable

import click
import structlog
import svcs
from fastapi import FastAPI
from starlette.middleware import Middleware

from .settings import Settings
from .exceptions import ExceptionExtension
from .logging import LoggingExtension
from .extensions import Extension, HasCLI, HasExceptionHandler, HasMiddleware
from ..ext.health import HealthExtension

logger = structlog.stdlib.get_logger("cuneus")

type ExtensionInput = Extension | Callable[..., Extension]

DEFAULTS = (
    LoggingExtension,
    HealthExtension,
    ExceptionExtension,
)


class ExtensionConflictError(Exception):
    """Raised when extensions have conflicting state keys."""

    pass


def _instantiate_extension(
    ext: ExtensionInput, settings: Settings | None = None
) -> Extension:
    if isinstance(ext, type) or callable(ext):
        try:
            return ext(settings=settings)
        except TypeError:
            return ext()

    return ext


def build_app(
    *extensions: ExtensionInput,
    settings: Settings | None = None,
    include_defaults: bool = True,
    **fastapi_kwargs: Any,
) -> tuple[FastAPI, click.Group]:
    """
    Build a FastAPI with extensions preconfigured.

    The returned lifespan has a `.registry` attribute for testing overrides.

    Usage:
        from cuneus import build_app, Settings, SettingsExtension
        from myapp.extensions import DatabaseExtension

        settings = Settings()
        app, cli = build_app(
            SettingsExtension(settings),
            DatabaseExtension(settings),
            title="Args are passed to FastAPI",
        )

        __all__ = ["app", "cli"]

    Testing:
        from myapp import app, lifespan

        def test_with_mock_db(client):
            mock_db = Mock(spec=Database)
            lifespan.registry.register_value(Database, mock_db)
    """
    if "lifespan" in fastapi_kwargs:
        raise AttributeError("cannot set lifespan with build_app")
    if "middleware" in fastapi_kwargs:
        raise AttributeError("cannot set middleware with build_app")

    settings = settings or Settings()

    all_inputs = (*DEFAULTS, *extensions) if include_defaults else extensions

    all_extensions = [_instantiate_extension(ext, settings) for ext in all_inputs]

    @click.group()
    @click.pass_context
    def app_cli(ctx: click.Context) -> None:
        """Application CLI."""
        ctx.ensure_object(dict)

    @svcs.fastapi.lifespan
    @asynccontextmanager
    async def lifespan(
        app: FastAPI, registry: svcs.Registry
    ) -> AsyncIterator[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            state: dict[str, Any] = {}

            for ext in all_extensions:
                ext_name = ext.__class__.__name__
                ext_state = await stack.enter_async_context(ext.register(registry, app))
                if ext_state:
                    if overlap := state.keys() & ext_state.keys():
                        msg = f"Extension {ext_name} state key collision: {overlap}"
                        logger.error(msg, ext=ext_name, overlap=overlap)
                        raise ExtensionConflictError(msg).with_traceback(None) from None
                    state.update(ext_state)

            yield state

    # Parse extensions for middleware and cli commands
    middleware: list[Middleware] = []

    for ext in all_extensions:
        ext_name = ext.__class__.__name__
        if isinstance(ext, HasMiddleware):
            logger.debug(f"Loading middleware from {ext_name}")
            middleware.extend(ext.middleware())
        if isinstance(ext, HasCLI):
            logger.debug(f"Adding cli commands from {ext_name}")
            ext.register_cli(app_cli)

    app = FastAPI(lifespan=lifespan, middleware=middleware, **fastapi_kwargs)

    # Preform post app initialization extension customization
    for ext in all_extensions:
        ext_name = ext.__class__.__name__
        if isinstance(ext, HasExceptionHandler):
            logger.debug(f"Loading exception handlers from {ext_name}")
            ext.add_exception_handler(app)

    return app, app_cli

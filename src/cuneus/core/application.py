"""
cuneus - The wedge stone that locks the arch together.

Lightweight lifespan management for FastAPI applications.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable

import click
import svcs
from fastapi import FastAPI
from starlette.middleware import Middleware

from .settings import Settings
from .execptions import ExceptionExtension
from .logging import LoggingExtension
from .extensions import Extension, HasCLI, HasMiddleware
from ..ext.health import HealthExtension


type ExtensionInput = Extension | Callable[..., Extension]

DEFAULT_EXTENSIONS = (
    LoggingExtension,
    HealthExtension,
    ExceptionExtension,
)


def _instantiate_extension(
    ext: ExtensionInput, settings: Settings | None = None
) -> Extension:
    if isinstance(ext, type):
        # It's a class, instantiate it
        return ext(settings)
    if callable(ext):
        # It's a factory function
        return ext(settings)
    # Already an instance
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

    if include_defaults:
        # Allow users to override a default extension
        user_types = {type(ext) for ext in extensions}
        defaults = [ext for ext in DEFAULT_EXTENSIONS if type(ext) not in user_types]
        all_inputs = (*defaults, *extensions)
    else:
        all_inputs = extensions

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
                ext_state = await stack.enter_async_context(ext.register(registry, app))
                if ext_state:
                    if overlap := state.keys() & ext_state.keys():
                        raise ValueError(f"Extension state key collision: {overlap}")
                    state.update(ext_state)

            yield state

    # Parse extensions for middleware and cli commands
    middleware: list[Middleware] = []

    for ext in all_extensions:
        if isinstance(ext, HasMiddleware):
            middleware.extend(ext.middleware())
        if isinstance(ext, HasCLI):
            ext.register_cli(app_cli)

    app = FastAPI(lifespan=lifespan, middleware=middleware, **fastapi_kwargs)
    return app, app_cli

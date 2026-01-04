# cuneus

> _The wedge stone that locks the arch together_

**cuneus** is a lightweight lifespan manager for FastAPI applications. It provides a simple pattern for composing extensions that handle startup/shutdown and service registration.

The name comes from Roman architecture: a _cuneus_ is the wedge-shaped stone in a Roman arch. Each stone is simple on its own, but together they lock under pressure to create structures that have stood for millennia—no rebar required.

## Installation

```bash
uv add cuneus
```

or

```bash
pip install cuneus
```

## Quick Start

```python
# app.py
from fastapi import FastAPI
from cuneus import build_lifespan, Settings
from cuneus.middleware.logging import LoggingMiddleware

from myapp.extensions import DatabaseExtension

settings = Settings()
lifespan = build_lifespan(
    settings,
    DatabaseExtension(settings),
)

app = FastAPI(lifespan=lifespan, title="My App", version="1.0.0")

# Add middleware directly to FastAPI
app.add_middleware(LoggingMiddleware)
```

That's it. Extensions handle their lifecycle, FastAPI handles the rest.

## Creating Extensions

Use `BaseExtension` for simple cases:

```python
from cuneus import BaseExtension
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
import svcs

class DatabaseExtension(BaseExtension):
    def __init__(self, settings):
        self.settings = settings
        self.engine: AsyncEngine | None = None

    async def startup(self, registry: svcs.Registry, app: FastAPI) -> dict[str, Any]:
        self.engine = create_async_engine(self.settings.database_url)

        # Register with svcs for dependency injection
        registry.register_value(AsyncEngine, self.engine)

        # Add routes
        app.include_router(health_router, prefix="/health")

        # Add exception handlers
        app.add_exception_handler(DBError, self.handle_db_error)

        # Return state (accessible via request.state.db)
        return {"db": self.engine}

    async def shutdown(self, app: FastAPI) -> None:
        if self.engine:
            await self.engine.dispose()
```

For full control, override `register()` directly:

```python
from contextlib import asynccontextmanager

class RedisExtension(BaseExtension):
    def __init__(self, settings):
        self.settings = settings

    @asynccontextmanager
    async def register(self, registry: svcs.Registry, app: FastAPI):
        redis = await aioredis.from_url(self.settings.redis_url)
        registry.register_value(Redis, redis)

        try:
            yield {"redis": redis}
        finally:
            await redis.close()
```

## Testing

The lifespan exposes a `.registry` attribute for test overrides:

```python
# test_app.py
from unittest.mock import Mock
from starlette.testclient import TestClient
from myapp import app, lifespan, Database

def test_db_error_handling():
    with TestClient(app) as client:
        # Override after app startup
        mock_db = Mock(spec=Database)
        mock_db.get_user.side_effect = Exception("boom")
        lifespan.registry.register_value(Database, mock_db)

        resp = client.get("/users/42")
        assert resp.status_code == 500
```

## Settings

cuneus includes a base `Settings` class that loads from multiple sources:

```python
from cuneus import Settings

class AppSettings(Settings):
    database_url: str = "sqlite+aiosqlite:///./app.db"
    redis_url: str = "redis://localhost"

    model_config = SettingsConfigDict(env_prefix="APP_")
```

Load priority (highest wins):

1. Environment variables
2. `.env` file
3. `pyproject.toml` under `[tool.cuneus]`

## API Reference

### `build_lifespan(settings, *extensions)`

Creates a lifespan context manager for FastAPI.

- `settings`: Your settings instance (subclass of `Settings`)
- `*extensions`: Extension instances to register

Returns a lifespan with a `.registry` attribute for testing.

### `BaseExtension`

Base class with `startup()` and `shutdown()` hooks:

- `startup(registry, app) -> dict[str, Any]`: Setup resources, return state
- `shutdown(app) -> None`: Cleanup resources

### `Extension` Protocol

For full control, implement the protocol directly:

```python
def register(self, registry: svcs.Registry, app: FastAPI) -> AsyncContextManager[dict[str, Any]]
```

### Accessors

- `aget(request, *types)` - Async get services from svcs
- `get(request, *types)` - Sync get services from svcs
- `get_settings(request)` - Get settings from request state
- `get_request_id(request)` - Get request ID from request state

## Why cuneus?

- **Simple** — one function, `build_lifespan()`, does what you need
- **No magic** — middleware added directly to FastAPI, not hidden
- **Testable** — registry exposed via `lifespan.registry`
- **Composable** — extensions are just async context managers
- **Built on svcs** — proper dependency injection, not global state

## License

MIT

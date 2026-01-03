# qtip 🎤

A wrapper for FastAPI applications. Like the artist Q-Tip from A Tribe Called Quest.

**qtip** is batteries-included infrastructure for FastAPI, built on [svcs](https://svcs.hynek.me/) for service lifecycle and [starlette-context](https://github.com/tomwojcik/starlette-context) for request context. It handles configuration, database sessions, Redis, health checks, retries, and CLI tools so you can focus on your app.

## Installation

```bash
pip install asgi-qtip

# With database support (SQLAlchemy + asyncpg + Alembic)
pip install asgi-qtip[database]

# With Redis
pip install asgi-qtip[redis]

# Everything
pip install asgi-qtip[all]
```

## Quick Start

**pyproject.toml**

```toml
[tool.qtip]
app_name = "myapp"
app_module = "myapp.main:app"
database_url = "postgresql+asyncpg://localhost/myapp"
redis_url = "redis://localhost:6379/0"
```

**myapp/main.py**

```python
from qtip import Application, Settings
from qtip.ext.database import configure_database, DatabaseSettings
from qtip.ext.redis import configure_redis, RedisSettings
from qtip.ext.health import configure_health

class AppSettings(DatabaseSettings, RedisSettings):
    pass

settings = AppSettings()
app = Application(settings, title="My App")

configure_database(app, settings)
configure_redis(app, settings)
configure_health(app, settings, version="1.0.0")

fastapi_app = app.build()
```

**Run it**

```bash
myapp run --reload
myapp db upgrade
myapp check
```

## Using Services

qtip uses [svcs](https://svcs.hynek.me/) under the hood. Access services via annotated dependencies or directly:

```python
from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
import svcs

from qtip import NotFound
from qtip.ext.database import DBSession  # Annotated dependency

router = APIRouter()

# Option 1: Annotated dependency (recommended)
@router.get("/users/{id}")
async def get_user(id: int, db: DBSession):
    result = await db.execute(...)
    if not (user := result.scalar_one_or_none()):
        raise NotFound("User not found")
    return user

# Option 2: Get multiple services at once
@router.get("/dashboard")
async def dashboard(request: Request):
    db, redis = await svcs.fastapi.aget(request, AsyncSession, Redis)
    # ...
```

## Configuration

Config loads from (highest priority first):

1. **Environment variables**
2. **.env file**
3. **pyproject.toml `[tool.qtip]`**

Commit defaults in pyproject.toml, override secrets via environment.

## Health Checks

Automatic Kubernetes-ready endpoints using svcs ping capabilities:

```
GET /health       → Full check with all registered services
GET /health/live  → Liveness probe (always 200)
GET /health/ready → Readiness probe (503 if unhealthy)
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": [
    { "name": "AsyncSession", "status": "healthy" },
    { "name": "Redis", "status": "healthy" }
  ]
}
```

## Custom Services

Register your own services with full lifecycle management:

```python
from myapp.clients import GitHubClient

@app.on_startup
async def setup_github(registry):
    client = GitHubClient(settings.github_token)
    registry.register_value(GitHubClient, client, ping=client.ping)
    yield
    await client.close()
```

## Error Handling

Consistent JSON errors with request ID tracking:

```python
from qtip import NotFound, BadRequest, RateLimited

raise NotFound("User not found", details={"user_id": 123})
```

```json
{
  "error": {
    "code": "not_found",
    "message": "User not found",
    "request_id": "a1b2c3d4",
    "details": { "user_id": 123 }
  }
}
```

## Retry

Built-in retry with exponential backoff:

```python
from qtip import with_retry

@with_retry(max_attempts=3, retry_on=(httpx.HTTPError,))
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
```

## CLI

```bash
myapp run --reload       # Dev server with auto-reload
myapp run --workers 4    # Production with multiple workers
myapp db upgrade         # Run migrations
myapp db migrate -m "x"  # Create migration
myapp check              # Verify config + test connectivity
myapp config             # Show loaded configuration
myapp shell              # Interactive REPL with app context
```

## Testing

```python
import pytest
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

async def test_health(client):
    resp = await client.get("/health")
    assert resp.json()["status"] == "healthy"
```

## Why "qtip"?

Because it's a wrapper. Like the artist.

## License

MIT

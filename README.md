# QTip

ASGI application wrapper to assist with development. It is not quite a framework, but since it wraps the application it is named after Qtip the rapper from Tribe Called Quest.

## Features

- Authentication Sessions
- Database session management
- Environment Settings
- Event/Task/Background Queue
- Logging Middleware
- HTTP Error handling and traces
- Retry logic

## Quick Start

Install with UV:

```bash
uv add qtip
# pip
pip install qtip
```

**pyproject.toml**

```toml
# Configure qtip
[tool.qtip]
app_module="application:app"
extensions=[
    "qtip.ext.database.PostgresSQLExtension",
]
ext.database={
    "version": "17.0"
}
```

Create an `App` instance and set it up
**application.py**:

```python
from fastapi import FastAPI
from qtip import App, BaseSettings, cli
from qtip.ext.middleware import Frank

class Settings(BaseSettings):
    # BaseSettings includes all the settings for extension
    custom_setting: str = "why-not"

app = App(settings=Settings())

# Order matters: logging first (for request IDs), then exceptions, then infra
application.add_extension(LoggingExtension(settings))
application.add_extension(ExceptionExtension(settings))
application.add_extension(DatabaseExtension(settings))
application.add_extension(RedisExtension(settings))
# Add your routes
app.add_router(myroutes)

if __name__== "__main__":
    # most of the magic happens in the cli commands
    cli.run()
```

U

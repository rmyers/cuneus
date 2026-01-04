"""
qtip - A wrapper for FastAPI applications, like the artist.

Example:
    from qtip import Application, Settings
    from qtip.ext.database import DatabaseExtension

    class AppSettings(Settings):
        database_url: str

    settings = AppSettings()
    app = Application(settings)
    app.add_extension(DatabaseExtension(settings))

    fastapi_app = app.build()
"""

from cuneus.core.application import (
    BaseExtension,
    Extension,
    Settings,
    build_lifespan,
    get_settings,
    load_pyproject_config,
)
from cuneus.core.execptions import (
    AppException,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    Conflict,
    RateLimited,
    ServiceUnavailable,
    DatabaseError,
    RedisError,
    ExternalServiceError,
    ExceptionExtension,
)

__version__ = "0.2.1"
__all__ = [
    # Core
    "BaseExtension",
    "Extension",
    "Settings",
    "build_lifespan",
    "get_settings",
    "load_pyproject_config",
    # Exceptions
    "AppException",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "Conflict",
    "RateLimited",
    "ServiceUnavailable",
    "DatabaseError",
    "RedisError",
    "ExternalServiceError",
    "ExceptionExtension",
]

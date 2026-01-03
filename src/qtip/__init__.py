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

from qtip.core.application import (
    Application,
    Settings,
    aget,
    get,
    get_settings,
)
from qtip.core.execptions import (
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
    configure_exceptions,
    ExceptionSettings,
)

__version__ = "0.2.0"
__all__ = [
    # Core
    "Application",
    "Settings",
    "aget",
    "get",
    "get_settings",
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
    "configure_exceptions",
    "ExceptionSettings",
]

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
    Extension,
    Settings,
    SettingsProtocol,
    get_state,
    get_app_state,
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
)

__version__ = "0.1.0"
__all__ = [
    # Core
    "Extension",
    "Settings",
    "SettingsProtocol",
    "get_state",
    "get_app_state",
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
]

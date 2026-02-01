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

from .core.application import build_app
from .core.exceptions import (
    AppException,
    BadRequest,
    Conflict,
    DatabaseError,
    ErrorResponse,
    ExceptionExtension,
    ExternalServiceError,
    Forbidden,
    NotFound,
    RateLimited,
    RedisError,
    ServiceUnavailable,
    Unauthorized,
    error_responses,
)
from .core.extensions import BaseExtension, Extension
from .core.settings import Settings

__version__ = "0.2.1"
__all__ = [
    # Core exported functions
    # Application
    "build_app",
    # Extension
    "BaseExtension",
    "Extension",
    # Settings
    "Settings",
    # Exceptions
    "AppException",
    "BadRequest",
    "Conflict",
    "DatabaseError",
    "ErrorResponse",
    "ExceptionExtension",
    "ExternalServiceError",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "RedisError",
    "ServiceUnavailable",
    "Unauthorized",
    "error_responses",
]

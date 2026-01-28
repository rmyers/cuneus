from __future__ import annotations

import logging
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
)

logger = logging.getLogger(__name__)

DEFAULT_TOOL_NAME = "cuneus"


class CuneusBaseSettings(BaseSettings):
    """
    Base settings that loads from:
    1. pyproject.toml [tool.cuneus] (lowest priority)
    2. .env file
    3. Environment variables (highest priority)
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            PyprojectTomlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


class Settings(CuneusBaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        pyproject_toml_depth=2,
        pyproject_toml_table_header=("tool", DEFAULT_TOOL_NAME),
    )

    app_name: str = "app"
    app_module: str = "app.main:app"
    debug: bool = False
    version: str | None = None

    # logging
    log_level: str = "INFO"
    log_json: bool = False
    log_server_errors: bool = True
    request_id_header: str = "X-Request-ID"

    # health
    health_enabled: bool = True
    health_prefix: str = "/healthz"

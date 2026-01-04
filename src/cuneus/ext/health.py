"""
Health check endpoints using svcs ping capabilities.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import structlog
import svcs
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel

from cuneus.core.application import BaseExtension, Settings

log = structlog.get_logger()


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class ServiceHealth(BaseModel):
    name: str
    status: HealthStatus
    message: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    version: str | None = None
    services: list[ServiceHealth] = []


class HealthExtension(BaseExtension):
    """
    Health check extension using svcs pings.

    Adds:
        GET /health       - Full health check using svcs pings
        GET /health/live  - Liveness probe (always 200)
        GET /health/ready - Readiness probe (503 if unhealthy)

    Usage:
        from qtip import build_app
        from qtip.ext.health import HealthExtension, HealthSettings

        app = build_app(
            settings,
            extensions=[HealthExtension(settings)],
        )
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def startup(self, registry: svcs.Registry, app: FastAPI) -> dict[str, Any]:
        if not self.settings.health_enabled:
            return {}

        router = APIRouter(prefix=self.settings.health_prefix, tags=["health"])
        version = self.settings.version

        @router.get("", response_model=HealthResponse)
        async def health(services: svcs.fastapi.DepContainer) -> HealthResponse:
            """Full health check - pings all registered services."""
            pings = services.get_pings()

            _services: list[ServiceHealth] = []
            overall_healthy = True

            for ping in pings:
                try:
                    await ping.aping()
                    _services.append(
                        ServiceHealth(
                            name=ping.name,
                            status=HealthStatus.HEALTHY,
                        )
                    )
                except Exception as e:
                    log.warning("health_check_failed", service=ping.name, error=str(e))
                    _services.append(
                        ServiceHealth(
                            name=ping.name,
                            status=HealthStatus.UNHEALTHY,
                            message=str(e),
                        )
                    )
                    overall_healthy = False

            return HealthResponse(
                status=(
                    HealthStatus.HEALTHY if overall_healthy else HealthStatus.UNHEALTHY
                ),
                version=version,
                services=_services,
            )

        @router.get("/live")
        async def liveness() -> dict[str, str]:
            """Liveness probe - is the process running?"""
            return {"status": "ok"}

        @router.get("/ready")
        async def readiness(services: svcs.fastapi.DepContainer) -> dict[str, str]:
            """Readiness probe - can we serve traffic?"""
            from fastapi import HTTPException

            pings = services.get_pings()

            for ping in pings:
                try:
                    await ping.aping()
                except Exception as e:
                    log.warning(
                        "readiness_check_failed", service=ping.name, error=str(e)
                    )
                    raise HTTPException(
                        status_code=503, detail=f"{ping.name} unhealthy"
                    )

            return {"status": "ok"}

        app.include_router(router)
        return {}

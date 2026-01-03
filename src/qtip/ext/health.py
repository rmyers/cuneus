"""
Health check endpoints using svcs ping capabilities.
"""

from __future__ import annotations

import logging
from enum import Enum

import svcs
from fastapi import APIRouter, Request
from pydantic import BaseModel

from qtip.core.application import Application, Settings

logger = logging.getLogger(__name__)


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


class HealthSettings(Settings):
    """Settings for health checks."""

    health_enabled: bool = True
    health_prefix: str = "/health"


def configure_health(
    app: Application,
    settings: HealthSettings,
    *,
    version: str | None = None,
) -> None:
    """
    Configure health check endpoints.

    Adds:
        GET /health       - Full health check using svcs pings
        GET /health/live  - Liveness probe (always 200)
        GET /health/ready - Readiness probe (503 if unhealthy)

    Usage:
        from qtip.ext.health import configure_health, HealthSettings

        configure_health(app, settings, version="1.0.0")
    """

    if not settings.health_enabled:
        return

    router = APIRouter(prefix=settings.health_prefix, tags=["health"])

    @router.get("", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        """Full health check - pings all registered services."""

        pings = svcs.starlette.get_pings(request)

        services: list[ServiceHealth] = []
        overall_healthy = True

        for ping in pings:
            try:
                await ping.aping()
                services.append(
                    ServiceHealth(
                        name=ping.name,
                        status=HealthStatus.HEALTHY,
                    )
                )
            except Exception as e:
                logger.warning(f"Health check failed for {ping.name}: {e}")
                services.append(
                    ServiceHealth(
                        name=ping.name,
                        status=HealthStatus.UNHEALTHY,
                        message=str(e),
                    )
                )
                overall_healthy = False

        return HealthResponse(
            status=HealthStatus.HEALTHY if overall_healthy else HealthStatus.UNHEALTHY,
            version=version,
            services=services,
        )

    @router.get("/live")
    async def liveness() -> dict[str, str]:
        """Liveness probe - is the process running?"""
        return {"status": "ok"}

    @router.get("/ready")
    async def readiness(request: Request) -> dict[str, str]:
        """Readiness probe - can we serve traffic?"""
        from fastapi import HTTPException

        pings = svcs.starlette.get_pings(request)

        for ping in pings:
            try:
                await ping.aping()
            except Exception as e:
                logger.warning(f"Readiness check failed for {ping.name}: {e}")
                raise HTTPException(status_code=503, detail=f"{ping.name} unhealthy")

        return {"status": "ok"}

    # Register the router
    app.include_router(router)

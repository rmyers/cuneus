"""
Health check endpoints for Kubernetes/load balancer probes.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel

from qtip.core.application import Extension, SettingsProtocol

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    version: str | None = None
    components: dict[str, ComponentHealth] = {}


class HealthExtension(Extension):
    """
    Health check extension.

    Settings:
        health_enabled: bool = True
        health_prefix: str = "/health"
        health_check_timeout: float = 5.0
        health_detailed: bool = True

    Adds endpoints:
        GET /health       - Full health check (for monitoring)
        GET /health/live  - Liveness probe (is the process running?)
        GET /health/ready - Readiness probe (can we serve traffic?)

    Automatically checks:
        - Database connectivity (if DatabaseExtension is registered)
        - Redis connectivity (if RedisExtension is registered)
    """

    name = "health"
    settings_keys = [
        "health_enabled",
        "health_prefix",
        "health_check_timeout",
        "health_detailed",
    ]

    def __init__(
        self, settings: SettingsProtocol, *, version: str | None = None
    ) -> None:
        super().__init__(settings)
        self.version = version
        self._checks: dict[str, Any] = {}

    def add_check(self, name: str, check_fn) -> None:
        """
        Register a custom health check.

        check_fn should be an async function that returns (bool, optional_message).
        """
        self._checks[name] = check_fn

    async def startup(self, app: FastAPI) -> None:
        if not self.get_setting("health_enabled", True):
            return

        prefix = self.get_setting("health_prefix", "/health")
        router = APIRouter(prefix=prefix, tags=["health"])

        @router.get("", response_model=HealthResponse)
        async def health(request: Request) -> HealthResponse:
            return await self._full_health_check(request)

        @router.get("/live")
        async def _liveness() -> dict[str, str]:
            # Liveness: is the process alive? Always yes if we get here
            return {"status": "ok"}

        @router.get("/ready")
        async def _readiness(request: Request) -> dict[str, str]:
            # Readiness: can we handle traffic?
            result = await self._full_health_check(request)
            if result.status == HealthStatus.UNHEALTHY:
                from fastapi import HTTPException

                raise HTTPException(status_code=503, detail="Not ready")
            return {"status": "ok"}

        app.include_router(router)

    async def _full_health_check(self, request: Request) -> HealthResponse:
        components: dict[str, ComponentHealth] = {}
        overall_status = HealthStatus.HEALTHY

        # Check database if available
        if hasattr(request.app.state, "db_engine"):
            db_health = await self._check_database(request)
            components["database"] = db_health
            if db_health.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif (
                db_health.status == HealthStatus.DEGRADED
                and overall_status == HealthStatus.HEALTHY
            ):
                overall_status = HealthStatus.DEGRADED

        # Check Redis if available
        if hasattr(request.app.state, "redis") and request.app.state.redis:
            redis_health = await self._check_redis(request)
            components["redis"] = redis_health
            if redis_health.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif (
                redis_health.status == HealthStatus.DEGRADED
                and overall_status == HealthStatus.HEALTHY
            ):
                overall_status = HealthStatus.DEGRADED

        # Run custom checks
        for name, check_fn in self._checks.items():
            timeout = self.get_setting("health_check_timeout", 5.0)
            try:
                async with asyncio.timeout(timeout):
                    import time

                    start = time.perf_counter()
                    ok, message = await check_fn(request)
                    latency = (time.perf_counter() - start) * 1000

                    components[name] = ComponentHealth(
                        status=HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY,
                        latency_ms=round(latency, 2),
                        message=message,
                    )

                    if not ok:
                        overall_status = HealthStatus.UNHEALTHY

            except asyncio.TimeoutError:
                components[name] = ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="Check timed out",
                )
                overall_status = HealthStatus.UNHEALTHY
            except Exception as e:
                components[name] = ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                )
                overall_status = HealthStatus.UNHEALTHY

        detailed = self.get_setting("health_detailed", True)
        return HealthResponse(
            status=overall_status,
            version=self.version,
            components=components if detailed else {},
        )

    async def _check_database(self, request: Request) -> ComponentHealth:
        import time
        from sqlalchemy import text

        timeout = self.get_setting("health_check_timeout", 5.0)
        try:
            async with asyncio.timeout(timeout):
                start = time.perf_counter()
                async with request.app.state.db_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                latency = (time.perf_counter() - start) * 1000

                # Warn if latency is high
                status = HealthStatus.HEALTHY
                message = None
                if latency > 1000:
                    status = HealthStatus.DEGRADED
                    message = "High latency"

                return ComponentHealth(
                    status=status,
                    latency_ms=round(latency, 2),
                    message=message,
                )
        except asyncio.TimeoutError:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Connection timed out",
            )
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def _check_redis(self, request: Request) -> ComponentHealth:
        import time

        timeout = self.get_setting("health_check_timeout", 5.0)
        try:
            async with asyncio.timeout(timeout):
                start = time.perf_counter()
                await request.app.state.redis.ping()
                latency = (time.perf_counter() - start) * 1000

                status = HealthStatus.HEALTHY
                message = None
                if latency > 100:
                    status = HealthStatus.DEGRADED
                    message = "High latency"

                return ComponentHealth(
                    status=status,
                    latency_ms=round(latency, 2),
                    message=message,
                )
        except asyncio.TimeoutError:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Connection timed out",
            )
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

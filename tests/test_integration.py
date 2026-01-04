from starlette.testclient import TestClient

from fastapi import FastAPI
from cuneus import ExceptionExtension, Settings, build_lifespan
from cuneus.middleware import logging
from cuneus.ext import health


async def test_cuneus():
    settings = Settings()
    lifespan = build_lifespan(
        settings,
        ExceptionExtension(settings),
        logging.LoggingExtension(settings),
        health.HealthExtension(settings),
    )
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(logging.LoggingMiddleware)

    with TestClient(app) as client:

        resp = client.get("/healthz")
        assert resp.status_code == 200

        assert resp.json()["status"] == health.HealthStatus.HEALTHY

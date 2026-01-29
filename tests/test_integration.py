from starlette.testclient import TestClient

from cuneus import build_app
from cuneus.ext import health


async def test_cuneus():
    app, _ = build_app()

    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 201

        assert resp.json()["status"] == health.HealthStatus.HEALTHY

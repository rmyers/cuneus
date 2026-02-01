from typing import Any

import pytest
from click.testing import CliRunner
from fastapi import FastAPI, Request
from starlette.testclient import TestClient
from svcs import Registry

from cuneus import build_app, BaseExtension
from cuneus.ext import health


class MyParamLessExtension(BaseExtension):

    def __init__(self):
        pass


class MyExtraSettings(BaseExtension):

    def __init__(self, debug: bool):
        self.debug = debug

    async def startup(self, registry: Registry, app: FastAPI) -> dict[str, Any]:
        await super().startup(registry, app)
        return {"my_ext": {"debug": self.debug}}


class MyConflictState(BaseExtension):

    def __init__(self, debug: bool):
        self.debug = debug

    async def startup(self, registry: Registry, app: FastAPI) -> dict[str, Any]:
        await super().startup(registry, app)
        return {"my_ext": {"debug": self.debug}}


async def test_cuneus_defaults():
    app, _ = build_app()

    @app.get("/some_path")
    async def something():
        return {"it": "works"}

    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") is None
        assert resp.json()["status"] == health.HealthStatus.HEALTHY

        # Test other health routes
        resp = client.get("/healthz/live")
        assert resp.status_code == 200
        resp = client.get("/healthz/ready")
        assert resp.status_code == 200

        resp = client.get("/some_path")
        assert resp.status_code == 200
        assert resp.headers["X-Request-ID"] is not None


async def test_cuneus_custom_extension():
    app, _ = build_app(MyParamLessExtension, MyExtraSettings(debug=True))

    @app.get("/some_path")
    async def something(request: Request):
        return request.state.my_ext

    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") is None

        assert resp.json()["status"] == health.HealthStatus.HEALTHY

        resp = client.get("/some_path")
        assert resp.status_code == 200
        assert resp.headers["X-Request-ID"] is not None
        assert resp.json() == {"debug": True}


async def test_cuneus_conflict():
    app, _ = build_app(MyExtraSettings(debug=True), MyConflictState(False))

    @app.get("/some_path")
    async def something():
        return {"it": "works"}

    with pytest.raises(Exception):
        with TestClient(app) as client:
            resp = client.get("/healthz")
            assert resp.status_code == 200
            assert resp.headers.get("X-Request-ID") is None


def test_build_app_setup():
    with pytest.raises(AttributeError):
        build_app(lifespan={"lifespan": "this is not allowed"})

    with pytest.raises(AttributeError):
        build_app(middleware=[{"not": "allowed"}])


def test_cli():
    _, cli = build_app(MyParamLessExtension, MyExtraSettings(debug=True))
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output

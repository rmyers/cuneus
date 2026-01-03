from starlette.testclient import TestClient

from qtip import Application, ExceptionSettings, configure_exceptions
from qtip.middleware import logging
from qtip.ext import health


class AppSettings(ExceptionSettings, logging.LoggingSettings, health.HealthSettings):
    pass


async def test_qtip():
    settings = AppSettings()
    app = Application(settings)

    configure_exceptions(app, settings)
    logging.configure_logging(app, settings)
    health.configure_health(app, settings)

    fastapi = app.build()
    with TestClient(fastapi) as client:

        resp = client.get("/health")
        assert resp.status_code == 200

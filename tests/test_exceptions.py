import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from cuneus import (
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
    Settings,
    Unauthorized,
    build_app,
    error_responses,
)


class TestAppException:
    def test_defaults(self):
        exc = AppException()
        assert exc.status_code == 500
        assert exc.error_code == "internal_error"
        assert exc.message == "An unexpected error occurred"
        assert exc.details == {}

    def test_custom_values(self):
        exc = AppException(
            "Something broke",
            error_code="custom_error",
            status_code=418,
            details={"foo": "bar"},
        )
        assert exc.message == "Something broke"
        assert exc.error_code == "custom_error"
        assert exc.status_code == 418
        assert exc.details == {"foo": "bar"}

    def test_to_response(self):
        exc = AppException("Test error", error_code="test", details={"key": "value"})
        response = exc.to_response(request_id="req-123")

        assert isinstance(response, ErrorResponse)
        assert response.error.status == 500
        assert response.error.code == "test"
        assert response.error.message == "Test error"
        assert response.error.request_id == "req-123"
        assert response.error.details == {"key": "value"}

    def test_to_response_no_request_id(self):
        exc = AppException()
        response = exc.to_response()
        assert response.error.request_id is None


class TestHttpExceptions:
    @pytest.mark.parametrize(
        "exc_class,status,code",
        [
            (BadRequest, 400, "bad_request"),
            (Unauthorized, 401, "unauthorized"),
            (Forbidden, 403, "forbidden"),
            (NotFound, 404, "not_found"),
            (Conflict, 409, "conflict"),
            (RateLimited, 429, "rate_limited"),
            (ServiceUnavailable, 503, "service_unavailable"),
        ],
    )
    def test_http_exception_defaults(self, exc_class, status, code):
        exc = exc_class()
        assert exc.status_code == status
        assert exc.error_code == code
        assert isinstance(exc, AppException)

    def test_rate_limited_retry_after(self):
        exc = RateLimited(retry_after=60)
        assert exc.retry_after == 60


class TestInfrastructureExceptions:
    @pytest.mark.parametrize(
        "exc_class,status,code",
        [
            (DatabaseError, 503, "database_error"),
            (RedisError, 503, "cache_error"),
            (ExternalServiceError, 502, "external_service_error"),
        ],
    )
    def test_infra_exception_defaults(self, exc_class, status, code):
        exc = exc_class()
        assert exc.status_code == status
        assert exc.error_code == code


class TestErrorResponses:
    def test_single_exception(self):
        responses = error_responses(NotFound())
        assert 404 in responses
        assert responses[404]["model"] == ErrorResponse

    def test_multiple_exceptions(self):
        responses = error_responses(NotFound(), BadRequest(), Forbidden())
        assert set(responses.keys()) == {400, 403, 404}


class TestExceptionExtension:
    @pytest.fixture
    def app(self, request):
        params = getattr(request, "param", {})
        settings = Settings(**params)
        app, _ = build_app(settings=settings)

        @app.get("/app-error")
        async def raise_app_error():
            raise NotFound("Item not found", details={"id": 123})

        @app.get("/unexpected")
        async def raise_unexpected():
            raise RuntimeError("Boom")

        @app.get("/rate-limited")
        async def raise_rate_limited():
            raise RateLimited(retry_after=30)

        return app

    @pytest.fixture
    def client(self, app):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    def test_handles_app_exception(self, client):
        resp = client.get("/app-error")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Item not found"
        assert body["error"]["details"] == {"id": 123}

    @pytest.mark.parametrize("app", [{"debug": False}], indirect=True)
    def test_handles_unexpected_exception(self, client):
        resp = client.get("/unexpected")
        assert resp.status_code == 500, resp.text
        body = resp.json()
        assert body["error"]["code"] == "internal_error"
        assert body["error"]["message"] == "An unexpected error occurred"
        assert "details" not in body["error"]

    @pytest.mark.parametrize("app", [{"debug": True}], indirect=True)
    def test_debug_mode_includes_exception_details(self, client):
        resp = client.get("/unexpected")
        assert resp.status_code == 500, resp.text
        body = resp.json()
        assert body["error"]["details"]["exception"] == "RuntimeError"
        assert body["error"]["details"]["message"] == "Boom"

    def test_rate_limited_includes_retry_after_header(self, client):
        resp = client.get("/rate-limited")
        assert resp.status_code == 429, resp.text
        assert resp.headers["Retry-After"] == "30"

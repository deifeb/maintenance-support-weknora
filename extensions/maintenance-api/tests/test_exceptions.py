from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from app.core.exceptions import register_exception_handlers


def create_validation_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/validate")
    def validate_quantity(
        quantity: int = Query(ge=1),
    ) -> dict[str, int]:
        return {"quantity": quantity}

    return app


def create_unexpected_error_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/error")
    def raise_unexpected_error() -> None:
        raise RuntimeError("sensitive internal error")

    return app


def test_validation_error_uses_standard_error_envelope() -> None:
    with TestClient(create_validation_test_app()) as client:
        response = client.get("/validate?quantity=0")

    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)


def test_unexpected_error_does_not_expose_internal_message() -> None:
    with TestClient(
        create_unexpected_error_test_app(),
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/error")

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": None,
        },
    }

    assert "sensitive internal error" not in response.text

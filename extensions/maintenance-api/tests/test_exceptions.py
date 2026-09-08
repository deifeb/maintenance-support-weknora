from app.core.exceptions import register_exception_handlers
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient


def test_validation_error_uses_standard_error_envelope() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/validate")
    def validate(quantity: int = Query(ge=1)):
        return {"quantity": quantity}

    with TestClient(app) as client:
        response = client.get("/validate?quantity=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unexpected_error_does_not_expose_internal_message() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/error")
    def fail():
        raise RuntimeError("sensitive internal error")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/error")
    assert response.status_code == 500
    assert "sensitive internal error" not in response.text

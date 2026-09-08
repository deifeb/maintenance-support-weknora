from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Annotated

import jwt
import pytest
from app.security.actor import ActorContext
from app.security.dependencies import get_actor, get_internal_token_verifier
from app.security.internal_jwt import InternalTokenVerifier
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

TEST_SECRET = "unit-five-internal-jwt-secret-0001"
FIXED_NOW = datetime(2026, 7, 25, 8, 0, 0, tzinfo=timezone.utc)
FIXED_NOW_TS = int(FIXED_NOW.timestamp())


def fixed_clock() -> datetime:
    return FIXED_NOW


def encode_token() -> str:
    return jwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "12",
            "roles": ["contributor"],
            "aud": ["maintenance-api"],
            "iss": "weknora",
            "iat": FIXED_NOW_TS,
            "exp": FIXED_NOW_TS + 180,
            "jti": "5ea49880-7b27-4d9e-a383-1219b8164dc0",
            "request_id": "request-1",
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def make_verifier() -> InternalTokenVerifier:
    return InternalTokenVerifier(
        secret=TEST_SECRET,
        issuer="weknora",
        audience="maintenance-api",
        max_lifetime_seconds=180,
        clock_skew_seconds=5,
        clock=fixed_clock,
    )


@contextmanager
def protected_client(
    verifier: InternalTokenVerifier | None = None,
) -> Iterator[TestClient]:
    application = FastAPI()
    application.dependency_overrides[get_internal_token_verifier] = (
        lambda: verifier or make_verifier()
    )

    @application.get("/protected")
    def protected(
        request: Request,
        actor: Annotated[ActorContext, Depends(get_actor)],
    ) -> dict[str, object]:
        return {
            "user_id": actor.user_id,
            "tenant_id": actor.tenant_id,
            "role": actor.role,
            "request_id": actor.request_id,
            "state_actor_matches": request.state.actor is actor,
            "state_request_id": request.state.request_id,
        }

    with TestClient(application) as client:
        yield client


def test_get_actor_returns_verified_actor_and_populates_request_state() -> None:
    with protected_client() as client:
        response = client.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {encode_token()}",
                "X-Request-ID": "browser-supplied-request-id",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "tenant_id": "12",
        "role": "contributor",
        "request_id": "request-1",
        "state_actor_matches": True,
        "state_request_id": "request-1",
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc123"},
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
def test_get_actor_rejects_missing_or_invalid_credentials(
    headers: dict[str, str],
) -> None:
    with protected_client() as client:
        response = client.get("/protected", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_TOKEN_INVALID",
            "message": "Invalid internal authentication token",
        }
    }

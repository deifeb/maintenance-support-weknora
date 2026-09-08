from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.security.actor import ActorContext
from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier

_internal_bearer = HTTPBearer(auto_error=False)


def get_internal_token_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> InternalTokenVerifier:
    return InternalTokenVerifier(
        secret=settings.internal_jwt_secret.get_secret_value(),
        issuer=settings.internal_jwt_issuer,
        audience=settings.internal_jwt_audience,
        max_lifetime_seconds=settings.internal_jwt_max_lifetime_seconds,
        clock_skew_seconds=settings.internal_jwt_clock_skew_seconds,
    )


def get_actor(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_internal_bearer),
    ],
    verifier: Annotated[
        InternalTokenVerifier,
        Depends(get_internal_token_verifier),
    ],
) -> ActorContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _invalid_internal_token()

    try:
        actor = verifier.verify(credentials.credentials)
    except InternalTokenError as exc:
        raise _invalid_internal_token() from exc

    request.state.actor = actor
    request.state.request_id = actor.request_id
    return actor


def _invalid_internal_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INTERNAL_TOKEN_INVALID",
            "message": "Invalid internal authentication token",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

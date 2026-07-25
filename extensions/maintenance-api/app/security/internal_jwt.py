from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.security.actor import ActorContext, MaintenanceRole

_REQUIRED_CLAIMS = (
    "sub",
    "tenant_id",
    "roles",
    "aud",
    "iss",
    "iat",
    "exp",
    "jti",
    "request_id",
)


class InternalTokenError(ValueError):
    """Raised when an internal JWT cannot be trusted."""


class InternalTokenVerifier:
    def __init__(
        self,
        secret: str,
        issuer: str,
        audience: str,
        *,
        max_lifetime_seconds: int = 180,
        clock_skew_seconds: int = 5,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError(
                "internal JWT secret must contain at least 32 UTF-8 bytes"
            )

        normalized_issuer = issuer.strip()
        if not normalized_issuer:
            raise ValueError("internal JWT issuer must not be blank")

        normalized_audience = audience.strip()
        if not normalized_audience:
            raise ValueError("internal JWT audience must not be blank")

        if not 1 <= max_lifetime_seconds <= 180:
            raise ValueError(
                "internal JWT maximum lifetime must be between 1 and 180 seconds"
            )

        if not 0 <= clock_skew_seconds <= 30:
            raise ValueError(
                "internal JWT clock skew must be between 0 and 30 seconds"
            )

        self._secret = secret
        self._issuer = normalized_issuer
        self._audience = normalized_audience
        self._max_lifetime_seconds = max_lifetime_seconds
        self._clock_skew_seconds = clock_skew_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def verify(self, token: str) -> ActorContext:
        if not isinstance(token, str) or not token.strip():
            raise InternalTokenError("invalid internal JWT")

        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "HS256":
                raise InternalTokenError("invalid internal JWT")

            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": list(_REQUIRED_CLAIMS),
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )

            user_id = self._required_text(claims, "sub")
            tenant_id = self._required_text(claims, "tenant_id")
            request_id = self._required_text(claims, "request_id")
            token_id = self._required_text(claims, "jti")
            role = self._single_role(claims["roles"])
            issued_at = self._numeric_date(claims, "iat")
            expires_at = self._numeric_date(claims, "exp")
            self._validate_time_window(issued_at=issued_at, expires_at=expires_at)

            return ActorContext(
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                request_id=request_id,
                token_id=token_id,
            )
        except InternalTokenError:
            raise
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise InternalTokenError("invalid internal JWT") from exc

    @staticmethod
    def _required_text(claims: dict[str, Any], name: str) -> str:
        value = claims[name]
        if not isinstance(value, str) or not value.strip():
            raise InternalTokenError("invalid internal JWT")
        return value

    @staticmethod
    def _numeric_date(claims: dict[str, Any], name: str) -> int:
        value = claims[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise InternalTokenError("invalid internal JWT")
        return value

    def _validate_time_window(self, *, issued_at: int, expires_at: int) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise InternalTokenError("invalid internal JWT")

        now_timestamp = now.astimezone(timezone.utc).timestamp()
        lifetime = expires_at - issued_at

        if lifetime <= 0 or lifetime > self._max_lifetime_seconds:
            raise InternalTokenError("invalid internal JWT")

        if issued_at > now_timestamp + self._clock_skew_seconds:
            raise InternalTokenError("invalid internal JWT")

        if expires_at <= now_timestamp - self._clock_skew_seconds:
            raise InternalTokenError("invalid internal JWT")

    @staticmethod
    def _single_role(value: object) -> MaintenanceRole:
        if (
            not isinstance(value, list)
            or len(value) != 1
            or not isinstance(value[0], str)
        ):
            raise InternalTokenError("invalid internal JWT")

        return MaintenanceRole(value[0])

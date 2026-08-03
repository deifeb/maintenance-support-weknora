from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import jwt
import pytest
from app.core.config import Settings
from app.security.actor import ActorContext, MaintenanceRole
from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier
from pydantic import ValidationError

TEST_SECRET = "unit-five-internal-jwt-secret-0001"
FIXED_NOW = datetime(2026, 7, 25, 8, 0, 0, tzinfo=timezone.utc)
FIXED_NOW_TS = int(FIXED_NOW.timestamp())
CANONICAL_JTI = "5ea49880-7b27-4d9e-a383-1219b8164dc0"


def fixed_clock() -> datetime:
    return FIXED_NOW


def canonical_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "sub": "user-1",
        "tenant_id": "12",
        "roles": ["contributor"],
        "aud": ["maintenance-api"],
        "iss": "weknora",
        "iat": FIXED_NOW_TS,
        "exp": FIXED_NOW_TS + 180,
        "jti": CANONICAL_JTI,
        "request_id": "request-1",
    }
    payload.update(overrides)
    return payload


def encode_token(
    payload: dict[str, object] | None = None,
    *,
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
) -> str:
    source = canonical_payload() if payload is None else payload
    return jwt.encode(source, secret, algorithm=algorithm)


def make_verifier(
    *,
    max_lifetime_seconds: int = 180,
    clock_skew_seconds: int = 5,
    clock: Callable[[], datetime] = fixed_clock,
) -> InternalTokenVerifier:
    return InternalTokenVerifier(
        secret=TEST_SECRET,
        issuer="weknora",
        audience="maintenance-api",
        max_lifetime_seconds=max_lifetime_seconds,
        clock_skew_seconds=clock_skew_seconds,
        clock=clock,
    )


def replace_algorithm_header(token: str, algorithm: str) -> str:
    header = json.dumps({"alg": algorithm, "typ": "JWT"}, separators=(",", ":")).encode()
    encoded_header = base64.urlsafe_b64encode(header).rstrip(b"=").decode()
    _, payload, signature = token.split(".")
    return f"{encoded_header}.{payload}.{signature}"


def test_settings_require_internal_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERNAL_JWT_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "internal_jwt_secret" in str(exc_info.value)


def test_settings_reject_short_secret_without_disclosing_it() -> None:
    short_secret = "not-long-enough"

    with pytest.raises(ValidationError) as exc_info:
        Settings(internal_jwt_secret=short_secret, _env_file=None)

    assert short_secret not in str(exc_info.value)
    assert "input_value=" not in str(exc_info.value)
    assert "32 UTF-8 bytes" in str(exc_info.value)


def test_settings_measure_secret_length_in_utf8_bytes() -> None:
    settings = Settings(internal_jwt_secret="密" * 11, _env_file=None)

    assert settings.internal_jwt_secret.get_secret_value() == "密" * 11


def test_settings_hide_valid_secret_in_diagnostics() -> None:
    settings = Settings(internal_jwt_secret=TEST_SECRET, _env_file=None)

    assert TEST_SECRET not in repr(settings)
    assert TEST_SECRET not in repr(settings.model_dump())
    assert str(settings.internal_jwt_secret) == "**********"


@pytest.mark.parametrize("field", ["internal_jwt_issuer", "internal_jwt_audience"])
def test_settings_reject_blank_identity_names(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            **{field: " \t "},
            _env_file=None,
        )


@pytest.mark.parametrize("value", [0, -1, 181])
def test_settings_reject_invalid_max_lifetime(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            internal_jwt_max_lifetime_seconds=value,
            _env_file=None,
        )


@pytest.mark.parametrize("value", [-1, 31])
def test_settings_reject_invalid_clock_skew(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            internal_jwt_clock_skew_seconds=value,
            _env_file=None,
        )


@pytest.mark.parametrize("value", [1, 180])
def test_settings_accept_bounded_max_lifetime(value: int) -> None:
    settings = Settings(
        internal_jwt_secret=TEST_SECRET,
        internal_jwt_max_lifetime_seconds=value,
        _env_file=None,
    )

    assert settings.internal_jwt_max_lifetime_seconds == value


@pytest.mark.parametrize("value", [0, 5, 30])
def test_settings_accept_bounded_clock_skew(value: int) -> None:
    settings = Settings(
        internal_jwt_secret=TEST_SECRET,
        internal_jwt_clock_skew_seconds=value,
        _env_file=None,
    )

    assert settings.internal_jwt_clock_skew_seconds == value


def test_actor_context_is_immutable_and_single_role() -> None:
    actor = ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-1",
        token_id=CANONICAL_JTI,
    )

    assert actor.role is MaintenanceRole.CONTRIBUTOR
    with pytest.raises(FrozenInstanceError):
        actor.role = MaintenanceRole.ADMIN  # type: ignore[misc]


def test_actor_context_uses_slots() -> None:
    actor = ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=MaintenanceRole.VIEWER,
        request_id="request-1",
        token_id=CANONICAL_JTI,
    )

    assert not hasattr(actor, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(actor, "unexpected", "value")


def test_verifier_returns_canonical_actor() -> None:
    actor = make_verifier().verify(encode_token())

    assert actor == ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-1",
        token_id=CANONICAL_JTI,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"secret": "short"}, "32 UTF-8 bytes"),
        ({"issuer": " "}, "issuer"),
        ({"audience": " "}, "audience"),
        ({"max_lifetime_seconds": 0}, "maximum lifetime"),
        ({"max_lifetime_seconds": 181}, "maximum lifetime"),
        ({"clock_skew_seconds": -1}, "clock skew"),
        ({"clock_skew_seconds": 31}, "clock skew"),
    ],
)
def test_verifier_rejects_unsafe_constructor_values(
    kwargs: dict[str, object], message: str
) -> None:
    arguments: dict[str, object] = {
        "secret": TEST_SECRET,
        "issuer": "weknora",
        "audience": "maintenance-api",
        "max_lifetime_seconds": 180,
        "clock_skew_seconds": 5,
        "clock": fixed_clock,
    }
    arguments.update(kwargs)

    with pytest.raises(ValueError, match=message):
        InternalTokenVerifier(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("token", ["", "   ", "not-a-jwt"])
def test_verifier_rejects_empty_or_malformed_token(token: str) -> None:
    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(token)


def test_verifier_rejects_wrong_secret() -> None:
    token = encode_token(secret="different-secret-value-with-32-bytes")

    with pytest.raises(InternalTokenError):
        make_verifier().verify(token)


@pytest.mark.parametrize(
    "payload",
    [
        canonical_payload(iss="other"),
        canonical_payload(aud=["other"]),
    ],
)
def test_verifier_rejects_wrong_issuer_or_audience(payload: dict[str, object]) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(payload))


@pytest.mark.parametrize("claim", list(canonical_payload()))
def test_verifier_requires_every_claim(claim: str) -> None:
    payload = canonical_payload()
    del payload[claim]

    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(payload))


@pytest.mark.parametrize("algorithm", ["none", "HS384", "HS512", "RS256"])
def test_verifier_rejects_every_non_hs256_header(algorithm: str) -> None:
    forged = replace_algorithm_header(encode_token(), algorithm)

    with pytest.raises(InternalTokenError):
        make_verifier().verify(forged)


@pytest.mark.parametrize(
    "payload",
    [
        canonical_payload(exp=FIXED_NOW_TS - 5),
        canonical_payload(
            iat=FIXED_NOW_TS + 6,
            exp=FIXED_NOW_TS + 6 + 180,
        ),
        canonical_payload(
            iat=FIXED_NOW_TS,
            exp=FIXED_NOW_TS + 181,
        ),
        canonical_payload(
            iat=FIXED_NOW_TS,
            exp=FIXED_NOW_TS,
        ),
    ],
)
def test_verifier_rejects_invalid_time_windows(payload: dict[str, object]) -> None:
    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(encode_token(payload))


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iat", True),
        ("iat", "1784966400"),
        ("iat", 1784966400.5),
        ("exp", False),
        ("exp", "1784966580"),
        ("exp", 1784966580.5),
    ],
)
def test_verifier_requires_integer_numeric_dates(
    claim: str,
    value: object,
) -> None:
    payload = canonical_payload(**{claim: value})

    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(encode_token(payload))


def test_verifier_accepts_clock_skew_inside_boundaries() -> None:
    payload = canonical_payload(
        iat=FIXED_NOW_TS + 5,
        exp=FIXED_NOW_TS + 5 + 180,
    )

    actor = make_verifier().verify(encode_token(payload))

    assert actor.user_id == "user-1"


def test_verifier_accepts_recent_expiry_inside_clock_skew() -> None:
    payload = canonical_payload(
        iat=FIXED_NOW_TS - 184,
        exp=FIXED_NOW_TS - 4,
    )

    actor = make_verifier().verify(encode_token(payload))

    assert actor.token_id == CANONICAL_JTI


def test_verifier_rejects_naive_clock_result() -> None:
    def naive_clock() -> datetime:
        return FIXED_NOW.replace(tzinfo=None)

    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier(clock=naive_clock).verify(encode_token())

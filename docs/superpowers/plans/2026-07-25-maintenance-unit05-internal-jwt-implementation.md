# Maintenance Unit 05 Internal JWT Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Maintenance FastAPI service's fail-closed internal identity boundary by validating WeKnora-issued HS256 JWTs into immutable, single-role `ActorContext` values and exposing a reusable `get_actor` dependency without protecting existing business routers yet.

**Architecture:** Pydantic Settings validates the shared-secret contract at startup. A focused `InternalTokenVerifier` uses PyJWT only for signature, issuer, audience, and required-claim decoding, then performs strict application-level type, shape, UUID, string-safety, lifetime, and clock-skew checks with an injectable UTC clock. A FastAPI dependency converts all credential and verification failures into the existing project error envelope with a fixed Bearer challenge.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, pydantic-settings, PyJWT `>=2.10,<3`, pytest, HTTPX TestClient, Ruff.

## Global Constraints

- Work only on branch `feature/maintenance-frontend-plan05` in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Start from approved Unit 5 design head `21b6a92f913661593f80ebee412b6f36ed9d1931` plus this plan commit.
- Do not implement on `main` or the primary worktree.
- Unit 5 must not attach authentication globally to `/api/v1` or modify existing business endpoints.
- Internal JWT algorithm is exactly HS256; never derive the allowed algorithm from token input.
- Required claims are `sub`, `tenant_id`, `roles`, `aud`, `iss`, `iat`, `exp`, `jti`, and `request_id`.
- `roles` must be a JSON array containing exactly one of `viewer`, `contributor`, or `admin`.
- `aud` must be a JSON array containing exactly one configured audience.
- `jti` must be a canonical lowercase hyphenated UUIDv4.
- `sub`, `tenant_id`, and `request_id` must be non-empty strings without surrounding whitespace or Unicode category-C characters and must not exceed 128 UTF-8 bytes.
- `iat` and `exp` must be exact Python integers; booleans, floats, strings, and null are rejected.
- Token lifetime must satisfy `0 < exp - iat <= configured maximum`, where the configured maximum is in `1..180` seconds.
- Default clock skew is five seconds and may be configured only within `0..30` seconds.
- Current-time checks use the exact rules `iat <= now + skew` and `exp > now - skew`; therefore a token exactly five seconds expired is rejected when skew is five seconds, while one four seconds expired is accepted.
- Missing or unsafe JWT settings fail `Settings` construction immediately.
- The shared secret contains at least 32 UTF-8 bytes and is represented with `SecretStr`.
- No code introduced by this unit may log or expose the raw token, shared secret, rejected user ID, tenant ID, role, or claim payload.
- Every authentication failure exposed through FastAPI returns the same `401 INTERNAL_TOKEN_INVALID` envelope and `WWW-Authenticate: Bearer` header.
- Every task follows RED, observed failure, minimal GREEN, affected-suite verification, review, and commit.
- Preserve current `/`, `/health`, `/api/v1/system/info`, and existing business-route behavior.

---

## File Map

### Create

- `extensions/maintenance-api/app/security/__init__.py` — public exports for trusted actor and verifier types.
- `extensions/maintenance-api/app/security/actor.py` — `MaintenanceRole` and immutable `ActorContext`.
- `extensions/maintenance-api/app/security/internal_jwt.py` — strict internal JWT verifier and uniform verifier exception.
- `extensions/maintenance-api/app/security/dependencies.py` — cached verifier construction and FastAPI `get_actor` dependency.
- `extensions/maintenance-api/tests/security/test_internal_jwt.py` — settings, actor, verifier, dependency, and error-envelope coverage.

### Modify

- `extensions/maintenance-api/app/core/config.py` — required secret and bounded issuer, audience, lifetime, and skew settings.
- `extensions/maintenance-api/app/core/exceptions.py` — optional response headers and `InternalAuthenticationError`.
- `extensions/maintenance-api/requirements.txt` — add `PyJWT>=2.10,<3`.
- `extensions/maintenance-api/.env.example` — document canonical internal JWT settings.
- `extensions/maintenance-api/tests/conftest.py` — set deterministic safe JWT settings before importing `app` modules.
- `.superpowers/sdd/progress.md` — mark Unit 5 complete only after every gate passes.

### Preserve

- `extensions/maintenance-api/app/main.py`
- `extensions/maintenance-api/app/api/v1/router.py`
- all existing endpoint modules
- repositories, services, models, and migrations
- all Go files

---

### Task 1: Fail-Closed Internal JWT Settings

**Files:**

- Modify: `extensions/maintenance-api/requirements.txt`
- Modify: `extensions/maintenance-api/app/core/config.py`
- Modify: `extensions/maintenance-api/.env.example`
- Modify: `extensions/maintenance-api/tests/conftest.py`
- Create: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**

- Consumes: existing `Settings(BaseSettings)` and `get_settings()` in `app.core.config`.
- Produces: `Settings.internal_jwt_secret: SecretStr`, `internal_jwt_issuer: str`, `internal_jwt_audience: str`, `internal_jwt_max_lifetime_seconds: int`, and `internal_jwt_clock_skew_seconds: int`.
- Consumed by: Task 3 verifier tests and Task 5 dependency construction.

- [ ] **Step 1: Add the pinned runtime dependency**

Append exactly this line to `extensions/maintenance-api/requirements.txt`:

```text
PyJWT>=2.10,<3
```

Install the updated development environment from the service directory:

```powershell
cd extensions\maintenance-api
python -m pip install -r requirements-dev.txt
```

Expected: installation completes and `python -c "import jwt; print(jwt.__version__)"` reports a `2.x` version not lower than `2.10`.

- [ ] **Step 2: Create the security test module and write failing settings tests**

Create `extensions/maintenance-api/tests/security/test_internal_jwt.py` with this initial content:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

TEST_SECRET = "unit-five-internal-jwt-secret-0001"


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
```

- [ ] **Step 3: Run the settings tests and observe RED**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -v
```

Expected: collection or tests fail because `Settings` has no `internal_jwt_*` fields, missing secrets do not fail, and unsafe values are accepted.

- [ ] **Step 4: Implement the settings contract**

Update imports at the top of `extensions/maintenance-api/app/core/config.py`:

```python
from pydantic import Field, SecretStr, field_validator
```

Add these fields inside `Settings`, immediately after `api_v1_prefix`:

```python
    internal_jwt_secret: SecretStr
    internal_jwt_issuer: str = "weknora"
    internal_jwt_audience: str = "maintenance-api"
    internal_jwt_max_lifetime_seconds: int = Field(default=180, ge=1, le=180)
    internal_jwt_clock_skew_seconds: int = Field(default=5, ge=0, le=30)
```

Add these validators inside `Settings`, before `model_config`:

```python
    @field_validator("internal_jwt_secret")
    @classmethod
    def validate_internal_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("internal JWT secret must contain at least 32 UTF-8 bytes")
        return value

    @field_validator("internal_jwt_issuer", "internal_jwt_audience")
    @classmethod
    def validate_internal_jwt_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("internal JWT issuer and audience must not be blank")
        return normalized
```

Do not give `internal_jwt_secret` a default. This is what makes service startup fail closed.

- [ ] **Step 5: Document settings and bootstrap tests before application imports**

Append to `extensions/maintenance-api/.env.example`:

```text
INTERNAL_JWT_SECRET=replace-with-at-least-32-random-bytes
INTERNAL_JWT_ISSUER=weknora
INTERNAL_JWT_AUDIENCE=maintenance-api
INTERNAL_JWT_MAX_LIFETIME_SECONDS=180
INTERNAL_JWT_CLOCK_SKEW_SECONDS=5
```

In `extensions/maintenance-api/tests/conftest.py`, add these assignments immediately after the existing database environment assignments and before `import app.models`:

```python
os.environ["INTERNAL_JWT_SECRET"] = "unit-five-internal-jwt-secret-0001"
os.environ["INTERNAL_JWT_ISSUER"] = "weknora"
os.environ["INTERNAL_JWT_AUDIENCE"] = "maintenance-api"
os.environ["INTERNAL_JWT_MAX_LIFETIME_SECONDS"] = "180"
os.environ["INTERNAL_JWT_CLOCK_SKEW_SECONDS"] = "5"
```

- [ ] **Step 6: Run focused and public-route regression tests**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -v
python -m pytest tests/test_health.py tests/test_system.py -v
python -m ruff check app/core/config.py tests/conftest.py tests/security/test_internal_jwt.py
```

Expected: all commands pass. Existing public routes continue to start because test configuration is installed before application imports.

- [ ] **Step 7: Review and commit Task 1**

Review:

```powershell
git diff --check
git diff -- extensions/maintenance-api/requirements.txt `
  extensions/maintenance-api/app/core/config.py `
  extensions/maintenance-api/.env.example `
  extensions/maintenance-api/tests/conftest.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Confirm the real secret never appears and no unrelated setting changed.

Commit:

```powershell
git add extensions/maintenance-api/requirements.txt `
  extensions/maintenance-api/app/core/config.py `
  extensions/maintenance-api/.env.example `
  extensions/maintenance-api/tests/conftest.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "feat: configure internal maintenance identity"
```

---

### Task 2: Immutable Single-Role Actor Context

**Files:**

- Create: `extensions/maintenance-api/app/security/__init__.py`
- Create: `extensions/maintenance-api/app/security/actor.py`
- Modify: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**

- Consumes: Python 3.11 `StrEnum` and `dataclass`.
- Produces: `MaintenanceRole` and `ActorContext(user_id, tenant_id, role, request_id, token_id)`.
- Consumed by: Tasks 3–5.

- [ ] **Step 1: Append failing actor tests**

Append these imports to `tests/security/test_internal_jwt.py`:

```python
from dataclasses import FrozenInstanceError

from app.security.actor import ActorContext, MaintenanceRole
```

Append these tests:

```python
def test_actor_context_is_immutable_and_single_role() -> None:
    actor = ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-1",
        token_id="5ea49880-7b27-4d9e-a383-1219b8164dc0",
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
        token_id="5ea49880-7b27-4d9e-a383-1219b8164dc0",
    )

    assert not hasattr(actor, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(actor, "unexpected", "value")
```

- [ ] **Step 2: Run the actor tests and observe RED**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k Actor -v
```

Expected: collection fails because `app.security.actor` does not exist.

- [ ] **Step 3: Implement `MaintenanceRole` and `ActorContext`**

Create `extensions/maintenance-api/app/security/actor.py`:

```python
from dataclasses import dataclass
from enum import StrEnum


class MaintenanceRole(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str
    tenant_id: str
    role: MaintenanceRole
    request_id: str
    token_id: str
```

Create `extensions/maintenance-api/app/security/__init__.py`:

```python
from app.security.actor import ActorContext, MaintenanceRole

__all__ = ["ActorContext", "MaintenanceRole"]
```

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k Actor -v
python -m ruff check app/security/actor.py app/security/__init__.py `
  tests/security/test_internal_jwt.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Review and commit Task 2**

Review:

```powershell
git diff --check
git diff -- extensions/maintenance-api/app/security `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Commit:

```powershell
git add extensions/maintenance-api/app/security/__init__.py `
  extensions/maintenance-api/app/security/actor.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "feat: define maintenance actor context"
```

---

### Task 3: HS256 Verification and Canonical Happy Path

**Files:**

- Create: `extensions/maintenance-api/app/security/internal_jwt.py`
- Modify: `extensions/maintenance-api/app/security/__init__.py`
- Modify: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**

- Consumes: `ActorContext`, `MaintenanceRole`, PyJWT, and an aware UTC `clock: Callable[[], datetime]`.
- Produces: `InternalTokenError` and `InternalTokenVerifier.verify(token: str) -> ActorContext`.
- Consumed by: Tasks 4 and 5.

- [ ] **Step 1: Add deterministic token helpers and failing happy-path tests**

Add these imports to `tests/security/test_internal_jwt.py`:

```python
import base64
import json
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

import jwt

from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier
```

Add these constants and helpers below `TEST_SECRET`:

```python
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
    return jwt.encode(payload or canonical_payload(), secret, algorithm=algorithm)


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
```

Append these tests:

```python
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

    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(token)


@pytest.mark.parametrize("claim", canonical_payload().keys())
def test_verifier_requires_every_claim(claim: str) -> None:
    payload = canonical_payload()
    del payload[claim]

    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(encode_token(payload))
```

- [ ] **Step 2: Run verifier tests and observe RED**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k Verifier -v
```

Expected: collection fails because `app.security.internal_jwt` does not exist.

- [ ] **Step 3: Implement the verifier skeleton and canonical projection**

Create `extensions/maintenance-api/app/security/internal_jwt.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unicodedata import category
from uuid import UUID

import jwt
from jwt import PyJWTError

from app.security.actor import ActorContext, MaintenanceRole

REQUIRED_CLAIMS = (
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
SUPPORTED_ROLES = {role.value: role for role in MaintenanceRole}


class InternalTokenError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InternalTokenVerifier:
    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        max_lifetime_seconds: int = 180,
        clock_skew_seconds: int = 5,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("internal JWT secret must contain at least 32 UTF-8 bytes")
        if not issuer.strip():
            raise ValueError("internal JWT issuer must not be blank")
        if not audience.strip():
            raise ValueError("internal JWT audience must not be blank")
        if type(max_lifetime_seconds) is not int or not 1 <= max_lifetime_seconds <= 180:
            raise ValueError("internal JWT maximum lifetime must be within 1..180 seconds")
        if type(clock_skew_seconds) is not int or not 0 <= clock_skew_seconds <= 30:
            raise ValueError("internal JWT clock skew must be within 0..30 seconds")

        self._secret = secret
        self._issuer = issuer.strip()
        self._audience = audience.strip()
        self._max_lifetime_seconds = max_lifetime_seconds
        self._clock_skew_seconds = clock_skew_seconds
        self._clock = clock

    def verify(self, token: str) -> ActorContext:
        try:
            if type(token) is not str or not token.strip():
                raise InternalTokenError("invalid internal JWT")

            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": list(REQUIRED_CLAIMS),
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            return self._project_claims(claims)
        except InternalTokenError:
            raise
        except (PyJWTError, KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise InternalTokenError("invalid internal JWT") from exc

    def _project_claims(self, claims: dict[str, Any]) -> ActorContext:
        user_id = self._safe_string(claims["sub"])
        tenant_id = self._safe_string(claims["tenant_id"])
        request_id = self._safe_string(claims["request_id"])
        self._validate_issuer_and_audience(claims)
        role = self._validate_role(claims["roles"])
        token_id = self._validate_token_id(claims["jti"])
        self._validate_time_claims(claims["iat"], claims["exp"])

        return ActorContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            request_id=request_id,
            token_id=token_id,
        )

    @staticmethod
    def _safe_string(value: object) -> str:
        if type(value) is not str or not value or value != value.strip():
            raise InternalTokenError("invalid internal JWT")
        if len(value.encode("utf-8")) > 128:
            raise InternalTokenError("invalid internal JWT")
        if any(category(character).startswith("C") for character in value):
            raise InternalTokenError("invalid internal JWT")
        return value

    def _validate_issuer_and_audience(self, claims: dict[str, Any]) -> None:
        issuer = claims["iss"]
        audience = claims["aud"]
        if type(issuer) is not str or issuer != self._issuer:
            raise InternalTokenError("invalid internal JWT")
        if (
            type(audience) is not list
            or len(audience) != 1
            or type(audience[0]) is not str
            or audience[0] != self._audience
        ):
            raise InternalTokenError("invalid internal JWT")

    @staticmethod
    def _validate_role(value: object) -> MaintenanceRole:
        if type(value) is not list or len(value) != 1 or type(value[0]) is not str:
            raise InternalTokenError("invalid internal JWT")
        role = SUPPORTED_ROLES.get(value[0])
        if role is None:
            raise InternalTokenError("invalid internal JWT")
        return role

    @staticmethod
    def _validate_token_id(value: object) -> str:
        if type(value) is not str or value != value.strip():
            raise InternalTokenError("invalid internal JWT")
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise InternalTokenError("invalid internal JWT")
        return value

    def _validate_time_claims(self, issued_at: object, expires_at: object) -> None:
        if type(issued_at) is not int or type(expires_at) is not int:
            raise InternalTokenError("invalid internal JWT")

        lifetime = expires_at - issued_at
        if lifetime <= 0 or lifetime > self._max_lifetime_seconds:
            raise InternalTokenError("invalid internal JWT")

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise InternalTokenError("invalid internal JWT")
        now_timestamp = int(now.astimezone(timezone.utc).timestamp())

        if issued_at > now_timestamp + self._clock_skew_seconds:
            raise InternalTokenError("invalid internal JWT")
        if expires_at <= now_timestamp - self._clock_skew_seconds:
            raise InternalTokenError("invalid internal JWT")
```

Update `app/security/__init__.py`:

```python
from app.security.actor import ActorContext, MaintenanceRole
from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier

__all__ = [
    "ActorContext",
    "InternalTokenError",
    "InternalTokenVerifier",
    "MaintenanceRole",
]
```

- [ ] **Step 4: Run the canonical verifier tests**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k Verifier -v
python -m ruff check app/security tests/security/test_internal_jwt.py
```

Expected: all current verifier tests pass.

- [ ] **Step 5: Add explicit wrong-algorithm tests**

Append helper:

```python
def replace_algorithm_header(token: str, algorithm: str) -> str:
    header = json.dumps({"alg": algorithm, "typ": "JWT"}, separators=(",", ":")).encode()
    encoded_header = base64.urlsafe_b64encode(header).rstrip(b"=").decode()
    _, payload, signature = token.split(".")
    return f"{encoded_header}.{payload}.{signature}"
```

Append tests:

```python
@pytest.mark.parametrize("algorithm", ["none", "HS384", "HS512", "RS256"])
def test_verifier_rejects_every_non_hs256_header(algorithm: str) -> None:
    forged = replace_algorithm_header(encode_token(), algorithm)

    with pytest.raises(InternalTokenError, match="invalid internal JWT"):
        make_verifier().verify(forged)


def test_verifier_accepts_only_canonical_hs256_header() -> None:
    token = encode_token()
    assert jwt.get_unverified_header(token)["alg"] == "HS256"

    assert make_verifier().verify(token).user_id == "user-1"
```

- [ ] **Step 6: Run algorithm and full focused tests**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "algorithm or hs256" -v
python -m pytest tests/security/test_internal_jwt.py -v
```

Expected: PASS. The forged RS256 fixture requires no asymmetric dependency because only the compact-token header is changed and the fixed whitelist rejects it before signature interpretation.

- [ ] **Step 7: Review and commit Task 3**

Review the verifier for a hard-coded `algorithms=["HS256"]`, disabled built-in time checks, and no logging.

```powershell
git diff --check
git diff -- extensions/maintenance-api/app/security `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Commit:

```powershell
git add extensions/maintenance-api/app/security `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "feat: verify internal maintenance tokens"
```

---

### Task 4: Strict Claims, UUID, Lifetime, and Clock Boundaries

**Files:**

- Modify: `extensions/maintenance-api/app/security/internal_jwt.py`
- Modify: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**

- Consumes: Task 3 `InternalTokenVerifier` and token helpers.
- Produces: complete Unit 5 verifier contract, including strict type and boundary rejection.
- Consumed by: Task 5 HTTP dependency.

- [ ] **Step 1: Add strict string-claim rejection tests**

Append:

```python
@pytest.mark.parametrize("claim", ["sub", "tenant_id", "request_id"])
@pytest.mark.parametrize("value", [123, True, [], {}, None])
def test_verifier_rejects_non_string_actor_claims(claim: str, value: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(**{claim: value})))


@pytest.mark.parametrize("claim", ["sub", "tenant_id", "request_id"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        " leading",
        "trailing ",
        "line\nfeed",
        "carriage\rreturn",
        "tab\tvalue",
        "null\x00value",
        "zero\u200bwidth",
        "x" * 129,
        "界" * 43,
    ],
)
def test_verifier_rejects_unsafe_actor_strings(claim: str, value: str) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(**{claim: value})))


def test_verifier_accepts_exactly_128_utf8_bytes() -> None:
    actor = make_verifier().verify(encode_token(canonical_payload(sub="x" * 128)))

    assert actor.user_id == "x" * 128
```

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "actor_claims or actor_strings or 128" -v
```

Expected: PASS if Task 3 implementation is complete. A failure identifies a concrete strictness defect; fix only the demonstrated helper.

- [ ] **Step 2: Add strict audience and role-shape tests**

Append:

```python
@pytest.mark.parametrize(
    "audience",
    [
        "maintenance-api",
        [],
        ["maintenance-api", "other"],
        [123],
        ["other"],
        None,
    ],
)
def test_verifier_requires_single_element_audience_array(audience: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(aud=audience)))


@pytest.mark.parametrize(
    "roles",
    [
        "viewer",
        [],
        ["viewer", "admin"],
        ["owner"],
        ["Admin"],
        [" admin"],
        [123],
        [["admin"]],
        None,
    ],
)
def test_verifier_requires_one_supported_role(roles: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(roles=roles)))


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("viewer", MaintenanceRole.VIEWER),
        ("contributor", MaintenanceRole.CONTRIBUTOR),
        ("admin", MaintenanceRole.ADMIN),
    ],
)
def test_verifier_accepts_each_supported_single_role(
    role: str, expected: MaintenanceRole
) -> None:
    actor = make_verifier().verify(encode_token(canonical_payload(roles=[role])))

    assert actor.role is expected
```

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "audience or supported_role" -v
```

Expected: PASS.

- [ ] **Step 3: Add canonical UUIDv4 tests**

Append:

```python
@pytest.mark.parametrize(
    "token_id",
    [
        "",
        "not-a-uuid",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "6fa459ea-ee8a-3ca4-894e-db77e160355e",
        "886313e1-3b8a-5372-9b90-0c9aee199e5d",
        CANONICAL_JTI.upper(),
        "{" + CANONICAL_JTI + "}",
        " " + CANONICAL_JTI,
        CANONICAL_JTI + " ",
        123,
        None,
    ],
)
def test_verifier_requires_canonical_lowercase_uuid4(token_id: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(jti=token_id)))


def test_verifier_accepts_generated_canonical_uuid4() -> None:
    token_id = str(uuid4())

    assert make_verifier().verify(
        encode_token(canonical_payload(jti=token_id))
    ).token_id == token_id
```

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "uuid4" -v
```

Expected: PASS.

- [ ] **Step 4: Add exact numeric-type and lifetime tests**

Append:

```python
@pytest.mark.parametrize("claim", ["iat", "exp"])
@pytest.mark.parametrize("value", [True, False, 1.5, "1784956800", None])
def test_verifier_rejects_non_integer_numeric_dates(claim: str, value: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(**{claim: value})))


@pytest.mark.parametrize(
    ("issued_at", "expires_at"),
    [
        (FIXED_NOW_TS, FIXED_NOW_TS),
        (FIXED_NOW_TS + 1, FIXED_NOW_TS),
        (FIXED_NOW_TS, FIXED_NOW_TS + 181),
    ],
)
def test_verifier_rejects_invalid_lifetime(issued_at: int, expires_at: int) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(
            encode_token(canonical_payload(iat=issued_at, exp=expires_at))
        )


def test_verifier_honors_stricter_configured_lifetime() -> None:
    token = encode_token(canonical_payload(exp=FIXED_NOW_TS + 91))

    with pytest.raises(InternalTokenError):
        make_verifier(max_lifetime_seconds=90).verify(token)


def test_verifier_accepts_exact_maximum_lifetime() -> None:
    actor = make_verifier().verify(
        encode_token(canonical_payload(exp=FIXED_NOW_TS + 180))
    )

    assert actor.user_id == "user-1"
```

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "numeric_dates or lifetime" -v
```

Expected: PASS.

- [ ] **Step 5: Add fixed clock-skew boundary tests**

Append:

```python
def test_verifier_accepts_iat_at_future_skew_boundary() -> None:
    actor = make_verifier().verify(
        encode_token(
            canonical_payload(
                iat=FIXED_NOW_TS + 5,
                exp=FIXED_NOW_TS + 180,
            )
        )
    )

    assert actor.user_id == "user-1"


def test_verifier_rejects_iat_beyond_future_skew() -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(
            encode_token(
                canonical_payload(
                    iat=FIXED_NOW_TS + 6,
                    exp=FIXED_NOW_TS + 180,
                )
            )
        )


def test_verifier_accepts_token_expired_four_seconds_with_five_second_skew() -> None:
    actor = make_verifier().verify(
        encode_token(
            canonical_payload(
                iat=FIXED_NOW_TS - 184,
                exp=FIXED_NOW_TS - 4,
            )
        )
    )

    assert actor.user_id == "user-1"


def test_verifier_rejects_token_expired_exactly_five_seconds() -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(
            encode_token(
                canonical_payload(
                    iat=FIXED_NOW_TS - 185,
                    exp=FIXED_NOW_TS - 5,
                )
            )
        )


def test_verifier_zero_skew_requires_future_expiration() -> None:
    with pytest.raises(InternalTokenError):
        make_verifier(clock_skew_seconds=0).verify(
            encode_token(
                canonical_payload(
                    iat=FIXED_NOW_TS - 180,
                    exp=FIXED_NOW_TS,
                )
            )
        )


def test_verifier_rejects_naive_clock() -> None:
    with pytest.raises(InternalTokenError):
        make_verifier(clock=lambda: FIXED_NOW.replace(tzinfo=None)).verify(encode_token())
```

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "skew or naive_clock" -v
```

Expected: PASS with the exact approved boundary semantics.

- [ ] **Step 6: Run complete verifier tests and inspect coverage by test list**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py --collect-only -q
python -m pytest tests/security/test_internal_jwt.py -v
python -m ruff check app/security tests/security/test_internal_jwt.py
```

Expected: all tests pass. Inspect the collected names and confirm there is explicit coverage for algorithm, required claims, type strictness, string safety, audience shape, role cardinality, UUIDv4, lifetime, future `iat`, expiration, and naive clocks.

- [ ] **Step 7: Review and commit Task 4**

Review:

```powershell
git diff --check
git diff -- extensions/maintenance-api/app/security/internal_jwt.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Confirm clock skew appears only in comparisons against `now`, never in `exp - iat`.

Commit:

```powershell
git add extensions/maintenance-api/app/security/internal_jwt.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "test: harden internal maintenance claims"
```

---

### Task 5: Uniform FastAPI Authentication Dependency

**Files:**

- Create: `extensions/maintenance-api/app/security/dependencies.py`
- Modify: `extensions/maintenance-api/app/security/__init__.py`
- Modify: `extensions/maintenance-api/app/core/exceptions.py`
- Modify: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**

- Consumes: `get_settings()`, `InternalTokenVerifier`, `ActorContext`, existing `AppException`, and `register_exception_handlers()`.
- Produces: `InternalAuthenticationError`, `get_internal_token_verifier() -> InternalTokenVerifier`, and `get_actor(...) -> ActorContext`.
- Consumed by: Unit 6 permission dependencies and all later authenticated Maintenance routes.

- [ ] **Step 1: Write failing exception-header tests**

Add these imports to `tests/security/test_internal_jwt.py`:

```python
from app.core.exceptions import InternalAuthenticationError
```

Append:

```python
def test_internal_authentication_error_has_fixed_contract() -> None:
    error = InternalAuthenticationError()

    assert error.status_code == 401
    assert error.code == "INTERNAL_TOKEN_INVALID"
    assert error.message == "Internal authentication failed"
    assert error.details is None
    assert error.headers == {"WWW-Authenticate": "Bearer"}


def test_app_exception_headers_are_defensively_copied() -> None:
    source = {"WWW-Authenticate": "Bearer"}
    error = InternalAuthenticationError()
    source["WWW-Authenticate"] = "Basic"

    assert error.headers == {"WWW-Authenticate": "Bearer"}
```

- [ ] **Step 2: Run the exception tests and observe RED**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "authentication_error or defensively" -v
```

Expected: collection fails because `InternalAuthenticationError` and `AppException.headers` do not exist.

- [ ] **Step 3: Extend the project exception contract minimally**

Update imports in `app/core/exceptions.py`:

```python
from collections.abc import Mapping
from typing import Any
```

Extend `AppException.__init__`:

```python
class AppException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = dict(headers) if headers is not None else None
```

Add this exception after `AppException`:

```python
class InternalAuthenticationError(AppException):
    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            code="INTERNAL_TOKEN_INVALID",
            message="Internal authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

Pass headers in the existing handler:

```python
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=jsonable_encoder(
                build_error_body(code=exc.code, message=exc.message, details=exc.details)
            ),
        )
```

- [ ] **Step 4: Run exception and existing error regression tests**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "authentication_error or defensively" -v
python -m pytest tests/test_health.py -v
python -m ruff check app/core/exceptions.py tests/security/test_internal_jwt.py
```

Expected: PASS. Existing 503 error bodies remain unchanged.

- [ ] **Step 5: Write failing dependency and HTTP-envelope tests**

Add imports:

```python
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import register_exception_handlers
from app.security.dependencies import get_actor, get_internal_token_verifier
```

Append fixture:

```python
@pytest.fixture()
def protected_client() -> Generator[TestClient, None, None]:
    application = FastAPI()
    register_exception_handlers(application)
    application.dependency_overrides[get_internal_token_verifier] = make_verifier

    @application.get("/protected")
    def protected(
        actor: Annotated[ActorContext, Depends(get_actor)],
    ) -> dict[str, str]:
        return {
            "user_id": actor.user_id,
            "tenant_id": actor.tenant_id,
            "role": actor.role.value,
            "request_id": actor.request_id,
            "token_id": actor.token_id,
        }

    with TestClient(application) as client:
        yield client
```

Append tests:

```python
@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic abc123",
        "Bearer",
        "Bearer invalid-token",
    ],
)
def test_get_actor_returns_uniform_401(
    protected_client: TestClient, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}

    response = protected_client.get("/protected", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "success": False,
        "error": {
            "code": "INTERNAL_TOKEN_INVALID",
            "message": "Internal authentication failed",
            "details": None,
        },
    }
    assert "invalid-token" not in response.text


def test_get_actor_returns_same_401_for_expired_token(protected_client: TestClient) -> None:
    token = encode_token(
        canonical_payload(
            iat=FIXED_NOW_TS - 186,
            exp=FIXED_NOW_TS - 6,
        )
    )

    response = protected_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INTERNAL_TOKEN_INVALID"
    assert response.json()["error"]["details"] is None


def test_get_actor_returns_verified_actor(protected_client: TestClient) -> None:
    response = protected_client.get(
        "/protected", headers={"Authorization": f"Bearer {encode_token()}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "tenant_id": "12",
        "role": "contributor",
        "request_id": "request-1",
        "token_id": CANONICAL_JTI,
    }
```

- [ ] **Step 6: Run dependency tests and observe RED**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "get_actor" -v
```

Expected: collection fails because `app.security.dependencies` does not exist.

- [ ] **Step 7: Implement cached verifier construction and `get_actor`**

Create `extensions/maintenance-api/app/security/dependencies.py`:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.exceptions import InternalAuthenticationError
from app.security.actor import ActorContext
from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier

internal_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_internal_token_verifier() -> InternalTokenVerifier:
    settings = get_settings()
    return InternalTokenVerifier(
        secret=settings.internal_jwt_secret.get_secret_value(),
        issuer=settings.internal_jwt_issuer,
        audience=settings.internal_jwt_audience,
        max_lifetime_seconds=settings.internal_jwt_max_lifetime_seconds,
        clock_skew_seconds=settings.internal_jwt_clock_skew_seconds,
    )


def get_actor(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(internal_bearer),
    ],
    verifier: Annotated[
        InternalTokenVerifier,
        Depends(get_internal_token_verifier),
    ],
) -> ActorContext:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise InternalAuthenticationError()

    try:
        return verifier.verify(credentials.credentials)
    except InternalTokenError as exc:
        raise InternalAuthenticationError() from exc
```

Update `app/security/__init__.py` to export the dependency functions:

```python
from app.security.actor import ActorContext, MaintenanceRole
from app.security.dependencies import get_actor, get_internal_token_verifier
from app.security.internal_jwt import InternalTokenError, InternalTokenVerifier

__all__ = [
    "ActorContext",
    "InternalTokenError",
    "InternalTokenVerifier",
    "MaintenanceRole",
    "get_actor",
    "get_internal_token_verifier",
]
```

- [ ] **Step 8: Run dependency, envelope, and public-route regression tests**

Run:

```powershell
python -m pytest tests/security/test_internal_jwt.py -k "get_actor" -v
python -m pytest tests/security/test_internal_jwt.py -v
python -m pytest tests/test_health.py tests/test_system.py -v
python -m ruff check app/security app/core/config.py app/core/exceptions.py `
  tests/security/test_internal_jwt.py
```

Expected: all commands pass. No production route was added or protected.

- [ ] **Step 9: Review and commit Task 5**

Review:

```powershell
git diff --check
git diff -- extensions/maintenance-api/app/security `
  extensions/maintenance-api/app/core/exceptions.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Confirm all HTTP failures instantiate the same exception and no exception detail reaches the response.

Commit:

```powershell
git add extensions/maintenance-api/app/security `
  extensions/maintenance-api/app/core/exceptions.py `
  extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "feat: expose internal maintenance actor dependency"
```

---

### Task 6: Unit 5 Integration, Regression, Security Review, and Ledger

**Files:**

- Modify only if a failing approved test proves a defect: Unit 5 files listed in the File Map.
- Modify after all gates pass: `.superpowers/sdd/progress.md`.

**Interfaces:**

- Consumes: complete Tasks 1–5 implementation.
- Produces: reviewed Unit 5 completion commit and persisted recovery state for Unit 6.

- [ ] **Step 1: Verify the branch and clean starting state**

Run from the repository worktree:

```powershell
git branch --show-current
git status --short
git rev-parse HEAD
```

Expected:

```text
feature/maintenance-frontend-plan05
```

`git status --short` must be empty before final gates.

- [ ] **Step 2: Run focused Unit 5 tests**

```powershell
cd extensions\maintenance-api
python -m pytest tests/security/test_internal_jwt.py -v
```

Expected: PASS for settings, actor immutability, HS256 whitelist, every required claim, strict types, string safety, role cardinality, audience shape, UUIDv4, lifetime, skew, dependency, and HTTP envelope.

- [ ] **Step 3: Run affected public-route regressions**

```powershell
python -m pytest tests/test_health.py tests/test_system.py -v
```

Expected: PASS. `/`, `/health`, and `/api/v1/system/info` retain their existing behavior and response shape.

- [ ] **Step 4: Run Ruff on the approved scope**

```powershell
python -m ruff check app/security app/core/config.py app/core/exceptions.py `
  tests/conftest.py tests/security/test_internal_jwt.py
```

Expected: `All checks passed!`.

- [ ] **Step 5: Run the complete Maintenance API suite**

```powershell
python -m pytest -v
```

Expected: all existing non-performance, non-external tests pass under the new required settings bootstrap.

If a failure is unrelated to Unit 5, record the exact failing test and existing baseline evidence before changing any file. Do not broaden Unit 5 to repair unrelated behavior.

- [ ] **Step 6: Run static security scans over changed code**

From the repository root:

```powershell
$files = @(
  "extensions/maintenance-api/app/security/__init__.py",
  "extensions/maintenance-api/app/security/actor.py",
  "extensions/maintenance-api/app/security/internal_jwt.py",
  "extensions/maintenance-api/app/security/dependencies.py",
  "extensions/maintenance-api/app/core/config.py",
  "extensions/maintenance-api/app/core/exceptions.py",
  "extensions/maintenance-api/tests/security/test_internal_jwt.py"
)

Select-String -Path $files -Pattern 'print\(|logger\.|logging\.|token\s*=.*log|secret\s*=.*log'
Select-String -Path extensions/maintenance-api/app/security/internal_jwt.py `
  -Pattern 'algorithms=\["HS256"\]'
Select-String -Path extensions/maintenance-api/app/security/internal_jwt.py `
  -Pattern 'verify_exp.*False|verify_iat.*False'
```

Expected:

- the first command returns no logging or print statements;
- the second command finds exactly the fixed HS256 whitelist;
- the third command confirms built-in wall-clock checks are disabled so the injectable manual clock is authoritative.

- [ ] **Step 7: Confirm no router or unrelated code changed**

Run:

```powershell
git diff --name-only 21b6a92f913661593f80ebee412b6f36ed9d1931...HEAD
```

The list may contain only:

```text
docs/superpowers/plans/2026-07-25-maintenance-unit05-internal-jwt-implementation.md
extensions/maintenance-api/app/security/__init__.py
extensions/maintenance-api/app/security/actor.py
extensions/maintenance-api/app/security/internal_jwt.py
extensions/maintenance-api/app/security/dependencies.py
extensions/maintenance-api/app/core/config.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/requirements.txt
extensions/maintenance-api/.env.example
extensions/maintenance-api/tests/conftest.py
extensions/maintenance-api/tests/security/test_internal_jwt.py
```

Before the ledger update, `app/main.py`, `app/api/v1/router.py`, endpoint modules, repositories, services, models, migrations, and all Go files must be absent.

- [ ] **Step 8: Perform the final specification review**

Check each statement against tests and code:

1. Settings construction fails without a secret.
2. Secret length uses UTF-8 bytes and is at least 32.
3. `SecretStr` masks diagnostics.
4. Only HS256 is accepted.
5. All nine claims are required.
6. Audience and role are exact one-element arrays.
7. Actor strings reject whitespace, category-C characters, and values above 128 UTF-8 bytes.
8. `jti` is canonical lowercase UUIDv4.
9. Numeric dates reject bool and non-int values.
10. Lifetime remains positive and at most 180 seconds.
11. Skew affects only `now` comparisons.
12. `ActorContext` is frozen, slotted, and single-role.
13. Every HTTP authentication failure has the same 401 body and Bearer challenge.
14. Existing routers remain unprotected in Unit 5.
15. No sensitive values are logged.

Any failed statement requires a new focused regression test before changing production code.

- [ ] **Step 9: Update the durable progress ledger only after every gate passes**

In `.superpowers/sdd/progress.md`, replace the Unit 5 line with:

```text
- Unit 5: complete — FastAPI internal HS256 JWT verification implemented with fail-closed SecretStr settings, strict single-role claims, canonical UUIDv4 token IDs, deterministic lifetime and clock-skew checks, immutable ActorContext projection, uniform 401 Bearer errors, focused and full-suite verification, and security review clean.
```

Do not change the Unit 6 line.

Commit:

```powershell
cd ..\..
git add .superpowers/sdd/progress.md
git commit -m "docs: mark maintenance unit 5 complete"
```

- [ ] **Step 10: Final clean-state evidence**

Run:

```powershell
git status --short
git log --oneline -8
git diff --check 21b6a92f913661593f80ebee412b6f36ed9d1931...HEAD
```

Expected:

- clean working tree;
- task-isolated commits visible;
- no whitespace errors.

---

## Planned Commit Sequence

```text
docs: add maintenance unit 5 implementation plan
feat: configure internal maintenance identity
feat: define maintenance actor context
feat: verify internal maintenance tokens
test: harden internal maintenance claims
feat: expose internal maintenance actor dependency
docs: mark maintenance unit 5 complete
```

## Execution Gate

Do not begin Task 1 until this implementation plan has been reviewed and explicitly approved. After approval, execute one task at a time. Each task requires observed RED evidence, GREEN evidence, focused regression results, an inline specification and quality review, and a clean commit before the next task starts.

# Maintenance Unit 05 Internal JWT Verification Design

**Status:** Approved design, pending written-spec review

**Repository:** `deifeb/maintenance-support-weknora`

**Branch:** `feature/maintenance-frontend-plan05`

**Starting point:** Unit 4 completion commit `b0ce7cec6545328261b35fb44f720cb8cd57aaa2`

## 1. Goal

Unit 5 establishes the Maintenance FastAPI service's trusted internal identity boundary. It verifies the short-lived HS256 token issued by the WeKnora Go proxy and converts the verified claims into an immutable `ActorContext` that later units can use for role enforcement, tenant scoping, response metadata, idempotency, auditing, and optimistic concurrency.

This unit does not protect existing business routers yet. It provides the verifier and FastAPI dependency only. Unit 6 will apply role-aware dependencies and response metadata to business operations.

## 2. Confirmed Decisions

The following decisions are fixed for Unit 5.

1. **Integration scope:** implement `ActorContext`, a strict internal JWT verifier, and `get_actor`; do not attach authentication globally to the existing `/api/v1` router.
2. **Startup behavior:** missing or unsafe internal JWT configuration fails settings construction immediately.
3. **Clock skew:** allow five seconds of clock skew while still requiring `0 < exp - iat <= 180`.
4. **Role cardinality:** `roles` must be an array containing exactly one supported role.
5. **Client-facing errors:** every authentication failure produces the same 401 response and never exposes the specific verification reason.
6. **Claim strictness:** claim types are not coerced; strings are bounded and control-character free; `jti` must be a canonical lowercase UUIDv4.

## 3. Current Repository Context

The Maintenance API currently:

- loads configuration through `app/core/config.py` using Pydantic Settings;
- registers project-level exception handlers through `app/core/exceptions.py`;
- registers public and business routers from `app/main.py`;
- has no existing `app/security` package;
- does not currently depend on PyJWT;
- sets test environment variables in `tests/conftest.py` before importing application modules.

The existing exception contract is:

```json
{
  "success": false,
  "error": {
    "code": "...",
    "message": "...",
    "details": null
  }
}
```

Unit 5 preserves this envelope.

## 4. Scope

### 4.1 Files to create

```text
extensions/maintenance-api/app/security/__init__.py
extensions/maintenance-api/app/security/actor.py
extensions/maintenance-api/app/security/internal_jwt.py
extensions/maintenance-api/app/security/dependencies.py
extensions/maintenance-api/tests/security/test_internal_jwt.py
```

### 4.2 Files to modify

```text
extensions/maintenance-api/app/core/config.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/requirements.txt
extensions/maintenance-api/.env.example
extensions/maintenance-api/tests/conftest.py
```

### 4.3 Explicitly out of scope

Unit 5 must not modify:

- `app/main.py`;
- `app/api/v1/router.py`;
- existing business endpoints;
- repositories or services;
- SQLAlchemy models or migrations;
- Go configuration, signer, proxy, resolver, or router code;
- role-floor enforcement, which belongs to Unit 6;
- tenant query scoping, which belongs to Units 7 and 8.

## 5. Architecture

The security boundary contains three focused components.

```text
Authorization: Bearer <internal JWT>
                 |
                 v
        FastAPI HTTPBearer parser
                 |
                 v
              get_actor
                 |
                 v
       InternalTokenVerifier.verify
                 |
                 v
     immutable single-role ActorContext
```

### 5.1 `actor.py`

This module defines only the trusted identity value objects.

```python
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

Design requirements:

- `ActorContext` is immutable;
- `slots=True` prevents arbitrary attributes;
- the actor contains one role, matching the Go signer contract;
- no raw JWT or secret is stored in the actor;
- no authorization ranking logic belongs in this module.

### 5.2 `internal_jwt.py`

This module owns token verification and claim projection.

Public interface:

```python
class InternalTokenError(ValueError):
    pass


class InternalTokenVerifier:
    def verify(self, token: str) -> ActorContext:
        """Verify the internal token and return a trusted actor."""
```

The verifier constructor accepts:

```text
secret
issuer
audience
max_lifetime_seconds = 180
clock_skew_seconds = 5
clock = UTC current-time callable
```

The injectable clock is part of the verifier's constructor for deterministic tests. Production dependency construction uses the default UTC clock. No external time-freezing package is added.

### 5.3 `dependencies.py`

This module adapts FastAPI credentials to the verifier.

Public interface:

```python
get_internal_token_verifier() -> InternalTokenVerifier
get_actor(...) -> ActorContext
```

`get_actor` uses `HTTPBearer(auto_error=False)` so the project controls every failure response instead of FastAPI emitting a separate default envelope.

This dependency is reusable but is not attached to current routers in Unit 5.

## 6. Configuration Contract

`Settings` gains the following fields:

```python
internal_jwt_secret: SecretStr
internal_jwt_issuer: str = "weknora"
internal_jwt_audience: str = "maintenance-api"
internal_jwt_max_lifetime_seconds: int = 180
internal_jwt_clock_skew_seconds: int = 5
```

Environment variables:

```text
INTERNAL_JWT_SECRET
INTERNAL_JWT_ISSUER
INTERNAL_JWT_AUDIENCE
INTERNAL_JWT_MAX_LIFETIME_SECONDS
INTERNAL_JWT_CLOCK_SKEW_SECONDS
```

### 6.1 Startup validation

Settings construction fails when any of these conditions is true:

- `INTERNAL_JWT_SECRET` is missing;
- the secret contains fewer than 32 UTF-8 bytes;
- issuer is blank after trimming;
- audience is blank after trimming;
- maximum lifetime is outside `1..180` seconds;
- clock skew is outside `0..30` seconds.

The maximum lifetime remains configurable only to permit a stricter deployment value. It can never exceed the Go contract's 180-second maximum.

### 6.2 Secret handling

- use `pydantic.SecretStr`;
- use `get_secret_value()` only at verifier construction;
- do not include the secret in validation messages;
- do not log the settings object's secret value;
- tests must verify that `repr(settings)` and validation errors do not expose the real secret.

### 6.3 Test environment

`tests/conftest.py` sets a fixed test secret before importing any `app` module:

```text
INTERNAL_JWT_SECRET=<fixed value containing at least 32 UTF-8 bytes>
INTERNAL_JWT_ISSUER=weknora
INTERNAL_JWT_AUDIENCE=maintenance-api
INTERNAL_JWT_MAX_LIFETIME_SECONDS=180
INTERNAL_JWT_CLOCK_SKEW_SECONDS=5
```

This preserves startup-fail-closed behavior without breaking unrelated test collection.

## 7. JWT Contract

The verifier accepts only tokens matching the Go Unit 2 signer contract.

Required claims:

```text
sub
tenant_id
roles
aud
iss
iat
exp
jti
request_id
```

Expected example payload:

```json
{
  "sub": "user-1",
  "tenant_id": "12",
  "roles": ["contributor"],
  "aud": ["maintenance-api"],
  "iss": "weknora",
  "iat": 1784956800,
  "exp": 1784956980,
  "jti": "5ea49880-7b27-4d9e-a383-1219b8164dc0",
  "request_id": "request-1"
}
```

## 8. Verification Pipeline

`InternalTokenVerifier.verify` applies the following ordered checks.

### 8.1 Token and algorithm

1. token must be a non-empty string;
2. decode using PyJWT with `algorithms=["HS256"]` only;
3. reject `none`, HS384, HS512, RS256, and algorithm-confusion attempts;
4. verify the signature with the configured shared secret.

### 8.2 Registered claims

5. require all nine claims;
6. verify issuer against the configured issuer;
7. verify audience against the configured audience;
8. require `aud` to be a JSON array containing exactly one string equal to the configured audience;
9. disable PyJWT's wall-clock `exp` and `iat` decisions while retaining required-claim, signature, issuer, and audience verification;
10. validate `iat` and `exp` manually against the injected UTC clock and configured skew.

Manual time validation is required because the verifier must use a deterministic injected clock and must reject bool, float, and string numeric dates before applying time arithmetic.

### 8.3 Strict types

No implicit type coercion is permitted.

- `sub`, `tenant_id`, `iss`, `jti`, and `request_id` must be strings;
- `roles` must be a list, not a tuple, string, set, or object;
- the role list must contain exactly one string;
- `aud` must be a list containing exactly one string;
- `iat` and `exp` must be integers;
- booleans are rejected for numeric date claims even though `bool` is an `int` subclass in Python.

### 8.4 String safety

`sub`, `tenant_id`, and `request_id` must:

- remain non-empty after trimming leading and trailing whitespace;
- contain no Unicode control characters;
- contain at most 128 UTF-8 bytes.

The verifier returns the original string in `ActorContext` only when the value equals its trimmed form. Tokens with surrounding whitespace are rejected rather than silently normalized.

Issuer and audience are compared to their already validated configured values. They are not projected into `ActorContext`.

### 8.5 Token ID

`jti` must:

- parse as a UUID;
- be UUID version 4;
- match the canonical lowercase hyphenated representation exactly;
- contain no surrounding whitespace.

### 8.6 Role

The sole role must be exactly one of:

```text
viewer
contributor
admin
```

Unknown values, mixed case, blanks, duplicate arrays, and multi-role arrays are rejected.

### 8.7 Lifetime and clock skew

Let `now` be `int(clock().timestamp())`, where the injected clock returns an aware UTC datetime.

The verifier requires:

```text
exp > iat
exp - iat <= configured maximum lifetime
iat <= now + configured clock skew
exp > now - configured clock skew
```

The configured maximum is at most 180 seconds.

Clock skew affects current-time comparisons only. It does not enlarge the allowed token lifetime.

With the default five-second skew:

Accepted boundaries:

- `iat == now + 5`;
- `exp == now - 4`;
- `exp - iat == 180` when the configured maximum is 180.

Rejected boundaries:

- `iat > now + 5`;
- `exp == now - 5` or any earlier expiration;
- `exp <= iat`;
- `exp - iat > 180`.

This strict boundary makes a token valid for less than five full seconds after its expiration instant, never five seconds or more.

### 8.8 Actor construction

A valid payload is projected to:

```text
user_id    <- sub
tenant_id   <- tenant_id
role        <- MaintenanceRole(roles[0])
request_id <- request_id
token_id    <- jti
```

Only verified values reach the actor.

## 9. Error Model

### 9.1 Internal verifier errors

Every invalid token condition raises the same public verifier exception:

```python
InternalTokenError("invalid internal JWT")
```

The original exception may be chained for debugging and tests, but must not be copied to an HTTP response.

The verifier must not log:

- the raw token;
- the signing secret;
- actual rejected user IDs;
- actual rejected tenant IDs;
- actual rejected roles;
- claim payloads.

### 9.2 Application exception

Add:

```python
class InternalAuthenticationError(AppException):
    """Stable 401 for every internal authentication failure."""
```

It has the fixed contract:

```text
status_code: 401
code: INTERNAL_TOKEN_INVALID
message: Internal authentication failed
details: null
headers: {"WWW-Authenticate": "Bearer"}
```

### 9.3 Exception headers

`AppException` gains an optional immutable or defensively copied `headers` mapping. The registered exception handler passes it to `JSONResponse`.

Existing exception subclasses remain source compatible because the new constructor argument is optional. Existing response bodies do not change.

### 9.4 HTTP dependency behavior

The following all raise `InternalAuthenticationError`:

- no Authorization header;
- malformed Authorization header;
- non-Bearer authentication scheme;
- empty bearer credentials;
- invalid signature;
- wrong algorithm;
- wrong issuer or audience;
- missing or malformed claims;
- expired or not-yet-valid token;
- unsafe role, UUID, or string content.

Client response:

```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_TOKEN_INVALID",
    "message": "Internal authentication failed",
    "details": null
  }
}
```

Response header:

```text
WWW-Authenticate: Bearer
```

No client-visible distinction is made between authentication failure categories.

## 10. Dependency Construction

`get_internal_token_verifier` constructs the verifier from `get_settings()` and is cached so the immutable verifier is reused.

Tests must be able to override the dependency or clear its cache. The design must not require changing global environment variables after application modules have already cached settings.

A protected test-only route may inject the dependency as follows:

```python
@app.get("/protected")
def protected(actor: Annotated[ActorContext, Depends(get_actor)]):
    return {
        "user_id": actor.user_id,
        "tenant_id": actor.tenant_id,
        "role": actor.role,
        "request_id": actor.request_id,
        "token_id": actor.token_id,
    }
```

No equivalent production route is added in Unit 5.

## 11. Test Design

All token tests use a fixed UTC timestamp and a locally generated token. No test relies on wall-clock timing.

### 11.1 Configuration tests

Cover:

- missing secret fails;
- secret shorter than 32 UTF-8 bytes fails;
- multibyte secret length is measured in bytes;
- valid secret succeeds;
- secret is hidden in `repr` and serialization intended for diagnostics;
- blank issuer fails;
- blank audience fails;
- lifetime `0`, negative, and greater than 180 fail;
- lifetime values `1` and `180` succeed;
- negative skew and skew greater than 30 fail;
- skew values `0`, `5`, and `30` succeed.

### 11.2 Successful verification tests

Cover:

- a canonical Go-compatible HS256 token is accepted;
- every actor field matches its source claim;
- role is a `MaintenanceRole` enum;
- actor assignment raises `FrozenInstanceError`;
- arbitrary attribute insertion fails because slots are enabled;
- exact 180-second lifetime is accepted;
- `iat == now + skew` is accepted;
- `exp == now - skew + 1` is accepted.

### 11.3 Cryptographic and registered-claim rejection tests

Cover:

- empty token;
- malformed compact JWT;
- `alg=none`;
- HS384 token;
- RS256 token or algorithm-confusion fixture;
- wrong secret;
- wrong issuer;
- wrong audience;
- missing each required claim individually;
- `exp == now - skew` and earlier expiration;
- future `iat` beyond skew;
- `exp <= iat`;
- lifetime above the configured maximum.

### 11.4 Strict claim tests

Cover:

- numeric, boolean, list, mapping, and null values for string claims;
- boolean, float, string, and null values for `iat` and `exp`;
- audience encoded as a string;
- empty, multi-element, non-string, or extra-value audience arrays;
- roles encoded as a string;
- empty roles;
- multiple roles;
- nested roles;
- unknown role;
- mixed-case role;
- leading or trailing whitespace;
- empty and whitespace-only subject, tenant, or request ID;
- control characters, including newline, carriage return, tab, null, and other Unicode control characters;
- values exceeding 128 UTF-8 bytes;
- non-UUID token ID;
- UUIDv1, UUIDv3, or UUIDv5 token ID;
- uppercase or non-canonical UUIDv4 token ID.

### 11.5 FastAPI dependency and envelope tests

Using a temporary test application with the project's real exception handlers, cover:

- missing Authorization returns the fixed 401 envelope;
- Basic authentication returns the fixed 401 envelope;
- malformed Bearer authentication returns the fixed 401 envelope;
- invalid token returns the fixed 401 envelope;
- expired token returns the same fixed 401 envelope;
- every 401 includes `WWW-Authenticate: Bearer`;
- no response contains validation details or raw token fragments;
- a valid token returns actor data from the protected test route.

### 11.6 Regression tests

Run existing health and system tests to prove that public route behavior remains unchanged.

Run the full Maintenance API test suite after focused tests because settings now require a secret at import/startup time.

## 12. Verification Commands

From the repository worktree:

```powershell
cd extensions\maintenance-api

python -m pytest tests/security/test_internal_jwt.py -v
python -m pytest tests/test_health.py tests/test_system.py -v
python -m ruff check app/security app/core/config.py app/core/exceptions.py tests/security/test_internal_jwt.py
python -m pytest -v
```

Additional repository checks:

```powershell
git diff --check
git status --short
```

## 13. Acceptance Criteria

Unit 5 is complete only when all of the following are true:

1. unsafe or absent JWT configuration fails settings construction;
2. secret values are not exposed by repr, validation messages, HTTP responses, or logs introduced by this unit;
3. the verifier accepts only HS256;
4. every required claim is present and strictly typed;
5. audience shape is exactly a one-element array;
6. roles shape is exactly a one-element supported-role array;
7. `jti` is canonical lowercase UUIDv4;
8. actor strings are non-empty, control-character free, and no longer than 128 UTF-8 bytes;
9. token lifetime is positive and no greater than 180 seconds;
10. five-second clock skew is enforced without enlarging lifetime;
11. valid tokens return immutable, slotted, single-role `ActorContext` objects;
12. every authentication failure produces the same 401 envelope and Bearer challenge;
13. current production routers are not newly protected in this unit;
14. focused security tests, health/system regression tests, Ruff checks, and the full Maintenance API suite pass;
15. only the approved Unit 5 files change.

## 14. Security Review Checklist

Before completion, review the implementation for:

- accidental acceptance of multiple algorithms;
- Python bool-to-int confusion for numeric dates;
- PyJWT audience shape permissiveness bypassing the array contract;
- PyJWT wall-clock validation bypassing the injected test clock;
- time skew accidentally added to maximum lifetime;
- normalization that silently accepts surrounding whitespace;
- raw exception details escaping through `AppException`;
- secret access outside verifier construction;
- dependency caches that make tests order-dependent;
- router changes that prematurely enforce Unit 6 behavior;
- token, actor, tenant, or role values written to logs.

## 15. Transition to Implementation Planning

After this written design is reviewed and approved, create a separate task-by-task TDD implementation plan. The plan must preserve the file scope and split work into small RED/GREEN commits rather than implementing all security behavior in one change.

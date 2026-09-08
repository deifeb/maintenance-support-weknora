# Plan 05-1 Integration and Security Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a secure browser-to-WeKnora-to-Maintenance API path with internal JWT identity exchange, complete tenant scoping, role enforcement, idempotent writes, optimistic concurrency, and durable audit records.

**Architecture:** The existing WeKnora Gin server remains the public authentication boundary. An authenticated reverse proxy signs a three-minute HS256 internal JWT and forwards HTTP and SSE traffic to FastAPI; FastAPI verifies that token into an immutable `ActorContext`, scopes every repository query by `tenant_id`, and applies role, version, idempotency, and audit controls in deterministic services.

**Tech Stack:** Go 1.26, Gin, `github.com/golang-jwt/jwt/v5`, `httputil.ReverseProxy`, Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, pytest, HTTPX, Ruff, SQLite/PostgreSQL-compatible SQL.

## Global Constraints

- Base work on `baf71615504606331ad4634fb6507843b6df5452` in an isolated `feature/maintenance-frontend-plan05` worktree.
- Browser requests use `/api/maintenance/*`; Maintenance API remains inaccessible to browser code as a separate origin.
- Internal JWT expiry is exactly 180 seconds, audience is `maintenance-api`, and issuer is `weknora`.
- Never forward a browser-supplied internal bearer token, `tenant_id`, user ID, roles, or signing headers.
- Maintenance API obtains tenant and role only from verified internal JWT claims.
- All tenant-owned unique constraints include `tenant_id`.
- Repository methods never commit; service methods own transactions.
- All state-changing endpoints use role checks; inventory/version/publish endpoints additionally use idempotency and expected version.
- Existing Phase 01—04 tests must remain green.
- No frontend business page is implemented in this plan; only the reusable security and API foundation is delivered.

---

## File Map

**Create:**

```text
internal/config/maintenance.go
internal/maintenanceproxy/claims.go
internal/maintenanceproxy/signer.go
internal/maintenanceproxy/proxy.go
internal/maintenanceproxy/proxy_test.go
internal/router/maintenance_routes.go
internal/router/maintenance_routes_test.go
extensions/maintenance-api/app/security/__init__.py
extensions/maintenance-api/app/security/actor.py
extensions/maintenance-api/app/security/internal_jwt.py
extensions/maintenance-api/app/security/dependencies.py
extensions/maintenance-api/app/security/permissions.py
extensions/maintenance-api/app/models/audit.py
extensions/maintenance-api/app/models/idempotency.py
extensions/maintenance-api/app/repositories/audit_repository.py
extensions/maintenance-api/app/repositories/idempotency_repository.py
extensions/maintenance-api/app/services/audit_service.py
extensions/maintenance-api/app/services/idempotency_service.py
extensions/maintenance-api/alembic/versions/20260724_05_add_tenant_security_foundation.py
extensions/maintenance-api/tests/security/test_internal_jwt.py
extensions/maintenance-api/tests/security/test_permissions.py
extensions/maintenance-api/tests/repositories/test_tenant_scope.py
extensions/maintenance-api/tests/services/test_idempotency_service.py
extensions/maintenance-api/tests/services/test_audit_service.py
extensions/maintenance-api/tests/migrations/test_tenant_security_migration.py
extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py
```

**Modify:**

```text
internal/config/config.go
internal/router/router.go
config/config.yaml.example
.env.example
extensions/maintenance-api/.env.example
extensions/maintenance-api/requirements.txt
extensions/maintenance-api/app/core/config.py
extensions/maintenance-api/app/core/responses.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/app/main.py
extensions/maintenance-api/app/models/mixins.py
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/models/{equipment,catalog,reliability,inventory,supplier,repair,demand_scenario,demand_calculation,ai_session,ai_execution,ai_evidence,ai_review,ai_report}.py
extensions/maintenance-api/app/repositories/base.py
extensions/maintenance-api/app/services/base.py
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/tests/conftest.py
extensions/maintenance-api/README.md
```

---

### Task 1: Add WeKnora Maintenance Proxy Configuration

**Files:**
- Create: `internal/config/maintenance.go`
- Modify: `internal/config/config.go`
- Modify: `config/config.yaml.example`
- Modify: `.env.example`
- Test: `internal/config/maintenance_test.go`

**Interfaces:**
- Produces: `config.MaintenanceConfig`, `config.MaintenanceProxyEnabled(*Config) bool`.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Write the failing configuration tests**

```go
package config

import (
    "testing"
    "time"

    "github.com/stretchr/testify/require"
)

func TestMaintenanceConfigDefaults(t *testing.T) {
    cfg := defaultMaintenanceConfig()
    require.False(t, cfg.Enabled)
    require.Equal(t, "http://127.0.0.1:8100", cfg.BaseURL)
    require.Equal(t, "weknora", cfg.Issuer)
    require.Equal(t, "maintenance-api", cfg.Audience)
    require.Equal(t, 180*time.Second, cfg.TokenTTL)
    require.Equal(t, 30*time.Second, cfg.RequestTimeout)
}

func TestMaintenanceProxyEnabledIsNilSafe(t *testing.T) {
    require.False(t, MaintenanceProxyEnabled(nil))
    require.False(t, MaintenanceProxyEnabled(&Config{}))
    require.True(t, MaintenanceProxyEnabled(&Config{Maintenance: &MaintenanceConfig{Enabled: true}}))
}
```

- [ ] **Step 2: Run the test and observe the missing types**

Run:

```powershell
go test ./internal/config -run Maintenance -v
```

Expected: FAIL because `MaintenanceConfig`, `defaultMaintenanceConfig`, and `MaintenanceProxyEnabled` do not exist.

- [ ] **Step 3: Implement the configuration contract**

```go
package config

import "time"

type MaintenanceConfig struct {
    Enabled        bool          `yaml:"enabled" json:"enabled" mapstructure:"enabled"`
    BaseURL        string        `yaml:"base_url" json:"base_url" mapstructure:"base_url"`
    SigningSecret  string        `yaml:"signing_secret" json:"-" mapstructure:"signing_secret"`
    Issuer         string        `yaml:"issuer" json:"issuer" mapstructure:"issuer"`
    Audience       string        `yaml:"audience" json:"audience" mapstructure:"audience"`
    TokenTTL       time.Duration `yaml:"token_ttl" json:"token_ttl" mapstructure:"token_ttl"`
    RequestTimeout time.Duration `yaml:"request_timeout" json:"request_timeout" mapstructure:"request_timeout"`
}

func defaultMaintenanceConfig() *MaintenanceConfig {
    return &MaintenanceConfig{
        BaseURL:        "http://127.0.0.1:8100",
        Issuer:         "weknora",
        Audience:       "maintenance-api",
        TokenTTL:       180 * time.Second,
        RequestTimeout: 30 * time.Second,
    }
}

func MaintenanceProxyEnabled(cfg *Config) bool {
    return cfg != nil && cfg.Maintenance != nil && cfg.Maintenance.Enabled
}
```

Add `Maintenance *MaintenanceConfig` to `Config`, apply defaults during configuration loading, and document environment variables:

```text
WEKNORA_MAINTENANCE_ENABLED=true
WEKNORA_MAINTENANCE_BASE_URL=http://maintenance-api:8100
WEKNORA_MAINTENANCE_SIGNING_SECRET=<32-or-more-random-bytes>
WEKNORA_MAINTENANCE_ISSUER=weknora
WEKNORA_MAINTENANCE_AUDIENCE=maintenance-api
WEKNORA_MAINTENANCE_TOKEN_TTL=3m
WEKNORA_MAINTENANCE_REQUEST_TIMEOUT=30s
```

- [ ] **Step 4: Run focused and package tests**

```powershell
go test ./internal/config -run Maintenance -v
go test ./internal/config
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add internal/config/maintenance.go internal/config/maintenance_test.go internal/config/config.go config/config.yaml.example .env.example
git commit -m "feat: configure maintenance proxy"
```

---

### Task 2: Implement Internal JWT Claims and Signer

**Files:**
- Create: `internal/maintenanceproxy/claims.go`
- Create: `internal/maintenanceproxy/signer.go`
- Test: `internal/maintenanceproxy/signer_test.go`

**Interfaces:**
- Consumes: `config.MaintenanceConfig` from Task 1.
- Produces: `maintenanceproxy.Actor`, `maintenanceproxy.Signer`, `Signer.Sign(Actor) (string, error)`.
- Consumed by: Task 3.

- [ ] **Step 1: Write failing signer tests**

```go
package maintenanceproxy

import (
    "testing"
    "time"

    "github.com/golang-jwt/jwt/v5"
    "github.com/stretchr/testify/require"
)

func TestSignerCreatesBoundShortLivedToken(t *testing.T) {
    now := time.Unix(1_784_894_400, 0)
    signer := NewSigner([]byte("01234567890123456789012345678901"), "weknora", "maintenance-api", 180*time.Second)
    signer.now = func() time.Time { return now }

    token, err := signer.Sign(Actor{
        UserID: "u-1", TenantID: "t-1", Roles: []string{"contributor"}, RequestID: "r-1",
    })
    require.NoError(t, err)

    parsed, err := jwt.ParseWithClaims(token, &Claims{}, func(token *jwt.Token) (any, error) {
        require.Equal(t, jwt.SigningMethodHS256, token.Method)
        return []byte("01234567890123456789012345678901"), nil
    }, jwt.WithAudience("maintenance-api"), jwt.WithIssuer("weknora"), jwt.WithTimeFunc(func() time.Time { return now }))
    require.NoError(t, err)
    claims := parsed.Claims.(*Claims)
    require.Equal(t, "u-1", claims.Subject)
    require.Equal(t, "t-1", claims.TenantID)
    require.Equal(t, []string{"contributor"}, claims.Roles)
    require.Equal(t, "r-1", claims.RequestID)
    require.Equal(t, now.Add(180*time.Second), claims.ExpiresAt.Time)
    require.NotEmpty(t, claims.ID)
}

func TestSignerRejectsShortSecretAndMissingActorFields(t *testing.T) {
    require.Panics(t, func() { NewSigner([]byte("short"), "weknora", "maintenance-api", 180*time.Second) })
    signer := NewSigner([]byte("01234567890123456789012345678901"), "weknora", "maintenance-api", 180*time.Second)
    _, err := signer.Sign(Actor{UserID: "u-1"})
    require.Error(t, err)
}
```

- [ ] **Step 2: Run the failing test**

```powershell
go test ./internal/maintenanceproxy -run Signer -v
```

Expected: FAIL because the package and types do not exist.

- [ ] **Step 3: Implement claims and signer**

```go
package maintenanceproxy

import (
    "errors"
    "time"

    "github.com/golang-jwt/jwt/v5"
    "github.com/google/uuid"
)

type Actor struct {
    UserID    string
    TenantID  string
    Roles     []string
    RequestID string
}

type Claims struct {
    TenantID string   `json:"tenant_id"`
    Roles    []string `json:"roles"`
    RequestID string  `json:"request_id"`
    jwt.RegisteredClaims
}

type Signer struct {
    secret []byte
    issuer string
    audience string
    ttl time.Duration
    now func() time.Time
}

func NewSigner(secret []byte, issuer, audience string, ttl time.Duration) *Signer {
    if len(secret) < 32 { panic("maintenance signing secret must contain at least 32 bytes") }
    return &Signer{secret: secret, issuer: issuer, audience: audience, ttl: ttl, now: time.Now}
}

func (s *Signer) Sign(actor Actor) (string, error) {
    if actor.UserID == "" || actor.TenantID == "" || actor.RequestID == "" || len(actor.Roles) == 0 {
        return "", errors.New("maintenance actor is incomplete")
    }
    now := s.now().UTC()
    claims := Claims{
        TenantID: actor.TenantID,
        Roles: append([]string(nil), actor.Roles...),
        RequestID: actor.RequestID,
        RegisteredClaims: jwt.RegisteredClaims{
            Subject: actor.UserID,
            Issuer: s.issuer,
            Audience: jwt.ClaimStrings{s.audience},
            IssuedAt: jwt.NewNumericDate(now),
            ExpiresAt: jwt.NewNumericDate(now.Add(s.ttl)),
            ID: uuid.NewString(),
        },
    }
    return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(s.secret)
}
```

- [ ] **Step 4: Run signer tests**

```powershell
go test ./internal/maintenanceproxy -run Signer -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add internal/maintenanceproxy/claims.go internal/maintenanceproxy/signer.go internal/maintenanceproxy/signer_test.go
git commit -m "feat: sign maintenance actor tokens"
```

---

### Task 3: Implement Authenticated HTTP and SSE Reverse Proxy

**Files:**
- Create: `internal/maintenanceproxy/proxy.go`
- Test: `internal/maintenanceproxy/proxy_test.go`

**Interfaces:**
- Consumes: `Signer.Sign(Actor)`.
- Produces: `New(baseURL string, signer *Signer, actorResolver ActorResolver, timeout time.Duration) (*Proxy, error)` and `(*Proxy).ServeHTTP`.
- `ActorResolver` signature: `func(*gin.Context) (Actor, error)`.
- Consumed by: Task 4.

- [ ] **Step 1: Write failing proxy tests**

```go
func TestProxyRewritesPathAndInjectsOnlyInternalIdentity(t *testing.T) {
    upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        require.Equal(t, "/api/v1/dashboard/summary", r.URL.Path)
        require.Equal(t, "q=x", r.URL.RawQuery)
        require.Equal(t, "r-1", r.Header.Get("X-Request-ID"))
        require.Empty(t, r.Header.Get("X-Tenant-ID"))
        require.Regexp(t, `^Bearer .+`, r.Header.Get("Authorization"))
        w.Header().Set("Content-Type", "application/json")
        _, _ = w.Write([]byte(`{"success":true}`))
    }))
    defer upstream.Close()

    proxy := newTestProxy(t, upstream.URL)
    router := gin.New()
    router.Any("/api/maintenance/*path", proxy.ServeHTTP)

    request := httptest.NewRequest(http.MethodGet, "/api/maintenance/v1/dashboard/summary?q=x", nil)
    request.Header.Set("Authorization", "Bearer browser-token")
    request.Header.Set("X-Tenant-ID", "spoofed")
    response := httptest.NewRecorder()
    router.ServeHTTP(response, request)
    require.Equal(t, http.StatusOK, response.Code)
}

func TestProxyStreamsWithoutBuffering(t *testing.T) {
    upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        flusher := w.(http.Flusher)
        w.Header().Set("Content-Type", "text/event-stream")
        _, _ = io.WriteString(w, "id: 1\nevent: progress\ndata: {\"percent\":10}\n\n")
        flusher.Flush()
    }))
    defer upstream.Close()
    proxy := newTestProxy(t, upstream.URL)
    require.Equal(t, 100*time.Millisecond, proxy.flushInterval)
}
```

- [ ] **Step 2: Run proxy tests and observe failure**

```powershell
go test ./internal/maintenanceproxy -run Proxy -v
```

Expected: FAIL because `Proxy` and `ActorResolver` do not exist.

- [ ] **Step 3: Implement the proxy**

```go
package maintenanceproxy

import (
    "errors"
    "net/http"
    "net/http/httputil"
    "net/url"
    "strings"
    "time"

    "github.com/gin-gonic/gin"
)

type ActorResolver func(*gin.Context) (Actor, error)

type Proxy struct {
    reverse *httputil.ReverseProxy
    signer *Signer
    resolve ActorResolver
    flushInterval time.Duration
}

func New(baseURL string, signer *Signer, resolver ActorResolver, timeout time.Duration) (*Proxy, error) {
    target, err := url.Parse(baseURL)
    if err != nil || target.Scheme == "" || target.Host == "" { return nil, errors.New("invalid maintenance base URL") }
    reverse := httputil.NewSingleHostReverseProxy(target)
    reverse.FlushInterval = 100 * time.Millisecond
    originalDirector := reverse.Director
    p := &Proxy{reverse: reverse, signer: signer, resolve: resolver, flushInterval: reverse.FlushInterval}
    reverse.Director = func(r *http.Request) {
        originalDirector(r)
        r.URL.Path = "/api/" + strings.TrimPrefix(r.URL.Path, "/api/maintenance/")
        r.Header.Del("X-Tenant-ID")
        r.Header.Del("X-User-ID")
        r.Header.Del("X-User-Roles")
        r.Header.Del("X-Internal-Authorization")
    }
    reverse.Transport = &http.Transport{ResponseHeaderTimeout: timeout, Proxy: http.ProxyFromEnvironment}
    return p, nil
}

func (p *Proxy) ServeHTTP(c *gin.Context) {
    actor, err := p.resolve(c)
    if err != nil { c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "maintenance actor unavailable"}); return }
    token, err := p.signer.Sign(actor)
    if err != nil { c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "maintenance identity exchange failed"}); return }
    c.Request.Header.Set("Authorization", "Bearer "+token)
    c.Request.Header.Set("X-Request-ID", actor.RequestID)
    p.reverse.ServeHTTP(c.Writer, c.Request)
}
```

Add an `ErrorHandler` returning `502` with a request ID and ensure response headers do not expose upstream host or signing details.

- [ ] **Step 4: Run tests**

```powershell
go test ./internal/maintenanceproxy -v
```

Expected: PASS, including path rewriting, spoofed-header stripping, token injection, upstream failure mapping, and SSE flushing.

- [ ] **Step 5: Commit**

```powershell
git add internal/maintenanceproxy/proxy.go internal/maintenanceproxy/proxy_test.go
git commit -m "feat: proxy maintenance http and sse traffic"
```

---

### Task 4: Register WeKnora Maintenance Routes with Existing Auth Context

**Files:**
- Create: `internal/router/maintenance_routes.go`
- Create: `internal/router/maintenance_routes_test.go`
- Modify: `internal/router/router.go`

**Interfaces:**
- Consumes: `maintenanceproxy.New`, `types.UserIDFromContext`, `types.TenantIDFromContext`, `types.TenantRoleFromContext`.
- Produces: `RegisterMaintenanceRoutes(router gin.IRouter, cfg *config.Config)`.

- [ ] **Step 1: Write failing route tests**

```go
func TestMaintenanceRouteRequiresAuthenticatedActor(t *testing.T) {
    router := gin.New()
    RegisterMaintenanceRoutes(router, testMaintenanceConfig(t))

    response := httptest.NewRecorder()
    router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/maintenance/v1/dashboard/summary", nil))
    require.Equal(t, http.StatusUnauthorized, response.Code)
}

func TestMaintenanceActorResolverMapsOwnerToAdmin(t *testing.T) {
    ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
    request := httptest.NewRequest(http.MethodGet, "/", nil)
    request = request.WithContext(types.ContextWithTenantRole(request.Context(), types.TenantRoleOwner))
    request = request.WithContext(types.ContextWithUserID(request.Context(), "u-1"))
    request = request.WithContext(types.ContextWithTenantID(request.Context(), "t-1"))
    ctx.Request = request
    ctx.Set("request_id", "r-1")
    actor, err := maintenanceActor(ctx)
    require.NoError(t, err)
    require.Equal(t, []string{"admin"}, actor.Roles)
}
```

- [ ] **Step 2: Run and verify failure**

```powershell
go test ./internal/router -run Maintenance -v
```

Expected: FAIL because route registration is missing.

- [ ] **Step 3: Implement role mapping and registration**

```go
func maintenanceRole(role types.TenantRole) string {
    switch role {
    case types.TenantRoleOwner, types.TenantRoleAdmin:
        return "admin"
    case types.TenantRoleContributor:
        return "contributor"
    default:
        return "viewer"
    }
}

func maintenanceActor(c *gin.Context) (maintenanceproxy.Actor, error) {
    ctx := c.Request.Context()
    userID, userOK := types.UserIDFromContext(ctx)
    tenantID, tenantOK := types.TenantIDFromContext(ctx)
    requestID := c.GetString("request_id")
    if !userOK || !tenantOK || requestID == "" { return maintenanceproxy.Actor{}, errors.New("missing authenticated actor context") }
    return maintenanceproxy.Actor{
        UserID: userID,
        TenantID: tenantID,
        Roles: []string{maintenanceRole(types.TenantRoleFromContext(ctx))},
        RequestID: requestID,
    }, nil
}

func RegisterMaintenanceRoutes(router gin.IRouter, cfg *config.Config) {
    if !config.MaintenanceProxyEnabled(cfg) { return }
    signer := maintenanceproxy.NewSigner([]byte(cfg.Maintenance.SigningSecret), cfg.Maintenance.Issuer, cfg.Maintenance.Audience, cfg.Maintenance.TokenTTL)
    proxy, err := maintenanceproxy.New(cfg.Maintenance.BaseURL, signer, maintenanceActor, cfg.Maintenance.RequestTimeout)
    if err != nil { panic(err) }
    v1.Any("/maintenance/*path", proxy.ServeHTTP)
}
```

Call `RegisterMaintenanceRoutes(r, params.Config)` immediately after the global Auth middleware and before the `/api/v1` group is created. Browser-facing paths are `/api/maintenance/v1/*`; the proxy rewrites them to Maintenance API `/api/v1/*`.

- [ ] **Step 4: Run router and proxy tests**

```powershell
go test ./internal/router ./internal/maintenanceproxy -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add internal/router/maintenance_routes.go internal/router/maintenance_routes_test.go internal/router/router.go
git commit -m "feat: register authenticated maintenance routes"
```

---

### Task 5: Verify Internal JWT in Maintenance API

**Files:**
- Create: `extensions/maintenance-api/app/security/actor.py`
- Create: `extensions/maintenance-api/app/security/internal_jwt.py`
- Create: `extensions/maintenance-api/app/security/dependencies.py`
- Modify: `extensions/maintenance-api/app/core/config.py`
- Modify: `extensions/maintenance-api/requirements.txt`
- Modify: `extensions/maintenance-api/.env.example`
- Test: `extensions/maintenance-api/tests/security/test_internal_jwt.py`

**Interfaces:**
- Produces: `MaintenanceRole`, `ActorContext`, `InternalTokenVerifier.verify(token: str) -> ActorContext`, `get_actor()`.
- Consumed by: Tasks 6–10 and all later plans.

- [ ] **Step 1: Write failing verifier tests**

```python
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security.actor import MaintenanceRole
from app.security.internal_jwt import InternalTokenVerifier, InternalTokenError


def build_token(secret: str, **overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "u-1", "tenant_id": "t-1", "roles": ["contributor"],
        "aud": "maintenance-api", "iss": "weknora", "iat": now,
        "exp": now + timedelta(seconds=180), "jti": "j-1", "request_id": "r-1",
        **overrides,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_verify_returns_immutable_actor():
    verifier = InternalTokenVerifier("x" * 32, "weknora", "maintenance-api")
    actor = verifier.verify(build_token("x" * 32))
    assert actor.user_id == "u-1"
    assert actor.tenant_id == "t-1"
    assert actor.roles == frozenset({MaintenanceRole.CONTRIBUTOR})
    assert actor.request_id == "r-1"
    assert actor.token_id == "j-1"


@pytest.mark.parametrize("overrides", [
    {"aud": "other"}, {"iss": "other"}, {"tenant_id": ""},
    {"roles": ["owner"]}, {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
])
def test_verify_rejects_invalid_claims(overrides):
    verifier = InternalTokenVerifier("x" * 32, "weknora", "maintenance-api")
    with pytest.raises(InternalTokenError):
        verifier.verify(build_token("x" * 32, **overrides))
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/security/test_internal_jwt.py -v
```

Expected: FAIL because security modules and PyJWT dependency are missing.

- [ ] **Step 3: Implement actor and verifier**

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
    roles: frozenset[MaintenanceRole]
    request_id: str
    token_id: str
```

```python
import jwt
from jwt import InvalidTokenError

from app.security.actor import ActorContext, MaintenanceRole


class InternalTokenError(ValueError):
    pass


class InternalTokenVerifier:
    def __init__(self, secret: str, issuer: str, audience: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("internal JWT secret must contain at least 32 bytes")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> ActorContext:
        try:
            claims = jwt.decode(
                token, self._secret, algorithms=["HS256"],
                audience=self._audience, issuer=self._issuer,
                options={"require": ["sub", "tenant_id", "roles", "iat", "exp", "jti", "request_id"]},
            )
            roles = frozenset(MaintenanceRole(value) for value in claims["roles"])
            if not claims["sub"] or not claims["tenant_id"] or not claims["request_id"] or not claims["jti"] or not roles:
                raise InternalTokenError("internal JWT contains empty required claims")
            return ActorContext(claims["sub"], claims["tenant_id"], roles, claims["request_id"], claims["jti"])
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise InternalTokenError("invalid internal JWT") from exc
```

Add settings `internal_jwt_secret`, `internal_jwt_issuer="weknora"`, and `internal_jwt_audience="maintenance-api"`. Add `PyJWT>=2.10,<3` to requirements. Implement `get_actor` with `HTTPBearer(auto_error=False)` and return controlled `401 INTERNAL_TOKEN_INVALID`.

- [ ] **Step 4: Run tests and lint**

```powershell
python -m pytest tests/security/test_internal_jwt.py -v
python -m ruff check app/security tests/security/test_internal_jwt.py
```

Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/security extensions/maintenance-api/app/core/config.py extensions/maintenance-api/requirements.txt extensions/maintenance-api/.env.example extensions/maintenance-api/tests/security/test_internal_jwt.py
git commit -m "feat: verify internal maintenance identity"
```

---

### Task 6: Add Permission Dependencies and Response Metadata

**Files:**
- Create: `extensions/maintenance-api/app/security/permissions.py`
- Modify: `extensions/maintenance-api/app/core/responses.py`
- Modify: `extensions/maintenance-api/app/schemas/common.py`
- Modify: `extensions/maintenance-api/app/core/exceptions.py`
- Test: `extensions/maintenance-api/tests/security/test_permissions.py`
- Test: `extensions/maintenance-api/tests/test_responses.py`

**Interfaces:**
- Consumes: `ActorContext`.
- Produces: `require_viewer`, `require_contributor`, `require_admin`, `ApiMeta`, actor-aware `success_response`.

- [ ] **Step 1: Write failing permission tests**

```python
import pytest
from fastapi import HTTPException

from app.security.actor import ActorContext, MaintenanceRole
from app.security.permissions import require_role


def actor(*roles: MaintenanceRole) -> ActorContext:
    return ActorContext("u-1", "t-1", frozenset(roles), "r-1", "j-1")


def test_admin_satisfies_all_role_floors():
    assert require_role(actor(MaintenanceRole.ADMIN), MaintenanceRole.VIEWER).user_id == "u-1"
    assert require_role(actor(MaintenanceRole.ADMIN), MaintenanceRole.CONTRIBUTOR).user_id == "u-1"


def test_viewer_cannot_mutate():
    with pytest.raises(HTTPException) as exc:
        require_role(actor(MaintenanceRole.VIEWER), MaintenanceRole.CONTRIBUTOR)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "INSUFFICIENT_MAINTENANCE_ROLE"
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/security/test_permissions.py tests/test_responses.py -v
```

Expected: FAIL because permission helpers and metadata are absent.

- [ ] **Step 3: Implement the role ladder and metadata**

```python
ROLE_RANK = {
    MaintenanceRole.VIEWER: 10,
    MaintenanceRole.CONTRIBUTOR: 20,
    MaintenanceRole.ADMIN: 30,
}


def highest_role(actor: ActorContext) -> MaintenanceRole:
    return max(actor.roles, key=ROLE_RANK.__getitem__)


def require_role(actor: ActorContext, minimum: MaintenanceRole) -> ActorContext:
    if ROLE_RANK[highest_role(actor)] < ROLE_RANK[minimum]:
        raise HTTPException(status_code=403, detail={
            "code": "INSUFFICIENT_MAINTENANCE_ROLE",
            "message": f"{minimum.value} role is required",
            "request_id": actor.request_id,
        })
    return actor
```

Extend responses so every actor-aware API response contains:

```python
class ApiMeta(BaseModel):
    request_id: str
    tenant_id: str
    version: int | None = None
```

Do not change existing health/root response shapes; use the extended metadata on `/api/v1` maintenance business routers only to avoid breaking Phase 01—04 tests.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/security/test_permissions.py tests/test_responses.py tests/test_health.py tests/test_system.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/security/permissions.py extensions/maintenance-api/app/core/responses.py extensions/maintenance-api/app/schemas/common.py extensions/maintenance-api/app/core/exceptions.py extensions/maintenance-api/tests/security/test_permissions.py extensions/maintenance-api/tests/test_responses.py
git commit -m "feat: enforce maintenance roles and response metadata"
```

---

### Task 7: Add Tenant and Version Mixins to Business Models

**Files:**
- Modify: `extensions/maintenance-api/app/models/mixins.py`
- Modify: all tenant-owned model modules listed in the file map
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260724_05_add_tenant_security_foundation.py`
- Test: `extensions/maintenance-api/tests/migrations/test_tenant_security_migration.py`
- Test: `extensions/maintenance-api/tests/models/test_tenant_models.py`

**Interfaces:**
- Produces: `TenantScopedMixin.tenant_id`, `VersionedMixin.version`, tenant-aware unique constraints.
- Consumed by: Task 8 and all later plans.

- [ ] **Step 1: Write failing model and migration tests**

```python
TENANT_TABLES = {
    "equipment_models", "configuration_versions", "configuration_items", "parts",
    "spare_parts", "reliability_profiles", "warehouses", "warehouse_inventories",
    "suppliers", "supplier_offers", "repair_profiles", "demand_scenario_templates",
    "demand_scenario_versions", "demand_calculation_tasks", "ai_sessions",
    "ai_execution_plans", "ai_evidence_packages", "ai_review_runs", "ai_report_jobs",
}


def test_all_tenant_tables_have_tenant_id_and_index(engine):
    inspector = inspect(engine)
    for table in TENANT_TABLES:
        assert "tenant_id" in {column["name"] for column in inspector.get_columns(table)}
        indexed = {name for index in inspector.get_indexes(table) for name in index["column_names"]}
        assert "tenant_id" in indexed


def test_same_code_is_allowed_in_different_tenants(session):
    session.add_all([
        EquipmentModel(tenant_id="t-1", code="EQ", name="A"),
        EquipmentModel(tenant_id="t-2", code="EQ", name="B"),
    ])
    session.commit()
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/models/test_tenant_models.py tests/migrations/test_tenant_security_migration.py -v
```

Expected: FAIL because `tenant_id` and revised unique constraints do not exist.

- [ ] **Step 3: Implement mixins and reversible migration**

```python
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class TenantScopedMixin:
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class VersionedMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

Apply `TenantScopedMixin` to every root business row and to child rows whose independent query or mutation can occur. For child rows always reached through a tenant-scoped parent, still persist `tenant_id` to make accidental cross-tenant joins fail closed and to support database constraints.

Migration sequence:

1. Add nullable `tenant_id` with index and `version` with default 1.
2. Read `MAINTENANCE_LEGACY_TENANT_ID`; abort upgrade when existing rows exist and the setting is empty.
3. Backfill all existing rows with that explicit tenant.
4. Make `tenant_id` non-null.
5. Replace global code/name unique constraints with composite tenant constraints, for example `UniqueConstraint("tenant_id", "code", name="uq_equipment_model_tenant_code")`.
6. Preserve foreign keys and downgrade by restoring original constraints only after verifying one-tenant compatibility.

- [ ] **Step 4: Run upgrade/downgrade tests**

```powershell
python -m alembic upgrade head
python -m pytest tests/models/test_tenant_models.py tests/migrations/test_tenant_security_migration.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
```

Expected: all commands succeed; migration test confirms explicit backfill refusal without `MAINTENANCE_LEGACY_TENANT_ID` when legacy rows exist.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models extensions/maintenance-api/alembic/versions/20260724_05_add_tenant_security_foundation.py extensions/maintenance-api/tests/models/test_tenant_models.py extensions/maintenance-api/tests/migrations/test_tenant_security_migration.py
git commit -m "feat: scope maintenance models by tenant"
```

---

### Task 8: Make Repositories and Services Tenant-Safe

**Files:**
- Modify: `extensions/maintenance-api/app/repositories/base.py`
- Modify: every repository under `extensions/maintenance-api/app/repositories/`
- Modify: `extensions/maintenance-api/app/services/base.py`
- Modify: services that directly call `session.get`
- Test: `extensions/maintenance-api/tests/repositories/test_tenant_scope.py`
- Modify: `extensions/maintenance-api/tests/conftest.py`

**Interfaces:**
- Consumes: `ActorContext`, tenant-scoped models.
- Produces: `BaseRepository.get_by_id(session, tenant_id, identifier)`, `get_by_code(session, tenant_id, code)`, tenant-scoped list/create/update/delete.

- [ ] **Step 1: Write failing cross-tenant tests**

```python
def test_repository_never_returns_other_tenant(session):
    first = EquipmentModel(tenant_id="t-1", code="EQ", name="One")
    second = EquipmentModel(tenant_id="t-2", code="EQ", name="Two")
    session.add_all([first, second])
    session.commit()
    repository = EquipmentRepository()
    assert repository.get_by_id(session, "t-1", first.id) is first
    assert repository.get_by_id(session, "t-1", second.id) is None
    assert repository.get_by_code(session, "t-1", "EQ").name == "One"


def test_create_overrides_untrusted_tenant_field(session):
    actor = actor_context(tenant_id="t-1", role="contributor")
    row = equipment_service.create(session, actor, EquipmentModelCreate(code="EQ", name="One"))
    assert row.tenant_id == "t-1"
```

- [ ] **Step 2: Run and observe the leak**

```powershell
python -m pytest tests/repositories/test_tenant_scope.py -v
```

Expected: FAIL because current repository methods use global `session.get` and global code lookup.

- [ ] **Step 3: Implement tenant-scoped repository signatures**

```python
class BaseRepository(Generic[ModelT]):
    def get_by_id(self, session: Session, tenant_id: str, identifier: int) -> ModelT | None:
        return session.scalar(select(self.model).where(
            self.model.id == identifier,
            self.model.tenant_id == tenant_id,
        ))

    def get_by_code(self, session: Session, tenant_id: str, code: str, field_name: str = "code") -> ModelT | None:
        field = getattr(self.model, field_name)
        return session.scalar(select(self.model).where(
            field == code,
            self.model.tenant_id == tenant_id,
        ))

    def create(self, session: Session, tenant_id: str, data: dict[str, Any]) -> ModelT:
        clean = {key: value for key, value in data.items() if key != "tenant_id"}
        instance = self.model(tenant_id=tenant_id, **clean)
        session.add(instance)
        session.flush()
        return instance
```

Change service signatures to `create(session, actor, payload)`, `get(session, actor, id)`, and `list(session, actor, ...)`. Replace every direct `session.get(TenantOwnedModel, id)` with a tenant-filtered repository lookup. Add test fixtures `actor_viewer`, `actor_contributor`, and `actor_admin`.

- [ ] **Step 4: Run repository, service and API suites**

```powershell
python -m pytest tests/repositories tests/services tests/api -v
```

Expected: PASS; tests explicitly prove same numeric ID or code cannot be read, updated, referenced, or deleted from another tenant.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories extensions/maintenance-api/app/services extensions/maintenance-api/tests/repositories/test_tenant_scope.py extensions/maintenance-api/tests/conftest.py
git commit -m "fix: enforce tenant scope in maintenance persistence"
```

---

### Task 9: Add Idempotency, Optimistic Versioning and Audit Services

**Files:**
- Create: model, repository and service files listed in the file map
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Modify: migration from Task 7
- Test: `tests/services/test_idempotency_service.py`
- Test: `tests/services/test_audit_service.py`

**Interfaces:**
- Produces: `IdempotencyService.begin(...)`, `complete(...)`, `VersionConflictError`, `AuditService.record(...)`.
- Consumed by: all later inventory, publish, import and report tasks.

- [ ] **Step 1: Write failing idempotency and audit tests**

```python
def test_same_key_and_hash_replays_original_response(session, actor_contributor):
    service = IdempotencyService()
    first = service.begin(session, actor_contributor, "POST", "/inventory/reservations", "k-1", b'{"a":1}')
    service.complete(session, first, 201, {"data": {"id": 9}})
    replay = service.begin(session, actor_contributor, "POST", "/inventory/reservations", "k-1", b'{"a":1}')
    assert replay.replayed is True
    assert replay.status_code == 201
    assert replay.response_body == {"data": {"id": 9}}


def test_same_key_with_different_hash_conflicts(session, actor_contributor):
    service = IdempotencyService()
    service.begin(session, actor_contributor, "POST", "/inventory/reservations", "k-1", b'{"a":1}')
    with pytest.raises(IdempotencyConflictError):
        service.begin(session, actor_contributor, "POST", "/inventory/reservations", "k-1", b'{"a":2}')


def test_audit_row_records_actor_and_object_versions(session, actor_admin):
    row = AuditService().record(session, actor_admin, action="RULE_PUBLISH", resource_type="allocation_rule", resource_id="3", before={"version": 2}, after={"version": 3})
    assert row.tenant_id == "t-1"
    assert row.user_id == "u-admin"
    assert row.request_id == actor_admin.request_id
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/services/test_idempotency_service.py tests/services/test_audit_service.py -v
```

Expected: FAIL because persistence and services are absent.

- [ ] **Step 3: Implement deterministic request hashing and audit records**

```python
import hashlib


def request_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
```

`api_idempotency_records` fields:

```text
id, tenant_id, user_id, method, path, idempotency_key, request_hash,
state(IN_PROGRESS|COMPLETED|FAILED), status_code, response_json,
created_at, completed_at, expires_at
```

Unique constraint: `(tenant_id, user_id, method, path, idempotency_key)`.

`maintenance_audit_events` fields:

```text
id, tenant_id, user_id, roles_json, request_id, token_id,
action, resource_type, resource_id, before_json, after_json,
result, error_code, created_at
```

Add helper:

```python
def assert_expected_version(instance: VersionedMixin, expected_version: int) -> None:
    if instance.version != expected_version:
        raise VersionConflictError(expected=expected_version, actual=instance.version)
    instance.version += 1
```

- [ ] **Step 4: Run focused tests and migration test**

```powershell
python -m pytest tests/services/test_idempotency_service.py tests/services/test_audit_service.py tests/migrations/test_tenant_security_migration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/audit.py extensions/maintenance-api/app/models/idempotency.py extensions/maintenance-api/app/repositories/audit_repository.py extensions/maintenance-api/app/repositories/idempotency_repository.py extensions/maintenance-api/app/services/audit_service.py extensions/maintenance-api/app/services/idempotency_service.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260724_05_add_tenant_security_foundation.py extensions/maintenance-api/tests/services/test_idempotency_service.py extensions/maintenance-api/tests/services/test_audit_service.py
git commit -m "feat: add maintenance idempotency and audit controls"
```

---

### Task 10: Apply Actor, RBAC and Metadata to Existing APIs

**Files:**
- Modify: `extensions/maintenance-api/app/api/v1/master_data/*.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/*.py`
- Modify: `extensions/maintenance-api/app/api/v1/ai/*.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Test: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Test: `extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py`

**Interfaces:**
- Consumes: actor and role dependencies, tenant-scoped services.
- Produces: protected `/api/v1` business endpoints with stable metadata.

- [ ] **Step 1: Write failing API security tests**

```python
def test_viewer_can_list_but_cannot_create(client, viewer_headers):
    assert client.get("/api/v1/master-data/spare-parts", headers=viewer_headers).status_code == 200
    response = client.post("/api/v1/master-data/spare-parts", headers=viewer_headers, json={"code": "S1", "name": "Part"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_MAINTENANCE_ROLE"


def test_response_uses_actor_tenant_not_header(client, contributor_headers):
    headers = {**contributor_headers, "X-Tenant-ID": "spoofed"}
    response = client.get("/api/v1/master-data/spare-parts", headers=headers)
    assert response.status_code == 200
    assert response.json()["meta"]["tenant_id"] == "t-1"


def test_cross_tenant_identifier_is_not_disclosed(client, tenant_one_headers, tenant_two_spare_part):
    response = client.get(f"/api/v1/master-data/spare-parts/{tenant_two_spare_part.id}", headers=tenant_one_headers)
    assert response.status_code == 404
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/security/test_api_rbac.py tests/integration/test_weknora_proxy_identity.py -v
```

Expected: FAIL because current endpoints do not require internal actor context.

- [ ] **Step 3: Apply dependencies consistently**

Example router pattern:

```python
ActorDep = Annotated[ActorContext, Depends(get_actor)]
ContributorDep = Annotated[ActorContext, Depends(require_contributor)]

@router.get("", response_model=SuccessResponse[PageData[SparePartRead]])
def list_spare_parts(session: SessionDep, actor: ActorDep, params: Annotated[dict, Depends(list_params)]):
    page = spare_part_service.list(session, actor, **params)
    return success_response(page, "Query completed", actor=actor)

@router.post("", response_model=SuccessResponse[SparePartRead], status_code=201)
def create_spare_part(payload: SparePartCreate, session: SessionDep, actor: ContributorDep):
    row = spare_part_service.create(session, actor, payload)
    return success_response(SparePartRead.model_validate(row), "Spare part created", actor=actor, version=row.version)
```

Role policy:

- GET/list/export/status: viewer.
- ordinary create/update/deactivate/import/compute/review: contributor.
- destructive, high-risk confirmation, rule publication, stock adjustment: admin.

Keep health endpoints unprotected for container health checks; all business routes require internal actor.

- [ ] **Step 4: Run all API and integration tests**

```powershell
python -m pytest tests/api tests/integration tests/security -v
python -m ruff check app tests
```

Expected: PASS and Ruff clean.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api extensions/maintenance-api/tests/security/test_api_rbac.py extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py
git commit -m "feat: protect maintenance business APIs"
```

---

### Task 11: Document, Configure and Verify the Security Foundation

**Files:**
- Modify: `extensions/maintenance-api/README.md`
- Modify: root deployment documentation and Docker Compose environment where Maintenance API is declared
- Test: all Phase 05-1 suites

**Interfaces:**
- Produces: reproducible local and Docker configuration, verified security gate.

- [ ] **Step 1: Add an executable configuration smoke test**

Create `extensions/maintenance-api/tests/security/test_security_settings.py`:

```python
def test_production_requires_non_default_internal_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_JWT_SECRET", "change-me")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="INTERNAL_JWT_SECRET"):
        Settings()
```

Add an equivalent Go test that enabling the proxy without a 32-byte secret fails startup.

- [ ] **Step 2: Run the smoke tests and observe failure before documentation/config validation**

```powershell
go test ./internal/config ./internal/maintenanceproxy ./internal/router -v
cd extensions\maintenance-api
python -m pytest tests/security/test_security_settings.py -v
```

Expected: the new production-secret assertions initially fail.

- [ ] **Step 3: Add startup validation and exact runbook**

Document:

```powershell
$secretBytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$secret = [Convert]::ToBase64String($secretBytes)
$env:WEKNORA_MAINTENANCE_SIGNING_SECRET = $secret
$env:INTERNAL_JWT_SECRET = $secret
$env:MAINTENANCE_LEGACY_TENANT_ID = "<explicit-existing-weknora-tenant-id>"
```

The same generated value is configured on WeKnora and Maintenance API. The legacy tenant variable is used only for the one-time migration and is removed afterward.

- [ ] **Step 4: Run final Phase 05-1 gate**

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
go test ./internal/config ./internal/maintenanceproxy ./internal/router ./internal/middleware
cd extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m pytest tests/security tests/migrations tests/repositories tests/services tests/api tests/integration -v
python -m ruff check app tests
```

Expected: all tests pass, migration reaches head, and Ruff prints `All checks passed!`.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/README.md extensions/maintenance-api/tests/security/test_security_settings.py .env.example config/config.yaml.example
git commit -m "docs: document maintenance security integration"
```

## Phase Completion Evidence

Capture in the PR description:

- Go test command and pass count.
- pytest command and pass count.
- Alembic current revision.
- Ruff result.
- One redacted decoded internal JWT showing all required claims and 180-second expiry.
- Cross-tenant read, write and reference tests.
- viewer/contributor/admin API matrix test results.
- Idempotency replay and conflict test results.
- Confirmation that no signing secret appears in frontend bundles, API responses or logs.

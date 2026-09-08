# Maintenance Unit 04 Identity Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect trusted WeKnora web-user identity to the existing Maintenance reverse proxy, register the authenticated `/api/maintenance/*path` route only when enabled, and reject the unsupported bare path without changing global Gin routing behavior.

**Architecture:** Add a stateless actor resolver in `internal/maintenanceproxy`, construct the signer and proxy through a fail-closed `dig` provider, register the route after Auth/Langfuse/audit middleware, and wrap the Gin engine in a concrete `ApplicationHandler` that blocks only `/api/maintenance` when the proxy is enabled. Keep Unit 2 token and Unit 3 proxy contracts unchanged.

**Tech Stack:** Go 1.26, Gin 1.12, `gin-contrib/cors`, `go.uber.org/dig`, `github.com/golang-jwt/jwt/v5`, `net/http/httptest`, Windows PowerShell, GCC through MSYS2 UCRT64 for race detection.

## Global Constraints

- Work only on `feature/maintenance-frontend-plan05` in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Start from committed Unit 3 head `4125b860adef68f55f83248c99db930335f69750` plus the approved Unit 4 documentation commit.
- Do not implement on `main`.
- Maintenance remains disabled by default.
- Browser code and callers know only `/api/maintenance/*`; they never receive the private upstream URL or signing secret.
- Internal JWT lifetime remains exactly 180 seconds.
- Only an explicit `types.PrincipalWebUser` whose ID exactly matches `UserIDContextKey` may receive a Maintenance JWT.
- API keys and all non-web principals are rejected.
- Tenant and role are derived only from authenticated request context, never from headers, query strings, or request bodies.
- JWT contains exactly one normalized role: `viewer`, `contributor`, or `admin`.
- System admin, tenant owner, and tenant admin map to `admin`.
- Missing or invalid tenant role must not fall back to `viewer`.
- `/api/maintenance` returns 404 without redirect only when the proxy is enabled.
- `/api/maintenance/` and descendants continue through Gin and Unit 3.
- Do not change global `RedirectTrailingSlash` behavior.
- Do not modify Unit 2 or Unit 3 production files unless a newly written failing regression test proves an existing defect.
- Every implementation task follows RED, observed failure, minimal GREEN, affected-suite verification, review, and commit.
- Do not log the signing secret, internal JWT, actual rejected user ID, actual rejected tenant ID, or supplied rejected role.

---

## File Map

### Create

- `internal/maintenanceproxy/actor_resolver.go` — strict projection from authenticated WeKnora context to `maintenanceproxy.Actor`.
- `internal/maintenanceproxy/actor_resolver_test.go` — role, principal, context-completeness, system-admin, and header-spoofing tests.
- `internal/container/maintenance_proxy.go` — disabled-aware, fail-closed proxy provider.
- `internal/container/maintenance_proxy_test.go` — provider success and construction-failure tests.
- `internal/router/maintenance.go` — optional authenticated route registration.
- `internal/router/maintenance_test.go` — route absence, route table, and path forwarding tests.
- `internal/router/http_handler.go` — outer handler that rejects the enabled bare path.
- `internal/router/http_handler_test.go` — bare-path and transparent-pass-through tests.
- `internal/router/maintenance_integration_test.go` — JWT claims, request-ID propagation, principal rejection, spoofing, and OPTIONS behavior.

### Modify

- `internal/container/container.go` — register `newMaintenanceProxy` and `router.NewApplicationHandler`.
- `internal/router/router.go` — inject the proxy and register Maintenance after Auth/Langfuse/audit middleware.
- `cmd/server/main.go` — serve `*router.ApplicationHandler`.
- `cmd/desktop/main.go` — serve `*router.ApplicationHandler`.
- `.superpowers/sdd/progress.md` — mark Unit 4 complete only after every gate passes.

### Preserve

- `internal/config/maintenance.go`
- `internal/maintenanceproxy/claims.go`
- `internal/maintenanceproxy/signer.go`
- `internal/maintenanceproxy/proxy.go`

---

### Task 1: Strict WeKnora Web Actor Resolver

**Files:**

- Create: `internal/maintenanceproxy/actor_resolver.go`
- Create: `internal/maintenanceproxy/actor_resolver_test.go`

**Interfaces:**

- Consumes: `Actor`, `types.Principal`, `types.TenantRole`, and exported request-context keys.
- Produces: `func ResolveWebActor(*gin.Context) (Actor, error)` for the Unit 3 `ActorResolver` parameter.
- Produces: `func mapMaintenanceRole(types.TenantRole, bool) (string, error)` as a package-private role mapper.

- [ ] **Step 1: Add a focused test context builder and the successful role table**

Create `internal/maintenanceproxy/actor_resolver_test.go` with package `maintenanceproxy` and these helpers and first test:

```go
package maintenanceproxy

import (
    "context"
    "net/http"
    "net/http/httptest"
    "reflect"
    "testing"

    "github.com/gin-gonic/gin"

    "github.com/Tencent/WeKnora/internal/types"
)

func newActorTestContext(
    principal types.Principal,
    userID string,
    tenantID uint64,
    role types.TenantRole,
    systemAdmin *bool,
    requestID string,
) *gin.Context {
    recorder := httptest.NewRecorder()
    ginContext, _ := gin.CreateTestContext(recorder)
    request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs", nil)

    ctx := request.Context()
    ctx = context.WithValue(ctx, types.PrincipalContextKey, principal)
    ctx = context.WithValue(ctx, types.UserIDContextKey, userID)
    ctx = context.WithValue(ctx, types.TenantIDContextKey, tenantID)
    ctx = context.WithValue(ctx, types.TenantRoleContextKey, role)
    ctx = context.WithValue(ctx, types.RequestIDContextKey, requestID)
    if systemAdmin != nil {
        ctx = context.WithValue(ctx, types.SystemAdminContextKey, *systemAdmin)
    }

    ginContext.Request = request.WithContext(ctx)
    return ginContext
}

func boolPointer(value bool) *bool {
    return &value
}

func TestResolveWebActorMapsRoles(t *testing.T) {
    tests := []struct {
        name        string
        role        types.TenantRole
        systemAdmin *bool
        expected    string
    }{
        {name: "viewer", role: types.TenantRoleViewer, systemAdmin: boolPointer(false), expected: "viewer"},
        {name: "contributor", role: types.TenantRoleContributor, systemAdmin: boolPointer(false), expected: "contributor"},
        {name: "admin", role: types.TenantRoleAdmin, systemAdmin: boolPointer(false), expected: "admin"},
        {name: "owner", role: types.TenantRoleOwner, systemAdmin: boolPointer(false), expected: "admin"},
        {name: "missing system admin flag", role: types.TenantRoleViewer, systemAdmin: nil, expected: "viewer"},
        {name: "system admin elevation", role: types.TenantRoleViewer, systemAdmin: boolPointer(true), expected: "admin"},
    }

    for _, test := range tests {
        t.Run(test.name, func(t *testing.T) {
            principal := types.Principal{Type: types.PrincipalWebUser, ID: "user-1"}
            ginContext := newActorTestContext(principal, "user-1", 12, test.role, test.systemAdmin, "req-1")

            actor, err := ResolveWebActor(ginContext)
            if err != nil {
                t.Fatalf("ResolveWebActor() error = %v", err)
            }

            expectedRoles := []string{test.expected}
            if actor.UserID != "user-1" {
                t.Fatalf("UserID = %q, want user-1", actor.UserID)
            }
            if actor.TenantID != "12" {
                t.Fatalf("TenantID = %q, want 12", actor.TenantID)
            }
            if actor.RequestID != "req-1" {
                t.Fatalf("RequestID = %q, want req-1", actor.RequestID)
            }
            if !reflect.DeepEqual(actor.Roles, expectedRoles) {
                t.Fatalf("Roles = %#v, want %#v", actor.Roles, expectedRoles)
            }
        })
    }
}
```

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```powershell
go test ./internal/maintenanceproxy -run '^TestResolveWebActorMapsRoles$' -count=1 -v
```

Expected: compilation fails because `ResolveWebActor` is undefined.

- [ ] **Step 3: Add strict resolver errors, role mapping, and the minimal successful implementation**

Create `internal/maintenanceproxy/actor_resolver.go`:

```go
package maintenanceproxy

import (
    "errors"
    "fmt"
    "strconv"
    "strings"

    "github.com/gin-gonic/gin"

    "github.com/Tencent/WeKnora/internal/types"
)

var errMaintenanceActorUnavailable = errors.New("maintenance actor unavailable")

func actorUnavailable(reason string) error {
    return fmt.Errorf("%w: %s", errMaintenanceActorUnavailable, reason)
}

func ResolveWebActor(c *gin.Context) (Actor, error) {
    actor := Actor{}
    if c == nil || c.Request == nil {
        return actor, actorUnavailable("request context is missing")
    }

    ctx := c.Request.Context()
    requestID, ok := ctx.Value(types.RequestIDContextKey).(string)
    if !ok || strings.TrimSpace(requestID) == "" {
        return actor, actorUnavailable("request id is missing")
    }
    actor.RequestID = requestID

    principal, ok := ctx.Value(types.PrincipalContextKey).(types.Principal)
    if !ok || !principal.Valid() {
        return actor, actorUnavailable("principal is missing or invalid")
    }
    if principal.Type != types.PrincipalWebUser {
        return actor, actorUnavailable("principal type is not web_user")
    }

    userID, ok := ctx.Value(types.UserIDContextKey).(string)
    if !ok || strings.TrimSpace(userID) == "" {
        return actor, actorUnavailable("user id is missing")
    }
    if principal.ID != userID {
        return actor, actorUnavailable("principal and user id do not match")
    }

    tenantID, ok := ctx.Value(types.TenantIDContextKey).(uint64)
    if !ok || tenantID == 0 {
        return actor, actorUnavailable("tenant id is missing or invalid")
    }

    tenantRole, ok := ctx.Value(types.TenantRoleContextKey).(types.TenantRole)
    if !ok || !tenantRole.IsValid() {
        return actor, actorUnavailable("tenant role is missing or invalid")
    }

    systemAdmin := false
    if raw := ctx.Value(types.SystemAdminContextKey); raw != nil {
        value, valid := raw.(bool)
        if !valid {
            return actor, actorUnavailable("system admin flag is invalid")
        }
        systemAdmin = value
    }

    role, err := mapMaintenanceRole(tenantRole, systemAdmin)
    if err != nil {
        return actor, err
    }

    actor.UserID = userID
    actor.TenantID = strconv.FormatUint(tenantID, 10)
    actor.Roles = []string{role}
    return actor, nil
}

func mapMaintenanceRole(tenantRole types.TenantRole, systemAdmin bool) (string, error) {
    if systemAdmin {
        return "admin", nil
    }

    switch tenantRole {
    case types.TenantRoleOwner, types.TenantRoleAdmin:
        return "admin", nil
    case types.TenantRoleContributor:
        return "contributor", nil
    case types.TenantRoleViewer:
        return "viewer", nil
    default:
        return "", actorUnavailable("tenant role is unsupported")
    }
}
```

- [ ] **Step 4: Run the role test and observe GREEN**

Run:

```powershell
gofmt -w internal/maintenanceproxy/actor_resolver.go internal/maintenanceproxy/actor_resolver_test.go
go test ./internal/maintenanceproxy -run '^TestResolveWebActorMapsRoles$' -count=1 -v
```

Expected: `PASS`.

- [ ] **Step 5: Add principal-boundary tests**

Append a table-driven `TestResolveWebActorRejectsInvalidPrincipal` that mutates one field at a time and checks both the sentinel error and preserved request ID:

```go
func TestResolveWebActorRejectsInvalidPrincipal(t *testing.T) {
    tests := []struct {
        name      string
        principal any
        userID    any
    }{
        {name: "missing principal", principal: nil, userID: "user-1"},
        {name: "wrong principal type value", principal: "web_user:user-1", userID: "user-1"},
        {name: "blank principal", principal: types.Principal{}, userID: "user-1"},
        {name: "tenant api key", principal: types.Principal{Type: types.PrincipalAPITenant, ID: "12:1"}, userID: "system-12"},
        {name: "platform api key", principal: types.Principal{Type: types.PrincipalAPIPlatform, ID: "key-1"}, userID: "system-12"},
        {name: "external api user", principal: types.Principal{Type: types.PrincipalAPIExternalUser, ID: "external-1"}, userID: "external-1"},
        {name: "im user", principal: types.Principal{Type: types.PrincipalIMUser, ID: "im-1"}, userID: "user-1"},
        {name: "embed channel", principal: types.Principal{Type: types.PrincipalEmbedChannel, ID: "channel-1"}, userID: "user-1"},
        {name: "mismatched web user", principal: types.Principal{Type: types.PrincipalWebUser, ID: "user-2"}, userID: "user-1"},
    }

    for _, test := range tests {
        t.Run(test.name, func(t *testing.T) {
            recorder := httptest.NewRecorder()
            ginContext, _ := gin.CreateTestContext(recorder)
            request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs", nil)
            ctx := request.Context()
            ctx = context.WithValue(ctx, types.RequestIDContextKey, "req-invalid-principal")
            ctx = context.WithValue(ctx, types.TenantIDContextKey, uint64(12))
            ctx = context.WithValue(ctx, types.TenantRoleContextKey, types.TenantRoleViewer)
            if test.principal != nil {
                ctx = context.WithValue(ctx, types.PrincipalContextKey, test.principal)
            }
            if test.userID != nil {
                ctx = context.WithValue(ctx, types.UserIDContextKey, test.userID)
            }
            ginContext.Request = request.WithContext(ctx)

            actor, err := ResolveWebActor(ginContext)
            if !errors.Is(err, errMaintenanceActorUnavailable) {
                t.Fatalf("error = %v, want errMaintenanceActorUnavailable", err)
            }
            if actor.RequestID != "req-invalid-principal" {
                t.Fatalf("RequestID = %q, want req-invalid-principal", actor.RequestID)
            }
        })
    }
}
```

Add `errors` to the test imports.

- [ ] **Step 6: Add incomplete-context and system-admin type tests**

Add `TestResolveWebActorRejectsIncompleteIdentity` covering these exact mutations:

```text
nil gin context
Gin context with nil Request
missing RequestIDContextKey
RequestIDContextKey containing an integer
blank request ID
missing UserIDContextKey
UserIDContextKey containing an integer
blank user ID
missing TenantIDContextKey
TenantIDContextKey containing a string
zero tenant ID
missing TenantRoleContextKey
TenantRoleContextKey containing a string
TenantRole("operator")
SystemAdminContextKey containing "true"
```

For cases where a valid request ID exists, assert the returned partial Actor preserves it. For request-ID failures, assert `Actor.RequestID == ""`.

Use a helper that starts with a valid context and accepts a context-transform function:

```go
func validActorRequestContext() context.Context {
    ctx := context.Background()
    ctx = context.WithValue(ctx, types.RequestIDContextKey, "req-valid")
    ctx = context.WithValue(ctx, types.PrincipalContextKey, types.Principal{Type: types.PrincipalWebUser, ID: "user-1"})
    ctx = context.WithValue(ctx, types.UserIDContextKey, "user-1")
    ctx = context.WithValue(ctx, types.TenantIDContextKey, uint64(12))
    ctx = context.WithValue(ctx, types.TenantRoleContextKey, types.TenantRoleContributor)
    ctx = context.WithValue(ctx, types.SystemAdminContextKey, false)
    return ctx
}
```

Because `context.Context` values cannot be deleted, build each missing-key case from `context.Background()` with only the required remaining keys rather than trying to remove a value.

- [ ] **Step 7: Add browser-header spoofing test**

Create a valid viewer context, add browser headers, and assert the actor remains the authenticated context actor:

```go
func TestResolveWebActorIgnoresBrowserIdentityHeaders(t *testing.T) {
    principal := types.Principal{Type: types.PrincipalWebUser, ID: "user-1"}
    ginContext := newActorTestContext(principal, "user-1", 12, types.TenantRoleViewer, boolPointer(false), "req-spoof")
    ginContext.Request.Header.Set("X-Tenant-ID", "999")
    ginContext.Request.Header.Set("X-User-ID", "attacker")
    ginContext.Request.Header.Set("X-Role", "admin")
    ginContext.Request.Header.Set("X-User-Roles", "admin")
    ginContext.Request.Header.Set("X-System-Admin", "true")

    actor, err := ResolveWebActor(ginContext)
    if err != nil {
        t.Fatalf("ResolveWebActor() error = %v", err)
    }
    if actor.UserID != "user-1" || actor.TenantID != "12" || actor.RequestID != "req-spoof" {
        t.Fatalf("actor = %#v", actor)
    }
    if !reflect.DeepEqual(actor.Roles, []string{"viewer"}) {
        t.Fatalf("Roles = %#v, want viewer", actor.Roles)
    }
}
```

- [ ] **Step 8: Run the actor resolver suite**

Run:

```powershell
gofmt -w internal/maintenanceproxy/actor_resolver.go internal/maintenanceproxy/actor_resolver_test.go
go test ./internal/maintenanceproxy -run '^(TestResolveWebActor|TestMapMaintenanceRole)' -count=1 -v
go test ./internal/maintenanceproxy -count=1
```

Expected: all tests pass.

- [ ] **Step 9: Review and commit Task 1**

Review that no error includes actual rejected identity values and no request header is read.

Run:

```powershell
git diff --check
git status --short
git add internal/maintenanceproxy/actor_resolver.go internal/maintenanceproxy/actor_resolver_test.go
git commit -m "feat: map authenticated web actors for maintenance"
```

Expected: one focused commit and a clean Task 1 diff.

---

### Task 2: Disabled-Aware Maintenance Proxy Provider

**Files:**

- Create: `internal/container/maintenance_proxy.go`
- Create: `internal/container/maintenance_proxy_test.go`
- Modify: `internal/container/container.go:112-120`

**Interfaces:**

- Consumes: `*config.Config`, `config.MaintenanceProxyEnabled`, `maintenanceproxy.NewSigner`, `maintenanceproxy.ResolveWebActor`, and `maintenanceproxy.New`.
- Produces: `func newMaintenanceProxy(*config.Config) (*maintenanceproxy.Proxy, error)` for `dig` injection.

- [ ] **Step 1: Write disabled and enabled provider tests**

Create `internal/container/maintenance_proxy_test.go`:

```go
package container

import (
    "strings"
    "testing"
    "time"

    "github.com/Tencent/WeKnora/internal/config"
)

func validMaintenanceConfig() *config.Config {
    maintenance := config.DefaultMaintenanceConfig()
    maintenance.Enabled = true
    maintenance.BaseURL = "http://127.0.0.1:8100"
    maintenance.SigningSecret = strings.Repeat("s", 32)
    maintenance.Issuer = "weknora"
    maintenance.Audience = "maintenance-api"
    maintenance.TokenTTL = 180 * time.Second
    maintenance.RequestTimeout = 30 * time.Second
    return &config.Config{Maintenance: maintenance}
}

func TestNewMaintenanceProxyDisabled(t *testing.T) {
    cfg := &config.Config{Maintenance: &config.MaintenanceConfig{Enabled: false}}

    proxy, err := newMaintenanceProxy(cfg)
    if err != nil {
        t.Fatalf("newMaintenanceProxy() error = %v", err)
    }
    if proxy != nil {
        t.Fatalf("proxy = %#v, want nil", proxy)
    }
}

func TestNewMaintenanceProxyEnabled(t *testing.T) {
    proxy, err := newMaintenanceProxy(validMaintenanceConfig())
    if err != nil {
        t.Fatalf("newMaintenanceProxy() error = %v", err)
    }
    if proxy == nil {
        t.Fatal("proxy is nil")
    }
}
```

- [ ] **Step 2: Run the provider tests and observe RED**

Run:

```powershell
go test ./internal/container -run '^TestNewMaintenanceProxy(Disabled|Enabled)$' -count=1 -v
```

Expected: compilation fails because `newMaintenanceProxy` is undefined.

- [ ] **Step 3: Implement the provider**

Create `internal/container/maintenance_proxy.go`:

```go
package container

import (
    "errors"
    "fmt"

    "github.com/Tencent/WeKnora/internal/config"
    "github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func newMaintenanceProxy(cfg *config.Config) (*maintenanceproxy.Proxy, error) {
    if cfg == nil {
        return nil, errors.New("maintenance proxy config is nil")
    }
    if !config.MaintenanceProxyEnabled(cfg) {
        return nil, nil
    }

    if err := cfg.Maintenance.Validate(); err != nil {
        return nil, fmt.Errorf("validate maintenance proxy config: %w", err)
    }

    signer, err := maintenanceproxy.NewSigner(
        []byte(cfg.Maintenance.SigningSecret),
        cfg.Maintenance.Issuer,
        cfg.Maintenance.Audience,
        cfg.Maintenance.TokenTTL,
    )
    if err != nil {
        return nil, fmt.Errorf("create maintenance signer: %w", err)
    }

    proxy, err := maintenanceproxy.New(
        cfg.Maintenance.BaseURL,
        signer,
        maintenanceproxy.ResolveWebActor,
        cfg.Maintenance.RequestTimeout,
    )
    if err != nil {
        return nil, fmt.Errorf("create maintenance proxy: %w", err)
    }
    return proxy, nil
}
```

- [ ] **Step 4: Run the provider success tests and observe GREEN**

Run:

```powershell
gofmt -w internal/container/maintenance_proxy.go internal/container/maintenance_proxy_test.go
go test ./internal/container -run '^TestNewMaintenanceProxy(Disabled|Enabled)$' -count=1 -v
```

Expected: `PASS`.

- [ ] **Step 5: Add fail-closed construction cases**

Append:

```go
func TestNewMaintenanceProxyRejectsInvalidEnabledConfig(t *testing.T) {
    tests := []struct {
        name       string
        mutate     func(*config.Config)
        errorMatch string
    }{
        {name: "short secret", mutate: func(cfg *config.Config) { cfg.Maintenance.SigningSecret = "short" }, errorMatch: "signing secret"},
        {name: "blank issuer", mutate: func(cfg *config.Config) { cfg.Maintenance.Issuer = " " }, errorMatch: "issuer and audience"},
        {name: "blank audience", mutate: func(cfg *config.Config) { cfg.Maintenance.Audience = " " }, errorMatch: "issuer and audience"},
        {name: "wrong ttl", mutate: func(cfg *config.Config) { cfg.Maintenance.TokenTTL = 179 * time.Second }, errorMatch: "exactly 180 seconds"},
        {name: "zero timeout", mutate: func(cfg *config.Config) { cfg.Maintenance.RequestTimeout = 0 }, errorMatch: "request_timeout"},
        {name: "relative base url", mutate: func(cfg *config.Config) { cfg.Maintenance.BaseURL = "/maintenance" }, errorMatch: "absolute HTTP(S) URL"},
        {name: "service path base url", mutate: func(cfg *config.Config) { cfg.Maintenance.BaseURL = "http://127.0.0.1:8100/service" }, errorMatch: "service root"},
    }

    for _, test := range tests {
        t.Run(test.name, func(t *testing.T) {
            cfg := validMaintenanceConfig()
            test.mutate(cfg)

            proxy, err := newMaintenanceProxy(cfg)
            if err == nil {
                t.Fatal("newMaintenanceProxy() error is nil")
            }
            if proxy != nil {
                t.Fatalf("proxy = %#v, want nil", proxy)
            }
            if !strings.Contains(err.Error(), test.errorMatch) {
                t.Fatalf("error = %q, want substring %q", err.Error(), test.errorMatch)
            }
        })
    }
}

func TestNewMaintenanceProxyRejectsNilConfig(t *testing.T) {
    proxy, err := newMaintenanceProxy(nil)
    if err == nil {
        t.Fatal("newMaintenanceProxy(nil) error is nil")
    }
    if proxy != nil {
        t.Fatalf("proxy = %#v, want nil", proxy)
    }
}
```

The disabled test must keep blank fields to prove the secret and other enabled-only values are not required.

- [ ] **Step 6: Register the provider immediately after configuration**

Modify `internal/container/container.go`:

```go
must(container.Provide(config.LoadConfig))
must(container.Provide(newMaintenanceProxy))
must(container.Provide(initLangfuse))
```

Do not call the provider manually and do not swallow its error.

- [ ] **Step 7: Run provider and config regression tests**

Run:

```powershell
gofmt -w internal/container/maintenance_proxy.go internal/container/maintenance_proxy_test.go internal/container/container.go
go test ./internal/container -run '^TestNewMaintenanceProxy' -count=1 -v
go test ./internal/config -run 'Maintenance' -count=1 -v
go test ./internal/container -count=1
```

Expected: all tests pass.

- [ ] **Step 8: Review and commit Task 2**

Confirm the provider never formats `SigningSecret` into an error or log.

Run:

```powershell
git diff --check
git add internal/container/maintenance_proxy.go internal/container/maintenance_proxy_test.go internal/container/container.go
git commit -m "feat: provide configured maintenance proxy"
```

Expected: one focused provider commit.

---

### Task 3: Authenticated Maintenance Route Registration

**Files:**

- Create: `internal/router/maintenance.go`
- Create: `internal/router/maintenance_test.go`
- Modify: `internal/router/router.go:23-31,36-96,191-203`

**Interfaces:**

- Consumes: `*gin.Engine` and optional `*maintenanceproxy.Proxy`.
- Produces: `func RegisterMaintenanceRoutes(*gin.Engine, *maintenanceproxy.Proxy)`.
- Extends: `RouterParams` with `MaintenanceProxy *maintenanceproxy.Proxy`.

- [ ] **Step 1: Write route absence and presence tests**

Create `internal/router/maintenance_test.go`:

```go
package router

import (
    "io"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
    "time"

    "github.com/gin-gonic/gin"

    "github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func newRouterTestProxy(t *testing.T, upstreamURL string) *maintenanceproxy.Proxy {
    t.Helper()
    signer, err := maintenanceproxy.NewSigner(
        []byte(strings.Repeat("s", 32)),
        "weknora",
        "maintenance-api",
        180*time.Second,
    )
    if err != nil {
        t.Fatalf("NewSigner() error = %v", err)
    }
    proxy, err := maintenanceproxy.New(
        upstreamURL,
        signer,
        func(*gin.Context) (maintenanceproxy.Actor, error) {
            return maintenanceproxy.Actor{
                UserID:    "user-1",
                TenantID:  "12",
                Roles:     []string{"viewer"},
                RequestID: "req-route",
            }, nil
        },
        5*time.Second,
    )
    if err != nil {
        t.Fatalf("maintenanceproxy.New() error = %v", err)
    }
    return proxy
}

func TestRegisterMaintenanceRoutesDisabled(t *testing.T) {
    engine := gin.New()
    RegisterMaintenanceRoutes(engine, nil)

    for _, route := range engine.Routes() {
        if route.Path == "/api/maintenance/*path" {
            t.Fatalf("unexpected Maintenance route: %#v", route)
        }
    }

    recorder := httptest.NewRecorder()
    request := httptest.NewRequest(http.MethodGet, "/api/maintenance/", nil)
    engine.ServeHTTP(recorder, request)
    if recorder.Code != http.StatusNotFound {
        t.Fatalf("status = %d, want 404", recorder.Code)
    }
}

func TestRegisterMaintenanceRoutesForwardsPathAndQuery(t *testing.T) {
    received := make(chan string, 1)
    upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
        received <- request.URL.RequestURI()
        writer.Header().Set("Content-Type", "application/json")
        _, _ = io.WriteString(writer, `{"ok":true}`)
    }))
    defer upstream.Close()

    engine := gin.New()
    RegisterMaintenanceRoutes(engine, newRouterTestProxy(t, upstream.URL))

    recorder := httptest.NewRecorder()
    request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs?page=2", nil)
    engine.ServeHTTP(recorder, request)

    if recorder.Code != http.StatusOK {
        t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
    }
    if uri := <-received; uri != "/api/jobs?page=2" {
        t.Fatalf("upstream URI = %q, want /api/jobs?page=2", uri)
    }
}
```

- [ ] **Step 2: Run the route tests and observe RED**

Run:

```powershell
go test ./internal/router -run '^TestRegisterMaintenanceRoutes' -count=1 -v
```

Expected: compilation fails because `RegisterMaintenanceRoutes` is undefined.

- [ ] **Step 3: Implement optional route registration**

Create `internal/router/maintenance.go`:

```go
package router

import (
    "github.com/gin-gonic/gin"

    "github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func RegisterMaintenanceRoutes(engine *gin.Engine, proxy *maintenanceproxy.Proxy) {
    if engine == nil || proxy == nil {
        return
    }
    engine.Any("/api/maintenance/*path", proxy.ServeHTTP)
}
```

The nil-engine check is defensive and does not replace dependency-injection validation.

- [ ] **Step 4: Run route tests and observe GREEN**

Run:

```powershell
gofmt -w internal/router/maintenance.go internal/router/maintenance_test.go
go test ./internal/router -run '^TestRegisterMaintenanceRoutes' -count=1 -v
```

Expected: `PASS`.

- [ ] **Step 5: Assert route-table methods and Unit 3 method authority**

Add a test that collects methods for `/api/maintenance/*path` after `engine.Any` and requires at least GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS, CONNECT, and TRACE. Then issue CONNECT and assert Unit 3 returns:

```text
HTTP 405
Allow: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS
error.code: MAINTENANCE_METHOD_NOT_ALLOWED
```

Do not implement a second method allowlist in the router package.

- [ ] **Step 6: Inject and register the route in `NewRouter`**

Add the import:

```go
"github.com/Tencent/WeKnora/internal/maintenanceproxy"
```

Add to `RouterParams`:

```go
MaintenanceProxy *maintenanceproxy.Proxy
```

Insert after audit-service injection and before `v1 := r.Group("/api/v1")`:

```go
RegisterMaintenanceRoutes(r, params.MaintenanceProxy)
```

The resulting order must remain:

```text
Auth
authenticated file routes
Langfuse
AuditServiceProvider
RegisterMaintenanceRoutes
/api/v1
```

- [ ] **Step 7: Run router regression tests**

Run:

```powershell
gofmt -w internal/router/router.go internal/router/maintenance.go internal/router/maintenance_test.go
go test ./internal/router -run '^(TestRegisterMaintenanceRoutes|Test.*Router)' -count=1 -v
go test ./internal/router -count=1
```

Expected: all router tests pass.

- [ ] **Step 8: Review and commit Task 3**

Check that there is no `/api/v1/maintenance` route and no unauthenticated registration before `middleware.Auth`.

Run:

```powershell
git diff --check
git add internal/router/maintenance.go internal/router/maintenance_test.go internal/router/router.go
git commit -m "feat: register authenticated maintenance routes"
```

Expected: one focused route-registration commit.

---

### Task 4: Bare-Path Application Handler and Entry-Point Wiring

**Files:**

- Create: `internal/router/http_handler.go`
- Create: `internal/router/http_handler_test.go`
- Modify: `internal/container/container.go:145-152`
- Modify: `cmd/server/main.go:27-42,67-76`
- Modify: `cmd/desktop/main.go:22-37,190-198`

**Interfaces:**

- Consumes: `*gin.Engine` and optional `*maintenanceproxy.Proxy`.
- Produces: concrete `*router.ApplicationHandler` implementing `http.Handler`.
- Entry points consume: `*router.ApplicationHandler`.

- [ ] **Step 1: Write handler tests before implementation**

Create `internal/router/http_handler_test.go`:

```go
package router

import (
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/gin-gonic/gin"
)

func TestApplicationHandlerRejectsBareMaintenancePathWhenEnabled(t *testing.T) {
    calls := 0
    handler := &ApplicationHandler{
        next: http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
            calls++
            writer.WriteHeader(http.StatusNoContent)
        }),
        rejectBareMaintenance: true,
    }

    methods := []string{
        http.MethodGet,
        http.MethodPost,
        http.MethodPut,
        http.MethodPatch,
        http.MethodDelete,
        http.MethodOptions,
    }
    targets := []string{"/api/maintenance", "/api/maintenance?force=true"}

    for _, method := range methods {
        for _, target := range targets {
            recorder := httptest.NewRecorder()
            request := httptest.NewRequest(method, target, nil)
            handler.ServeHTTP(recorder, request)
            if recorder.Code != http.StatusNotFound {
                t.Fatalf("%s %s status = %d, want 404", method, target, recorder.Code)
            }
            if location := recorder.Header().Get("Location"); location != "" {
                t.Fatalf("%s %s Location = %q, want empty", method, target, location)
            }
        }
    }

    if calls != 0 {
        t.Fatalf("next handler calls = %d, want 0", calls)
    }
}

func TestApplicationHandlerPassesAllowedAndUnrelatedPaths(t *testing.T) {
    calls := 0
    handler := &ApplicationHandler{
        next: http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
            calls++
            writer.WriteHeader(http.StatusNoContent)
        }),
        rejectBareMaintenance: true,
    }

    paths := []string{
        "/api/maintenance/",
        "/api/maintenance/jobs",
        "/api/maintenance/jobs/123",
        "/api/maintenance-old",
        "/api/maintenance2",
        "/health",
    }

    for _, path := range paths {
        recorder := httptest.NewRecorder()
        request := httptest.NewRequest(http.MethodGet, path, nil)
        handler.ServeHTTP(recorder, request)
        if recorder.Code != http.StatusNoContent {
            t.Fatalf("%s status = %d, want 204", path, recorder.Code)
        }
    }

    if calls != len(paths) {
        t.Fatalf("next handler calls = %d, want %d", calls, len(paths))
    }
}

func TestNewApplicationHandlerDisablesGuardWithoutProxy(t *testing.T) {
    engine := gin.New()
    engine.GET("/api/maintenance", func(c *gin.Context) {
        c.Status(http.StatusNoContent)
    })

    handler := NewApplicationHandler(engine, nil)
    recorder := httptest.NewRecorder()
    request := httptest.NewRequest(http.MethodGet, "/api/maintenance", nil)
    handler.ServeHTTP(recorder, request)

    if recorder.Code != http.StatusNoContent {
        t.Fatalf("status = %d, want 204", recorder.Code)
    }
}
```

- [ ] **Step 2: Run handler tests and observe RED**

Run:

```powershell
go test ./internal/router -run '^(TestApplicationHandler|TestNewApplicationHandler)' -count=1 -v
```

Expected: compilation fails because `ApplicationHandler` and `NewApplicationHandler` are undefined.

- [ ] **Step 3: Implement the outer handler**

Create `internal/router/http_handler.go`:

```go
package router

import (
    "net/http"

    "github.com/gin-gonic/gin"

    "github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

const bareMaintenancePath = "/api/maintenance"

type ApplicationHandler struct {
    next                  http.Handler
    rejectBareMaintenance bool
}

func NewApplicationHandler(
    engine *gin.Engine,
    proxy *maintenanceproxy.Proxy,
) *ApplicationHandler {
    return &ApplicationHandler{
        next:                  engine,
        rejectBareMaintenance: proxy != nil,
    }
}

func (h *ApplicationHandler) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
    if h.rejectBareMaintenance && request.URL.Path == bareMaintenancePath {
        http.NotFound(writer, request)
        return
    }
    h.next.ServeHTTP(writer, request)
}
```

Do not change `engine.RedirectTrailingSlash`.

- [ ] **Step 4: Run handler tests and observe GREEN**

Run:

```powershell
gofmt -w internal/router/http_handler.go internal/router/http_handler_test.go
go test ./internal/router -run '^(TestApplicationHandler|TestNewApplicationHandler)' -count=1 -v
```

Expected: `PASS`.

- [ ] **Step 5: Register `NewApplicationHandler` in the container**

Immediately after `router.NewRouter` registration add:

```go
must(container.Provide(router.NewRouter))
must(container.Provide(router.NewApplicationHandler))
```

Do not expose a generic unnamed `http.Handler` provider; the concrete type avoids future `dig` collisions.

- [ ] **Step 6: Wire the server entry point**

In `cmd/server/main.go`, retain the Gin import for `gin.SetMode`, add:

```go
"github.com/Tencent/WeKnora/internal/router"
```

Change the `c.Invoke` parameter from:

```go
router *gin.Engine,
```

to:

```go
appHandler *router.ApplicationHandler,
```

Change the server construction to:

```go
server := &http.Server{
    Handler: appHandler,
}
```

No other server lifecycle code changes.

- [ ] **Step 7: Wire the desktop entry point**

In `cmd/desktop/main.go`, retain the Gin import for mode configuration and add the internal router import.

Change the backend `c.Invoke` parameter to:

```go
appHandler *router.ApplicationHandler,
```

Change:

```go
server := &http.Server{Handler: appHandler}
```

Do not alter desktop bind selection, backend URL calculation, LAN URL calculation, Wails lifecycle, or shutdown behavior.

- [ ] **Step 8: Compile both entry points and run handler regressions**

Run:

```powershell
gofmt -w internal/container/container.go internal/router/http_handler.go internal/router/http_handler_test.go cmd/server/main.go cmd/desktop/main.go
go test ./internal/router -run '^(TestApplicationHandler|TestNewApplicationHandler)' -count=1 -v
go test ./cmd/server -run '^$'
go test ./cmd/desktop -run '^$'
```

Expected: handler tests pass and both command packages compile.

- [ ] **Step 9: Review and commit Task 4**

Confirm `/api/maintenance` is the only path handled outside Gin and the guard is disabled when the proxy is nil.

Run:

```powershell
git diff --check
git add internal/router/http_handler.go internal/router/http_handler_test.go internal/container/container.go cmd/server/main.go cmd/desktop/main.go
git commit -m "fix: reject bare maintenance proxy path"
```

Expected: one focused entry-point wiring commit.

---

### Task 5: Identity, Request-ID, CORS, and Security Integration Gate

**Files:**

- Create: `internal/router/maintenance_integration_test.go`
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**

- Consumes: `middleware.RequestID`, `ResolveWebActor`, `NewSigner`, `Proxy`, `RegisterMaintenanceRoutes`, and `ApplicationHandler`.
- Verifies: the complete trusted-context-to-upstream-JWT contract without a real Maintenance API.
- Produces: final Unit 4 verification evidence and durable ledger update.

- [ ] **Step 1: Add a JWT-decoding upstream fixture**

Create `internal/router/maintenance_integration_test.go` with package `router` and a fixture that:

- starts `httptest.Server`;
- reads `Authorization: Bearer <token>`;
- parses `maintenanceproxy.Claims` with HS256 and the test secret;
- records `request.URL.RequestURI()` and `X-Request-ID`;
- returns JSON with status 200;
- counts calls atomically.

Use this exact parse contract:

```go
parsed, err := jwt.ParseWithClaims(
    tokenString,
    &maintenanceproxy.Claims{},
    func(token *jwt.Token) (any, error) {
        if token.Method != jwt.SigningMethodHS256 {
            return nil, fmt.Errorf("unexpected signing method %s", token.Method.Alg())
        }
        return secret, nil
    },
    jwt.WithIssuer("weknora"),
    jwt.WithAudience("maintenance-api"),
)
```

Require `parsed.Valid == true` and type-assert `parsed.Claims.(*maintenanceproxy.Claims)`.

- [ ] **Step 2: Add a trusted identity middleware for tests**

Use a test-only middleware that writes context values into `c.Request.Context()`:

```go
func injectMaintenanceIdentity(
    principal types.Principal,
    userID string,
    tenantID uint64,
    role types.TenantRole,
    systemAdmin bool,
) gin.HandlerFunc {
    return func(c *gin.Context) {
        ctx := c.Request.Context()
        ctx = context.WithValue(ctx, types.PrincipalContextKey, principal)
        ctx = context.WithValue(ctx, types.UserIDContextKey, userID)
        ctx = context.WithValue(ctx, types.TenantIDContextKey, tenantID)
        ctx = context.WithValue(ctx, types.TenantRoleContextKey, role)
        ctx = context.WithValue(ctx, types.SystemAdminContextKey, systemAdmin)
        c.Request = c.Request.WithContext(ctx)
        c.Next()
    }
}
```

Place `middleware.RequestID()` before this middleware so the request ID is already present.

- [ ] **Step 3: Test contributor claims and request-ID propagation**

Build an engine:

```text
middleware.RequestID
injectMaintenanceIdentity(web_user user-1, tenant 12, contributor, false)
RegisterMaintenanceRoutes
```

Send:

```http
GET /api/maintenance/jobs?page=1
X-Request-ID: req-integration-1
```

Assert:

```text
status == 200
claims.Subject == user-1
claims.TenantID == 12
claims.Roles == [contributor]
claims.RequestID == req-integration-1
claims.Issuer == weknora
claims.Audience contains maintenance-api
claims.ExpiresAt - claims.IssuedAt == 180 seconds
claims.ID is a UUIDv4
upstream X-Request-ID == req-integration-1
upstream URI == /api/jobs?page=1
response X-Request-ID == req-integration-1
upstream call count == 1
```

Reuse the UUIDv4 shape checks already established in Unit 2 tests rather than adding a new UUID dependency.

- [ ] **Step 4: Test owner and system-admin role mapping through the proxy**

Add table cases:

```text
owner, systemAdmin=false -> [admin]
viewer, systemAdmin=true -> [admin]
```

Decode the JWT at the upstream and require exactly one role.

- [ ] **Step 5: Test API-key and mismatched identities never reach upstream**

Cases:

```text
PrincipalAPITenant with synthetic user ID
PrincipalAPIPlatform
PrincipalAPIExternalUser
PrincipalWebUser user-2 with UserID user-1
missing PrincipalContextKey
missing TenantRoleContextKey
```

For each case assert:

```text
status == 401
error.code == MAINTENANCE_ACTOR_UNAVAILABLE
upstream call count does not increase
response has a non-blank X-Request-ID
```

When the input request ID is valid, assert the 401 response preserves it.

- [ ] **Step 6: Test browser identity headers cannot override claims**

Authenticated context:

```text
web_user user-1
tenant 12
viewer
systemAdmin false
```

Browser headers:

```http
X-Tenant-ID: 999
X-User-ID: attacker
X-Role: admin
X-User-Roles: admin
X-System-Admin: true
Authorization: Bearer browser-token
X-Internal-Authorization: browser-internal-token
```

Assert decoded claims remain:

```text
sub == user-1
tenant_id == 12
roles == [viewer]
```

Also assert the upstream authorization token is a newly valid HS256 token, not either browser token.

- [ ] **Step 7: Test CORS preflight and ordinary OPTIONS**

Construct a test engine with the same CORS method and header configuration as `NewRouter`, followed by `middleware.RequestID()` and the Maintenance route.

Browser preflight request:

```http
OPTIONS /api/maintenance/jobs
Origin: http://localhost:3000
Access-Control-Request-Method: GET
```

Assert:

```text
CORS middleware completes the request
status is the existing gin-contrib/cors preflight success status
upstream call count does not increase
body does not contain MAINTENANCE_ACTOR_UNAVAILABLE
```

Ordinary OPTIONS request without preflight headers:

```http
OPTIONS /api/maintenance/jobs
X-Request-ID: req-options
```

Assert:

```text
status == 401
error.code == MAINTENANCE_ACTOR_UNAVAILABLE
upstream call count does not increase
```

Do not hard-code a new CORS policy in production code.

- [ ] **Step 8: Test the outer bare-path guard with a real proxy**

Construct `ApplicationHandler` with the integration engine and non-nil proxy.

Send:

```text
GET /api/maintenance
GET /api/maintenance?x=1
```

Assert:

```text
status == 404
Location header is empty
upstream call count does not increase
```

Then send `GET /api/maintenance/` with valid identity and assert the upstream receives `/api/`.

- [ ] **Step 9: Run focused and affected suites**

Run:

```powershell
gofmt -w internal/router/maintenance_integration_test.go
go test ./internal/maintenanceproxy -count=1
go test ./internal/container -count=1
go test ./internal/router -count=1
go test ./internal/config -count=1
go test ./cmd/server -run '^$'
go test ./cmd/desktop -run '^$'
```

Expected: every command passes.

- [ ] **Step 10: Run static verification**

Run:

```powershell
go vet ./internal/maintenanceproxy ./internal/router ./internal/container
git diff --check
```

Expected: no vet or whitespace errors.

- [ ] **Step 11: Run race verification with the established Windows toolchain**

Run:

```powershell
$env:Path = "C:\msys64\ucrt64\bin;$env:Path"
$env:CGO_ENABLED = "1"
$env:CC = "gcc"
$env:CXX = "g++"
go test -race ./internal/maintenanceproxy ./internal/router -count=1
```

Expected: both packages pass with no race report.

- [ ] **Step 12: Perform the final security review**

Inspect the complete Unit 4 diff and confirm:

```text
no browser identity header is read by ResolveWebActor
no PrincipalFromContext fallback is used
no TenantRoleFromContext fallback is used
no signing secret or token is logged
no non-web principal can sign a token
no route is registered before Auth
no /api/v1/maintenance route exists
no global Gin redirect setting changed
no Unit 2 or Unit 3 production file changed
no upstream request occurs after actor-resolution failure
```

Run:

```powershell
git diff 4125b860adef68f55f83248c99db930335f69750 -- internal/maintenanceproxy internal/container internal/router cmd/server cmd/desktop
```

- [ ] **Step 13: Update the durable progress ledger only after all gates are green**

Change the Unit 4 line in `.superpowers/sdd/progress.md` to:

```markdown
- Unit 4: complete — explicit WeKnora web-user actor mapping, owner/admin/system-admin role normalization, disabled-aware fail-closed proxy construction, authenticated route registration, bare-path 404 guard, request-ID propagation, CORS behavior, entry-point compilation, focused suites, race detection, and security review all verified.
```

Do not change Unit 5 from pending.

- [ ] **Step 14: Commit integration evidence and ledger**

Run:

```powershell
git add internal/router/maintenance_integration_test.go .superpowers/sdd/progress.md
git commit -m "test: verify maintenance identity routing"
git status --short
```

Expected: commit succeeds and working tree is clean.

- [ ] **Step 15: Record final branch evidence**

Run:

```powershell
git log --oneline -8
git status --short
git rev-parse HEAD
git rev-parse origin/feature/maintenance-frontend-plan05
```

Expected:

```text
working tree clean
HEAD equals origin/feature/maintenance-frontend-plan05 after push
Unit 4 ledger line is complete
Unit 5 remains the first pending unit
```

---

## Final Verification Gate

Run from the worktree root:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05

gofmt -w internal/maintenanceproxy/actor_resolver.go internal/maintenanceproxy/actor_resolver_test.go internal/container/maintenance_proxy.go internal/container/maintenance_proxy_test.go internal/container/container.go internal/router/maintenance.go internal/router/maintenance_test.go internal/router/http_handler.go internal/router/http_handler_test.go internal/router/maintenance_integration_test.go internal/router/router.go cmd/server/main.go cmd/desktop/main.go

go test ./internal/maintenanceproxy -count=1
go test ./internal/container -count=1
go test ./internal/router -count=1
go test ./internal/config -count=1
go test ./cmd/server -run '^$'
go test ./cmd/desktop -run '^$'
go vet ./internal/maintenanceproxy ./internal/router ./internal/container

$env:Path = "C:\msys64\ucrt64\bin;$env:Path"
$env:CGO_ENABLED = "1"
$env:CC = "gcc"
$env:CXX = "g++"
go test -race ./internal/maintenanceproxy ./internal/router -count=1

git diff --check
git status --short
```

Expected: every test and vet command passes, race detection reports no race, `git diff --check` prints nothing, and the working tree is clean after the final commit.

## Implementation Completion Criteria

- `ResolveWebActor` uses explicit context values and rejects fallback identities.
- Resolver errors preserve a valid request ID in a partial Actor.
- Disabled mode returns a nil proxy without requiring a secret.
- Enabled invalid configuration prevents dependency construction.
- Router registers `/api/maintenance/*path` only with a non-nil proxy.
- Route registration occurs after Auth, Langfuse, and audit-service injection.
- The outer handler returns a non-redirecting 404 for `/api/maintenance` only when enabled.
- Server and desktop use `ApplicationHandler` without changing lifecycle behavior.
- Successful JWT claims use authenticated user, tenant, role, and request ID.
- API keys, embedded principals, IM principals, and mismatched web identities never reach upstream.
- Browser identity and authorization headers cannot control the internal actor or token.
- CORS preflight does not create a JWT or contact upstream.
- Unit 2 and Unit 3 production contracts remain unchanged.
- Focused tests, command-package compilation, vet, race detection, and security review pass.
- `.superpowers/sdd/progress.md` marks Unit 4 complete and Unit 5 remains pending.

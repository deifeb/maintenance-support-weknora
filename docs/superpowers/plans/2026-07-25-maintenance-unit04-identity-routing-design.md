# Maintenance Unit 04 Identity Routing Design

**Status:** Approved

**Approved date:** 2026-07-25

**Branch:** `feature/maintenance-frontend-plan05`

**Depends on:**

- Unit 1 canonical Maintenance proxy configuration
- Unit 2 short-lived HS256 actor token signer
- Unit 3 HTTP and SSE reverse proxy

## 1. Purpose

Unit 4 connects WeKnora authentication to the private Maintenance API proxy. It projects a trusted, authenticated WeKnora web user into the `maintenanceproxy.Actor` contract, constructs the proxy through dependency injection, registers `/api/maintenance/*path` after the authenticated middleware chain, and prevents Gin from redirecting the unsupported bare path `/api/maintenance`.

The unit does not implement FastAPI token verification, Maintenance RBAC, business APIs, database models, frontend pages, WebSocket proxying, or persisted Maintenance audit events.

## 2. Request architecture

```text
Browser
  -> ApplicationHandler
  -> Gin Engine
  -> CORS
  -> RequestID
  -> Language
  -> Logger
  -> Recovery
  -> ErrorHandler
  -> Auth
  -> Langfuse
  -> AuditServiceProvider
  -> /api/maintenance/*path
  -> ResolveWebActor
  -> Signer.Sign
  -> ReverseProxy
  -> Maintenance API /api/*
```

Maintenance remains disabled by default. When disabled, no signer or proxy is constructed, no Maintenance route is registered, and the existing Gin engine handles requests normally.

## 3. Accepted principals

Only an explicitly authenticated WeKnora web user may receive a Maintenance internal JWT.

The resolver requires all of the following:

- `types.PrincipalContextKey` exists and contains a valid `types.Principal`.
- `Principal.Type == types.PrincipalWebUser`.
- `types.UserIDContextKey` exists and contains a non-blank string.
- `Principal.ID` exactly equals the authenticated user ID.
- `types.TenantIDContextKey` exists, is `uint64`, and is greater than zero.
- `types.TenantRoleContextKey` exists, is `types.TenantRole`, and is valid.
- `types.RequestIDContextKey` exists and contains a non-blank string.
- `types.SystemAdminContextKey`, when present, is a boolean.

The resolver must not call `types.PrincipalFromContext`, because that helper may synthesize a `web_user` principal from `UserIDContextKey`. It must not call `types.TenantRoleFromContext`, because that helper falls back to `viewer` when the role is missing or invalid.

The following principals are rejected:

- `api_tenant`
- `api_platform`
- `api_external_user`
- `im_user`
- `embed_channel`
- `embed_session`
- `embed_visitor`

Resolver rejection is deliberately indistinguishable at the public boundary. Unit 3 returns `401 MAINTENANCE_ACTOR_UNAVAILABLE` and does not disclose which identity field failed.

## 4. Actor mapping

```text
Actor.UserID
  <- authenticated UserIDContextKey
  -> JWT sub

Actor.TenantID
  <- authenticated TenantIDContextKey
  -> base-10 string
  -> JWT tenant_id

Actor.RequestID
  <- RequestIDContextKey
  -> JWT request_id
  -> upstream X-Request-ID

Actor.Roles
  <- one normalized Maintenance role
  -> JWT roles
```

The subject is the raw WeKnora user ID. It is not a username, email address, `Principal.StorageID`, or browser-supplied value.

The resolver captures a valid request ID before later identity checks. On a later resolver error it returns a partial `Actor{RequestID: requestID}` with the error, allowing Unit 3 to preserve the WeKnora correlation ID in the 401 response. Missing or malformed request IDs remain subject to Unit 3 fallback handling.

## 5. Role mapping

The JWT contains exactly one normalized role.

| WeKnora state | Maintenance role |
|---|---|
| system administrator | `admin` |
| tenant owner | `admin` |
| tenant admin | `admin` |
| tenant contributor | `contributor` |
| tenant viewer | `viewer` |

A system administrator must still have a valid explicit web principal, matching user ID, positive tenant ID, explicit valid tenant role, and request ID. The system-admin flag elevates the role only; it does not bypass identity completeness checks.

Role inheritance is not encoded in the JWT. Maintenance API RBAC will define that `admin` includes lower-level operations and that `contributor` includes read operations.

## 6. Trusted data boundary

Actor construction reads only `c.Request.Context()` values written by WeKnora middleware. It ignores browser-controlled identity material, including:

- `X-Tenant-ID`
- `X-User-ID`
- `X-Role`
- `X-User-Roles`
- `X-System-Admin`
- query parameters
- request bodies
- custom cookie fields

Unit 3 continues to remove browser authorization, cookie, tenant, user, internal, forwarding, and Maintenance-prefixed headers before forwarding the request.

## 7. Actor resolver component

File:

```text
internal/maintenanceproxy/actor_resolver.go
```

Public package interface:

```go
func ResolveWebActor(c *gin.Context) (Actor, error)
```

Package-private helper:

```go
func mapMaintenanceRole(role types.TenantRole, systemAdmin bool) (string, error)
```

The resolver is stateless and safe for concurrent use. Errors contain only structural reasons and never include actual user IDs, tenant IDs, supplied roles, tokens, or secrets.

## 8. Proxy provider

File:

```text
internal/container/maintenance_proxy.go
```

Provider interface:

```go
func newMaintenanceProxy(cfg *config.Config) (*maintenanceproxy.Proxy, error)
```

Behavior:

```text
nil root config
  -> error

Maintenance disabled
  -> nil proxy, nil error
  -> do not require a signing secret

Maintenance enabled
  -> validate MaintenanceConfig
  -> NewSigner(SigningSecret, Issuer, Audience, TokenTTL)
  -> maintenanceproxy.New(BaseURL, signer, ResolveWebActor, RequestTimeout)
  -> return proxy

Any enabled-state validation or construction error
  -> return wrapped error
  -> dependency graph fails
  -> WeKnora startup fails
```

The provider revalidates the enabled configuration even though `config.LoadConfig` already validates it. This preserves fail-closed behavior when the provider is tested or reused with manually assembled configuration.

The provider must not log or expose `SigningSecret`.

## 9. Dependency injection

`BuildContainer` registers the provider after `config.LoadConfig` and before `router.NewRouter`:

```go
must(container.Provide(config.LoadConfig))
must(container.Provide(newMaintenanceProxy))
// existing providers
must(container.Provide(router.NewRouter))
must(container.Provide(router.NewApplicationHandler))
```

`dig` remains responsible for propagating constructor errors. The disabled provider returns a typed nil `*maintenanceproxy.Proxy`, which is injected into both the router and application handler and interpreted as disabled.

## 10. Route registration

File:

```text
internal/router/maintenance.go
```

Interface:

```go
func RegisterMaintenanceRoutes(engine *gin.Engine, proxy *maintenanceproxy.Proxy)
```

Behavior:

```text
proxy == nil
  -> register nothing

proxy != nil
  -> engine.Any("/api/maintenance/*path", proxy.ServeHTTP)
```

The call is inserted after:

```text
Auth
Langfuse
AuditServiceProvider
```

and before creation of the `/api/v1` route group.

The route remains `/api/maintenance/*path`, not `/api/v1/maintenance/*path`.

`gin.Engine.Any` allows requests to reach Unit 3 for normal and uncommon HTTP methods. Unit 3 remains the authority that accepts GET, HEAD, POST, PUT, PATCH, DELETE, and OPTIONS and rejects CONNECT or TRACE with `405 MAINTENANCE_METHOD_NOT_ALLOWED`.

## 11. Bare-path protection

Unit 3 accepts `/api/maintenance/` and descendants but rejects paths without the trailing slash. Registering both `/api/maintenance` and `/api/maintenance/*path` is not possible because Gin catch-all routes conflict with an exact sibling route. Registering only the catch-all allows Gin to redirect `/api/maintenance` to `/api/maintenance/`.

The approved solution is an outer HTTP handler.

File:

```text
internal/router/http_handler.go
```

Interface:

```go
type ApplicationHandler struct {
    next                  http.Handler
    rejectBareMaintenance bool
}

func NewApplicationHandler(
    engine *gin.Engine,
    proxy *maintenanceproxy.Proxy,
) *ApplicationHandler

func (h *ApplicationHandler) ServeHTTP(
    writer http.ResponseWriter,
    request *http.Request,
)
```

Behavior:

```text
proxy != nil and request.URL.Path == "/api/maintenance"
  -> standard HTTP 404
  -> no Location header
  -> do not enter Gin

otherwise
  -> engine.ServeHTTP
```

The guard compares `URL.Path`, so query strings do not bypass it. It does not block `/api/maintenance/`, descendants, or unrelated lookalike paths such as `/api/maintenance-old`.

The guard is inactive when Maintenance is disabled and does not alter global Gin trailing-slash behavior for existing routes.

## 12. Server entry points

Modify:

```text
cmd/server/main.go
cmd/desktop/main.go
```

Both entry points inject `*router.ApplicationHandler` instead of using `*gin.Engine` as the server handler:

```go
server := &http.Server{
    Handler: appHandler,
}
```

Gin imports remain because both entry points still set Gin mode. Listener setup, route-count logging, desktop reverse proxying, graceful shutdown, and resource cleanup remain unchanged.

## 13. Request ID rules

WeKnora `RequestID` middleware remains the source of the correlation ID. Unit 4 does not generate a second internal request ID and does not add a parent request ID claim.

Unit 4 performs presence and type checks. Unit 3 remains the single authority for normalization, the 128-byte maximum, and control-character rejection.

Expected correlation for a successful request:

```text
WeKnora response X-Request-ID
  == Actor.RequestID
  == JWT request_id
  == upstream X-Request-ID
```

## 14. OPTIONS and CORS

A valid browser CORS preflight is handled by the existing CORS middleware before authentication and proxying. It does not create an internal JWT or reach the Maintenance API.

A non-preflight OPTIONS request may pass the Auth middleware's OPTIONS bypass but has no explicit web-user context. The actor resolver rejects it, Unit 3 returns `401 MAINTENANCE_ACTOR_UNAVAILABLE`, and the upstream is not called.

## 15. Error semantics

Actor resolution errors:

```text
401 MAINTENANCE_ACTOR_UNAVAILABLE
```

Identity signing or trusted request-ID failures after successful actor resolution:

```text
500 MAINTENANCE_IDENTITY_EXCHANGE_FAILED
```

Invalid proxy paths and unsupported methods continue to use Unit 3 contracts. Provider construction errors are startup errors and never become runtime 404 or 503 responses.

The bare path `/api/maintenance` uses the standard Go 404 response because it is outside the valid proxy route contract.

## 16. Concurrency and state

New Unit 4 components do not maintain request-to-request mutable state:

- `ResolveWebActor` transforms one request context.
- `newMaintenanceProxy` runs during dependency construction.
- `RegisterMaintenanceRoutes` runs during router construction.
- `ApplicationHandler` contains only read-only fields after construction.

No locks, actor caches, shared role slices, token reuse, delayed initialization, or runtime configuration mutation are introduced.

## 17. Files

Create:

```text
internal/maintenanceproxy/actor_resolver.go
internal/maintenanceproxy/actor_resolver_test.go
internal/container/maintenance_proxy.go
internal/container/maintenance_proxy_test.go
internal/router/maintenance.go
internal/router/maintenance_test.go
internal/router/maintenance_integration_test.go
internal/router/http_handler.go
internal/router/http_handler_test.go
```

Modify:

```text
internal/container/container.go
internal/router/router.go
cmd/server/main.go
cmd/desktop/main.go
.superpowers/sdd/progress.md
```

Do not modify unless a test exposes a verified defect:

```text
internal/config/maintenance.go
internal/maintenanceproxy/claims.go
internal/maintenanceproxy/signer.go
internal/maintenanceproxy/proxy.go
```

## 18. Verification contract

Focused verification:

```powershell
go test ./internal/maintenanceproxy -count=1
go test ./internal/container -count=1
go test ./internal/router -count=1
go test ./internal/config -count=1
go test ./cmd/server -run '^$'
go test ./cmd/desktop -run '^$'
```

Static verification:

```powershell
gofmt -w <changed-go-files>
go vet ./internal/maintenanceproxy ./internal/router ./internal/container
```

Race verification on the established Windows toolchain:

```powershell
$env:Path = "C:\msys64\ucrt64\bin;$env:Path"
$env:CGO_ENABLED = "1"
$env:CC = "gcc"
$env:CXX = "g++"
go test -race ./internal/maintenanceproxy ./internal/router -count=1
```

## 19. Acceptance criteria

Unit 4 is complete only when all of the following are true:

- Maintenance remains disabled by default.
- Disabled mode does not require a signing secret.
- Disabled mode registers no Maintenance route.
- Enabled configuration errors prevent startup.
- Only an explicit matching `web_user` principal can receive an internal JWT.
- API keys and every other machine or embedded principal are rejected.
- JWT `sub`, `tenant_id`, `roles`, and `request_id` come from authenticated context.
- Browser identity headers cannot override the actor.
- Owner, tenant admin, and system admin map to one `admin` role.
- Contributor maps to one `contributor` role.
- Viewer maps to one `viewer` role.
- Missing or invalid tenant role does not silently become viewer.
- `/api/maintenance` returns 404 without redirect when enabled.
- `/api/maintenance/` and descendants enter the authenticated proxy.
- The route is registered after Auth, Langfuse, and audit-service injection.
- Unit 2 and Unit 3 contracts remain unchanged.
- Focused, entry-point compilation, static, and race verification pass.

## 20. Static design self-review

The approved design was checked against the existing branch before implementation planning.

- **Gin route conflict:** exact and catch-all sibling routes cannot coexist. Resolved by the approved `ApplicationHandler` guard rather than changing global Gin redirect behavior.
- **Correlation on resolver failure:** Unit 3 reads `actor.RequestID` even when the resolver returns an error. The implementation plan therefore captures a valid request ID first and returns it in a partial Actor on later failures.
- **Disabled construction:** configuration validation that requires a secret occurs only after the enabled check. Disabled deployments continue to start with no secret.
- **Identity fallback:** the implementation must use direct context-key type assertions rather than helper methods that synthesize a principal or viewer role.
- **Authority separation:** Unit 4 checks identity completeness; Unit 3 remains the authority for request-ID normalization, path validation, method validation, header isolation, signing invocation, and stable proxy errors.
- **Scope:** no FastAPI, database, frontend, WebSocket, or business authorization work is included.

No unresolved design gap remains. Functional implementation still requires a separately approved implementation plan and TDD execution gate.

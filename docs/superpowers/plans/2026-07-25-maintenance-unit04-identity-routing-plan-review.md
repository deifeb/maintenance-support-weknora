# Maintenance Unit 04 Implementation Plan Static Review

**Review date:** 2026-07-25

**Reviewed files:**

- `2026-07-25-maintenance-unit04-identity-routing-design.md`
- `2026-07-25-maintenance-unit04-identity-routing-implementation.md`

**Result:** Ready for implementation approval. No functional code has been changed.

## 1. Specification coverage

Every approved Unit 4 requirement maps to an implementation task:

| Approved requirement | Implementation task |
|---|---|
| Explicit `web_user` principal only | Task 1 |
| Principal ID equals authenticated User ID | Task 1 |
| Tenant and role from explicit context keys | Task 1 |
| Owner/admin/system-admin normalization | Task 1 |
| One Maintenance role only | Task 1 |
| Preserve request ID on resolver failure | Task 1 and Task 5 |
| Disabled mode constructs no proxy | Task 2 |
| Enabled construction errors fail startup | Task 2 |
| Route after Auth, Langfuse, and audit injection | Task 3 |
| No `/api/v1/maintenance` route | Task 3 |
| `/api/maintenance` returns non-redirecting 404 | Task 4 |
| Server and desktop use the outer handler | Task 4 |
| JWT claims and upstream request ID verified | Task 5 |
| API keys and non-web principals rejected | Task 5 |
| Browser identity headers ignored | Task 5 |
| CORS preflight does not reach upstream | Task 5 |
| Race and security gates | Task 5 |

No approved requirement lacks an implementation or verification step.

## 2. Normative clarifications

These clarifications are binding during execution and resolve wording that was less exact in the longer documents.

### 2.1 CORS preflight status

The current Gin CORS configuration does not override `OptionsResponseStatusCode`; the expected successful preflight status is therefore:

```text
204 No Content
```

Task 5 Step 7 must assert status 204, no Maintenance actor error, and zero upstream calls.

### 2.2 Exact formatting command

Where the design document uses the shorthand `<changed-go-files>`, execute the exact final list from the implementation plan:

```powershell
gofmt -w internal/maintenanceproxy/actor_resolver.go internal/maintenanceproxy/actor_resolver_test.go internal/container/maintenance_proxy.go internal/container/maintenance_proxy_test.go internal/container/container.go internal/router/maintenance.go internal/router/maintenance_test.go internal/router/http_handler.go internal/router/http_handler_test.go internal/router/maintenance_integration_test.go internal/router/router.go cmd/server/main.go cmd/desktop/main.go
```

No placeholder is permitted in the executed command.

### 2.3 Missing-context test construction

A Go `context.Context` value cannot be removed after insertion. Each missing-key case in Task 1 must be constructed from `context.Background()` with an explicit set of remaining valid values. Tests must not attempt to overwrite a key with `nil` as a substitute for absence.

### 2.4 Resolver error correlation

For any failure after a valid request ID has been extracted, `ResolveWebActor` returns:

```go
Actor{RequestID: requestID}, err
```

For missing, non-string, or blank request IDs it returns an empty Actor. This is necessary because Unit 3 reads `actor.RequestID` on resolver failure before writing `MAINTENANCE_ACTOR_UNAVAILABLE`.

### 2.5 Route-method ownership

`RegisterMaintenanceRoutes` uses `engine.Any` and does not duplicate Unit 3's allowlist. The route test must prove that CONNECT reaches Unit 3 and receives:

```text
405 MAINTENANCE_METHOD_NOT_ALLOWED
Allow: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS
```

### 2.6 Upstream fixture synchronization

The integration upstream must use buffered channels or mutex/atomic-protected state. No test may block indefinitely waiting for an upstream observation. Each channel read uses a bounded timeout:

```go
select {
case observation := <-observations:
    _ = observation
case <-time.After(2 * time.Second):
    t.Fatal("timed out waiting for Maintenance upstream request")
}
```

For tests that require zero upstream requests, use an atomic call counter rather than waiting on a channel.

## 3. Placeholder scan

The implementation plan contains no `TODO`, `TBD`, `implement later`, or deferred feature marker. The design document's formatting shorthand is resolved by Section 2.2 of this review.

## 4. Type and interface consistency

The following signatures are consistent across design and implementation tasks:

```go
func ResolveWebActor(*gin.Context) (maintenanceproxy.Actor, error)
func newMaintenanceProxy(*config.Config) (*maintenanceproxy.Proxy, error)
func RegisterMaintenanceRoutes(*gin.Engine, *maintenanceproxy.Proxy)
func NewApplicationHandler(*gin.Engine, *maintenanceproxy.Proxy) *ApplicationHandler
func (*ApplicationHandler).ServeHTTP(http.ResponseWriter, *http.Request)
```

The injected concrete types are:

```text
*maintenanceproxy.Proxy
*gin.Engine
*router.ApplicationHandler
```

No generic unnamed `http.Handler` provider is added to `dig`.

## 5. Scope review

The plan does not include or require:

- FastAPI internal JWT verification
- Maintenance API RBAC
- database models or migrations
- frontend pages
- WebSocket proxy support
- business endpoints
- persisted Maintenance audit rows

Unit 2 and Unit 3 production files remain protected unless a new failing regression test proves a defect.

## 6. Execution gate

Implementation may start only after explicit user approval of the implementation plan. Approval authorizes Task 1 RED tests, not uncontrolled execution of all later tasks. Each task remains subject to its own test, review, commit, and progress checkpoint.

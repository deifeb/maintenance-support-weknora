# Plan 05-1 Security Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Starting from commit `70c6f460981b8d841569881c4ed86006057b39ab`, close the remaining Plan 05-1 route-security, RBAC/metadata, proxy-identity, production-configuration, Docker, documentation, and final-gate gaps so Plan 05-2 may begin safely.

**Architecture:** Keep the existing `browser -> WeKnora Gin proxy -> internal JWT -> FastAPI ActorContext -> tenant-scoped service/repository` chain. Finish security at the router boundary with named role dependencies, pass the verified actor into services, emit actor metadata on every business success response, and prove the whole contract with static route inventory plus HTTP integration tests. Package Maintenance API as an internal-only Compose service sharing the same signing secret with WeKnora.

**Tech Stack:** Go 1.26, Gin, `github.com/golang-jwt/jwt/v5`, Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Pytest, Ruff, Docker Compose, PowerShell 5.1, Git.

## Global Constraints

- Repository: `deifeb/maintenance-support-weknora`.
- Worktree: `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Branch: `feature/maintenance-frontend-plan05`.
- Required starting commit: `70c6f460981b8d841569881c4ed86006057b39ab`.
- PR target after the final gate: `feature/demand-calculation-engine`.
- Do not begin Plan 05-2 implementation before every Task 8 gate in this plan is green and committed.
- Browser code calls only `/api/maintenance/*`.
- FastAPI derives actor, tenant, role, request ID, and token ID only from the verified internal JWT.
- Request headers, query parameters, and JSON bodies never select a tenant.
- Every business route declares exactly one named role dependency: `require_viewer`, `require_contributor`, or `require_admin`.
- Every business `success_response(...)` call supplies `actor=actor`.
- `GET`, list, detail, status, export, SSE, and read-only comparison are viewer capabilities.
- Ordinary create, update, activate/deactivate, import, validate, compute, cancel, retry, clone, and child editing are contributor capabilities.
- Delete, publish, retire, and high-risk confirmation are admin capabilities.
- Health, root, and system-info endpoints keep their existing unauthenticated response shape.
- Services receive `ActorContext`; repositories receive explicit `tenant_id`.
- Cross-tenant reads, writes, references, comparisons, and child mutations return 404 or a stable business denial without disclosing target existence.
- Repository methods do not commit. Existing service transaction boundaries are preserved.
- Do not add idempotency, audit, inventory, frontend, or schema functionality unrelated to this security closure.
- Every production change follows observed RED, focused GREEN, affected regression, Ruff, compile/build, diff check, review, then commit.
- RED/GREEN scripts must not stage, commit, push, reset, clean, or discard files.
- Keep the Git index empty until each task’s review is approved.

---

## File Map

### Create

```text
docs/superpowers/plans/2026-07-26-maintenance-plan05-01-security-closure.md
extensions/maintenance-api/tests/security/test_api_rbac.py
extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py
extensions/maintenance-api/tests/security/test_security_settings.py
extensions/maintenance-api/Dockerfile
```

### Modify

```text
.superpowers/sdd/progress.md

extensions/maintenance-api/app/api/v1/demand/scenarios.py
extensions/maintenance-api/app/api/v1/demand/comparisons.py
extensions/maintenance-api/app/api/v1/demand/calculations.py
extensions/maintenance-api/app/api/v1/demand/repair_profiles.py

extensions/maintenance-api/app/api/v1/master_data/configurations.py
extensions/maintenance-api/app/api/v1/master_data/equipment_models.py
extensions/maintenance-api/app/api/v1/master_data/imports.py
extensions/maintenance-api/app/api/v1/master_data/inventories.py
extensions/maintenance-api/app/api/v1/master_data/parts.py
extensions/maintenance-api/app/api/v1/master_data/reliability.py
extensions/maintenance-api/app/api/v1/master_data/spare_parts.py
extensions/maintenance-api/app/api/v1/master_data/supplier_offers.py
extensions/maintenance-api/app/api/v1/master_data/suppliers.py
extensions/maintenance-api/app/api/v1/master_data/warehouses.py

extensions/maintenance-api/app/api/v1/ai/sessions.py
extensions/maintenance-api/app/api/v1/ai/confirmations.py
extensions/maintenance-api/app/api/v1/ai/models.py
extensions/maintenance-api/app/api/v1/ai/reviews.py
extensions/maintenance-api/app/api/v1/ai/reports.py

extensions/maintenance-api/app/core/config.py
internal/config/maintenance.go
internal/config/maintenance_test.go

extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
extensions/maintenance-api/tests/security/test_master_data_crud_call_contracts.py
extensions/maintenance-api/tests/api/test_ai_actor_routes.py

docker-compose.yml
.env.example
extensions/maintenance-api/.env.example
extensions/maintenance-api/README.md
```

### Modify only when the new RED test proves necessary

```text
extensions/maintenance-api/app/security/permissions.py
extensions/maintenance-api/app/core/responses.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/services/scenario_service.py
extensions/maintenance-api/app/services/demand_calculation_service.py
```

---

### Task 0: Persist the Approved Closure Plan and Verify the Baseline

**Files:**
- Create: `docs/superpowers/plans/2026-07-26-maintenance-plan05-01-security-closure.md`
- Do not modify production code.

**Interfaces:**
- Consumes: pushed commit `70c6f460981b8d841569881c4ed86006057b39ab`.
- Produces: a stable execution document and a clean verified starting state.

- [ ] **Step 1: Verify branch, local/remote commit, and clean worktree**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05"

git fetch origin feature/maintenance-frontend-plan05
git branch --show-current
git rev-parse HEAD
git rev-parse origin/feature/maintenance-frontend-plan05
git status --short
git diff --cached --name-only
```

Expected:

```text
branch = feature/maintenance-frontend-plan05
HEAD = 70c6f460981b8d841569881c4ed86006057b39ab
origin/feature/maintenance-frontend-plan05 = 70c6f460981b8d841569881c4ed86006057b39ab
git status --short = no output
git diff --cached --name-only = no output
```

- [ ] **Step 2: Copy this approved plan into the repository**

```powershell
Copy-Item `
  "D:\Desktop\2026-07-26-maintenance-plan05-01-security-closure.md" `
  "docs\superpowers\plans\2026-07-26-maintenance-plan05-01-security-closure.md"
```

- [ ] **Step 3: Verify plan-only diff**

```powershell
git status --short
git diff --check
git diff -- docs/superpowers/plans/2026-07-26-maintenance-plan05-01-security-closure.md
```

Expected: exactly one untracked plan file and no business-code changes.

- [ ] **Step 4: Commit the approved plan**

```powershell
git add docs/superpowers/plans/2026-07-26-maintenance-plan05-01-security-closure.md
git diff --cached --check
git commit -m "docs: plan maintenance security closure"
```

---

### Task 1: Establish the Global Business-Route RED Contract

**Files:**
- Create: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Modify: `extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py`
- Modify: `extensions/maintenance-api/tests/security/test_master_data_crud_call_contracts.py`
- Modify: `extensions/maintenance-api/tests/api/test_ai_actor_routes.py`

**Interfaces:**
- Consumes: `require_viewer`, `require_contributor`, `require_admin`, `success_response`.
- Produces: one executable inventory for all 127 current business endpoints: 61 master-data, 40 demand, and 26 AI.

- [ ] **Step 1: Add exact demand role expectations**

Add this function-to-role map to `test_api_rbac.py`:

```python
DEMAND_ROLE_BY_FUNCTION = {
    # Scenarios: viewer
    "list_scenarios": "require_viewer",
    "get_scenario": "require_viewer",
    "list_versions": "require_viewer",
    "get_version": "require_viewer",
    "full_version": "require_viewer",
    # Scenarios: contributor
    "create_scenario": "require_contributor",
    "update_scenario": "require_contributor",
    "create_version": "require_contributor",
    "update_version": "require_contributor",
    "validate_version": "require_contributor",
    "clone_version": "require_contributor",
    "add_stage": "require_contributor",
    "add_fleet_group": "require_contributor",
    "add_age_group": "require_contributor",
    "add_fleet_usage": "require_contributor",
    "add_override": "require_contributor",
    "add_shock": "require_contributor",
    # Scenarios: admin
    "delete_scenario": "require_admin",
    "publish_version": "require_admin",
    "retire_version": "require_admin",
    # Read-only comparison
    "compare": "require_viewer",
    # Calculations: viewer
    "list_calculations": "require_viewer",
    "get_calculation": "require_viewer",
    "get_status": "require_viewer",
    "result_items": "require_viewer",
    "runs": "require_viewer",
    "comparison": "require_viewer",
    "export": "require_viewer",
    # Calculations: contributor
    "preview": "require_contributor",
    "submit": "require_contributor",
    "cancel": "require_contributor",
    "retry": "require_contributor",
    "replay": "require_contributor",
    "rerun_latest": "require_contributor",
    # Repair profiles
    "list_profiles": "require_viewer",
    "get_profile": "require_viewer",
    "create_profile": "require_contributor",
    "update_profile": "require_contributor",
    "set_active": "require_contributor",
    "delete_profile": "require_admin",
}
```

- [ ] **Step 2: Add exact route inventory and static security checks**

The new test must parse:

```python
BUSINESS_ROUTE_FILES = (
    *sorted(Path("app/api/v1/master_data").glob("*.py")),
    *sorted(Path("app/api/v1/demand").glob("*.py")),
    *sorted(Path("app/api/v1/ai").glob("*.py")),
)
```

Exclude `router.py`, `common.py`, and `__init__.py`. Assert:

```python
assert master_data_endpoint_count == 61
assert demand_endpoint_count == 40
assert ai_endpoint_count == 26
assert total_endpoint_count == 127
```

For every endpoint:

```python
assert role_dependencies in (
    ["require_viewer"],
    ["require_contributor"],
    ["require_admin"],
)
```

Also assert:

```python
assert "Depends(get_actor)" not in route_source
assert "session.get(" not in route_source
```

Every `success_response(...)` inside a business endpoint must contain:

```python
actor=actor
```

Master-data method defaults are:

```python
MASTER_DATA_ROLE_BY_METHOD = {
    "get": "require_viewer",
    "post": "require_contributor",
    "put": "require_contributor",
    "patch": "require_contributor",
    "delete": "require_admin",
}
```

AI route role specificity remains covered by `test_ai_actor_routes.py`; the global test requires exactly one named role dependency and actor metadata for each AI endpoint.

- [ ] **Step 3: Update the existing master-data contract**

Change:

```python
"delete": "require_contributor",
```

to:

```python
"delete": "require_admin",
```

Add a static assertion that each business endpoint’s `success_response` carries `actor=actor`.

- [ ] **Step 4: Extend the demand contract to scenarios and comparisons**

Add:

```python
DEMAND_ROUTE_FILES = (
    Path("app/api/v1/demand/scenarios.py"),
    Path("app/api/v1/demand/comparisons.py"),
    Path("app/api/v1/demand/calculations.py"),
    Path("app/api/v1/demand/repair_profiles.py"),
)
```

Assert 40 endpoints, exact role map, ActorContext forwarding, tenant-filtered direct queries, and actor metadata.

- [ ] **Step 5: Run RED and capture exact failures**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api"

$python = "E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe"

& $python -m pytest `
  tests/security/test_api_rbac.py `
  tests/security/test_demand_routes_actor_context.py `
  tests/security/test_master_data_crud_call_contracts.py `
  tests/api/test_ai_actor_routes.py `
  -q -ra --tb=short
```

Valid RED must report behavioral contract failures including:

```text
scenarios.py missing named role dependencies
comparisons.py missing named role dependency and actor forwarding
calculations.py / repair_profiles.py still use get_actor rather than role dependencies
business success responses missing actor metadata
master-data DELETE routes use contributor rather than admin
```

Collection, syntax, fixture, import, or environment failures do not count as valid RED.

- [ ] **Step 6: Review the RED evidence**

Do not modify production code until the failing endpoint list and expected count are exported and reviewed.

---

### Task 2: Migrate Scenario and Comparison Routes to ActorContext

**Files:**
- Modify: `extensions/maintenance-api/app/api/v1/demand/scenarios.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/comparisons.py`
- Modify: `extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py`
- Test: `extensions/maintenance-api/tests/security/test_api_rbac.py`

**Interfaces:**
- Consumes: actor-aware `ScenarioService` and `DemandCalculationService`.
- Produces: 21 protected scenario/comparison endpoints.

- [ ] **Step 1: Add named actor dependency aliases**

Use in both modules:

```python
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)

ViewerDep = Annotated[
    ActorContext,
    Depends(require_viewer),
]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep = Annotated[
    ActorContext,
    Depends(require_admin),
]
```

Do not import or use `get_actor` directly.

- [ ] **Step 2: Apply the exact scenario role map**

Use `ViewerDep` for:

```text
list_scenarios
get_scenario
list_versions
get_version
full_version
```

Use `ContributorDep` for:

```text
create_scenario
update_scenario
create_version
update_version
validate_version
clone_version
add_stage
add_fleet_group
add_age_group
add_fleet_usage
add_override
add_shock
```

Use `AdminDep` for:

```text
delete_scenario
publish_version
retire_version
```

- [ ] **Step 3: Forward actor to every scenario service call**

Examples:

```python
scenario_service.create_template(
    session,
    actor,
    payload,
)
```

```python
scenario_service.get_version(
    session,
    actor,
    version_id,
    full=True,
)
```

```python
scenario_service.add_shock(
    session,
    actor,
    stage_id,
    payload,
)
```

No scenario service call may omit the second positional `actor` argument.

- [ ] **Step 4: Protect comparison as read-only viewer work**

Implement:

```python
@router.post("")
def compare(
    payload: HistoricalComparisonRequest,
    session: SessionDep,
    actor: ViewerDep,
):
    left = calculation_service.get(
        session,
        actor,
        payload.left_calculation_id,
    )
    right = calculation_service.get(
        session,
        actor,
        payload.right_calculation_id,
    )
    ...
    return success_response(
        result,
        actor=actor,
    )
```

The two calculations must be independently resolved within the actor tenant. A cross-tenant ID returns 404.

- [ ] **Step 5: Add actor metadata to all scenario responses**

Each response uses:

```python
success_response(
    payload,
    "...",
    actor=actor,
)
```

For returned versioned rows, also supply:

```python
version=row.version
```

only when the concrete returned object exposes a non-null integer `version`.

- [ ] **Step 6: Add HTTP tenant and role tests**

Add tests proving:

```text
missing token -> 401
viewer can list/get/full/compare
viewer cannot create/update/validate/clone/publish/delete -> 403
contributor can ordinary edit but cannot publish/retire/delete -> 403
admin can publish/retire/delete
tenant-b cannot read, mutate, clone, publish, retire, or compare tenant-a rows
X-Tenant-ID, tenant_id query, and tenant_id JSON fields do not switch tenant
response meta tenant_id and request_id come from ActorContext
```

- [ ] **Step 7: Run focused GREEN**

```powershell
& $python -m pytest `
  tests/security/test_demand_routes_actor_context.py `
  tests/security/test_api_rbac.py `
  tests/services/test_scenario_service.py `
  tests/services/test_scenario_service_tenant_scope.py `
  -q -ra --tb=short

& $python -m ruff check `
  app/api/v1/demand/scenarios.py `
  app/api/v1/demand/comparisons.py `
  tests/security/test_demand_routes_actor_context.py `
  tests/security/test_api_rbac.py
```

- [ ] **Step 8: Commit after review**

```powershell
git add `
  extensions/maintenance-api/app/api/v1/demand/scenarios.py `
  extensions/maintenance-api/app/api/v1/demand/comparisons.py `
  extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py `
  extensions/maintenance-api/tests/security/test_api_rbac.py

git diff --cached --check
git commit -m "fix: protect demand scenario and comparison routes"
```

---

### Task 3: Normalize Calculation and Repair Roles and Metadata

**Files:**
- Modify: `extensions/maintenance-api/app/api/v1/demand/calculations.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/repair_profiles.py`
- Modify: `extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py`
- Test: `extensions/maintenance-api/tests/security/test_api_rbac.py`

**Interfaces:**
- Consumes: actor forwarding completed by commit `70c6f460...`.
- Produces: named role floors and actor metadata for the remaining 19 demand endpoints.

- [ ] **Step 1: Replace raw ActorDep with named role aliases**

Remove:

```python
from app.security.dependencies import get_actor
ActorDep = Annotated[ActorContext, Depends(get_actor)]
```

Add `ViewerDep`, `ContributorDep`, and `AdminDep` exactly as in Task 2.

- [ ] **Step 2: Apply calculation roles**

Viewer:

```text
list_calculations
get_calculation
get_status
result_items
runs
comparison
export
```

Contributor:

```text
preview
submit
cancel
retry
replay
rerun_latest
```

- [ ] **Step 3: Apply repair-profile roles**

Viewer:

```text
list_profiles
get_profile
```

Contributor:

```text
create_profile
update_profile
set_active
```

Admin:

```text
delete_profile
```

- [ ] **Step 4: Add metadata to every success response**

Use:

```python
success_response(
    data,
    message,
    actor=actor,
)
```

For a returned versioned model:

```python
success_response(
    data,
    message,
    actor=actor,
    version=row.version,
)
```

Do not alter health or non-business response shapes.

- [ ] **Step 5: Extend role tests**

Prove:

```text
viewer can list/get/status/results/export
viewer cannot preview/submit/cancel/retry/replay/rerun or maintain repair profiles
contributor can compute and maintain ordinary repair profiles
contributor cannot delete repair profiles
admin can delete repair profiles
all success responses contain matching meta.request_id and meta.tenant_id
```

- [ ] **Step 6: Run GREEN**

```powershell
& $python -m pytest `
  tests/security/test_demand_routes_actor_context.py `
  tests/security/test_api_rbac.py `
  tests/api/test_async_calculation.py `
  tests/api/test_calculation_routes.py `
  tests/api/test_repair_profiles.py `
  -q -ra --tb=short

& $python -m ruff check `
  app/api/v1/demand/calculations.py `
  app/api/v1/demand/repair_profiles.py `
  tests/security/test_demand_routes_actor_context.py `
  tests/security/test_api_rbac.py
```

- [ ] **Step 7: Commit after review**

```powershell
git add `
  extensions/maintenance-api/app/api/v1/demand/calculations.py `
  extensions/maintenance-api/app/api/v1/demand/repair_profiles.py `
  extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py `
  extensions/maintenance-api/tests/security/test_api_rbac.py

git diff --cached --check
git commit -m "fix: enforce demand route roles and metadata"
```

---

### Task 4: Complete Master-Data and AI RBAC/Metadata

**Files:**
- Modify: the ten master-data route files listed in the File Map.
- Modify only failing AI route files among the five AI modules listed in the File Map.
- Modify: `tests/security/test_master_data_crud_call_contracts.py`
- Modify: `tests/api/test_ai_actor_routes.py`
- Modify: `tests/security/test_api_rbac.py`

**Interfaces:**
- Consumes: existing actor-aware services and named role dependencies.
- Produces: uniform role floors and metadata for all 87 master-data/AI endpoints.

- [ ] **Step 1: Make master-data DELETE admin-only**

Every master-data `@router.delete(...)` endpoint must use:

```python
actor: Annotated[
    ActorContext,
    Depends(require_admin),
]
```

POST/PUT/PATCH remain contributor; GET remains viewer.

- [ ] **Step 2: Add actor metadata to master-data responses**

Every route-level `success_response(...)` supplies:

```python
actor=actor
```

For create/update/active responses returning a versioned row, supply the row’s `version`.

Import rules:

```text
template download -> viewer
preview/validate -> contributor
execute -> contributor
```

Import preview and validation remain non-mutating; execution revalidates server-side.

- [ ] **Step 3: Add actor metadata to AI responses**

Keep the current exact AI role dependency for each endpoint. Add `actor=actor` to each `success_response(...)` that lacks it.

Do not change:

```text
worker ActorContext signatures
dynamic admin escalation
tool permission derivation
recovery state behavior
```

unless the focused RED test proves a regression.

- [ ] **Step 4: Run the global 127-route contract**

```powershell
& $python -m pytest `
  tests/security/test_api_rbac.py `
  tests/security/test_master_data_crud_call_contracts.py `
  tests/api/test_ai_actor_routes.py `
  -q -ra --tb=short
```

Expected:

```text
61 master-data endpoints
40 demand endpoints
26 AI endpoints
127 total
exactly one named role dependency per endpoint
zero raw Depends(get_actor)
zero route session.get
zero success_response calls without actor metadata
```

- [ ] **Step 5: Run affected suites**

```powershell
& $python -m pytest `
  tests/api/test_master_data_api.py `
  tests/api/test_ai_actor_routes.py `
  tests/api/test_ai_sessions.py `
  tests/api/test_ai_confirmations.py `
  tests/api/test_ai_reports.py `
  tests/api/test_ai_reviews.py `
  tests/security/test_master_data_crud_call_contracts.py `
  tests/services/test_master_data_service_tenant_scope.py `
  tests/services/test_ai_service_tenant_scope.py `
  -q -ra --tb=short

& $python -m ruff check app/api/v1 tests/security/test_api_rbac.py
```

- [ ] **Step 6: Commit after review**

```powershell
git add `
  extensions/maintenance-api/app/api/v1/master_data `
  extensions/maintenance-api/app/api/v1/ai `
  extensions/maintenance-api/tests/security/test_master_data_crud_call_contracts.py `
  extensions/maintenance-api/tests/security/test_api_rbac.py `
  extensions/maintenance-api/tests/api/test_ai_actor_routes.py

git diff --cached --check
git commit -m "fix: complete maintenance api rbac metadata"
```

---

### Task 5: Add the WeKnora-to-FastAPI Identity Integration Gate

**Files:**
- Create: `extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py`
- Modify production files only when the new integration test exposes a real contract failure.

**Interfaces:**
- Consumes: WeKnora HS256 claims contract and FastAPI `get_actor`.
- Produces: executable cross-layer identity evidence.

- [ ] **Step 1: Write the integration tests**

Use the existing `internal_auth_headers` fixture. Test:

```python
def test_proxy_identity_ignores_spoofed_tenant_inputs(
    client,
    session,
    internal_auth_headers,
):
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="user-a",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-a",
    )
    headers["X-Tenant-ID"] = "tenant-b"

    response = client.post(
        "/api/v1/master-data/equipment-models?tenant_id=tenant-b",
        headers=headers,
        json={
            "code": "EQ-PROXY",
            "name": "Proxy identity",
            "tenant_id": "tenant-b",
        },
    )

    assert response.status_code == 201
    assert response.json()["meta"]["tenant_id"] == "tenant-a"
    assert response.json()["meta"]["request_id"] == "request-a"

    row = session.scalar(
        select(EquipmentModel).where(
            EquipmentModel.code == "EQ-PROXY"
        )
    )
    assert row.tenant_id == "tenant-a"
```

Add tests proving:

```text
missing token -> 401 INTERNAL_TOKEN_INVALID
viewer GET succeeds
viewer POST returns 403 INSUFFICIENT_MAINTENANCE_ROLE
tenant-b cannot GET/PUT/DELETE tenant-a row
unknown role token is rejected
wrong issuer, audience, algorithm, expired token, future iat, and >180-second lifetime are rejected
```

- [ ] **Step 2: Run Python integration RED/GREEN**

```powershell
& $python -m pytest `
  tests/integration/test_weknora_proxy_identity.py `
  tests/security/test_internal_jwt.py `
  tests/security/test_dependencies.py `
  -q -ra --tb=short
```

- [ ] **Step 3: Run the existing Go identity/proxy evidence**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05"

go test `
  ./internal/config `
  ./internal/maintenanceproxy `
  ./internal/router `
  ./internal/middleware `
  -v
```

- [ ] **Step 4: Commit after review**

```powershell
git add extensions/maintenance-api/tests/integration/test_weknora_proxy_identity.py
git diff --cached --check
git commit -m "test: verify maintenance proxy identity contract"
```

If production fixes were required, stage only the reviewed files that caused the integration test to pass.

---

### Task 6: Add Production Secret Validation and Internal-Only Docker Packaging

**Files:**
- Create: `extensions/maintenance-api/tests/security/test_security_settings.py`
- Create: `extensions/maintenance-api/Dockerfile`
- Modify: `extensions/maintenance-api/app/core/config.py`
- Modify: `internal/config/maintenance.go`
- Modify: `internal/config/maintenance_test.go`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `extensions/maintenance-api/.env.example`
- Modify: `extensions/maintenance-api/README.md`

**Interfaces:**
- Consumes: the same secret on WeKnora and Maintenance API.
- Produces: fail-closed production startup and internal-only Compose service.

- [ ] **Step 1: Write Python production-settings RED**

Use the actual example placeholder:

```python
EXAMPLE_INTERNAL_JWT_SECRET = (
    "replace-with-at-least-32-random-bytes"
)
```

Tests:

```python
def test_production_rejects_example_internal_secret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        EXAMPLE_INTERNAL_JWT_SECRET,
    )
    with pytest.raises(
        ValidationError,
        match="INTERNAL_JWT_SECRET",
    ):
        Settings()


def test_development_allows_documented_example_secret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        EXAMPLE_INTERNAL_JWT_SECRET,
    )
    assert Settings().app_env == "development"
```

- [ ] **Step 2: Write Go placeholder-secret RED**

Add:

```go
func TestMaintenanceConfigRejectsExampleSecretWhenEnabled(
    t *testing.T,
) {
    cfg := DefaultMaintenanceConfig()
    cfg.Enabled = true
    cfg.SigningSecret =
        "replace-with-at-least-32-random-bytes"
    require.ErrorContains(
        t,
        cfg.Validate(),
        "signing secret",
    )
}
```

- [ ] **Step 3: Implement production placeholder rejection**

Python:

```python
from pydantic import model_validator

EXAMPLE_INTERNAL_JWT_SECRET = (
    "replace-with-at-least-32-random-bytes"
)

@model_validator(mode="after")
def validate_production_security(self) -> "Settings":
    if (
        self.app_env.strip().lower() == "production"
        and self.internal_jwt_secret.get_secret_value()
        == EXAMPLE_INTERNAL_JWT_SECRET
    ):
        raise ValueError(
            "INTERNAL_JWT_SECRET must be replaced in production"
        )
    return self
```

Go `MaintenanceConfig.Validate()` rejects the same exact example value whenever the proxy is enabled.

- [ ] **Step 4: Create the Maintenance API Dockerfile**

Use:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data /app/exports

EXPOSE 8100

CMD [
  "uvicorn",
  "app.main:app",
  "--host",
  "0.0.0.0",
  "--port",
  "8100"
]
```

- [ ] **Step 5: Add the internal-only Compose service**

Add `maintenance-api`:

```yaml
maintenance-api:
  build:
    context: ./extensions/maintenance-api
    dockerfile: Dockerfile
  container_name: WeKnora-maintenance-api
  expose:
    - "8100"
  environment:
    APP_ENV: production
    APP_DEBUG: "false"
    INTERNAL_JWT_SECRET: ${WEKNORA_MAINTENANCE_SIGNING_SECRET:?set WEKNORA_MAINTENANCE_SIGNING_SECRET}
    INTERNAL_JWT_ISSUER: ${WEKNORA_MAINTENANCE_ISSUER:-weknora}
    INTERNAL_JWT_AUDIENCE: ${WEKNORA_MAINTENANCE_AUDIENCE:-maintenance-api}
    INTERNAL_JWT_MAX_LIFETIME_SECONDS: "180"
    DATABASE_URL: sqlite:////app/data/maintenance.db
  volumes:
    - maintenance-data:/app/data
    - maintenance-exports:/app/exports
  healthcheck:
    test:
      [
        "CMD",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=3)",
      ]
    interval: 10s
    timeout: 5s
    retries: 12
    start_period: 20s
  networks:
    - WeKnora-network
  restart: unless-stopped
```

Do not add `ports:` to this service.

Add to the `app` service:

```yaml
- WEKNORA_MAINTENANCE_ENABLED=${WEKNORA_MAINTENANCE_ENABLED:-false}
- WEKNORA_MAINTENANCE_BASE_URL=${WEKNORA_MAINTENANCE_BASE_URL:-http://maintenance-api:8100}
- WEKNORA_MAINTENANCE_SIGNING_SECRET=${WEKNORA_MAINTENANCE_SIGNING_SECRET:-}
- WEKNORA_MAINTENANCE_ISSUER=${WEKNORA_MAINTENANCE_ISSUER:-weknora}
- WEKNORA_MAINTENANCE_AUDIENCE=${WEKNORA_MAINTENANCE_AUDIENCE:-maintenance-api}
- WEKNORA_MAINTENANCE_TOKEN_TTL=${WEKNORA_MAINTENANCE_TOKEN_TTL:-3m}
- WEKNORA_MAINTENANCE_REQUEST_TIMEOUT=${WEKNORA_MAINTENANCE_REQUEST_TIMEOUT:-30s}
```

Add named volumes:

```yaml
maintenance-data:
maintenance-exports:
```

- [ ] **Step 6: Document exact secret generation and migration**

Document:

```powershell
$secretBytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill(
    $secretBytes
)
$secret = [Convert]::ToBase64String($secretBytes)

$env:WEKNORA_MAINTENANCE_SIGNING_SECRET = $secret
$env:INTERNAL_JWT_SECRET = $secret
```

Document that:

```text
the same secret is configured on both services
Maintenance API has no browser-facing host port
/health remains unauthenticated
database migration must succeed before the service is considered ready
MAINTENANCE_LEGACY_TENANT_ID is used only for explicit one-time legacy backfill
```

- [ ] **Step 7: Run focused settings and Compose gates**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora"

go test ./internal/config -run Maintenance -v

Set-Location "extensions\maintenance-api"
& $python -m pytest `
  tests/security/test_security_settings.py `
  tests/security/test_internal_jwt.py `
  -q -ra --tb=short
& $python -m ruff check app/core/config.py tests/security/test_security_settings.py

Set-Location "..\.."
docker compose config
```

Expected: all commands exit 0; rendered `maintenance-api` service has `expose: 8100` and no `ports`.

- [ ] **Step 8: Commit after review**

```powershell
git add `
  extensions/maintenance-api/Dockerfile `
  extensions/maintenance-api/app/core/config.py `
  extensions/maintenance-api/tests/security/test_security_settings.py `
  internal/config/maintenance.go `
  internal/config/maintenance_test.go `
  docker-compose.yml `
  .env.example `
  extensions/maintenance-api/.env.example `
  extensions/maintenance-api/README.md

git diff --cached --check
git commit -m "docs: configure maintenance security deployment"
```

---

### Task 7: Run the Complete Plan 05-1 Verification Gate

**Files:**
- Modify: `.superpowers/sdd/progress.md`
- No production modification is allowed during the gate. A failure returns to the owning task.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: review-ready Phase 05-1 evidence.

- [ ] **Step 1: Verify a clean branch before the gate**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05"

git status --short
git diff --cached --name-only
git log -8 --oneline
```

Expected: clean worktree and empty index.

- [ ] **Step 2: Run Go security packages**

```powershell
go test `
  ./internal/config `
  ./internal/maintenanceproxy `
  ./internal/router `
  ./internal/middleware
```

- [ ] **Step 3: Run migration round-trip on a disposable database**

```powershell
Set-Location "extensions\maintenance-api"

$gateDb = Join-Path (Get-Location) "data\phase05-security-gate.db"
Remove-Item -LiteralPath $gateDb -Force -ErrorAction SilentlyContinue

$oldDatabaseUrl = $env:DATABASE_URL
$oldLegacyTenant = $env:MAINTENANCE_LEGACY_TENANT_ID

try {
    $env:DATABASE_URL = "sqlite:///$($gateDb -replace '\\','/')"
    $env:MAINTENANCE_LEGACY_TENANT_ID = "phase05-gate-tenant"

    & $python -m alembic upgrade head
    & $python -m alembic downgrade base
    & $python -m alembic upgrade head
}
finally {
    $env:DATABASE_URL = $oldDatabaseUrl
    $env:MAINTENANCE_LEGACY_TENANT_ID = $oldLegacyTenant
    Remove-Item -LiteralPath $gateDb -Force -ErrorAction SilentlyContinue
}
```

All three Alembic commands must exit 0.

- [ ] **Step 4: Run the complete Python security scope**

```powershell
& $python -m pytest `
  tests/security `
  tests/migrations `
  tests/models `
  tests/repositories `
  tests/services `
  tests/api `
  tests/workers `
  tests/integration `
  -q -ra --tb=short
```

- [ ] **Step 5: Run static and compile gates**

```powershell
& $python -m ruff check app tests
& $python -m compileall -q app tests

Set-Location "..\.."

git diff --check
git diff --cached --check
docker compose config
```

- [ ] **Step 6: Verify route and secret evidence**

Capture:

```text
127 protected business endpoints
61 master-data, 40 demand, 26 AI
zero raw get_actor dependencies in business routers
zero success responses without actor metadata
cross-tenant read/write/reference/comparison tests pass
viewer/contributor/admin matrix tests pass
Go proxy header stripping and JWT tests pass
Python internal JWT validation tests pass
production example secret is rejected
Maintenance API has no host port in Compose
```

- [ ] **Step 7: Export review package**

Create:

```text
D:\Desktop\maintenance-plan05-01-security-closure-review.diff
D:\Desktop\maintenance-plan05-01-security-closure-files.txt
D:\Desktop\maintenance-plan05-01-security-closure-gates.log
D:\Desktop\maintenance-plan05-01-security-closure-status.txt
```

Status markers:

```text
PLAN05_01_SECURITY_CLOSURE=READY_FOR_REVIEW
GO_SECURITY=PASS
ALEMBIC_ROUNDTRIP=PASS
PYTHON_SECURITY=PASS
ROUTE_RBAC_MATRIX=127_PASS
TENANT_ISOLATION=PASS
PROXY_IDENTITY=PASS
PRODUCTION_SETTINGS=PASS
DOCKER_COMPOSE=PASS
RUFF=PASS
COMPILE=PASS
DIFF_CHECK=PASS
INDEX_EMPTY=PASS
STAGED=0
PUSHED=0
```

Stop for review. Do not stage final ledger changes before review approval.

---

### Task 8: Update the Durable Ledger, Commit the Phase Gate, and Open the PR

**Files:**
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: approved Task 7 review package.
- Produces: durable Plan 05-1 completion and the entry gate for Plan 05-2.

- [ ] **Step 1: Reconstruct the durable ledger from commits and gate evidence**

Mark Units 5–11 complete only when their corresponding commits and final gate are present. Record:

```text
Unit 5: internal JWT verification complete
Unit 6: RBAC, errors, and response metadata complete
Unit 7A/7B: tenant/version models and reversible migration complete
Unit 8A/8B: tenant-safe repositories, services, routes, and workers complete
Unit 9A/9B: idempotency, optimistic locking, and audit complete
Unit 10: 127 business endpoints protected with role and metadata contracts
Unit 11: Docker, operations documentation, and complete Phase 05-1 gate complete
```

Include the final commit SHAs and gate artifact hashes.

- [ ] **Step 2: Commit the ledger**

```powershell
git add .superpowers/sdd/progress.md
git diff --cached --check
git commit -m "docs: complete maintenance security foundation"
```

- [ ] **Step 3: Push the feature branch**

```powershell
git push origin feature/maintenance-frontend-plan05
```

- [ ] **Step 4: Verify local/remote equality**

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/feature/maintenance-frontend-plan05
```

Expected: clean worktree and equal SHAs.

- [ ] **Step 5: Create the PR**

Target:

```text
base: feature/demand-calculation-engine
head: feature/maintenance-frontend-plan05
```

PR evidence includes:

```text
Go test command and pass count
pytest command and pass count
Alembic round-trip revision
Ruff and compile results
127-route role/metadata inventory
cross-tenant HTTP evidence
idempotency/version/audit evidence
redacted internal JWT claims with 180-second expiry
Compose internal-only service evidence
confirmation that secrets do not appear in frontend bundles, responses, or logs
```

- [ ] **Step 6: Preserve the worktree**

Do not remove the worktree while the PR is open. Use it for review fixes.

---

## Plan 05-2 Entry Gate

Plan 05-2 implementation begins only after Task 8 is complete. Its first implementation task is:

```text
Create the typed frontend Maintenance API client:
frontend/src/api/maintenance/types.ts
frontend/src/api/maintenance/client.ts
frontend/src/api/maintenance/__tests__/client.test.ts
frontend/src/api/maintenance/__tests__/query.test.ts
frontend/src/utils/request.ts
```

First Plan 05-2 commit:

```text
feat: add typed maintenance frontend client
```

No menu, dashboard, or master-data page work begins before that typed client passes frontend tests and type checking.

---

## Self-Review Results

- The plan does not falsely treat commit `70c6f460...` as completion of Plan 05-1.
- The plan explicitly covers the observed unprotected `scenarios.py` and `comparisons.py`.
- The plan converts raw `get_actor` use in calculation and repair routes into named role dependencies.
- The plan resolves the role-policy mismatch by making DELETE admin-only according to the revised Unit 10 contract.
- The plan requires actor metadata on every business success response.
- The three missing planned tests are created: API RBAC, proxy identity, and security settings.
- The missing Maintenance API Dockerfile and internal-only Compose service are created.
- Migration verification uses a disposable database and does not destroy developer data.
- The durable progress ledger is updated only after fresh final-gate evidence.
- Plan 05-2 remains blocked until Plan 05-1 is committed, pushed, reviewed, and ready for integration.

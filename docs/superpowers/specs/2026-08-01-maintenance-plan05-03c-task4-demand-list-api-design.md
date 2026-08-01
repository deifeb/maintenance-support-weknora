# Plan 05-3C Task 4 Demand List Lifecycle API Design

**Date:** 2026-08-01
**Repository:** `https://github.com/deifeb/maintenance-support-weknora`
**Worktree:** `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`
**Branch:** `feature/maintenance-frontend-plan05`
**Local baseline:** `67bdabe4fe84df350cb7bddd9b2ac82129522c3e`
**Task 3 status:** implemented, locally committed, fully verified, not pushed because GitHub connectivity is unavailable.

## 1. Purpose

Expose the already implemented demand-list aggregate and lifecycle service through tenant-safe, role-gated FastAPI routes.

Task 4 is an API wiring task. It must not reimplement lifecycle business rules, duplicate service validation, change persistence, change schemas already delivered by Task 3, or introduce frontend behavior.

The API must expose:

```text
create
list
detail
item update
submit
confirm
publish
derive
void
```

## 2. Baseline Contracts

Task 3 already provides these request schemas:

```python
DemandListCreateRequest
DemandListItemUpdateRequest
DemandListTransitionRequest
DemandListConfirmRequest
```

Task 3 already provides these read schemas:

```python
DemandListSummaryRead
DemandListRead
```

Task 3 already provides these service methods:

```python
DemandListService.create_from_group(
    session,
    actor,
    *,
    calculation_group_id,
    name,
    description,
    idempotency_key,
) -> DemandListRead

DemandListService.get(
    session,
    actor,
    demand_list_id,
) -> DemandListRead

DemandListService.list(
    session,
    actor,
    *,
    page,
    page_size,
    status,
    lineage_id,
) -> PageData[DemandListSummaryRead]

DemandListService.update_item(
    session,
    actor,
    demand_list_id,
    item_id,
    *,
    expected_version,
    final_quantity,
    adjustment_reason,
) -> DemandListRead

DemandListService.submit(
    session,
    actor,
    demand_list_id,
    *,
    expected_version,
    idempotency_key,
) -> DemandListRead

DemandListService.confirm(
    session,
    actor,
    demand_list_id,
    *,
    expected_version,
    confirmation_note,
    idempotency_key,
) -> DemandListRead

DemandListService.publish(
    session,
    actor,
    demand_list_id,
    *,
    expected_version,
    idempotency_key,
) -> DemandListRead

DemandListService.derive(
    session,
    actor,
    demand_list_id,
    *,
    expected_version,
    idempotency_key,
) -> DemandListRead

DemandListService.void(
    session,
    actor,
    demand_list_id,
    *,
    expected_version,
    idempotency_key,
) -> DemandListRead
```

The API must pass `session` and `actor` as the first two service arguments for every call.

## 3. Scope Correction to the Older Roadmap

The older Task 4 roadmap listed only three files:

```text
create demand_lists.py
modify demand/router.py
create test_demand_lists.py
```

That file map is insufficient for the current repository because the security suite maintains an exact AST-derived route inventory.

Adding nine demand routes changes:

```text
demand route count: 55 -> 64
all business routes: 148 -> 157
```

Therefore Task 4 must also modify:

```text
extensions/maintenance-api/tests/security/test_api_rbac.py
extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
```

This is a contract-test alignment, not a production-scope expansion.

A second outdated example used request field `note` for confirmation. Task 3 implemented the authoritative field:

```text
confirmation_note
```

Task 4 must use `confirmation_note` exactly. The API must not add a `note` alias.

## 4. Design Options

### Option A — Thin typed routes, one endpoint per command

Each FastAPI route uses explicit request and response models, one named role dependency, and a direct service call.

Advantages:

- follows existing scenario and calculation-group route patterns;
- preserves stable OpenAPI contracts;
- keeps AST-based RBAC tests simple;
- prevents the API from rebuilding domain state;
- makes frontend client generation straightforward;
- gives every lifecycle operation a distinct permission boundary.

Disadvantages:

- five lifecycle route functions contain similar forwarding code.

**Decision: use Option A.**

### Option B — One generic lifecycle action endpoint

Example:

```text
POST /demand-lists/{id}/actions/{action}
```

Rejected because it weakens OpenAPI typing, complicates route-level RBAC, encourages string-dispatched business behavior, and makes action-specific request validation less explicit.

### Option C — Reimplement transitions in the route layer

Rejected because the service already owns status, version, role, idempotency, transaction, and concurrency rules. Duplicating those rules creates divergent HTTP and non-HTTP behavior.

## 5. Endpoint Contract

All paths are relative to:

```text
/api/v1/demand
```

| Method | Path | Role dependency | Request | Success data | Status |
|---|---|---|---|---|---:|
| POST | `/demand-lists` | contributor | `DemandListCreateRequest` + `Idempotency-Key` | `DemandListRead` | 201 |
| GET | `/demand-lists` | viewer | page/status/lineage query | `PageData[DemandListSummaryRead]` | 200 |
| GET | `/demand-lists/{demand_list_id}` | viewer | path only | `DemandListRead` | 200 |
| PUT | `/demand-lists/{demand_list_id}/items/{item_id}` | contributor | `DemandListItemUpdateRequest` | `DemandListRead` | 200 |
| POST | `/demand-lists/{demand_list_id}/submit` | contributor | `DemandListTransitionRequest` + `Idempotency-Key` | `DemandListRead` | 200 |
| POST | `/demand-lists/{demand_list_id}/confirm` | admin | `DemandListConfirmRequest` + `Idempotency-Key` | `DemandListRead` | 200 |
| POST | `/demand-lists/{demand_list_id}/publish` | admin | `DemandListTransitionRequest` + `Idempotency-Key` | `DemandListRead` | 200 |
| POST | `/demand-lists/{demand_list_id}/derive` | admin | `DemandListTransitionRequest` + `Idempotency-Key` | `DemandListRead` | 200 |
| POST | `/demand-lists/{demand_list_id}/void` | admin | `DemandListTransitionRequest` + `Idempotency-Key` | `DemandListRead` | 200 |

Role dependencies are minimum-role dependencies. Admin therefore inherits viewer and contributor capabilities through the existing rank model.

## 6. Route Naming

Use unique function names so the exact route inventory has no ambiguity:

```python
create_demand_list
list_demand_lists
get_demand_list
update_demand_list_item
submit_demand_list
confirm_demand_list
publish_demand_list
derive_demand_list
void_demand_list
```

Do not use generic function names such as `submit`, `get`, or `list`.

## 7. Dependency Aliases

The route module defines:

```python
SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep = Annotated[ActorContext, Depends(require_admin)]
IdempotencyKeyDep = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
]
```

Every route must have exactly one named role dependency. Routes must never depend directly on `get_actor`.

## 8. Request Validation

### 8.1 Idempotency key

Create and all five lifecycle commands require `Idempotency-Key`.

FastAPI validates header presence and length. The service remains authoritative for whitespace normalization and stable business codes:

```text
IDEMPOTENCY_KEY_REQUIRED
INVALID_IDEMPOTENCY_KEY
IDEMPOTENCY_KEY_REUSED
IDEMPOTENT_RESPONSE_UNAVAILABLE
```

The route must not trim, hash, persist, or interpret the key.

### 8.2 Confirmation

Confirmation JSON is:

```json
{
  "expected_version": 3,
  "confirmation_note": "Approved after engineering review"
}
```

The following body is invalid and returns the global validation envelope:

```json
{
  "expected_version": 3,
  "note": "Approved"
}
```

### 8.3 List filters

The list endpoint accepts:

```text
page >= 1
1 <= page_size <= 200
status: DemandListStatus | null
lineage_id: non-empty string | null
```

Unknown tenant selectors are not accepted as business inputs. No route declares:

```text
tenant_id
X-Tenant-ID
tenant header dependency
```

## 9. Response Contract

Every route returns `MaintenanceSuccessResponse`.

Single-aggregate routes return:

```python
MaintenanceSuccessResponse[DemandListRead]
```

and set:

```text
meta.request_id = actor.request_id
meta.tenant_id = actor.tenant_id
meta.version = demand_list.version
```

The list route returns:

```python
MaintenanceSuccessResponse[
    PageData[DemandListSummaryRead]
]
```

with `meta.version = None`.

Decimal fields remain JSON strings through the existing Pydantic serializers. Route code must not convert Decimal values to float.

## 10. Error Contract

The route module contains no custom `try/except` for application errors.

Existing global exception handlers map service exceptions directly:

| Source | HTTP | Stable code behavior |
|---|---:|---|
| missing/invalid internal token | 401 | existing internal-token code |
| insufficient route role | 403 | `INSUFFICIENT_MAINTENANCE_ROLE` |
| tenant-hidden or missing resource | 404 | `RESOURCE_NOT_FOUND` |
| invalid body/header/query | 422 | `VALIDATION_ERROR` |
| service business validation | 422 | service code preserved |
| version/transition/idempotency conflict | 409 | service code and details preserved |
| unexpected error | 500 | `INTERNAL_SERVER_ERROR` |

The client must never parse exception message text to recover business meaning.

## 11. Tenant Safety

Tenant identity comes only from `ActorContext`.

Every route:

1. resolves the actor through a named role dependency;
2. forwards the actor to `demand_list_service`;
3. does not issue direct ORM queries;
4. does not call `session.get`;
5. does not accept tenant selection in path, body, query, or trusted headers.

Cross-tenant resources remain hidden as 404 because the service and repositories are tenant-scoped.

## 12. RBAC Defense in Depth

Route-level minimum roles:

```text
viewer:
  list
  detail

contributor:
  create
  item update
  submit

admin:
  confirm
  publish
  derive
  void
```

Task 3 service guards remain unchanged. Route guards improve HTTP behavior and OpenAPI clarity, while service guards protect workers, scripts, tests, and future non-HTTP callers.

## 13. Idempotency and Replay

The route layer forwards the raw validated header and request fields.

It must not:

- generate a key for the caller;
- reuse one key for multiple commands;
- retry a failed command automatically;
- change `expected_version` during replay;
- reconstruct a response from current database state.

Exact replay is entirely owned by Task 3 receipts.

## 14. Router Registration

`extensions/maintenance-api/app/api/v1/demand/router.py` imports `demand_lists` and includes:

```python
router.include_router(demand_lists.router)
```

The route module uses:

```python
router = APIRouter(
    prefix="/demand-lists",
    tags=["demand: demand lists"],
)
```

## 15. Test Strategy

### 15.1 Static security contract

Update `test_api_rbac.py`:

```text
EXPECTED_COUNTS["demand"] = 64
total business routes = 157
```

Add all nine unique route function names and expected named dependencies.

Update `test_demand_routes_actor_context.py` so:

```text
demand_lists.py is inventoried
demand_list_service is the expected service singleton
every service call begins with session, actor
every success response includes actor metadata
```

### 15.2 API contract tests

Create `tests/api/test_demand_lists.py` covering:

- exact method/path inventory;
- router registration under `/api/v1/demand`;
- missing token returns 401;
- Viewer can list/detail and cannot mutate;
- Contributor can create/update/submit;
- Contributor cannot confirm/publish/derive/void;
- Admin can use all routes;
- all service calls receive the resolved actor;
- create and lifecycle routes require `Idempotency-Key`;
- header length over 128 returns `VALIDATION_ERROR`;
- transition bodies require `expected_version >= 1`;
- confirmation requires `confirmation_note`;
- `note` is rejected;
- extra body fields, including `tenant_id`, are rejected;
- list filters are forwarded exactly;
- aggregate responses set `meta.version`;
- list response leaves `meta.version` null;
- Decimal fields serialize as strings;
- service `AppException` codes/details pass through unchanged.

### 15.3 Existing regression suites

Run:

```text
Task 3 service suite
API RBAC static suite
demand route actor-context suite
demand repository tenant-scope suite
full maintenance-api suite
compileall
Ruff
Git diff checks
```

## 16. File Scope

Production:

```text
CREATE extensions/maintenance-api/app/api/v1/demand/demand_lists.py
MODIFY extensions/maintenance-api/app/api/v1/demand/router.py
```

Tests:

```text
CREATE extensions/maintenance-api/tests/api/test_demand_lists.py
MODIFY extensions/maintenance-api/tests/security/test_api_rbac.py
MODIFY extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
```

No other file is in the approved Task 4 implementation scope.

## 17. Explicitly Deferred Work

Task 4 does not include:

1. frontend API client;
2. Pinia store;
3. lifecycle action resolver;
4. demand-list detail view;
5. inventory reservation;
6. review workflow;
7. procurement or allocation;
8. reporting;
9. notifications;
10. external event delivery or outbox;
11. repository pagination tie-break changes;
12. service lifecycle changes;
13. schema aliases for outdated request fields;
14. GitHub push or PR update while connectivity is unavailable.

## 18. Commit Boundaries

After explicit approval, documentation is committed separately:

```text
docs: plan plan05 demand list lifecycle api
```

Implementation is one focused commit:

```text
feat(maintenance): expose demand list lifecycle api
```

The implementation commit contains exactly the five files in Section 16.

## 19. Approval Gate

No production or test code is changed until this design and its implementation plan are approved.

Approval phrase:

```text
批准实施 Plan 05-3C Task 4 demand list lifecycle API
```

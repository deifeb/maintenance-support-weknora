# Plan 05-3C Task 4 Demand List Lifecycle API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the Task 3 demand-list creation, read, update, and lifecycle service methods through tenant-safe, role-gated, strongly typed FastAPI routes.

**Architecture:** Add one thin FastAPI router whose handlers validate HTTP inputs, resolve exactly one named role dependency, forward `session` and `actor` directly to `demand_list_service`, and return typed maintenance success envelopes. Keep all lifecycle, transaction, concurrency, tenant, idempotency, and business validation inside Task 3 service code. Extend the existing AST security tests because the repository enforces an exact route inventory.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, pytest 8, Ruff, Windows PowerShell, Git.

## Global Constraints

- Work only in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Branch must be `feature/maintenance-frontend-plan05`.
- Starting HEAD must be `67bdabe4fe84df350cb7bddd9b2ac82129522c3e`.
- Starting worktree and index must be clean.
- The local branch may remain ahead of GitHub while network access is unavailable.
- Do not fetch, pull, push, merge, rebase, reset, stash, clean, or force.
- Do not amend Task 3 commits.
- Task 4 is TDD-first: RED evidence precedes production edits.
- Tenant comes only from `ActorContext`.
- Every business route has exactly one named role dependency.
- Every service call begins with `session, actor`.
- No route uses `session.get` or direct ORM queries.
- No route catches and rewrites `AppException`.
- Create and lifecycle commands require `Idempotency-Key`.
- Confirmation uses `confirmation_note`, not `note`.
- Decimal quantities remain JSON strings.
- No service, repository, model, migration, or frontend file is modified.
- Do not commit until the user approves the final reviewed diff.

---

## Approved File Map

### Create

```text
extensions/maintenance-api/app/api/v1/demand/demand_lists.py
extensions/maintenance-api/tests/api/test_demand_lists.py
```

### Modify

```text
extensions/maintenance-api/app/api/v1/demand/router.py
extensions/maintenance-api/tests/security/test_api_rbac.py
extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
```

## Public Interfaces

### Routes

```text
POST /api/v1/demand/demand-lists
GET  /api/v1/demand/demand-lists
GET  /api/v1/demand/demand-lists/{demand_list_id}
PUT  /api/v1/demand/demand-lists/{demand_list_id}/items/{item_id}
POST /api/v1/demand/demand-lists/{demand_list_id}/submit
POST /api/v1/demand/demand-lists/{demand_list_id}/confirm
POST /api/v1/demand/demand-lists/{demand_list_id}/publish
POST /api/v1/demand/demand-lists/{demand_list_id}/derive
POST /api/v1/demand/demand-lists/{demand_list_id}/void
```

### Route function names

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

### Role matrix

```text
Viewer:      list, detail
Contributor: create, item update, submit
Admin:       confirm, publish, derive, void
```

Admin inherits Viewer and Contributor through the existing role-rank dependency functions.

---

### Task 4A: Lock the Local Baseline and Write Static RED Contracts

**Files:**
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Modify: `extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py`

**Interfaces:**
- Consumes: existing AST route inventory and actor-forwarding helpers.
- Produces: exact Task 4 route names, counts, roles, and service-forwarding expectations.

- [ ] **Step 1: Verify the exact local baseline**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05

git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
```

Expected:

```text
feature/maintenance-frontend-plan05
67bdabe4fe84df350cb7bddd9b2ac82129522c3e
```

`git status --short` and `git diff --cached --name-only` must be empty.

- [ ] **Step 2: Update the exact RBAC route inventory as the RED contract**

In `tests/security/test_api_rbac.py`, change:

```python
EXPECTED_COUNTS = {
    "master_data": 67,
    "demand": 64,
    "ai": 26,
}
```

Change the total assertion:

```python
assert sum(counts.values()) == 157
```

Add these exact entries to `DEMAND_ROLE_BY_FUNCTION`:

```python
"create_demand_list": "require_contributor",
"list_demand_lists": "require_viewer",
"get_demand_list": "require_viewer",
"update_demand_list_item": "require_contributor",
"submit_demand_list": "require_contributor",
"confirm_demand_list": "require_admin",
"publish_demand_list": "require_admin",
"derive_demand_list": "require_admin",
"void_demand_list": "require_admin",
```

Do not remove or rename an existing route entry.

- [ ] **Step 3: Add the demand-list module to actor-forwarding contracts**

In `tests/security/test_demand_routes_actor_context.py`, add:

```python
_ROUTE_FUNCTIONS["demand_lists.py"] = {
    "create_demand_list",
    "list_demand_lists",
    "get_demand_list",
    "update_demand_list_item",
    "submit_demand_list",
    "confirm_demand_list",
    "publish_demand_list",
    "derive_demand_list",
    "void_demand_list",
}
```

Add:

```python
_SERVICE_NAMES["demand_lists.py"] = "demand_list_service"
```

Extend the exact-role alias contract with:

```python
_DEMAND_LIST_ROLES = {
    "create_demand_list": "ContributorDep",
    "list_demand_lists": "ViewerDep",
    "get_demand_list": "ViewerDep",
    "update_demand_list_item": "ContributorDep",
    "submit_demand_list": "ContributorDep",
    "confirm_demand_list": "AdminDep",
    "publish_demand_list": "AdminDep",
    "derive_demand_list": "AdminDep",
    "void_demand_list": "AdminDep",
}
```

Add a test that parses `demand_lists.py` and compares every route function's `actor` annotation with `_DEMAND_LIST_ROLES`.

- [ ] **Step 4: Run the static RED gate**

Run:

```powershell
cd extensions\maintenance-api

& .\.venv\Scripts\python.exe -m pytest `
  tests/security/test_api_rbac.py `
  tests/security/test_demand_routes_actor_context.py `
  -v
```

Expected: FAIL because `demand_lists.py` and its nine functions do not exist and the actual demand route count is still 55.

- [ ] **Step 5: Capture RED evidence**

Save:

```text
branch
HEAD
changed-file list
pytest command
failing test names
failure reason
```

Do not create production code before the RED output is reviewed.

---

### Task 4B: Write API Contract RED Tests

**Files:**
- Create: `extensions/maintenance-api/tests/api/test_demand_lists.py`

**Interfaces:**
- Consumes: `DemandListRead`, `DemandListSummaryRead`, `PageData`, actor fixtures, global exception handlers.
- Produces: executable HTTP contracts for paths, payloads, headers, envelopes, roles, actor forwarding, and stable errors.

- [ ] **Step 1: Add deterministic read-model builders**

Create `tests/api/test_demand_lists.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
)
from app.models.enums import DemandListStatus
from app.schemas.common import PageData
from app.schemas.demand_list import (
    DemandListRead,
    DemandListSummaryRead,
)
from app.security.actor import (
    ActorContext,
    MaintenanceRole,
)
from app.security.dependencies import get_actor


_NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _summary(
    *,
    demand_list_id: int = 41,
    status: DemandListStatus = DemandListStatus.DRAFT,
    version: int = 1,
) -> DemandListSummaryRead:
    return DemandListSummaryRead.model_validate(
        {
            "id": demand_list_id,
            "name": "Readiness demand",
            "description": "Task 4 API fixture",
            "lineage_id": (
                "11111111-1111-1111-1111-111111111111"
            ),
            "version_number": 1,
            "derived_from_id": None,
            "scenario_version_id": 7,
            "calculation_group_id": 9,
            "status": status,
            "is_current": (
                status is DemandListStatus.PUBLISHED
            ),
            "superseded_by_id": None,
            "superseded_at": None,
            "version": version,
            "created_by_user_id": "user-a",
            "created_by_request_id": "request-a",
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )


def _read(
    *,
    demand_list_id: int = 41,
    status: DemandListStatus = DemandListStatus.DRAFT,
    version: int = 1,
) -> DemandListRead:
    summary = _summary(
        demand_list_id=demand_list_id,
        status=status,
        version=version,
    ).model_dump()
    return DemandListRead.model_validate(
        {
            **summary,
            "submitted_by_user_id": None,
            "submitted_by_request_id": None,
            "submitted_at": None,
            "confirmed_by_user_id": None,
            "confirmed_by_request_id": None,
            "confirmed_at": None,
            "published_by_user_id": None,
            "published_by_request_id": None,
            "published_at": None,
            "voided_by_user_id": None,
            "voided_by_request_id": None,
            "voided_at": None,
            "items": [],
            "events": [],
        }
    )


def _page() -> PageData[DemandListSummaryRead]:
    return PageData[DemandListSummaryRead](
        items=[_summary()],
        page=1,
        page_size=20,
        total=1,
        pages=1,
    )


def _use_actor(
    client,
    actor: ActorContext,
) -> None:
    client.app.dependency_overrides[get_actor] = (
        lambda: actor
    )
```

Do not use current wall-clock time; deterministic timestamps make JSON assertions stable.

- [ ] **Step 2: Add exact route inventory test**

Add:

```python
def test_demand_list_route_inventory_is_exact(client) -> None:
    routes = {
        (
            next(iter(route.methods)),
            route.path,
        )
        for route in client.app.routes
        if route.path.startswith(
            "/api/v1/demand/demand-lists"
        )
        and route.methods
        and len(route.methods) == 1
    }

    assert routes == {
        ("POST", "/api/v1/demand/demand-lists"),
        ("GET", "/api/v1/demand/demand-lists"),
        (
            "GET",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}",
        ),
        (
            "PUT",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/items/{item_id}",
        ),
        (
            "POST",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/submit",
        ),
        (
            "POST",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/confirm",
        ),
        (
            "POST",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/publish",
        ),
        (
            "POST",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/derive",
        ),
        (
            "POST",
            "/api/v1/demand/demand-lists/"
            "{demand_list_id}/void",
        ),
    }
```

- [ ] **Step 3: Add request forwarding tests**

Use `monkeypatch` to replace methods on the imported route singleton and record exact arguments.

Example for create:

```python
def test_create_forwards_actor_payload_and_idempotency(
    client,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.api.v1.demand import demand_lists

    captured: dict[str, Any] = {}

    def fake_create(
        session,
        actor,
        *,
        calculation_group_id,
        name,
        description,
        idempotency_key,
    ):
        captured.update(
            {
                "actor": actor,
                "calculation_group_id": (
                    calculation_group_id
                ),
                "name": name,
                "description": description,
                "idempotency_key": idempotency_key,
            }
        )
        return _read()

    monkeypatch.setattr(
        demand_lists.demand_list_service,
        "create_from_group",
        fake_create,
    )
    _use_actor(client, actor_contributor)

    response = client.post(
        "/api/v1/demand/demand-lists",
        headers={"Idempotency-Key": "create-api-1"},
        json={
            "calculation_group_id": 9,
            "name": "Readiness demand",
            "description": "API",
        },
    )

    assert response.status_code == 201
    assert captured == {
        "actor": actor_contributor,
        "calculation_group_id": 9,
        "name": "Readiness demand",
        "description": "API",
        "idempotency_key": "create-api-1",
    }
    assert response.json()["meta"] == {
        "request_id": actor_contributor.request_id,
        "tenant_id": actor_contributor.tenant_id,
        "version": 1,
    }
```

Add equivalent direct-forwarding tests for:

```text
list
detail
item update
submit
confirm
publish
derive
void
```

Every fake service signature must begin with `session, actor`.

For confirmation, assert:

```python
confirmation_note == "Approved"
```

For item update, pass and assert:

```python
final_quantity == Decimal("12.500000")
adjustment_reason == "Engineering adjustment"
```

- [ ] **Step 4: Add RBAC matrix tests**

Parameterize mutation routes:

```python
@pytest.mark.parametrize(
    ("role", "path", "body", "allowed"),
    [
        (
            MaintenanceRole.VIEWER,
            "/api/v1/demand/demand-lists",
            {
                "calculation_group_id": 9,
                "name": "Denied",
            },
            False,
        ),
        (
            MaintenanceRole.CONTRIBUTOR,
            "/api/v1/demand/demand-lists/41/submit",
            {"expected_version": 1},
            True,
        ),
        (
            MaintenanceRole.CONTRIBUTOR,
            "/api/v1/demand/demand-lists/41/confirm",
            {
                "expected_version": 1,
                "confirmation_note": "Denied",
            },
            False,
        ),
        (
            MaintenanceRole.ADMIN,
            "/api/v1/demand/demand-lists/41/publish",
            {"expected_version": 1},
            True,
        ),
    ],
)
def test_demand_list_route_roles(
    client,
    actor_context,
    monkeypatch,
    role,
    path,
    body,
    allowed,
) -> None:
    ...
```

For denied requests assert:

```python
assert response.status_code == 403
assert (
    response.json()["error"]["code"]
    == "INSUFFICIENT_MAINTENANCE_ROLE"
)
```

For allowed requests, patch the corresponding service method to return `_read()`.

Add explicit Viewer GET tests for list and detail.

- [ ] **Step 5: Add header and body validation tests**

Add:

```python
def test_create_requires_idempotency_key(
    client,
    actor_contributor,
) -> None:
    _use_actor(client, actor_contributor)
    response = client.post(
        "/api/v1/demand/demand-lists",
        json={
            "calculation_group_id": 9,
            "name": "No key",
        },
    )
    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )
```

Add the same requirement test for all five lifecycle routes.

Add:

```python
def test_confirm_requires_confirmation_note(
    client,
    actor_admin,
) -> None:
    _use_actor(client, actor_admin)
    response = client.post(
        "/api/v1/demand/demand-lists/41/confirm",
        headers={"Idempotency-Key": "confirm-api-1"},
        json={
            "expected_version": 1,
            "note": "old field",
        },
    )
    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )
```

Add tests for:

```text
expected_version = 0
Idempotency-Key length = 129
extra body field tenant_id
blank create name
negative final_quantity
page = 0
page_size = 201
invalid status
```

- [ ] **Step 6: Add stable service-error passthrough tests**

Parameterize:

```python
@pytest.mark.parametrize(
    ("exception", "status_code", "code"),
    [
        (
            NotFoundError("demand_list", 41),
            404,
            "RESOURCE_NOT_FOUND",
        ),
        (
            BusinessValidationError(
                "invalid",
                code="DEMAND_LIST_SOURCE_INVALID",
            ),
            422,
            "DEMAND_LIST_SOURCE_INVALID",
        ),
        (
            ConflictError(
                "version conflict",
                code="DEMAND_LIST_VERSION_CONFLICT",
                details={
                    "expected_version": 1,
                    "actual_version": 2,
                },
            ),
            409,
            "DEMAND_LIST_VERSION_CONFLICT",
        ),
    ],
)
def test_service_errors_keep_stable_codes(
    client,
    actor_viewer,
    monkeypatch,
    exception,
    status_code,
    code,
) -> None:
    from app.api.v1.demand import demand_lists

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(
        demand_lists.demand_list_service,
        "get",
        fail,
    )
    _use_actor(client, actor_viewer)

    response = client.get(
        "/api/v1/demand/demand-lists/41"
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
```

For the conflict case also assert `details` are unchanged.

- [ ] **Step 7: Run the API RED gate**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  -v
```

Expected: collection or route-inventory failures because the route module is absent.

---

### Task 4C: Implement the Thin Typed Router

**Files:**
- Create: `extensions/maintenance-api/app/api/v1/demand/demand_lists.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/router.py`

**Interfaces:**
- Consumes: Task 3 schemas and `demand_list_service`.
- Produces: the nine REST routes defined in the public interface.

- [ ] **Step 1: Create dependency aliases and router metadata**

Create `app/api/v1/demand/demand_lists.py`:

```python
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db_session
from app.models.enums import DemandListStatus
from app.schemas.common import (
    MaintenanceSuccessResponse,
    PageData,
)
from app.schemas.demand_list import (
    DemandListConfirmRequest,
    DemandListCreateRequest,
    DemandListItemUpdateRequest,
    DemandListRead,
    DemandListSummaryRead,
    DemandListTransitionRequest,
)
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)
from app.services.demand_list_service import (
    demand_list_service,
)


router = APIRouter(
    prefix="/demand-lists",
    tags=["demand: demand lists"],
)

SessionDep = Annotated[
    Session,
    Depends(get_db_session),
]
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
IdempotencyKeyDep = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
]
```

- [ ] **Step 2: Implement create, list, detail, and item update**

Add:

```python
@router.post(
    "",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
    status_code=status.HTTP_201_CREATED,
)
def create_demand_list(
    payload: DemandListCreateRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.create_from_group(
        session,
        actor,
        calculation_group_id=(
            payload.calculation_group_id
        ),
        name=payload.name,
        description=payload.description,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list created",
        actor=actor,
        version=result.version,
    )


@router.get(
    "",
    response_model=MaintenanceSuccessResponse[
        PageData[DemandListSummaryRead]
    ],
)
def list_demand_lists(
    session: SessionDep,
    actor: ViewerDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: DemandListStatus | None = Query(
        default=None,
        alias="status",
    ),
    lineage_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=36,
    ),
):
    result = demand_list_service.list(
        session,
        actor,
        page=page,
        page_size=page_size,
        status=status_filter,
        lineage_id=lineage_id,
    )
    return success_response(
        result,
        actor=actor,
    )


@router.get(
    "/{demand_list_id}",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def get_demand_list(
    demand_list_id: int,
    session: SessionDep,
    actor: ViewerDep,
):
    result = demand_list_service.get(
        session,
        actor,
        demand_list_id,
    )
    return success_response(
        result,
        actor=actor,
        version=result.version,
    )


@router.put(
    "/{demand_list_id}/items/{item_id}",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def update_demand_list_item(
    demand_list_id: int,
    item_id: int,
    payload: DemandListItemUpdateRequest,
    session: SessionDep,
    actor: ContributorDep,
):
    result = demand_list_service.update_item(
        session,
        actor,
        demand_list_id,
        item_id,
        expected_version=payload.expected_version,
        final_quantity=payload.final_quantity,
        adjustment_reason=payload.adjustment_reason,
    )
    return success_response(
        result,
        "Demand list item updated",
        actor=actor,
        version=result.version,
    )
```

Do not add a tenant parameter or direct database query.

- [ ] **Step 3: Implement five lifecycle routes**

Add:

```python
@router.post(
    "/{demand_list_id}/submit",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def submit_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.submit(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list submitted",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/confirm",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def confirm_demand_list(
    demand_list_id: int,
    payload: DemandListConfirmRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.confirm(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        confirmation_note=payload.confirmation_note,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list confirmed",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/publish",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def publish_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.publish(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list published",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/derive",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def derive_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.derive(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list version derived",
        actor=actor,
        version=result.version,
    )


@router.post(
    "/{demand_list_id}/void",
    response_model=MaintenanceSuccessResponse[
        DemandListRead
    ],
)
def void_demand_list(
    demand_list_id: int,
    payload: DemandListTransitionRequest,
    session: SessionDep,
    actor: AdminDep,
    idempotency_key: IdempotencyKeyDep,
):
    result = demand_list_service.void(
        session,
        actor,
        demand_list_id,
        expected_version=payload.expected_version,
        idempotency_key=idempotency_key,
    )
    return success_response(
        result,
        "Demand list voided",
        actor=actor,
        version=result.version,
    )
```

Do not factor these calls into a string-dispatched generic action helper.

- [ ] **Step 4: Register the router**

Modify `app/api/v1/demand/router.py`.

Add `demand_lists` to the module import tuple and add:

```python
router.include_router(demand_lists.router)
```

Place it after `calculation_groups.router` so related demand orchestration routes remain grouped.

- [ ] **Step 5: Run the focused GREEN gate**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  tests/security/test_api_rbac.py `
  tests/security/test_demand_routes_actor_context.py `
  -v
```

Expected: PASS with no skipped or xfailed tests.

---

### Task 4D: Harden API Serialization, Validation, and Error Contracts

**Files:**
- Modify: `extensions/maintenance-api/tests/api/test_demand_lists.py`
- Modify only if a test proves necessary: `extensions/maintenance-api/app/api/v1/demand/demand_lists.py`

**Interfaces:**
- Consumes: completed Task 4C routes.
- Produces: proof that HTTP validation and global exception mapping are stable.

- [ ] **Step 1: Add aggregate metadata assertions**

For every single-aggregate route, assert:

```python
assert response.json()["meta"]["version"] == (
    response.json()["data"]["version"]
)
assert response.json()["meta"]["tenant_id"] == (
    actor.tenant_id
)
assert response.json()["meta"]["request_id"] == (
    actor.request_id
)
```

For list, assert:

```python
assert response.json()["meta"]["version"] is None
```

- [ ] **Step 2: Add decimal-string serialization proof**

Return a `DemandListRead` whose first item has:

```python
original_quantity=Decimal("10.250000")
final_quantity=Decimal("12.500000")
```

Assert:

```python
item = response.json()["data"]["items"][0]
assert item["original_quantity"] == "10.250000"
assert item["final_quantity"] == "12.500000"
assert not isinstance(item["final_quantity"], float)
```

The test builder must supply all required `DemandListItemRead` fields rather than bypassing model validation.

- [ ] **Step 3: Add tenant-input rejection and ignoring proof**

Create body:

```json
{
  "calculation_group_id": 9,
  "name": "Tenant injection",
  "tenant_id": "tenant-b"
}
```

Expected:

```text
422 VALIDATION_ERROR
```

For list/detail, send:

```text
?tenant_id=tenant-b
X-Tenant-ID: tenant-b
```

Patch the service and assert the forwarded actor still has the authenticated tenant. Do not assert that arbitrary unknown query parameters influence service filtering.

- [ ] **Step 4: Add conflict-detail passthrough proof**

Make a service fake raise:

```python
ConflictError(
    "demand list version conflict",
    code="DEMAND_LIST_VERSION_CONFLICT",
    details={
        "expected_version": 2,
        "actual_version": 3,
        "conflict_object": "demand_list",
        "retryable": False,
    },
)
```

Assert exact response JSON:

```python
assert response.json()["error"]["details"] == {
    "expected_version": 2,
    "actual_version": 3,
    "conflict_object": "demand_list",
    "retryable": False,
}
```

- [ ] **Step 5: Run API contract tests**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  -v
```

Expected: PASS.

---

### Task 4E: Run the Approved Regression and Scope Gates

**Files:**
- No new files.
- The working diff must contain exactly the five approved files.

**Interfaces:**
- Consumes: completed Task 4 implementation.
- Produces: final review evidence before any commit.

- [ ] **Step 1: Run focused Task 4 tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  tests/security/test_api_rbac.py `
  tests/security/test_demand_routes_actor_context.py `
  -v
```

Expected: PASS, zero skipped, zero xfailed.

- [ ] **Step 2: Run Task 3 service regression**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -v
```

Expected: the previously verified Task 3 service suite remains green.

- [ ] **Step 3: Run approved demand-domain regression**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  tests/services/test_demand_list_service.py `
  tests/services/test_demand_decision_policy.py `
  tests/services/test_calculation_group_service.py `
  tests/repositories/test_demand_list_repository.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  tests/migrations/test_demand_list_migration.py `
  tests/security/test_api_rbac.py `
  tests/security/test_demand_routes_actor_context.py `
  -v
```

Expected: PASS.

- [ ] **Step 4: Run the complete maintenance-api suite**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q
```

Expected:

```text
all collected non-deselected tests pass
8 existing deselections remain unless the collected suite itself has intentionally changed
no skipped, xfailed, or xpassed results
```

Record the actual passed count; do not reuse the pre-Task-4 count as a hardcoded assertion.

- [ ] **Step 5: Run static gates**

```powershell
& .\.venv\Scripts\python.exe -m compileall -q app tests
& .\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 6: Verify exact diff scope**

From the worktree root:

```powershell
git -c core.safecrlf=false diff --check
git diff --cached --check
git status --short
git diff --name-only
git diff --cached --name-only
```

Expected unstaged files exactly:

```text
extensions/maintenance-api/app/api/v1/demand/demand_lists.py
extensions/maintenance-api/app/api/v1/demand/router.py
extensions/maintenance-api/tests/api/test_demand_lists.py
extensions/maintenance-api/tests/security/test_api_rbac.py
extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
```

Expected staged files: none.

- [ ] **Step 7: Perform final code review**

Review for:

```text
no tenant selector
no direct ORM query
no session.get
one named role dependency per route
session and actor are the first service arguments
confirmation_note is exact
Idempotency-Key is required on six routes
meta.version is set only for aggregate responses
no float conversion
no exception-text parsing
no unrelated edits
```

Stop and request user approval before staging or committing.

---

## Final Commit Gate After Explicit Approval

The approved local implementation commit message is:

```text
feat(maintenance): expose demand list lifecycle api
```

Stage only:

```powershell
git add -- `
  extensions/maintenance-api/app/api/v1/demand/demand_lists.py `
  extensions/maintenance-api/app/api/v1/demand/router.py `
  extensions/maintenance-api/tests/api/test_demand_lists.py `
  extensions/maintenance-api/tests/security/test_api_rbac.py `
  extensions/maintenance-api/tests/security/test_demand_routes_actor_context.py
```

Before commit:

```powershell
git diff --cached --name-only
git -c core.safecrlf=false diff --cached --check
```

The index must contain exactly those five files.

After commit:

```powershell
git show --stat --summary HEAD
git status -sb
```

Expected:

```text
worktree clean
index empty
local branch advances by one commit
push not performed
```

Do not push until GitHub connectivity is restored and the user explicitly approves a normal non-force push.

## Explicitly Deferred Work

The implementation must not silently include:

1. frontend demand-list client;
2. frontend permission matrix;
3. Pinia demand-list store;
4. lifecycle buttons or detail page;
5. inventory reservation;
6. procurement or allocation;
7. reports;
8. notifications;
9. outbox infrastructure;
10. repository pagination changes;
11. lifecycle service changes;
12. Pydantic schema changes;
13. migration changes;
14. GitHub push;
15. Draft PR update.

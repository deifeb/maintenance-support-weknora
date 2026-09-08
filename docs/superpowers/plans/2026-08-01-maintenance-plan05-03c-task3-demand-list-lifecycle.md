# Plan 05-3C Task 3 Demand List Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce the complete demand-list lifecycle with tenant-safe service-layer RBAC, optimistic versions, exact idempotent replay, atomic publication and supersession, immutable published content, lineage-preserving derivation, and append-only lifecycle evidence.

**Architecture:** Extend the existing `DemandListService` through a shared lifecycle command shell that owns role checks, idempotency normalization, canonical request hashes, replay validation, optimistic-version errors, event response snapshots, and concurrent unique-conflict recovery. Keep `submit`, `confirm`, `publish`, `derive`, and `void` as action-specific methods because publication and derivation have distinct locking and aggregate-copy behavior. Reuse the existing persistence, repository, snapshot, risk, and read-model contracts without modifying models, repositories, migrations, APIs, or frontend code.

**Tech Stack:** Python 3.11, SQLAlchemy 2, Pydantic 2, pytest, Ruff, SQLite/PostgreSQL-compatible locking and constraints.

## Global Constraints

- Work only in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Target branch is `feature/maintenance-frontend-plan05`.
- The approved design baseline is `f4c8228cde77acb97a106540751d64fc5724f074` (`docs: design plan05 demand list lifecycle`).
- Before implementation, fast-forward the local branch to the approved design baseline; do not reset, rewrite, rebase, stash, or force-push.
- The only implementation files allowed to change are:
  - `extensions/maintenance-api/app/services/demand_list_service.py`
  - `extensions/maintenance-api/app/schemas/demand_list.py`
  - `extensions/maintenance-api/tests/services/test_demand_list_service.py`
- Do not modify models, enums, repositories, migrations, API routes, RBAC registries, frontend files, integration tests, progress ledgers, or the approved design document.
- Lifecycle is exactly `DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED`.
- `derive()` accepts a `PUBLISHED` source and creates a new `DRAFT` in the same lineage; it is not a direct state transition on the source row.
- Contributor may submit. Admin may submit, confirm, publish, derive, and void. Viewer has no lifecycle write capability.
- `ActorContext.tenant_id` is the only tenant source. Every repository call must use it.
- Every lifecycle action requires `expected_version` and a nonblank `Idempotency-Key`.
- `confirm()` also requires a nonblank trimmed confirmation note no longer than 1000 characters.
- Published item content is immutable. Edits require `derive()`.
- One tenant and lineage may have at most one `PUBLISHED && is_current` version.
- All lifecycle events are append-only and retain actor, role, request ID, request hash, idempotency key, before/after summaries, and a complete typed response snapshot.
- All JSON snapshots and replay responses must be deeply isolated.
- Each successful service mutation commits exactly once. Every failure rolls back.
- No external inventory, procurement, allocation, review-engine, notification, report, or outbox side effect may run inside a lifecycle transaction.
- Every production behavior starts with a failing test.
- Do not create intermediate commits. After all tasks and evidence gates pass, stop for final review. The single approved implementation commit will be `feat: enforce demand list lifecycle`.

---

## Approved File Map

### Modify: `extensions/maintenance-api/app/schemas/demand_list.py`

Responsibility:

- retain all Task 2 create, update, summary, event, item, and aggregate schemas;
- add lifecycle transition request schemas;
- trim and validate confirmation notes;
- reject extra request fields.

### Modify: `extensions/maintenance-api/app/services/demand_list_service.py`

Responsibility:

- retain Task 2 DRAFT generation, read/list, risk evaluation, and optimistic item update;
- generalize idempotent receipt validation without changing create semantics;
- add lifecycle role, key, hash, version, status, event, response-snapshot, and race-recovery helpers;
- add `submit`, `confirm`, `publish`, `derive`, and `void`;
- enforce published immutability in `update_item()`.

### Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

Responsibility:

- retain all Task 2 tests and fixtures;
- add Task 3 schema, role, transition, transaction, publication, derivation, void, replay, race, and full-lifecycle tests;
- use real SQLAlchemy rows for business behavior;
- use monkeypatch only for deterministic commit/rollback and unique-conflict simulations.

---

## Public Interfaces

### Request schemas

```python
class DemandListTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class DemandListConfirmRequest(DemandListTransitionRequest):
    confirmation_note: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator("confirmation_note", mode="before")
    @classmethod
    def strip_confirmation_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value
```

### Service methods

```python
def submit(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> DemandListRead:
    ...


def confirm(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    confirmation_note: str,
    idempotency_key: str,
) -> DemandListRead:
    ...


def publish(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> DemandListRead:
    ...


def derive(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> DemandListRead:
    ...


def void(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> DemandListRead:
    ...
```

### Stable lifecycle error codes

```text
IDEMPOTENCY_KEY_REQUIRED
INVALID_IDEMPOTENCY_KEY
IDEMPOTENCY_KEY_REUSED
IDEMPOTENT_RESPONSE_UNAVAILABLE
RESOURCE_NOT_FOUND
DEMAND_LIST_VERSION_INVALID
DEMAND_LIST_VERSION_CONFLICT
DEMAND_LIST_INVALID_TRANSITION
DEMAND_LIST_EMPTY
DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED
DEMAND_LIST_CONFIRMATION_NOTE_REQUIRED
DEMAND_LIST_CONFIRMATION_NOTE_INVALID
PUBLISHED_DEMAND_LIST_IMMUTABLE
DEMAND_LIST_NOT_EDITABLE
INSUFFICIENT_MAINTENANCE_ROLE
```

---

### Task 3A: Add Lifecycle Request Schemas

**Files:**
- Modify: `extensions/maintenance-api/app/schemas/demand_list.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes: existing Pydantic imports and `DemandListItemUpdateRequest` validation style.
- Produces: `DemandListTransitionRequest` and `DemandListConfirmRequest` for Tasks 3B–3H.

- [ ] **Step 1: Extend the schema export-contract RED test**

Add both names to `test_schema_contract_exports_required_models()`:

```python
required = {
    "DemandListCreateRequest",
    "DemandListItemUpdateRequest",
    "DemandListTransitionRequest",
    "DemandListConfirmRequest",
    "DemandListItemRead",
    "DemandListEventRead",
    "DemandListSummaryRead",
    "DemandListRead",
}
```

- [ ] **Step 2: Add focused failing schema tests**

Append these tests near the existing create/update schema tests:

```python
def test_task3a_transition_schema_requires_positive_version() -> None:
    schema = _schema("DemandListTransitionRequest")

    with pytest.raises(ValidationError):
        schema(expected_version=0)


def test_task3a_transition_schema_rejects_extra_fields() -> None:
    schema = _schema("DemandListTransitionRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            tenant_id="forbidden",
        )


def test_task3a_confirm_schema_strips_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    request = schema(
        expected_version=2,
        confirmation_note="  Reviewed by maintenance admin  ",
    )

    assert request.confirmation_note == (
        "Reviewed by maintenance admin"
    )


def test_task3a_confirm_schema_rejects_blank_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="   ",
        )


def test_task3a_confirm_schema_rejects_overlong_note() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="x" * 1001,
        )


def test_task3a_confirm_schema_rejects_extra_fields() -> None:
    schema = _schema("DemandListConfirmRequest")

    with pytest.raises(ValidationError):
        schema(
            expected_version=1,
            confirmation_note="Approved",
            actor_user_id="forbidden",
        )
```

- [ ] **Step 3: Run the schema RED gate**

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api

& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3a or schema_contract_exports_required_models" `
  -v
```

Expected: FAIL because the two lifecycle schemas do not exist.

- [ ] **Step 4: Add the two schemas**

Insert after `DemandListItemUpdateRequest`:

```python
class DemandListTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class DemandListConfirmRequest(
    DemandListTransitionRequest
):
    confirmation_note: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator(
        "confirmation_note",
        mode="before",
    )
    @classmethod
    def strip_confirmation_note(
        cls,
        value: object,
    ) -> object:
        return (
            value.strip()
            if isinstance(value, str)
            else value
        )
```

- [ ] **Step 5: Run the schema GREEN gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3a or schema_contract_exports_required_models" `
  -v
```

Expected: PASS.

- [ ] **Step 6: Run Ruff on the two changed files**

```powershell
& .\.venv\Scripts\python.exe -m ruff check `
  app/schemas/demand_list.py `
  tests/services/test_demand_list_service.py
```

Expected: PASS.

Do not commit. Continue to Task 3B.

---

### Task 3B: Add the Shared Lifecycle Command Shell and Submit

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes:
  - `DemandListRepository.get_for_update()`
  - `DemandListRepository.get_event_by_idempotency_key()`
  - `DemandListRepository.append_event()`
  - `DemandListItemRepository.list_for_demand_list()`
  - `DemandListRead`
  - `snapshot_service.canonical_hash()`
- Produces:
  - shared lifecycle helpers used by Tasks 3C–3G;
  - `submit()` with exact `SUBMITTED` evidence.

- [ ] **Step 1: Add reusable Task 3 test helpers**

Append these helpers after `_task2g_create_draft()`:

```python
def _task3_create_draft(
    session,
    actor,
    *,
    key: str,
    name: str = "Task 3 lifecycle draft",
):
    service, created = _task2g_create_draft(
        session,
        actor,
        key=key,
        name=name,
    )
    return service, created


def _task3_persisted_list(
    session,
    demand_list_id: int,
):
    from app.models import DemandList

    row = session.get(DemandList, demand_list_id)
    assert row is not None
    return row


def _task3_latest_event(
    session,
    demand_list_id: int,
):
    from app.models import DemandListEvent

    return (
        session.query(DemandListEvent)
        .filter(
            DemandListEvent.demand_list_id
            == demand_list_id
        )
        .order_by(DemandListEvent.id.desc())
        .first()
    )
```

- [ ] **Step 2: Write submit RED tests**

Add these exact test cases:

```python
def test_task3b_submit_moves_draft_and_records_counts(
    session,
    actor_contributor,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-submit-success",
    )

    submitted = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3b-submit-command",
    )

    assert submitted.status.value == (
        "PENDING_CONFIRMATION"
    )
    assert submitted.version == created.version + 1
    assert submitted.submitted_by_user_id == (
        actor_contributor.user_id
    )
    assert submitted.submitted_by_request_id == (
        actor_contributor.request_id
    )
    assert submitted.submitted_at is not None

    event = submitted.events[-1]
    assert event.event_type.value == "SUBMITTED"
    assert event.after_summary_json == {
        "lineage_id": submitted.lineage_id,
        "version_number": submitted.version_number,
        "status": "PENDING_CONFIRMATION",
        "is_current": False,
        "item_count": 2,
        "high_risk_item_count": 0,
        "requires_admin_confirmation_count": 0,
        "unconfirmed_item_count": 0,
        "version": submitted.version,
    }


def test_task3b_submit_counts_required_high_risk_items(
    session,
    actor_contributor,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-submit-risk-counts",
    )
    high = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )

    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        high.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Create high-risk review",
    )

    submitted = service.submit(
        session,
        actor_contributor,
        updated.id,
        expected_version=updated.version,
        idempotency_key="task3b-submit-risk-command",
    )

    assert submitted.events[-1].after_summary_json[
        "high_risk_item_count"
    ] == 1
    assert submitted.events[-1].after_summary_json[
        "requires_admin_confirmation_count"
    ] == 1
    assert submitted.events[-1].after_summary_json[
        "unconfirmed_item_count"
    ] == 1


def test_task3b_submit_rejects_empty_list(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandListItem

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-empty-source",
    )
    session.query(DemandListItem).filter(
        DemandListItem.demand_list_id == created.id
    ).delete(synchronize_session=False)
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-empty-submit",
        )

    assert captured.value.code == "DEMAND_LIST_EMPTY"


def test_task3b_viewer_cannot_submit(
    session,
    actor_contributor,
    actor_viewer,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-viewer-source",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ) as captured:
        service.submit(
            session,
            actor_viewer,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-viewer-submit",
        )

    assert captured.value.code == (
        "INSUFFICIENT_MAINTENANCE_ROLE"
    )


def test_task3b_submit_rejects_stale_version_details(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-stale-source",
    )
    stale = created.version + 1

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=stale,
            idempotency_key="task3b-stale-submit",
        )

    assert captured.value.code == (
        "DEMAND_LIST_VERSION_CONFLICT"
    )
    assert captured.value.details == {
        "expected_version": stale,
        "actual_version": created.version,
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3b_submit_rejects_invalid_transition(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-transition-source",
    )
    row = _task3_persisted_list(
        session,
        created.id,
    )
    row.status = DemandListStatus.CONFIRMED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.submit(
            session,
            actor_contributor,
            created.id,
            expected_version=created.version,
            idempotency_key=(
                "task3b-transition-submit"
            ),
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": "submit",
        "expected_status": "DRAFT",
        "actual_status": "CONFIRMED",
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3b_submit_cross_tenant_is_not_found(
    session,
    actor_contributor,
    actor_context,
) -> None:
    from app.core.exceptions import NotFoundError

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3b-tenant-source",
    )
    tenant_b = actor_context(
        tenant_id="tenant-b",
        user_id="user-b",
        request_id="request-b",
        token_id="token-b",
    )

    with pytest.raises(NotFoundError):
        service.submit(
            session,
            tenant_b,
            created.id,
            expected_version=created.version,
            idempotency_key="task3b-tenant-submit",
        )
```

Add `test_task3b_submit_rolls_back_row_and_event_on_failure`. Monkeypatch `service.repository.append_event` to raise `RuntimeError("task3b forced event failure")` after the aggregate fields have changed. Assert:

```python
row = _task3_persisted_list(session, created.id)
assert row.status.value == "DRAFT"
assert row.version == created.version
assert row.submitted_at is None
assert row.submitted_by_user_id is None
assert row.submitted_by_request_id is None
assert _task3_latest_event(
    session,
    created.id,
).event_type.value == "CREATED"
```

- [ ] **Step 3: Run the submit RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3b" `
  -v
```

Expected: FAIL because `DemandListService.submit()` and lifecycle helpers do not exist.

- [ ] **Step 4: Import lifecycle dependencies**

Update service imports:

```python
from datetime import UTC, date, datetime
from app.models.demand_list import (
    DemandList,
    DemandListEvent,
    DemandListItem,
)
```

Extend schema imports:

```python
from app.schemas.demand_list import (
    DemandListConfirmRequest,
    DemandListCreateRequest,
    DemandListRead,
    DemandListSummaryRead,
    DemandListTransitionRequest,
)
```

Use `datetime.now(UTC)` for lifecycle timestamps.

- [ ] **Step 5: Add role, input, hash, version, and status helpers**

Add inside `DemandListService` after `_require_contributor()`:

```python
@staticmethod
def _require_admin(
    actor: ActorContext,
) -> None:
    if actor.role is not MaintenanceRole.ADMIN:
        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.ADMIN.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )


@staticmethod
def _normalize_idempotency_key(
    idempotency_key: str,
) -> str:
    clean_key = idempotency_key.strip()
    if not clean_key:
        raise BusinessValidationError(
            "idempotency key is required",
            code="IDEMPOTENCY_KEY_REQUIRED",
        )
    if len(clean_key) > 128:
        raise BusinessValidationError(
            "idempotency key is invalid",
            code="INVALID_IDEMPOTENCY_KEY",
        )
    return clean_key


@staticmethod
def _require_expected_version(
    expected_version: int,
) -> None:
    if expected_version < 1:
        raise BusinessValidationError(
            "expected version is invalid",
            code="DEMAND_LIST_VERSION_INVALID",
        )


@staticmethod
def _require_version(
    demand_list: DemandList,
    expected_version: int,
) -> None:
    if demand_list.version != expected_version:
        raise ConflictError(
            "demand list version conflict",
            code="DEMAND_LIST_VERSION_CONFLICT",
            details={
                "expected_version": expected_version,
                "actual_version": demand_list.version,
                "conflict_object": "demand_list",
                "retryable": False,
            },
        )


@staticmethod
def _require_status(
    demand_list: DemandList,
    *,
    action: str,
    expected_status: DemandListStatus,
) -> None:
    if demand_list.status is not expected_status:
        raise ConflictError(
            "invalid demand list transition",
            code="DEMAND_LIST_INVALID_TRANSITION",
            details={
                "action": action,
                "expected_status": expected_status.value,
                "actual_status": demand_list.status.value,
                "conflict_object": "demand_list",
                "retryable": False,
            },
        )


@staticmethod
def _lifecycle_request_hash(
    *,
    action: str,
    demand_list_id: int,
    expected_version: int,
    confirmation_note: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "action": action,
        "demand_list_id": demand_list_id,
        "expected_version": expected_version,
    }
    if confirmation_note is not None:
        payload["confirmation_note"] = (
            confirmation_note
        )
    return snapshot_service.canonical_hash(payload)
```

Refactor `create_from_group()` to call `_normalize_idempotency_key()` without changing its request hash, receipt type, response, error codes, or race behavior.

- [ ] **Step 6: Generalize receipt validation while preserving create behavior**

Replace the create-only parser with:

```python
@staticmethod
def _idempotent_read_model(
    receipt: DemandListEvent,
    request_hash: str,
    *,
    expected_event_type: DemandListEventType,
) -> DemandListRead:
    if receipt.event_type is not expected_event_type:
        raise ConflictError(
            "idempotent response is unavailable",
            code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
        )
    if receipt.request_hash != request_hash:
        raise ConflictError(
            "idempotency key was reused",
            code="IDEMPOTENCY_KEY_REUSED",
            details={
                "conflict_object": "demand_list",
                "retryable": False,
            },
        )
    if receipt.response_snapshot_json is None:
        raise ConflictError(
            "idempotent response is unavailable",
            code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
        )
    try:
        return (
            DemandListRead.model_validate(
                receipt.response_snapshot_json
            )
            .model_copy(deep=True)
        )
    except ValidationError as exc:
        raise ConflictError(
            "idempotent response is unavailable",
            code="IDEMPOTENT_RESPONSE_UNAVAILABLE",
        ) from exc


@classmethod
def _idempotent_response(
    cls,
    receipt: DemandListEvent,
    request_hash: str,
) -> DemandListRead:
    return cls._idempotent_read_model(
        receipt,
        request_hash,
        expected_event_type=(
            DemandListEventType.CREATED
        ),
    )
```

- [ ] **Step 7: Add lifecycle response and item-summary helpers**

```python
def _load_locked_list(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
) -> DemandList:
    demand_list = self.repository.get_for_update(
        session,
        actor.tenant_id,
        demand_list_id,
    )
    if demand_list is None:
        raise NotFoundError(
            "demand_list",
            demand_list_id,
        )
    return demand_list


def _items(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
) -> list[DemandListItem]:
    return self.item_repository.list_for_demand_list(
        session,
        actor.tenant_id,
        demand_list_id,
    )


@staticmethod
def _item_counts(
    items: list[DemandListItem],
) -> dict[str, int]:
    return {
        "item_count": len(items),
        "high_risk_item_count": sum(
            1
            for item in items
            if (item.decision_risk or "").upper()
            == "HIGH"
        ),
        "requires_admin_confirmation_count": sum(
            1
            for item in items
            if item.requires_admin_confirmation
        ),
        "unconfirmed_item_count": sum(
            1
            for item in items
            if item.requires_admin_confirmation
            and not item.confirmed_by_admin
        ),
    }


def _response_with_event_snapshot(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    event: DemandListEvent,
) -> DemandListRead:
    loaded = self.repository.get(
        session,
        actor.tenant_id,
        demand_list_id,
    )
    assert loaded is not None
    response = self._read_model(loaded)
    event.response_snapshot_json = (
        response.model_dump(mode="json")
    )
    session.flush()
    return response
```

- [ ] **Step 8: Implement `submit()`**

Use this action-specific body:

```python
def submit(
    self,
    session: Session,
    actor: ActorContext,
    demand_list_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> DemandListRead:
    self._require_contributor(actor)
    self._require_expected_version(expected_version)
    clean_key = self._normalize_idempotency_key(
        idempotency_key
    )
    request_hash = self._lifecycle_request_hash(
        action="submit",
        demand_list_id=demand_list_id,
        expected_version=expected_version,
    )
    existing = (
        self.repository.get_event_by_idempotency_key(
            session,
            actor.tenant_id,
            clean_key,
        )
    )
    if existing is not None:
        return self._idempotent_read_model(
            existing,
            request_hash,
            expected_event_type=(
                DemandListEventType.SUBMITTED
            ),
        )

    try:
        demand_list = self._load_locked_list(
            session,
            actor,
            demand_list_id,
        )
        self._require_version(
            demand_list,
            expected_version,
        )
        self._require_status(
            demand_list,
            action="submit",
            expected_status=DemandListStatus.DRAFT,
        )
        items = self._items(
            session,
            actor,
            demand_list.id,
        )
        if not items:
            raise ConflictError(
                "demand list is empty",
                code="DEMAND_LIST_EMPTY",
                details={
                    "conflict_object": "demand_list",
                    "retryable": False,
                },
            )

        before = {
            "lineage_id": demand_list.lineage_id,
            "version_number": (
                demand_list.version_number
            ),
            "status": demand_list.status.value,
            "is_current": demand_list.is_current,
            "version": demand_list.version,
        }
        now = datetime.now(UTC)
        demand_list.status = (
            DemandListStatus.PENDING_CONFIRMATION
        )
        demand_list.submitted_by_user_id = (
            actor.user_id
        )
        demand_list.submitted_by_request_id = (
            actor.request_id
        )
        demand_list.submitted_at = now
        demand_list.version += 1
        session.flush()

        after = {
            "lineage_id": demand_list.lineage_id,
            "version_number": (
                demand_list.version_number
            ),
            "status": demand_list.status.value,
            "is_current": demand_list.is_current,
            **self._item_counts(items),
            "version": demand_list.version,
        }
        event = self.repository.append_event(
            session,
            actor.tenant_id,
            demand_list_id=demand_list.id,
            event_type=DemandListEventType.SUBMITTED,
            actor_user_id=actor.user_id,
            actor_roles=[actor.role.value],
            request_id=actor.request_id,
            idempotency_key=clean_key,
            request_hash=request_hash,
            before_summary=before,
            after_summary=after,
            response_snapshot={"id": demand_list.id},
        )
        response = self._response_with_event_snapshot(
            session,
            actor,
            demand_list.id,
            event,
        )
        session.commit()
        return response
    except IntegrityError:
        session.rollback()
        winner = (
            self.repository
            .get_event_by_idempotency_key(
                session,
                actor.tenant_id,
                clean_key,
            )
        )
        if winner is None:
            raise
        return self._idempotent_read_model(
            winner,
            request_hash,
            expected_event_type=(
                DemandListEventType.SUBMITTED
            ),
        )
    except Exception:
        session.rollback()
        raise
```

Task 3G will parameterize and harden the repeated race shell after all action methods exist.

- [ ] **Step 9: Run the submit GREEN gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3a or task3b or task2e or task2j" `
  -v
```

Expected: PASS. Existing Task 2 create idempotency and race tests must remain green.

- [ ] **Step 10: Run Ruff and diff checks**

```powershell
& .\.venv\Scripts\python.exe -m ruff check `
  app/services/demand_list_service.py `
  app/schemas/demand_list.py `
  tests/services/test_demand_list_service.py

git -c core.safecrlf=false diff --check
```

Expected: PASS.

Do not commit. Continue to Task 3C.

---

### Task 3C: Confirm All Required Items with Admin Evidence

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes: Task 3B lifecycle helpers and `DemandListConfirmRequest`.
- Produces: `confirm()` and complete `CONFIRMED` event evidence.

- [ ] **Step 1: Add a helper that creates a pending list with one required item**

```python
def _task3_pending_high_risk_list(
    session,
    actor,
    *,
    source_key: str,
    submit_key: str,
):
    service, created = _task3_create_draft(
        session,
        actor,
        key=source_key,
    )
    target = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )
    updated = service.update_item(
        session,
        actor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Require admin confirmation",
    )
    pending = service.submit(
        session,
        actor,
        updated.id,
        expected_version=updated.version,
        idempotency_key=submit_key,
    )
    return service, pending, target.id
```

- [ ] **Step 2: Write confirm RED tests**

Add these tests:

```python
def test_task3c_admin_confirms_all_required_items(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, pending, target_id = (
        _task3_pending_high_risk_list(
            session,
            actor_contributor,
            source_key="task3c-confirm-source",
            submit_key="task3c-confirm-submit",
        )
    )

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="  Reviewed risk evidence  ",
        idempotency_key="task3c-confirm-command",
    )

    target = next(
        item
        for item in confirmed.items
        if item.id == target_id
    )
    low = next(
        item
        for item in confirmed.items
        if item.id != target_id
    )

    assert confirmed.status.value == "CONFIRMED"
    assert confirmed.version == pending.version + 1
    assert confirmed.confirmed_by_user_id == (
        actor_admin.user_id
    )
    assert confirmed.confirmed_by_request_id == (
        actor_admin.request_id
    )
    assert confirmed.confirmed_at is not None
    assert target.confirmed_by_admin is True
    assert target.version == 3
    assert low.confirmed_by_admin is False
    assert low.version == 1

    event = confirmed.events[-1]
    assert event.event_type.value == "CONFIRMED"
    assert event.after_summary_json[
        "confirmation_note"
    ] == "Reviewed risk evidence"
    assert event.after_summary_json[
        "confirmed_item_ids"
    ] == [target_id]
    assert event.after_summary_json[
        "confirmed_item_count"
    ] == 1


def test_task3c_confirm_without_required_items_is_audited(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-low-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-low-submit",
    )

    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="No elevated risks found",
        idempotency_key="task3c-low-confirm",
    )

    assert confirmed.status.value == "CONFIRMED"
    assert confirmed.events[-1].after_summary_json[
        "confirmed_item_ids"
    ] == []
    assert confirmed.events[-1].after_summary_json[
        "confirmed_item_count"
    ] == 0
    assert all(
        item.version == 1
        for item in confirmed.items
    )


def test_task3c_contributor_cannot_confirm(
    session,
    actor_contributor,
) -> None:
    from app.core.exceptions import (
        InsufficientMaintenanceRoleError,
    )

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3c-role-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3c-role-submit",
    )

    with pytest.raises(
        InsufficientMaintenanceRoleError
    ):
        service.confirm(
            session,
            actor_contributor,
            pending.id,
            expected_version=pending.version,
            confirmation_note="Forbidden",
            idempotency_key="task3c-role-confirm",
        )


def test_task3c_direct_blank_note_has_stable_code(
    session,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.confirm(
            session,
            actor_admin,
            999,
            expected_version=1,
            confirmation_note="   ",
            idempotency_key="task3c-blank-note",
        )

    assert captured.value.code == (
        "DEMAND_LIST_CONFIRMATION_NOTE_REQUIRED"
    )


def test_task3c_direct_overlong_note_has_stable_code(
    session,
    actor_admin,
) -> None:
    from app.core.exceptions import (
        BusinessValidationError,
    )

    service = _demand_list_service()

    with pytest.raises(
        BusinessValidationError
    ) as captured:
        service.confirm(
            session,
            actor_admin,
            999,
            expected_version=1,
            confirmation_note="x" * 1001,
            idempotency_key="task3c-long-note",
        )

    assert captured.value.code == (
        "DEMAND_LIST_CONFIRMATION_NOTE_INVALID"
    )
```

Add these named confirm tests with the stated assertions:

- `test_task3c_confirm_rejects_invalid_transition`: change the persisted source status to `DRAFT`; assert `DEMAND_LIST_INVALID_TRANSITION` details contain action `confirm`, expected `PENDING_CONFIRMATION`, and actual `DRAFT`.
- `test_task3c_confirm_rejects_stale_version`: pass `pending.version + 1`; assert the exact `DEMAND_LIST_VERSION_CONFLICT` detail object.
- `test_task3c_confirm_cross_tenant_is_not_found`: invoke with a tenant-B admin actor; assert `RESOURCE_NOT_FOUND`.
- `test_task3c_confirm_commits_once`: monkeypatch `session.commit`, execute a valid confirmation, and assert exactly one call.
- `test_task3c_confirmed_ids_are_sorted`: mark both items as required and unconfirmed, reverse their in-memory ordering, confirm, and assert `confirmed_item_ids == sorted([first.id, second.id])`.
- `test_task3c_confirm_rolls_back_items_row_and_event`: monkeypatch `append_event()` to raise after flags and aggregate fields change; assert the list remains `PENDING_CONFIRMATION`, aggregate version is unchanged, every item flag/version is unchanged, and no `CONFIRMED` event exists.

- [ ] **Step 3: Run the confirm RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3c" `
  -v
```

Expected: FAIL because `confirm()` does not exist.

- [ ] **Step 4: Add direct confirmation-note validation**

```python
@staticmethod
def _normalize_confirmation_note(
    confirmation_note: str,
) -> str:
    note = confirmation_note.strip()
    if not note:
        raise BusinessValidationError(
            "confirmation note is required",
            code=(
                "DEMAND_LIST_CONFIRMATION_NOTE_REQUIRED"
            ),
        )
    if len(note) > 1000:
        raise BusinessValidationError(
            "confirmation note is invalid",
            code=(
                "DEMAND_LIST_CONFIRMATION_NOTE_INVALID"
            ),
        )
    return note
```

- [ ] **Step 5: Implement `confirm()`**

Follow the Task 3B command order. Use:

```python
self._require_admin(actor)
self._require_expected_version(expected_version)
note = self._normalize_confirmation_note(
    confirmation_note
)
clean_key = self._normalize_idempotency_key(
    idempotency_key
)
request_hash = self._lifecycle_request_hash(
    action="confirm",
    demand_list_id=demand_list_id,
    expected_version=expected_version,
    confirmation_note=note,
)
```

After locking, version, and `PENDING_CONFIRMATION` checks:

```python
items = self._items(
    session,
    actor,
    demand_list.id,
)
confirmed_item_ids = sorted(
    item.id
    for item in items
    if item.requires_admin_confirmation
)
unconfirmed_item_ids_before = sorted(
    item.id
    for item in items
    if item.requires_admin_confirmation
    and not item.confirmed_by_admin
)
before = {
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "version": demand_list.version,
    "unconfirmed_item_ids": (
        unconfirmed_item_ids_before
    ),
}
for item in items:
    if (
        item.requires_admin_confirmation
        and not item.confirmed_by_admin
    ):
        item.confirmed_by_admin = True
        item.version += 1

now = datetime.now(UTC)
demand_list.status = DemandListStatus.CONFIRMED
demand_list.confirmed_by_user_id = actor.user_id
demand_list.confirmed_by_request_id = (
    actor.request_id
)
demand_list.confirmed_at = now
demand_list.version += 1
session.flush()

after = {
    "confirmation_note": note,
    "confirmed_item_ids": confirmed_item_ids,
    "confirmed_item_count": len(
        confirmed_item_ids
    ),
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "version": demand_list.version,
}
```

The before-summary captures `unconfirmed_item_ids` before any item flag changes.

Append `CONFIRMED`, store the complete response snapshot, commit once, and use the Task 3B `IntegrityError` recovery pattern with expected event type `CONFIRMED`.

- [ ] **Step 6: Run the confirm GREEN gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3a or task3b or task3c" `
  -v
```

Expected: PASS.

- [ ] **Step 7: Run focused Ruff and diff checks**

```powershell
& .\.venv\Scripts\python.exe -m ruff check `
  app/services/demand_list_service.py `
  app/schemas/demand_list.py `
  tests/services/test_demand_list_service.py

git -c core.safecrlf=false diff --check
```

Expected: PASS.

Do not commit. Continue to Task 3D.

---

### Task 3D: Publish Atomically and Enforce Published Immutability

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes:
  - Task 3C `confirm()`;
  - `DemandListRepository.current_published_for_update()`;
  - database partial unique index for current published lineage.
- Produces:
  - `publish()`;
  - atomic supersession;
  - `PUBLISHED_DEMAND_LIST_IMMUTABLE`.

- [ ] **Step 1: Add a helper that produces a confirmed list**

```python
def _task3_confirmed_list(
    session,
    actor_contributor,
    actor_admin,
    *,
    source_key: str,
    submit_key: str,
    confirm_key: str,
):
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key=source_key,
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key=submit_key,
    )
    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Lifecycle approval",
        idempotency_key=confirm_key,
    )
    return service, confirmed
```

- [ ] **Step 2: Write publication RED tests**

Add:

```python
def test_task3d_publish_sets_current_and_metadata(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-publish-source",
        submit_key="task3d-publish-submit",
        confirm_key="task3d-publish-confirm",
    )

    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-publish-command",
    )

    assert published.status.value == "PUBLISHED"
    assert published.is_current is True
    assert published.version == confirmed.version + 1
    assert published.published_by_user_id == (
        actor_admin.user_id
    )
    assert published.published_by_request_id == (
        actor_admin.request_id
    )
    assert published.published_at is not None
    assert published.events[-1].event_type.value == (
        "PUBLISHED"
    )


def test_task3d_publish_rejects_unconfirmed_required_ids(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models import DemandListItem
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3d-unconfirmed-source",
    )
    target = created.items[0]
    row = _task3_persisted_list(
        session,
        created.id,
    )
    item = session.get(DemandListItem, target.id)
    assert item is not None
    item.requires_admin_confirmation = True
    item.confirmed_by_admin = False
    row.status = DemandListStatus.CONFIRMED
    session.commit()

    with pytest.raises(ConflictError) as captured:
        service.publish(
            session,
            actor_admin,
            created.id,
            expected_version=created.version,
            idempotency_key=(
                "task3d-unconfirmed-publish"
            ),
        )

    assert captured.value.code == (
        "DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED"
    )
    assert captured.value.details == {
        "unconfirmed_item_ids": [target.id],
        "conflict_object": "demand_list",
        "retryable": False,
    }


def test_task3d_new_publish_supersedes_old_current(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, confirmed_v1 = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-v1-source",
        submit_key="task3d-v1-submit",
        confirm_key="task3d-v1-confirm",
    )
    published_v1 = service.publish(
        session,
        actor_admin,
        confirmed_v1.id,
        expected_version=confirmed_v1.version,
        idempotency_key="task3d-v1-publish",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3d-v2-derive",
    )
    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3d-v2-submit",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3d-v2-confirm",
    )

    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3d-v2-publish",
    )

    old = session.get(DemandList, published_v1.id)
    assert old is not None
    assert old.status.value == "PUBLISHED"
    assert old.is_current is False
    assert old.superseded_by_id == published_v2.id
    assert old.superseded_at is not None
    assert old.version == published_v1.version + 1

    current_rows = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v2.lineage_id,
            DemandList.status == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .all()
    )
    assert [row.id for row in current_rows] == [
        published_v2.id
    ]
```

The supersession test depends on `derive()` from Task 3E. During Task 3D RED, mark only this one test with `@pytest.mark.skip(reason="enabled in Task 3E")`. Remove that marker in Task 3E before its GREEN gate. Do not skip any other Task 3D test.

Add these named publication tests:

- `test_task3d_publish_rejects_empty_confirmed_list`: delete all items from a `CONFIRMED` row and assert `DEMAND_LIST_EMPTY`.
- `test_task3d_contributor_cannot_publish`: assert `INSUFFICIENT_MAINTENANCE_ROLE`.
- `test_task3d_publish_rejects_invalid_transition`: invoke from `DRAFT` and assert exact `DEMAND_LIST_INVALID_TRANSITION` details.
- `test_task3d_publish_rejects_stale_version`: assert exact `DEMAND_LIST_VERSION_CONFLICT` details.
- `test_task3d_publish_cross_tenant_is_not_found`: invoke with tenant B and assert `RESOURCE_NOT_FOUND`.
- `test_task3d_publish_event_summaries_are_complete`: assert before-summary contains lineage, version number, `CONFIRMED`, non-current state, target version, and previous-current summary; assert after-summary contains `PUBLISHED`, current state, item count, superseded ID, and new version.
- `test_task3d_publish_commits_once`: monkeypatch `session.commit` and assert one call.
- `test_task3d_publish_rolls_back_both_versions_and_event`: prepare an old current version and a confirmed target, monkeypatch `_response_with_event_snapshot()` to raise after both rows and the event are flushed, then assert the old row remains current without supersession, the target remains `CONFIRMED` and non-current, both versions are unchanged, and no `PUBLISHED` event remains.

- [ ] **Step 3: Add published update immutability RED test**

```python
def test_task3d_published_items_are_immutable(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.core.exceptions import ConflictError

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3d-immutable-source",
        submit_key="task3d-immutable-submit",
        confirm_key="task3d-immutable-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3d-immutable-publish",
    )

    with pytest.raises(ConflictError) as captured:
        service.update_item(
            session,
            actor_admin,
            published.id,
            published.items[0].id,
            expected_version=published.version,
            final_quantity=Decimal("1.000000"),
            adjustment_reason="Forbidden edit",
        )

    assert captured.value.code == (
        "PUBLISHED_DEMAND_LIST_IMMUTABLE"
    )
```

- [ ] **Step 4: Run the publication RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3d" `
  -v
```

Expected: FAIL because `publish()` is missing and published updates still use the generic non-editable error.

- [ ] **Step 5: Implement the published immutability branch**

In `update_item()`, after loading the list and before the generic non-DRAFT branch:

```python
if (
    demand_list.status
    is DemandListStatus.PUBLISHED
):
    raise ConflictError(
        "published demand list is immutable",
        code=(
            "PUBLISHED_DEMAND_LIST_IMMUTABLE"
        ),
        details={
            "conflict_object": "demand_list",
            "retryable": False,
        },
    )
if demand_list.status is not DemandListStatus.DRAFT:
    raise ConflictError(
        "demand list is not editable",
        code="DEMAND_LIST_NOT_EDITABLE",
    )
```

- [ ] **Step 6: Implement `publish()`**

Use the standard Admin/key/hash/replay shell with expected event `PUBLISHED`. After target lock, version, and `CONFIRMED` checks:

```python
items = self._items(
    session,
    actor,
    demand_list.id,
)
if not items:
    raise ConflictError(
        "demand list is empty",
        code="DEMAND_LIST_EMPTY",
        details={
            "conflict_object": "demand_list",
            "retryable": False,
        },
    )

unconfirmed_item_ids = sorted(
    item.id
    for item in items
    if item.requires_admin_confirmation
    and not item.confirmed_by_admin
)
if unconfirmed_item_ids:
    raise ConflictError(
        "admin confirmation is required",
        code=(
            "DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED"
        ),
        details={
            "unconfirmed_item_ids": (
                unconfirmed_item_ids
            ),
            "conflict_object": "demand_list",
            "retryable": False,
        },
    )

previous_current = (
    self.repository.current_published_for_update(
        session,
        actor.tenant_id,
        demand_list.lineage_id,
    )
)
now = datetime.now(UTC)
previous_current_summary = None
if (
    previous_current is not None
    and previous_current.id != demand_list.id
):
    previous_current_summary = {
        "id": previous_current.id,
        "version": previous_current.version,
        "is_current": previous_current.is_current,
    }
    previous_current.is_current = False
    previous_current.superseded_by_id = (
        demand_list.id
    )
    previous_current.superseded_at = now
    previous_current.version += 1

before = {
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "is_current": demand_list.is_current,
    "version": demand_list.version,
    "previous_current": previous_current_summary,
}
demand_list.status = DemandListStatus.PUBLISHED
demand_list.is_current = True
demand_list.published_by_user_id = actor.user_id
demand_list.published_by_request_id = (
    actor.request_id
)
demand_list.published_at = now
demand_list.version += 1
session.flush()

after = {
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "is_current": demand_list.is_current,
    "item_count": len(items),
    "superseded_demand_list_id": (
        previous_current.id
        if previous_current is not None
        and previous_current.id
        != demand_list.id
        else None
    ),
    "version": demand_list.version,
}
```

Append `PUBLISHED`, store the target aggregate response snapshot, commit once, and recover same-key races through expected event `PUBLISHED`.

- [ ] **Step 7: Run the Task 3D GREEN gate except the deferred supersession test**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3d and not new_publish_supersedes_old_current" `
  -v
```

Expected: PASS.

- [ ] **Step 8: Run Task 2 update regressions**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task2g or task2h or task3d" `
  -v
```

Expected: PASS except the single explicitly skipped Task 3D supersession test.

Do not commit. Continue to Task 3E.

---

### Task 3E: Derive a Deeply Isolated DRAFT in the Same Lineage

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes:
  - `DemandListRepository.create_version()`
  - `DemandListRepository.add_item()`
  - Task 3D `publish()`.
- Produces:
  - `derive()`;
  - item-copy helper;
  - enabled supersession test.

- [ ] **Step 1: Write derivation RED tests**

Add:

```python
def test_task3e_derive_copies_lineage_items_and_snapshots(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from copy import deepcopy

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-source",
        submit_key="task3e-submit",
        confirm_key="task3e-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3e-publish",
    )
    source_dump = published.model_dump(
        mode="json"
    )

    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-derive",
    )

    assert derived.status.value == "DRAFT"
    assert derived.is_current is False
    assert derived.lineage_id == published.lineage_id
    assert derived.version_number == (
        published.version_number + 1
    )
    assert derived.derived_from_id == published.id
    assert derived.scenario_version_id == (
        published.scenario_version_id
    )
    assert derived.calculation_group_id == (
        published.calculation_group_id
    )
    assert derived.name == published.name
    assert derived.description == published.description
    assert derived.version == 1
    assert len(derived.items) == len(published.items)
    assert all(item.version == 1 for item in derived.items)

    source_by_spare = {
        item.spare_part_id: item
        for item in published.items
    }
    for item in derived.items:
        source = source_by_spare[item.spare_part_id]
        assert item.id != source.id
        assert item.original_quantity == (
            source.original_quantity
        )
        assert item.final_quantity == (
            source.final_quantity
        )
        assert item.decision_type == source.decision_type
        assert item.decision_risk == source.decision_risk
        assert (
            item.requires_admin_confirmation
            is source.requires_admin_confirmation
        )
        assert (
            item.confirmed_by_admin
            is source.confirmed_by_admin
        )
        assert item.source_snapshot_json == (
            source.source_snapshot_json
        )
        assert item.decision_snapshot_json == (
            source.decision_snapshot_json
        )
        assert item.interval_snapshot_json == (
            source.interval_snapshot_json
        )
        assert item.parameter_snapshot_json == (
            source.parameter_snapshot_json
        )
        assert item.warning_snapshot_json == (
            source.warning_snapshot_json
        )
        assert item.inventory_snapshot_json == (
            source.inventory_snapshot_json
        )

    derived.items[0].interval_snapshot_json[
        "candidates"
    ][0]["warnings"].append("TASK3E-MUTATION")
    reloaded_source = service.get(
        session,
        actor_admin,
        published.id,
    )
    assert "TASK3E-MUTATION" not in (
        reloaded_source.items[0]
        .interval_snapshot_json["candidates"][0]
        ["warnings"]
    )
    assert published.model_dump(mode="json") == (
        source_dump
    )


def test_task3e_derive_event_is_on_new_draft(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3e-event-source",
        submit_key="task3e-event-submit",
        confirm_key="task3e-event-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3e-event-publish",
    )

    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3e-event-derive",
    )

    event = derived.events[-1]
    assert event.demand_list_id == derived.id
    assert event.event_type.value == "DERIVED"
    assert event.after_summary_json == {
        "derived_from_id": published.id,
        "lineage_id": published.lineage_id,
        "source_version_number": (
            published.version_number
        ),
        "new_version_number": (
            derived.version_number
        ),
        "copied_item_count": len(derived.items),
        "status": "DRAFT",
        "version": 1,
    }
```

Add these named derivation tests:

- `test_task3e_contributor_cannot_derive`: assert `INSUFFICIENT_MAINTENANCE_ROLE`.
- `test_task3e_derive_requires_published_source`: invoke from `CONFIRMED` and assert exact `DEMAND_LIST_INVALID_TRANSITION` details.
- `test_task3e_derive_rejects_stale_version`: assert exact `DEMAND_LIST_VERSION_CONFLICT` details.
- `test_task3e_derive_cross_tenant_is_not_found`: invoke with a tenant-B admin and assert `RESOURCE_NOT_FOUND`.
- `test_task3e_derive_does_not_mutate_source`: compare every source aggregate scalar, item scalar, JSON snapshot, version, status, and current flag before and after derivation.
- `test_task3e_derive_replays_exact_response`: invoke twice with the same key/hash and assert exact JSON equality and only one derived aggregate/event.
- `test_task3e_derive_commits_once`: monkeypatch `session.commit` and assert one call.
- `test_task3e_derive_rolls_back_partial_copy`: monkeypatch `_copy_item_to_derived()` to raise on its second call; assert no new lineage version, copied item, or `DERIVED` event remains.

- [ ] **Step 2: Run the derive RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3e" `
  -v
```

Expected: FAIL because `derive()` does not exist.

- [ ] **Step 3: Add an exact item-copy helper**

```python
def _copy_item_to_derived(
    self,
    session: Session,
    actor: ActorContext,
    *,
    source: DemandListItem,
    demand_list_id: int,
) -> DemandListItem:
    return self.repository.add_item(
        session,
        actor.tenant_id,
        demand_list_id=demand_list_id,
        spare_part_id=source.spare_part_id,
        original_quantity=source.original_quantity,
        final_quantity=source.final_quantity,
        source_snapshot=deepcopy(
            source.source_snapshot_json
        ),
        spare_part_code_snapshot=(
            source.spare_part_code_snapshot
        ),
        spare_part_name_snapshot=(
            source.spare_part_name_snapshot
        ),
        spare_part_unit_snapshot=(
            source.spare_part_unit_snapshot
        ),
        criticality_level_snapshot=(
            source.criticality_level_snapshot
        ),
        source_calculation_group_id=(
            source.source_calculation_group_id
        ),
        source_group_child_id=(
            source.source_group_child_id
        ),
        source_calculation_id=(
            source.source_calculation_id
        ),
        source_calculation_run_id=(
            source.source_calculation_run_id
        ),
        source_result_id=source.source_result_id,
        reliability_model=source.reliability_model,
        execution_mode=source.execution_mode,
        decision_type=source.decision_type,
        decision_reason=source.decision_reason,
        decision_risk=source.decision_risk,
        requires_admin_confirmation=(
            source.requires_admin_confirmation
        ),
        confirmed_by_admin=(
            source.confirmed_by_admin
        ),
        risk_rule_version=source.risk_rule_version,
        decision_snapshot_json=deepcopy(
            source.decision_snapshot_json
        ),
        interval_snapshot_json=deepcopy(
            source.interval_snapshot_json
        ),
        parameter_snapshot_json=deepcopy(
            source.parameter_snapshot_json
        ),
        warning_snapshot_json=deepcopy(
            source.warning_snapshot_json
        ),
        inventory_snapshot_json=deepcopy(
            source.inventory_snapshot_json
        ),
    )
```

Do not copy source item IDs, timestamps, or version numbers.

- [ ] **Step 4: Implement `derive()`**

Use the Admin/key/hash/replay shell with expected event `DERIVED`. Lock and validate the source row, then:

```python
source_items = self._items(
    session,
    actor,
    source.id,
)
derived = self.repository.create_version(
    session,
    actor.tenant_id,
    {
        "name": source.name,
        "description": source.description,
        "lineage_id": source.lineage_id,
        "derived_from_id": source.id,
        "scenario_version_id": (
            source.scenario_version_id
        ),
        "calculation_group_id": (
            source.calculation_group_id
        ),
        "status": DemandListStatus.DRAFT,
        "is_current": False,
        "created_by_user_id": actor.user_id,
        "created_by_request_id": (
            actor.request_id
        ),
    },
)
for source_item in source_items:
    self._copy_item_to_derived(
        session,
        actor,
        source=source_item,
        demand_list_id=derived.id,
    )

after = {
    "derived_from_id": source.id,
    "lineage_id": source.lineage_id,
    "source_version_number": (
        source.version_number
    ),
    "new_version_number": (
        derived.version_number
    ),
    "copied_item_count": len(source_items),
    "status": DemandListStatus.DRAFT.value,
    "version": derived.version,
}
event = self.repository.append_event(
    session,
    actor.tenant_id,
    demand_list_id=derived.id,
    event_type=DemandListEventType.DERIVED,
    actor_user_id=actor.user_id,
    actor_roles=[actor.role.value],
    request_id=actor.request_id,
    idempotency_key=clean_key,
    request_hash=request_hash,
    before_summary={
        "source_demand_list_id": source.id,
        "source_status": source.status.value,
        "source_is_current": source.is_current,
        "source_version": source.version,
    },
    after_summary=after,
    response_snapshot={"id": derived.id},
)
response = self._response_with_event_snapshot(
    session,
    actor,
    derived.id,
    event,
)
session.commit()
return response
```

The source aggregate must not be mutated.

- [ ] **Step 5: Remove the temporary skip from the Task 3D supersession test**

Delete the `pytest.mark.skip` marker from `test_task3d_new_publish_supersedes_old_current`.

- [ ] **Step 6: Run derive and supersession GREEN gates**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3d or task3e" `
  -v
```

Expected: PASS with no Task 3 skip.

- [ ] **Step 7: Run Task 2 snapshot and replay regressions**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task2h or task2j or task3e" `
  -v
```

Expected: PASS.

Do not commit. Continue to Task 3F.

---

### Task 3F: Void Published Versions Without Restoring History

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes: Task 3D publication and Task 3E lineage history.
- Produces: `void()` and stable `VOIDED` evidence.

- [ ] **Step 1: Write void RED tests**

Add:

```python
def test_task3f_void_current_published_clears_current(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-source",
        submit_key="task3f-submit",
        confirm_key="task3f-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3f-publish",
    )

    voided = service.void(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3f-void",
    )

    assert voided.status.value == "VOIDED"
    assert voided.is_current is False
    assert voided.version == published.version + 1
    assert voided.voided_by_user_id == (
        actor_admin.user_id
    )
    assert voided.voided_by_request_id == (
        actor_admin.request_id
    )
    assert voided.voided_at is not None
    assert len(voided.items) == len(published.items)
    assert voided.events[-1].event_type.value == (
        "VOIDED"
    )


def test_task3f_void_does_not_restore_superseded_version(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandList

    service, confirmed_v1 = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3f-v1-source",
        submit_key="task3f-v1-submit",
        confirm_key="task3f-v1-confirm",
    )
    published_v1 = service.publish(
        session,
        actor_admin,
        confirmed_v1.id,
        expected_version=confirmed_v1.version,
        idempotency_key="task3f-v1-publish",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3f-v2-derive",
    )
    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3f-v2-submit",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3f-v2-confirm",
    )
    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3f-v2-publish",
    )

    service.void(
        session,
        actor_admin,
        published_v2.id,
        expected_version=published_v2.version,
        idempotency_key="task3f-v2-void",
    )

    old = session.get(DemandList, published_v1.id)
    assert old is not None
    assert old.status.value == "PUBLISHED"
    assert old.is_current is False

    current_count = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v1.lineage_id,
            DemandList.status == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .count()
    )
    assert current_count == 0
```

Add these named void tests:

- `test_task3f_void_noncurrent_published_history`: void an already superseded `PUBLISHED` row; assert it becomes `VOIDED`, stays non-current, and does not change the current newer version.
- `test_task3f_contributor_cannot_void`: assert `INSUFFICIENT_MAINTENANCE_ROLE`.
- `test_task3f_void_requires_published_source`: invoke from `CONFIRMED` and assert exact `DEMAND_LIST_INVALID_TRANSITION` details.
- `test_task3f_void_rejects_stale_version`: assert exact `DEMAND_LIST_VERSION_CONFLICT` details.
- `test_task3f_void_cross_tenant_is_not_found`: invoke with tenant B and assert `RESOURCE_NOT_FOUND`.
- `test_task3f_void_commits_once`: monkeypatch `session.commit` and assert one call.
- `test_task3f_void_event_summaries_are_complete`: assert before/after lineage, version number, status, current flag, and aggregate version.
- `test_task3f_void_replays_exact_response`: invoke twice with the same key/hash; assert exact JSON equality and one `VOIDED` event.
- `test_task3f_void_rolls_back_row_and_event`: monkeypatch `_response_with_event_snapshot()` to raise; assert status/current/version/void metadata remain unchanged and no `VOIDED` event exists.

- [ ] **Step 2: Run the void RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3f" `
  -v
```

Expected: FAIL because `void()` does not exist.

- [ ] **Step 3: Implement `void()`**

Use the Admin/key/hash/replay shell with expected event `VOIDED`:

```python
before = {
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "is_current": demand_list.is_current,
    "version": demand_list.version,
}
now = datetime.now(UTC)
demand_list.status = DemandListStatus.VOIDED
demand_list.is_current = False
demand_list.voided_by_user_id = actor.user_id
demand_list.voided_by_request_id = (
    actor.request_id
)
demand_list.voided_at = now
demand_list.version += 1
session.flush()

after = {
    "lineage_id": demand_list.lineage_id,
    "version_number": demand_list.version_number,
    "status": demand_list.status.value,
    "is_current": demand_list.is_current,
    "version": demand_list.version,
}
```

Append `VOIDED`, store the response snapshot, commit once, and preserve all items/events. Do not query or reactivate an older version.

- [ ] **Step 4: Run the void GREEN gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3f" `
  -v
```

Expected: PASS.

- [ ] **Step 5: Run all lifecycle behavior tests so far**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3a or task3b or task3c or task3d or task3e or task3f" `
  -v
```

Expected: PASS.

Do not commit. Continue to Task 3G.

---

### Task 3G: Harden Exact Replay and Concurrent Receipt Recovery for Every Action

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Consumes: all five lifecycle methods and Task 2J race pattern.
- Produces:
  - one shared race-recovery helper;
  - consistent sequential and concurrent idempotency behavior for every action.

- [ ] **Step 1: Add a lifecycle action-case helper**

Create a test helper returning a callable and valid action input for each event type:

```python
def _task3g_action_cases(
    session,
    actor_contributor,
    actor_admin,
):
    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3g-submit-source",
    )
    pending = service.submit(
        session,
        actor_contributor,
        created.id,
        expected_version=created.version,
        idempotency_key="task3g-seed-submit",
    )
    confirmed = service.confirm(
        session,
        actor_admin,
        pending.id,
        expected_version=pending.version,
        confirmation_note="Seed confirmation",
        idempotency_key="task3g-seed-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="task3g-seed-publish",
    )
    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key="task3g-seed-derive",
    )

    return {
        "submit": {
            "actor": actor_contributor,
            "demand_list_id": derived.id,
            "expected_version": derived.version,
            "extra": {},
            "event_type": "SUBMITTED",
        },
        "derive": {
            "actor": actor_admin,
            "demand_list_id": published.id,
            "expected_version": published.version,
            "extra": {},
            "event_type": "DERIVED",
        },
    }
```

Do not use one shared database state for actions that mutate the same row. Build a fresh case per parameterized invocation through a factory fixture or helper call.

Create separate builders for `confirm`, `publish`, and `void` so each test starts from the exact required source status.

- [ ] **Step 2: Add sequential replay tests for all five actions**

Parameterize action name and event type. For each action:

1. call it once;
2. call it again with the same normalized input and key;
3. assert exact `model_dump(mode="json")` equality;
4. assert only one event with that idempotency key;
5. mutate a nested warning list in the replay;
6. assert the stored receipt snapshot was not mutated.

- [ ] **Step 3: Add different-request conflict tests**

Use the same idempotency key with changed `expected_version`; for `confirm`, also add a separate case changing only the trimmed confirmation note. Assert:

```python
assert captured.value.code == (
    "IDEMPOTENCY_KEY_REUSED"
)
assert captured.value.details == {
    "conflict_object": "demand_list",
    "retryable": False,
}
```

- [ ] **Step 4: Add receipt-integrity tests for every action**

For each lifecycle receipt, mutate one persisted event at a time:

- set a different event type;
- set `response_snapshot_json = None`;
- set `response_snapshot_json = {"id": demand_list_id}`.

Reinvoke the action and assert `IDEMPOTENT_RESPONSE_UNAVAILABLE`.

- [ ] **Step 5: Add same-key unique-conflict simulations**

Adapt `_task2j_install_receipt_race()` to accept the expected lifecycle event type and a supplied response snapshot. For every action:

- first receipt lookup returns `None`;
- `append_event()` raises `IntegrityError`;
- rollback occurs;
- second lookup returns a winner receipt;
- same request hash returns the exact winner snapshot;
- nested JSON is deeply isolated.

Add a rollback-order assertion by monkeypatching `session.rollback` and recording call order before the second receipt lookup.

- [ ] **Step 6: Add different-hash and no-winner race tests**

For each action:

- winner receipt has a different hash: assert `IDEMPOTENCY_KEY_REUSED`;
- second receipt lookup returns `None`: assert the original `IntegrityError` object is re-raised.

- [ ] **Step 7: Run the Task 3G RED gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3g" `
  -v
```

Expected: some tests may already pass through per-method code; race-order and shared-helper assertions must fail until the shell is consolidated.

- [ ] **Step 8: Add one shared recovery helper**

Use the original `IntegrityError` explicitly so the helper can re-raise the same failure when no winning receipt exists:

```python
def _recover_lifecycle_receipt(
    self,
    session: Session,
    actor: ActorContext,
    *,
    idempotency_key: str,
    request_hash: str,
    expected_event_type: DemandListEventType,
    original_error: IntegrityError,
) -> DemandListRead:
    winner = (
        self.repository
        .get_event_by_idempotency_key(
            session,
            actor.tenant_id,
            idempotency_key,
        )
    )
    if winner is None:
        raise original_error
    return self._idempotent_read_model(
        winner,
        request_hash,
        expected_event_type=(
            expected_event_type
        ),
    )
```

Use this final explicit-exception version.

- [ ] **Step 9: Refactor all six mutation race handlers**

Refactor `create_from_group`, `submit`, `confirm`, `publish`, `derive`, and `void`:

```python
except IntegrityError as exc:
    session.rollback()
    return self._recover_lifecycle_receipt(
        session,
        actor,
        idempotency_key=clean_key,
        request_hash=request_hash,
        expected_event_type=(
            DemandListEventType.SUBMITTED
        ),
        original_error=exc,
    )
```

Use the matching event type in each method. Preserve `CREATED` for `create_from_group()`.

- [ ] **Step 10: Run Task 2J and Task 3G GREEN gates**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task2j or task3g" `
  -v
```

Expected: PASS.

- [ ] **Step 11: Run all demand-list service tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -v
```

Expected: PASS.

Do not commit. Continue to Task 3H.

---

### Task 3H: Prove the Complete Lifecycle and Cross-Module Domain Contract

**Files:**
- Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`
- Verify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Verify: `extensions/maintenance-api/app/schemas/demand_list.py`

**Interfaces:**
- Consumes: all Task 3 methods.
- Produces: one service-level lifecycle proof and final review evidence.

- [ ] **Step 1: Add the complete invalid-transition matrix**

Add all 20 unsupported action/source combinations:

```python
@pytest.mark.parametrize(
    ("action", "source_status", "expected_status"),
    [
        ("submit", "PENDING_CONFIRMATION", "DRAFT"),
        ("submit", "CONFIRMED", "DRAFT"),
        ("submit", "PUBLISHED", "DRAFT"),
        ("submit", "VOIDED", "DRAFT"),
        (
            "confirm",
            "DRAFT",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "CONFIRMED",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "PUBLISHED",
            "PENDING_CONFIRMATION",
        ),
        (
            "confirm",
            "VOIDED",
            "PENDING_CONFIRMATION",
        ),
        ("publish", "DRAFT", "CONFIRMED"),
        (
            "publish",
            "PENDING_CONFIRMATION",
            "CONFIRMED",
        ),
        ("publish", "PUBLISHED", "CONFIRMED"),
        ("publish", "VOIDED", "CONFIRMED"),
        ("derive", "DRAFT", "PUBLISHED"),
        (
            "derive",
            "PENDING_CONFIRMATION",
            "PUBLISHED",
        ),
        ("derive", "CONFIRMED", "PUBLISHED"),
        ("derive", "VOIDED", "PUBLISHED"),
        ("void", "DRAFT", "PUBLISHED"),
        (
            "void",
            "PENDING_CONFIRMATION",
            "PUBLISHED",
        ),
        ("void", "CONFIRMED", "PUBLISHED"),
        ("void", "VOIDED", "PUBLISHED"),
    ],
)
def test_task3h_invalid_transition_matrix(
    session,
    actor_contributor,
    actor_admin,
    action,
    source_status,
    expected_status,
) -> None:
    from app.core.exceptions import ConflictError
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key=(
            f"task3h-matrix-source-"
            f"{action}-{source_status}"
        ),
    )
    row = _task3_persisted_list(
        session,
        created.id,
    )
    row.status = DemandListStatus(source_status)
    row.is_current = (
        row.status is DemandListStatus.PUBLISHED
    )
    session.commit()

    kwargs = {
        "expected_version": created.version,
        "idempotency_key": (
            f"task3h-matrix-command-"
            f"{action}-{source_status}"
        ),
    }
    if action == "confirm":
        kwargs["confirmation_note"] = (
            "Matrix confirmation"
        )

    with pytest.raises(ConflictError) as captured:
        getattr(service, action)(
            session,
            actor_admin,
            created.id,
            **kwargs,
        )

    assert captured.value.code == (
        "DEMAND_LIST_INVALID_TRANSITION"
    )
    assert captured.value.details == {
        "action": action,
        "expected_status": expected_status,
        "actual_status": source_status,
        "conflict_object": "demand_list",
        "retryable": False,
    }
```

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3h_invalid_transition_matrix" `
  -v
```

Expected: PASS only when every public lifecycle method uses the shared exact-status validator.

- [ ] **Step 2: Add the complete service lifecycle test**

```python
def test_task3h_complete_lifecycle_preserves_lineage_and_history(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandList
    from app.models.enums import DemandListStatus

    service, created = _task3_create_draft(
        session,
        actor_contributor,
        key="task3h-create",
    )
    high = next(
        item
        for item in created.items
        if item.criticality_level_snapshot == "HIGH"
    )
    updated = service.update_item(
        session,
        actor_contributor,
        created.id,
        high.id,
        expected_version=created.version,
        final_quantity=Decimal("90.000000"),
        adjustment_reason="Lifecycle risk change",
    )
    pending_v1 = service.submit(
        session,
        actor_contributor,
        updated.id,
        expected_version=updated.version,
        idempotency_key="task3h-submit-v1",
    )
    confirmed_v1 = service.confirm(
        session,
        actor_admin,
        pending_v1.id,
        expected_version=pending_v1.version,
        confirmation_note="Approve version 1",
        idempotency_key="task3h-confirm-v1",
    )
    published_v1 = service.publish(
        session,
        actor_admin,
        confirmed_v1.id,
        expected_version=confirmed_v1.version,
        idempotency_key="task3h-publish-v1",
    )
    derived_v2 = service.derive(
        session,
        actor_admin,
        published_v1.id,
        expected_version=published_v1.version,
        idempotency_key="task3h-derive-v2",
    )

    source_v1_before_v2_publish = service.get(
        session,
        actor_admin,
        published_v1.id,
    )
    assert source_v1_before_v2_publish.is_current is True
    assert derived_v2.status.value == "DRAFT"
    assert derived_v2.is_current is False

    pending_v2 = service.submit(
        session,
        actor_contributor,
        derived_v2.id,
        expected_version=derived_v2.version,
        idempotency_key="task3h-submit-v2",
    )
    confirmed_v2 = service.confirm(
        session,
        actor_admin,
        pending_v2.id,
        expected_version=pending_v2.version,
        confirmation_note="Approve version 2",
        idempotency_key="task3h-confirm-v2",
    )
    published_v2 = service.publish(
        session,
        actor_admin,
        confirmed_v2.id,
        expected_version=confirmed_v2.version,
        idempotency_key="task3h-publish-v2",
    )

    reloaded_v1 = service.get(
        session,
        actor_admin,
        published_v1.id,
    )
    assert reloaded_v1.status.value == "PUBLISHED"
    assert reloaded_v1.is_current is False
    assert reloaded_v1.superseded_by_id == (
        published_v2.id
    )
    assert published_v2.is_current is True
    assert published_v2.version_number == 2

    voided_v2 = service.void(
        session,
        actor_admin,
        published_v2.id,
        expected_version=published_v2.version,
        idempotency_key="task3h-void-v2",
    )
    assert voided_v2.status.value == "VOIDED"
    assert voided_v2.is_current is False

    current_count = (
        session.query(DemandList)
        .filter(
            DemandList.tenant_id
            == actor_contributor.tenant_id,
            DemandList.lineage_id
            == published_v1.lineage_id,
            DemandList.status == DemandListStatus.PUBLISHED,
            DemandList.is_current.is_(True),
        )
        .count()
    )
    assert current_count == 0

    assert [
        event.event_type.value
        for event in voided_v2.events
    ] == [
        "DERIVED",
        "SUBMITTED",
        "CONFIRMED",
        "PUBLISHED",
        "VOIDED",
    ]
```

Extend this test with assertions that:

- v1 item snapshots remain unchanged after mutating a v2 returned read model;
- all lifecycle event actor IDs and request IDs match the invoking actor;
- v1 and v2 share lineage but have distinct IDs;
- v1 version number is 1 and v2 version number is 2;
- high-risk v1 is confirmed;
- v2 aggregate still passes through a distinct `CONFIRMED` state even when copied item confirmation flags were already true;
- all request keys are unique and all response snapshots validate through `DemandListRead`.

- [ ] **Step 3: Add a downstream eligibility-contract test**

Without invoking external modules, assert the domain states that future modules consume:

```python
def test_task3h_operational_eligibility_is_only_current_published(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="task3h-eligibility-source",
        submit_key="task3h-eligibility-submit",
        confirm_key="task3h-eligibility-confirm",
    )
    published = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=(
            "task3h-eligibility-publish"
        ),
    )
    derived = service.derive(
        session,
        actor_admin,
        published.id,
        expected_version=published.version,
        idempotency_key=(
            "task3h-eligibility-derive"
        ),
    )

    assert (
        published.status.value == "PUBLISHED"
        and published.is_current
    )
    assert not (
        derived.status.value == "PUBLISHED"
        and derived.is_current
    )
```

This test documents the integration contract; it must not call inventory, procurement, allocation, reporting, or notification code.

- [ ] **Step 4: Run the Task 3H RED/GREEN gate**

Run before adding the final assertions to observe any missing lifecycle evidence, then implement only service/test corrections within the approved three files.

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "task3h" `
  -v
```

Expected final state: PASS.

- [ ] **Step 5: Run the complete focused service gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -v
```

Expected: PASS with no skipped Task 3 tests.

- [ ] **Step 6: Run the approved-domain gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  tests/services/test_demand_decision_policy.py `
  tests/services/test_calculation_group_service.py `
  tests/repositories/test_demand_list_repository.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  tests/migrations/test_demand_list_migration.py `
  tests/security/test_api_rbac.py `
  -v
```

Expected: PASS. Record the actual passed count and warnings in the review evidence.

- [ ] **Step 7: Run the full maintenance-api gate**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: PASS with no new unexpected deselections. Record the actual passed, deselected, warning, and duration values.

- [ ] **Step 8: Run compile, Ruff, and whitespace gates**

```powershell
& .\.venv\Scripts\python.exe -m compileall -q app tests

& .\.venv\Scripts\python.exe -m ruff check app tests

git -c core.safecrlf=false diff --check
```

Expected: all commands exit 0.

- [ ] **Step 9: Verify the exact uncommitted file scope**

```powershell
git status --short
git diff --name-only
git diff --cached --name-only
```

Required unstaged scope:

```text
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
```

Required staged scope: empty.

Any other modified, untracked, or staged path is a blocker.

- [ ] **Step 10: Create final review evidence without committing**

Capture:

```powershell
git diff --stat
git diff -- `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git status -sb
git log -5 --oneline --decorate
```

Preserve the focused, approved-domain, full-suite, compile, Ruff, diff, status, and patch evidence for final review.

- [ ] **Step 11: Stop for user approval**

Do not stage, commit, push, merge, reset, stash, or rewrite history. Report:

- exact changed-file scope;
- focused service count;
- approved-domain count;
- full-suite count;
- warning summary;
- compile/Ruff/diff status;
- known non-blocking follow-ups:
  - repository equal-timestamp page tie-break;
  - distinct-key concurrent derive retry/lineage locking;
  - API/frontend/outbox/downstream integrations.

---

## Final Commit Gate After Explicit Approval

Only after final code review approval:

```powershell
git add `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py

git diff --cached --name-only
git diff --cached --check
git commit -m "feat: enforce demand list lifecycle"
```

The staged file list must contain exactly the three approved implementation files.

After the commit, rerun:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -v

& .\.venv\Scripts\python.exe -m pytest tests -q

& .\.venv\Scripts\python.exe -m compileall -q app tests
& .\.venv\Scripts\python.exe -m ruff check app tests
git -c core.safecrlf=false diff --check
git status -sb
```

Expected:

- focused lifecycle service tests PASS;
- full maintenance-api suite PASS;
- compile and Ruff PASS;
- working tree clean;
- local branch ahead of origin by the approved plan and feature commits;
- push not performed unless explicitly requested.

---

## Explicitly Deferred Work

The implementation must not silently include:

1. repository SQL tie-break for equal `created_at` pagination;
2. automatic retry for distinct-key concurrent derivations;
3. lineage advisory locks or repository changes;
4. lifecycle API routes and route-level RBAC;
5. typed frontend client, store, action resolver, or detail page;
6. inventory reservation, procurement, allocation, or reports;
7. notification delivery;
8. reliable external event delivery or outbox infrastructure;
9. edits to `.superpowers/sdd/progress.md`;
10. edits to the approved Task 3 design document.

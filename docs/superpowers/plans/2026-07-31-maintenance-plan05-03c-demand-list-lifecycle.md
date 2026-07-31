# Plan 05-3C Demand List Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert complete calculation-group decisions into traceable demand-list drafts, enforce the five-state lifecycle with admin confirmation and publication, preserve immutable published versions and lineage, and verify the complete Plan 05-3 vertical slice.

**Architecture:** Add `DemandList` and `DemandListItem` as a versioned aggregate sourced from immutable calculation results and audited decisions. Add append-only lifecycle events that also retain idempotency receipts. Keep DRAFT edits optimistic and transactional; lock the lineage during publication so one current published version exists. Build a typed Vue detail flow whose actions are derived from server status and explicit permissions.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, pytest, Ruff, Vue 3.5, TypeScript 6, Pinia 3, Vue Router 4, TDesign Vue Next, Node `tsx --test`.

## Global Constraints

- Plan 05-3A and 05-3B complete gates must be green before Task 1.
- Follow `docs/superpowers/specs/2026-07-31-maintenance-plan05-03-scenario-calculation-design.md`.
- Lifecycle is exactly `DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED`.
- Published list content is immutable; edits require `derive`.
- A derived version is a new row in the same lineage and starts at `DRAFT`.
- One lineage has at most one current published version.
- Every item copies its source result and decision snapshot; it does not depend on mutable joins for historical meaning.
- Demand quantities and intervals use `Numeric/Decimal` and decimal-string JSON.
- Contributor may create/edit/submit DRAFT lists; admin confirms, publishes, derives, and voids.
- Viewer has read-only access.
- Tenant comes only from internal JWT; request bodies, paths, and headers cannot select a tenant.
- State transitions use `expected_version` and `Idempotency-Key`.
- Append-only lifecycle events retain actor, request, before/after summary, request hash, and replay result.
- No inventory reservation, review engine, allocation, or report generation is executed in this plan.
- Every task is TDD-first and ends with a focused commit.

---

## File Map

### Backend create

```text
extensions/maintenance-api/app/models/demand_list.py
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/app/repositories/demand_list_repository.py
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/app/api/v1/demand/demand_lists.py
extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
extensions/maintenance-api/tests/api/test_demand_lists.py
extensions/maintenance-api/tests/migrations/test_demand_list_migration.py
```

### Backend modify

```text
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/repositories/__init__.py
extensions/maintenance-api/app/api/v1/demand/router.py
extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py
extensions/maintenance-api/README.md
```

### Frontend create

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
frontend/src/views/maintenance/calculations/DemandListDetail.vue
frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

### Frontend modify

```text
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/zh-CN.ts
frontend/src/i18n/locales/en-US.ts
frontend/src/i18n/locales/ko-KR.ts
frontend/src/i18n/locales/ru-RU.ts
```

---

### Task 1: Add Demand List Persistence and Reversible Migration

**Files:**
- Create: `extensions/maintenance-api/app/models/demand_list.py`
- Create: `extensions/maintenance-api/app/schemas/demand_list.py`
- Create: `extensions/maintenance-api/app/repositories/demand_list_repository.py`
- Create: `extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py`
- Modify: `extensions/maintenance-api/app/models/enums.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Modify: `extensions/maintenance-api/app/repositories/__init__.py`
- Test: `extensions/maintenance-api/tests/migrations/test_demand_list_migration.py`
- Test: `extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py`

**Interfaces:**
- Produces: `DemandList`, `DemandListItem`, `DemandListEvent`.
- Produces: tenant-scoped repositories without commit.
- Consumed by: Tasks 2–7.

- [ ] **Step 1: Write failing schema, uniqueness, Decimal, and tenant tests**

```python
def test_demand_list_migration_creates_lineage_and_event_constraints(
    upgraded_connection
):
    inspector = inspect(upgraded_connection)
    assert {
        "demand_lists",
        "demand_list_items",
        "demand_list_events",
    } <= set(inspector.get_table_names())
    assert has_unique(
        inspector,
        "demand_lists",
        ("tenant_id", "lineage_id", "version_number"),
    )
    assert has_unique(
        inspector,
        "demand_list_items",
        ("tenant_id", "demand_list_id", "spare_part_id"),
    )
    assert has_partial_unique_index(
        inspector,
        "demand_lists",
        ("tenant_id", "lineage_id"),
        predicate="status = 'PUBLISHED' AND is_current",
    )


def test_decimal_quantity_round_trips_without_float(
    session, actor_contributor, demand_list_repository
):
    item = demand_list_repository.add_item(
        session,
        actor_contributor.tenant_id,
        demand_list_id=1,
        spare_part_id=10,
        original_quantity=Decimal("123456789.123456"),
        final_quantity=Decimal("123456789.123456"),
        source_snapshot={},
    )
    session.flush()
    assert item.final_quantity == Decimal("123456789.123456")
```

- [ ] **Step 2: Run tests and observe missing persistence**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/migrations/test_demand_list_migration.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -k "demand_list" `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Add exact enums**

```python
class DemandListStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    PUBLISHED = "PUBLISHED"
    VOIDED = "VOIDED"


class DemandListEventType(StrEnum):
    CREATED = "CREATED"
    ITEM_UPDATED = "ITEM_UPDATED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    PUBLISHED = "PUBLISHED"
    DERIVED = "DERIVED"
    VOIDED = "VOIDED"
```

- [ ] **Step 4: Add models and indexes**

`DemandList` includes:

```text
lineage_id UUID string
version_number integer
derived_from_id
scenario_version_id
calculation_group_id
status
is_current
superseded_by_id
superseded_at
version
submitted/confirmed/published/voided actor and time
```

`DemandListItem` includes identity snapshot, source group/child/calculation/run, reliability model, execution mode, original/final Decimal quantities, decision reason/risk, interval, warning, parameter, and inventory snapshots.

`DemandListEvent` includes list ID, event type, actor roles, request ID, optional idempotency key, request hash, before/after summary, response snapshot, and time. Add a unique tenant/idempotency-key index for non-null keys. Add a partial unique index on `(tenant_id, lineage_id)` where `status = 'PUBLISHED' AND is_current` so the database, not only the service lock, enforces one current published version. Use dialect predicates supported by both PostgreSQL and SQLite migration tests.

- [ ] **Step 5: Implement repository methods**

Required methods:

```python
DemandListRepository.get
DemandListRepository.get_for_update
DemandListRepository.list_page
DemandListRepository.current_published_for_update
DemandListRepository.create_version
DemandListRepository.add_item
DemandListRepository.append_event
DemandListRepository.get_event_by_idempotency_key
DemandListItemRepository.get_for_update
DemandListItemRepository.list_for_demand_list
```

Every query applies explicit tenant filtering.

- [ ] **Step 6: Implement migration**

```python
revision = "20260731_07"
down_revision = "20260731_06"
```

Downgrade order:

```text
demand_list_events
demand_list_items
demand_lists
```

- [ ] **Step 7: Run migration cycle, repository tests, and Ruff**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/migrations/test_demand_list_migration.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -k "demand_list" `
  -v
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 8: Commit persistence**

```powershell
git add `
  extensions/maintenance-api/app/models/demand_list.py `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/app/repositories/demand_list_repository.py `
  extensions/maintenance-api/app/models/enums.py `
  extensions/maintenance-api/app/models/__init__.py `
  extensions/maintenance-api/app/repositories/__init__.py `
  extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py `
  extensions/maintenance-api/tests/migrations/test_demand_list_migration.py `
  extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py
git commit -m "feat: add versioned demand list persistence"
```

---

### Task 2: Generate a Complete Demand List Draft

**Files:**
- Create: `extensions/maintenance-api/app/services/demand_list_service.py`
- Modify: `extensions/maintenance-api/app/schemas/demand_list.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Produces: `DemandListService.create_from_group/get/list/update_item`.
- Consumes: terminal calculation group, successful current children, union comparison, and saved decisions.
- Consumed by: Tasks 3–7.

- [ ] **Step 1: Write failing generation precondition and snapshot tests**

```python
def test_create_draft_copies_complete_source_snapshot(
    session, actor_contributor, decided_completed_group
):
    demand_list = DemandListService().create_from_group(
        session,
        actor_contributor,
        group_id=decided_completed_group.id,
        name="Readiness demand",
        idempotency_key="demand-list-create-1",
    )
    assert demand_list.status.value == "DRAFT"
    assert len(demand_list.items) == decided_completed_group.comparison_item_count
    item = demand_list.items[0]
    assert item.source_calculation_id
    assert item.reliability_model
    assert item.execution_mode
    assert item.final_quantity == item.decision.final_quantity


def test_create_rejects_missing_item_decision(
    session, actor_contributor, group_with_missing_decision
):
    with pytest.raises(ConflictError) as exc:
        DemandListService().create_from_group(
            session,
            actor_contributor,
            group_id=group_with_missing_decision.id,
            name="Incomplete demand",
            idempotency_key="missing-decision",
        )
    assert exc.value.code == "DEMAND_LIST_DECISIONS_INCOMPLETE"
```

- [ ] **Step 2: Run tests and observe missing service**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "create or decision or snapshot" `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Define request/read schemas with decimal strings**

```python
class DemandListCreateRequest(BaseModel):
    calculation_group_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class DemandListItemUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    final_quantity: Decimal = Field(ge=0)
    adjustment_reason: str = Field(min_length=1, max_length=1000)
```

Use Pydantic serializers that emit Decimal values as strings.

- [ ] **Step 4: Implement authoritative generation preconditions**

Before inserting any list row:

1. lock and tenant-load the group;
2. require terminal group status;
3. require at least one successful current child;
4. build the successful-result union;
5. require one current saved decision per union item;
6. verify each decision references a successful current child containing that item;
7. reject structural validation errors.

- [ ] **Step 5: Copy immutable item source snapshots**

Copy code/name/criticality, selected child, calculation/run IDs, reliability model, execution mode, original/final quantity, all quantiles, interval, risk, decision reason, warnings, parameters, and inventory summary. Do not serialize ORM objects into JSON.

- [ ] **Step 6: Implement idempotent create and optimistic DRAFT item update**

Create event `CREATED` stores request hash and response snapshot. Same key/hash returns the original list; different hash returns `IDEMPOTENCY_KEY_REUSED`.

`update_item()` locks list and item, requires `DRAFT`, checks list `expected_version`, reruns decision risk for the new quantity, increments list/item versions, appends `ITEM_UPDATED`, and commits once.

- [ ] **Step 7: Run service, Decimal, tenant, and Ruff tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  tests/services/test_calculation_group_service.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 8: Commit draft generation**

```powershell
git add `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git commit -m "feat: generate demand list drafts"
```

---

### Task 3: Enforce Lifecycle, Idempotency, and Lineage

**Files:**
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Modify: `extensions/maintenance-api/app/schemas/demand_list.py`
- Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

**Interfaces:**
- Produces: `submit`, `confirm`, `publish`, `derive`, `void`.
- Enforces: exact transitions, admin gates, immutable publication, one current published version.
- Consumed by: Tasks 4–7.

- [ ] **Step 1: Write a failing transition-matrix test**

```python
@pytest.mark.parametrize(
    ("source", "action", "expected"),
    [
        ("DRAFT", "submit", "PENDING_CONFIRMATION"),
        ("PENDING_CONFIRMATION", "confirm", "CONFIRMED"),
        ("CONFIRMED", "publish", "PUBLISHED"),
        ("PUBLISHED", "void", "VOIDED"),
    ],
)
def test_valid_lifecycle_transitions(source, action, expected, lifecycle_fixture):
    row = lifecycle_fixture(status=source)
    result = getattr(DemandListService(), action)(
        lifecycle_fixture.session,
        lifecycle_fixture.actor_for(action),
        row.id,
        expected_version=row.version,
        idempotency_key=f"{row.id}-{action}",
    )
    assert result.status.value == expected
```

- [ ] **Step 2: Write failing immutability, lineage, and role tests**

```python
def test_published_items_cannot_be_modified(
    session, actor_admin, published_demand_list
):
    with pytest.raises(ConflictError) as exc:
        DemandListService().update_item(
            session,
            actor_admin,
            published_demand_list.id,
            published_demand_list.items[0].id,
            expected_version=published_demand_list.version,
            final_quantity=Decimal("1"),
            adjustment_reason="forbidden",
        )
    assert exc.value.code == "PUBLISHED_DEMAND_LIST_IMMUTABLE"


def test_new_publish_supersedes_previous_current_version(
    session, actor_admin, confirmed_derived_list, current_published_list
):
    result = DemandListService().publish(
        session,
        actor_admin,
        confirmed_derived_list.id,
        expected_version=confirmed_derived_list.version,
        idempotency_key="publish-v2",
    )
    session.refresh(current_published_list)
    assert result.is_current is True
    assert current_published_list.is_current is False
    assert current_published_list.superseded_by_id == result.id
```

- [ ] **Step 3: Run lifecycle tests and observe missing transitions**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -k "lifecycle or published or lineage or role or idempotency" `
  -v
```

Expected: FAIL.

- [ ] **Step 4: Implement one transition helper**

```python
def _transition(
    self,
    session,
    actor,
    demand_list_id,
    *,
    expected_status,
    target_status,
    expected_version,
    idempotency_key,
    request_payload,
):
    replay = self._idempotent_replay(
        session, actor, idempotency_key, request_payload
    )
    if replay:
        return replay
    row = self.repository.get_for_update(
        session, actor.tenant_id, demand_list_id
    )
    self._require_version(row, expected_version)
    self._require_status(row, expected_status)
    self._apply_transition_actor_and_time(row, actor, target_status)
    self.repository.append_event(...)
    session.commit()
    session.refresh(row)
    return row
```

Use `require_role(actor, MaintenanceRole.ADMIN)` inside confirm, publish, derive, and void service methods so non-HTTP callers cannot bypass RBAC.

- [ ] **Step 5: Implement confirmation checks**

`submit` recomputes unresolved/high-risk item counts. `confirm` requires all high-risk items to have explicit admin confirmation metadata and a non-empty confirmation note. No shortcut moves a DRAFT directly to CONFIRMED.

- [ ] **Step 6: Implement atomic publication**

Lock the list and current published row in the same lineage. Revalidate items and status. Set previous current row `is_current = false`, `superseded_by_id`, and `superseded_at`; set new row `is_current = true` and publication actor/time; append both before/after summaries; commit once.

- [ ] **Step 7: Implement derive and void**

`derive` accepts only PUBLISHED source, copies all items into a new DRAFT with `version_number + 1`, `derived_from_id`, same lineage, and `is_current = false`. Original remains PUBLISHED and current until the derived version is later published.

`void` accepts only PUBLISHED and clears `is_current` if the voided list was current. It never deletes history.

- [ ] **Step 8: Run lifecycle, concurrency, permission, and Ruff tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  tests/security/test_api_rbac.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 9: Commit lifecycle**

```powershell
git add `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git commit -m "feat: enforce demand list lifecycle"
```

---

### Task 4: Expose Tenant-Safe Demand List APIs

**Files:**
- Create: `extensions/maintenance-api/app/api/v1/demand/demand_lists.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/router.py`
- Create: `extensions/maintenance-api/tests/api/test_demand_lists.py`

**Interfaces:**
- Produces: create/list/detail/item-update and five lifecycle action routes.
- Consumed by: Tasks 5–7.

- [ ] **Step 1: Write failing exact-route, RBAC, and error-code tests**

```python
def test_contributor_can_create_edit_and_submit(
    contributor_client, decided_completed_group
):
    created = contributor_client.post(
        "/api/v1/demand/demand-lists",
        headers={"Idempotency-Key": "create-list-api"},
        json={
            "calculation_group_id": decided_completed_group.id,
            "name": "Demand list",
        },
    )
    assert created.status_code == 201
    list_id = created.json()["data"]["id"]
    submitted = contributor_client.post(
        f"/api/v1/demand/demand-lists/{list_id}/submit",
        headers={"Idempotency-Key": "submit-list-api"},
        json={"expected_version": created.json()["data"]["version"]},
    )
    assert submitted.json()["data"]["status"] == "PENDING_CONFIRMATION"


def test_contributor_cannot_confirm_or_publish(
    contributor_client, pending_demand_list
):
    response = contributor_client.post(
        f"/api/v1/demand/demand-lists/{pending_demand_list.id}/confirm",
        headers={"Idempotency-Key": "forbidden-confirm"},
        json={"expected_version": pending_demand_list.version, "note": "approve"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests and observe missing router**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Implement viewer/contributor/admin dependencies**

Routes:

```text
POST /demand-lists                         contributor
GET  /demand-lists                         viewer
GET  /demand-lists/{list_id}               viewer
PUT  /demand-lists/{list_id}/items/{id}    contributor
POST /demand-lists/{list_id}/submit        contributor
POST /demand-lists/{list_id}/confirm       admin
POST /demand-lists/{list_id}/publish       admin
POST /demand-lists/{list_id}/derive        admin
POST /demand-lists/{list_id}/void          admin
```

All lifecycle POSTs require `Idempotency-Key`. Update and transition bodies include `expected_version`.

- [ ] **Step 4: Return stable envelopes and decimal strings**

Return `MaintenanceSuccessResponse` with `meta.version`. Map service conflicts to stable codes without parsing exception text in the client.

- [ ] **Step 5: Run API, service, tenant, RBAC, and Ruff tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/api/test_demand_lists.py `
  tests/services/test_demand_list_service.py `
  tests/security/test_api_rbac.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 6: Commit APIs**

```powershell
git add `
  extensions/maintenance-api/app/api/v1/demand/demand_lists.py `
  extensions/maintenance-api/app/api/v1/demand/router.py `
  extensions/maintenance-api/tests/api/test_demand_lists.py
git commit -m "feat: expose demand list lifecycle api"
```

---

### Task 5: Add Typed Demand List Client, Permissions, and Store

**Files:**
- Create: `frontend/src/api/maintenance/demand-lists.ts`
- Create: `frontend/src/api/maintenance/__tests__/demand-lists.test.ts`
- Create: `frontend/src/stores/maintenance/demandList.ts`
- Create: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`
- Create: `frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts`
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`

**Interfaces:**
- Consumes: Task 4 REST API.
- Produces: `demandListApi`, `useDemandListStore`, `demandListActions`.
- Consumed by: Task 6.

- [ ] **Step 1: Write failing typed client tests**

```ts
test('demand list client sends versions and idempotency headers', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))
  await api.submit(12, 3, 'submit-key')
  await api.publish(12, 4, 'publish-key')
  assert.equal(calls[0].path, '/v1/demand/demand-lists/12/submit')
  assert.deepEqual(calls[0].body, { expected_version: 3 })
  assert.equal(calls[0].headers['Idempotency-Key'], 'submit-key')
  assert.equal(JSON.stringify(calls).includes('tenant'), false)
})
```

- [ ] **Step 2: Write failing lifecycle and permission tests**

```ts
test('actions follow exact status and capability matrix', () => {
  assert.deepEqual(
    demandListActions('DRAFT', contributorPermissions),
    ['edit', 'submit'],
  )
  assert.deepEqual(
    demandListActions('PENDING_CONFIRMATION', adminPermissions),
    ['confirm'],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', adminPermissions),
    ['derive', 'void'],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', viewerPermissions),
    [],
  )
})
```

- [ ] **Step 3: Run tests and observe missing modules**

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: FAIL.

- [ ] **Step 4: Add explicit demand-list permissions**

Extend `MaintenancePermissions` with:

```ts
editDemandList: boolean
publishDemandList: boolean
```

Viewer has neither. Contributor has `editDemandList`. Admin has both. Preserve fail-closed auth hierarchy behavior.

- [ ] **Step 5: Implement typed API and pure action resolver**

Keep Decimal quantities as strings. The action resolver accepts only status and permission object; it must not infer raw role names.

- [ ] **Step 6: Implement serialized demand-list store**

Store owns current list, loading/error/busy state, request generation, and actions for load, update item, submit, confirm, publish, derive, and void. All mutations share one request gate. Stale responses cannot overwrite a newer route.

- [ ] **Step 7: Run focused tests and type-check**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 8: Commit client and permissions**

```powershell
git add `
  frontend/src/api/maintenance/demand-lists.ts `
  frontend/src/api/maintenance/__tests__/demand-lists.test.ts `
  frontend/src/stores/maintenance/demandList.ts `
  frontend/src/stores/maintenance/__tests__/demand-list.test.ts `
  frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts `
  frontend/src/stores/maintenance/permission-matrix.ts `
  frontend/src/stores/maintenance/__tests__/permissions.test.ts
git commit -m "feat: add demand list lifecycle client"
```

---

### Task 6: Build Demand List Detail and Lifecycle UI

**Files:**
- Create: `frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue`
- Create: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`
- Create: `frontend/src/views/maintenance/calculations/DemandListDetail.vue`
- Modify: `frontend/src/views/maintenance/calculations/CalculationComparison.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Create: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`
- Modify: locale files under `frontend/src/i18n/locales/`

**Interfaces:**
- Consumes: `useDemandListStore` and explicit demand-list permissions.
- Produces: calculation-to-list generation and complete lifecycle detail.

- [ ] **Step 1: Write failing navigation, read-only, and derive tests**

```ts
test('demand-list route is authenticated and hidden from menu', () => {
  const route = findMaintenanceRoute('maintenanceDemandListDetail')
  assert.equal(route.meta.requiresAuth, true)
  assert.equal(route.meta.requiresInit, true)
  assert.equal(route.meta.hideInMaintenanceMenu, true)
})


test('published item editor is always disabled', () => {
  assert.equal(canEditDemandListItem('PUBLISHED', adminPermissions), false)
  assert.equal(canEditDemandListItem('PUBLISHED', contributorPermissions), false)
})
```

- [ ] **Step 2: Run tests and observe missing view**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Add list generation to comparison**

Enable generation only when the server comparison reports a terminal group, at least one success, complete decisions, and no structural errors. Create with an idempotency key and route to the returned list ID.

- [ ] **Step 4: Implement DemandListDetail**

Display:

```text
version and lineage
source scenario/group
item table
risk and pending confirmations
lifecycle timeline
actor/time audit summary
superseded/current markers
```

DRAFT item edits use decimal-string inputs and require an adjustment reason. Only update the rendered row after the store returns the server version.

- [ ] **Step 5: Implement lifecycle actions**

Render actions from the pure resolver. Require explicit confirmation dialogs for confirm, publish, derive, and void. Derived response routes to the new DRAFT ID; published and voided lists remain readable.

- [ ] **Step 6: Add hidden route and locale keys**

Route:

```text
calculations/demand-lists/:listId
```

Name it `maintenanceDemandListDetail` and set authenticated, initialized, hidden metadata. Add matching locale shapes to all four existing locale files.

- [ ] **Step 7: Run component tests, full frontend tests, type-check, and build**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts
npm run test
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit lifecycle UI**

```powershell
git add `
  frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue `
  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  frontend/src/views/maintenance/calculations/DemandListDetail.vue `
  frontend/src/views/maintenance/calculations/CalculationComparison.vue `
  frontend/src/router/maintenance.ts `
  frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  frontend/src/i18n/locales
git commit -m "feat: add demand list lifecycle ui"
```

---

### Task 7: Verify the Complete Plan 05-3 Vertical Slice

**Files:**
- Modify: `extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py`
- Modify: `extensions/maintenance-api/README.md`
- Test: complete Plan 05-3 gate.

**Interfaces:**
- Produces: verified manual/AI-draft-to-published-demand-list workflow.
- Completes: Plan 05-3.

- [ ] **Step 1: Complete the end-to-end integration test**

The test must execute:

```text
contributor creates or resumes a scenario draft
contributor completes six-step data and materializes DRAFT version
contributor publish receives 403
admin publishes scenario version
contributor requests deterministic recommendation
contributor creates three candidate children
one child fails and two succeed
event retrieval resumes after a saved sequence
retry creates only a new failed attempt
all successful results form a union comparison
contributor saves alternative and manual decisions
contributor creates and submits a demand-list DRAFT
contributor confirm receives 403
admin confirms and publishes version 1
admin derives version 2 and publishes it
version 1 remains readable and is not current
tenant two receives secure not-found responses
viewer receives 403 for every write route
```

- [ ] **Step 2: Add exact assertions for immutable history and audit**

Assert source snapshots remain unchanged after modifying referenced master data, version 1 items cannot be edited, version 2 has the same lineage, only version 2 is current, and lifecycle events contain actor, request ID, request hash, before/after summary, and response snapshot.

- [ ] **Step 3: Update user and operator documentation**

Document:

- manual and AI scenario draft flows;
- contributor DRAFT materialization and admin publication;
- deterministic recommendation semantics;
- calculation-group idempotency, retry, recovery, SSE, and polling fallback;
- comparison decisions and `DEMAND-DECISION-RISK-1`;
- demand-list roles, lifecycle, derivation, supersession, and void behavior;
- exact local commands and troubleshooting.

- [ ] **Step 4: Run full migration and backend gate**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py `
  tests/integration/test_ai_scenario_wizard_handoff.py `
  tests/services/test_model_recommendation_service.py `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/workers/test_calculation_group_recovery.py `
  tests/services/test_demand_list_service.py `
  tests/api/test_demand_lists.py `
  tests/migrations/test_calculation_group_migration.py `
  tests/migrations/test_demand_list_migration.py `
  tests/integration/test_plan05_scenario_calculation.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Expected: all tests pass, Ruff clean, and migration cycle succeeds.

- [ ] **Step 5: Run full frontend and Go regression gate**

```powershell
cd ..\..\frontend
npm run test
npm run type-check
npm run build

cd ..
go test ./internal/maintenanceproxy ./internal/router
git diff --check
git status --short
```

Expected: frontend tests/type-check/build pass, Go proxy tests pass, diff check is clean, and only intentional files remain modified.

- [ ] **Step 6: Capture UX and security evidence**

Capture authenticated evidence for:

- six-step draft restoration;
- autosave success/error/conflict;
- admin scenario publication;
- disabled inapplicable model;
- mixed child outcomes and failed-only retry;
- SSE sequence resume;
- `NO_RESULT` comparison cell;
- alternative/manual decision risk;
- demand-list five-state timeline;
- derived and superseded versions;
- viewer/contributor/admin controls;
- tenant isolation.

- [ ] **Step 7: Commit final Plan 05-3 acceptance**

```powershell
git add `
  extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py `
  extensions/maintenance-api/README.md
git commit -m "test: verify plan05 scenario demand workflow"
```

## Plan 05-3 Completion Evidence

Plan 05-3 is complete only when:

- all 05-3A, 05-3B, and 05-3C focused gates pass;
- the full vertical integration test passes;
- migrations upgrade, downgrade one revision, and re-upgrade;
- Ruff is clean;
- full frontend tests, type-check, and build pass;
- Go maintenance proxy/router regression passes;
- tenant and role acceptance evidence is recorded;
- published scenario and demand-list admin boundaries remain enforced;
- no unresolved high-risk security, state-machine, or data-integrity finding remains.

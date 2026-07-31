# Plan 05-3C Task 1 Demand List Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tenant-scoped, versioned demand-list persistence with immutable source snapshots, exact decimal quantities, append-only lifecycle events, and a reversible Alembic migration.

**Architecture:** Introduce `DemandList`, `DemandListItem`, and `DemandListEvent` as the persistence boundary for Plan 05-3C. Keep Task 1 strictly below the service and API layers: repositories flush but never commit, every query filters by tenant, lifecycle business transitions remain for later tasks, and database constraints enforce version uniqueness and one current published version per lineage.

**Tech Stack:** Python 3.11, SQLAlchemy 2, Alembic, Pydantic 2, pytest, Ruff, SQLite migration verification, PostgreSQL-compatible partial indexes.

## Global Constraints

- Plan 05-3A and Plan 05-3B gates are green before this task starts.
- Follow `docs/superpowers/specs/2026-07-31-maintenance-plan05-03-scenario-calculation-design.md`.
- Lifecycle values are exactly `DRAFT`, `PENDING_CONFIRMATION`, `CONFIRMED`, `PUBLISHED`, and `VOIDED`.
- Published content is immutable; service-level edit, derive, publish, and void behavior is outside Task 1.
- A derived version is a separate row in the same lineage and starts at `DRAFT` in later service work.
- One lineage has at most one current published version.
- Every item stores source and decision snapshots so historical meaning does not depend on mutable joins.
- Demand quantities use `Numeric(20, 6)` and `Decimal`; JSON serialization uses plain decimal strings.
- Tenant identity is always an explicit repository argument and never comes from request-controlled tenant selectors.
- Repositories flush but do not commit.
- No inventory reservation, review engine, allocation, report generation, API route, or frontend work is included.
- Production code is written only after the focused persistence tests fail for the expected missing-feature reason.

---

## File Map

### Create

- `extensions/maintenance-api/app/models/demand_list.py`
- `extensions/maintenance-api/app/schemas/demand_list.py`
- `extensions/maintenance-api/app/repositories/demand_list_repository.py`
- `extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py`
- `extensions/maintenance-api/tests/migrations/test_demand_list_migration.py`

### Modify

- `extensions/maintenance-api/app/models/enums.py`
- `extensions/maintenance-api/app/models/__init__.py`
- `extensions/maintenance-api/app/repositories/__init__.py`
- `extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py`

---

## Persistence Design

### `DemandList`

Mixins: `TenantScopedMixin`, `VersionedMixin`, `TimestampMixin`.

Required fields:

- identity: `id`, `tenant_id`, `name`, `description`;
- lineage: `lineage_id`, `version_number`, `derived_from_id`;
- source: `scenario_version_id`, `calculation_group_id`;
- lifecycle: `status`, `is_current`, `superseded_by_id`, `superseded_at`;
- optimistic version: `version`;
- creator: `created_by_user_id`, `created_by_request_id`;
- transition actors and timestamps for submitted, confirmed, published, and voided states;
- timestamps: `created_at`, `updated_at`.

Constraints:

- unique `(tenant_id, lineage_id, version_number)`;
- check `version_number >= 1`;
- partial unique `(tenant_id, lineage_id)` where `status = 'PUBLISHED' AND is_current`.

`lineage_id` is a canonical UUID string stored as `String(36)`.

### `DemandListItem`

Mixins: `TenantScopedMixin`, `VersionedMixin`, `TimestampMixin`.

Required fields:

- identity: `id`, `tenant_id`, `demand_list_id`, `spare_part_id`;
- copied identity snapshot: code, name, unit, and criticality;
- source IDs: calculation group, group child, calculation, run, and result;
- model identity: reliability model and execution mode;
- quantities: `original_quantity`, `final_quantity` as `Numeric(20, 6)`;
- decision snapshot fields: type, reason, risk, admin-confirmation flags, rule version;
- JSON snapshots: source, decision, interval, parameter, warning, and inventory.

Constraints:

- unique `(tenant_id, demand_list_id, spare_part_id)`;
- check `original_quantity >= 0`;
- check `final_quantity >= 0`.

### `DemandListEvent`

Mixins: `TenantScopedMixin`.

Required fields:

- `id`, `tenant_id`, `demand_list_id`, `event_type`;
- actor user and roles;
- request ID, optional idempotency key, and request hash;
- before summary, after summary, and response snapshot;
- `occurred_at`.

Constraint:

- partial unique `(tenant_id, idempotency_key)` where `idempotency_key IS NOT NULL`.

The event table is append-only audit and idempotency storage. It is not the authoritative current-state table and does not carry an SSE sequence.

---

## Repository Interfaces

### `DemandListRepository`

Produces:

```python
get(session, tenant_id, demand_list_id) -> DemandList | None
get_for_update(session, tenant_id, demand_list_id) -> DemandList | None
list_page(session, tenant_id, *, page=1, page_size=20, status=None, lineage_id=None) -> tuple[list[DemandList], int]
current_published_for_update(session, tenant_id, lineage_id) -> DemandList | None
create_version(session, tenant_id, data) -> DemandList
add_item(session, tenant_id, *, demand_list_id, spare_part_id, original_quantity, final_quantity, source_snapshot, **snapshot_fields) -> DemandListItem
append_event(session, tenant_id, *, demand_list_id, event_type, actor_user_id, actor_roles, request_id, idempotency_key=None, request_hash=None, before_summary=None, after_summary=None, response_snapshot=None) -> DemandListEvent
get_event_by_idempotency_key(session, tenant_id, idempotency_key) -> DemandListEvent | None
```

`create_version` creates UUID lineage/version 1 when no lineage is supplied. For an existing tenant lineage it allocates `max(version_number) + 1`. It performs no lifecycle transition or supersede operation.

### `DemandListItemRepository`

Produces:

```python
get_for_update(session, tenant_id, demand_list_id, item_id) -> DemandListItem | None
list_for_demand_list(session, tenant_id, demand_list_id) -> list[DemandListItem]
```

Every statement includes an explicit tenant predicate and loader criteria.

---

## Schema Boundary

Task 1 creates only the shared decimal-string boundary and a minimal quantity snapshot model. Creation, update, read, transition, and API schemas remain in Task 2 and later tasks.

```python
DecimalString = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: format(value, "f"),
        return_type=str,
        when_used="json",
    ),
]

class DemandListItemQuantitySnapshot(BaseModel):
    original_quantity: DecimalString
    final_quantity: DecimalString
```

JSON must preserve `123456789.123456` as the exact string `"123456789.123456"`, without float conversion or scientific notation.

---

### Task 1: Add RED Persistence Tests

**Files:**
- Create: `extensions/maintenance-api/tests/migrations/test_demand_list_migration.py`
- Modify: `extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py`

**Interfaces:**
- Consumes: current Alembic head `20260731_06`, repository fixtures, and existing demand-domain tenant test helpers.
- Produces: failing specifications for schema shape, reversibility, decimal handling, tenant filtering, version allocation, and transaction ownership.

- [ ] **Step 1: Add migration shape tests**

Assert that `demand_lists`, `demand_list_items`, and `demand_list_events` exist at `20260731_07`; assert lineage-version and item uniqueness; inspect the two partial unique indexes; inspect `Numeric(20, 6)` quantity columns.

- [ ] **Step 2: Add migration round-trip test**

Use an isolated SQLite database and process-only `INTERNAL_JWT_SECRET`; run `20260731_07 -> 20260731_06 -> 20260731_07` and assert the three tables disappear and return in dependency-safe order.

- [ ] **Step 3: Add decimal-string schema test**

Serialize `DemandListItemQuantitySnapshot` with `Decimal("123456789.123456")` and assert exact string JSON values.

- [ ] **Step 4: Add repository signature and tenant tests**

Require `tenant_id` on all demand-list repository methods. Verify tenant A cannot get, lock, list, or load tenant B lists/items/events. Verify equal idempotency keys are isolated by tenant.

- [ ] **Step 5: Add version and precision tests**

Verify a new lineage starts at version 1, the next row in the same tenant lineage is version 2, another tenant can have an independent lineage, and `Numeric(20, 6)` round-trips exactly.

- [ ] **Step 6: Run RED gate**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/migrations/test_demand_list_migration.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -k "demand_list" `
  -v
```

Expected: FAIL because demand-list models, schemas, repositories, and migration do not exist. Syntax, fixture, environment, and path failures are not an acceptable RED result.

---

### Task 2: Implement Minimal Persistence

**Files:**
- Create: `extensions/maintenance-api/app/models/demand_list.py`
- Create: `extensions/maintenance-api/app/schemas/demand_list.py`
- Create: `extensions/maintenance-api/app/repositories/demand_list_repository.py`
- Create: `extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py`
- Modify: `extensions/maintenance-api/app/models/enums.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Modify: `extensions/maintenance-api/app/repositories/__init__.py`

**Interfaces:**
- Produces: `DemandList`, `DemandListItem`, `DemandListEvent`, `DemandListRepository`, `DemandListItemRepository`, `DemandListStatus`, `DemandListEventType`, `DecimalString`, and `DemandListItemQuantitySnapshot`.
- Consumed by: Plan 05-3C Tasks 2–7.

- [ ] **Step 1: Add exact enums**

Add only the five statuses and seven event types approved by the Plan 05-3 design.

- [ ] **Step 2: Add ORM models and relationships**

Use the established model/mixin style. Set cascade only from list to owned items/events; retain restrictive or nulling foreign-key behavior for historical sources and self-references.

- [ ] **Step 3: Add repository methods**

Use explicit tenant predicates, `tenant_loader_criteria`, `populate_existing`, `selectinload` for owned collections, and `with_for_update` for lock methods. Flush but never commit.

- [ ] **Step 4: Add decimal-string schema**

Implement only the shared serializer and minimal quantity snapshot.

- [ ] **Step 5: Export models and repositories**

Update `__all__` without unrelated reordering or refactoring.

- [ ] **Step 6: Add reversible migration**

Set `revision = "20260731_07"` and `down_revision = "20260731_06"`. Create lists, then items, then events. Downgrade events, items, then lists. Supply PostgreSQL and SQLite predicates for both partial unique indexes.

- [ ] **Step 7: Run focused GREEN gate**

Run the focused migration/repository tests until all pass.

- [ ] **Step 8: Run migration cycle and Ruff**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m ruff check app tests
```

Use a disposable SQLite database for migration verification, not the working application database.

- [ ] **Step 9: Verify committed scope**

```powershell
git diff --check
git status --short
git diff --stat
```

Only the Task 1 files in this plan may be included.

- [ ] **Step 10: Commit**

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

## Acceptance Gate

Task 1 is complete only when all of the following are evidenced:

- focused migration and repository tests pass;
- exact decimal database round-trip passes;
- decimal-string JSON serialization passes;
- cross-tenant reads and locks are rejected by query scope;
- version allocation starts at 1 and increments within a tenant lineage;
- both partial unique indexes are present;
- Alembic upgrade/downgrade/upgrade passes on a disposable database;
- Ruff passes over `app` and `tests`;
- `git diff --check` passes;
- the implementation commit contains only the listed files.

Expected implementation commit:

```text
feat: add versioned demand list persistence
```

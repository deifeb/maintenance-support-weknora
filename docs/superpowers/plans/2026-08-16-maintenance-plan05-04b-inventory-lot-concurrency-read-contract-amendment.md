# Plan 05-4B Inventory Lot Concurrency Read Contract Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the smallest tenant-safe public read contract needed for correct `FREEZE` / `UNFREEZE` optimistic concurrency by exposing `lot_version` and `lot_is_frozen` on Inventory balance list/detail responses, without changing Inventory mutation semantics, Task 10.5 list semantics, database schema, or frontend production.

**Architecture:** Keep the existing Task 10.5 parent query pipeline unchanged: tenant → filters → count → validated sort → stable ID tie-break → OFFSET/LIMIT. After the parent balance page/detail is loaded, hydrate current-page lot concurrency state through one bounded repository query and copy `lot_version` / `lot_is_frozen` into `InventoryBalanceRead`. No lot join participates in parent count/sort/page SQL, and no operation-service code changes.

**Tech Stack:** Python 3.11.9, FastAPI, Pydantic v2, SQLAlchemy 2.x ORM, pytest 8.4.2, Ruff, Alembic, SQLite focused/local backend tests plus the existing disposable PostgreSQL 17.11 / psycopg 3.3.4 real-database gate.

## Global Constraints

- Authoritative amendment design:
  `docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment-design.md`
- Authoritative amendment design SHA256:
  `d1cb92f29fea4a200882746927a9af9f53de9c3e671f46fed2696c9abdd4786a`
- Parent Frontend Inventory Gap design SHA256:
  `fdd845a24cd1781e59dec5222d1861d52c86b7dc60f480abec3e06cb0b020b68`
- Frozen backend baseline commit:
  `4cc20eebf85d621d32d95143309b3925e96f349e`
- Branch:
  `codex/maintenance-plan05-4b`
- Existing PR #8 remains Draft.
- This amendment is **additive read-only**.
- Add exactly two public balance fields:
  - `lot_version: int | None`
  - `lot_is_frozen: bool | None`
- Do **not** add:
  - `lot_code`
  - `manufacture_date`
  - `received_date`
  - `expiry_date`
  - `quality_status`
  - `freeze_reason`
  - inventory risk
  - demand gap
  - policy fields
- Do not add a new lot endpoint.
- Do not add a new list filter.
- Do not add a new sort field.
- Do not alter `InventoryOperationService`, operation routes, transaction mutation semantics, confirmation-token semantics, or idempotency semantics.
- Do not alter FEFO.
- Do not modify models.
- Do not create migration/table/index/constraint changes.
- Alembic head must remain `20260803_11`.
- Parent balance pipeline remains:
  `tenant -> filters -> COUNT -> sort -> stable id tie-break -> OFFSET/LIMIT -> hydration -> PageData`.
- Lot hydration must happen **after parent page selection**.
- Lot hydration must be tenant-safe and spare-part-safe.
- A no-lot balance returns:
  - `lot_version = None`
  - `lot_is_frozen = None`
- A non-null `lot_id` whose lot cannot be safely matched returns the two derived fields as `None`; no cross-tenant or mismatched lot state is exposed.
- No raw SQL string interpolation.
- No frontend production/test files in this amendment.
- No tracked test-fixture/conftest changes solely to make PostgreSQL run.
- If a fourth backend production file is required, STOP.
- RED and GREEN are separately approved phases.
- Commit, push, PR update, PR ready, and merge are each separately approved.
- No reset/rebase/stash/clean/force-push.
- If any preflight or gate reveals unexpected repository state, STOP before writing.

---

## File Map

### Production scope — frozen to exactly three existing files

1. `extensions/maintenance-api/app/schemas/inventory_ledger.py`
   - add the two optional public read fields to `InventoryBalanceRead`.

2. `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
   - add a bounded tenant-safe page/detail lot concurrency hydration helper.
   - do **not** change `list_balances()` parent query semantics.

3. `extensions/maintenance-api/app/services/inventory_query_service.py`
   - call the hydration helper after balance page/detail lookup.
   - copy the derived fields into `InventoryBalanceRead`.

If implementation requires any other backend production file, STOP.

### Test scope — frozen to exactly two existing files

1. `extensions/maintenance-api/tests/services/test_inventory_query_service.py`
2. `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`

No new tracked test helper, fixture, conftest, migration test, or integration file is required for the feature slice.

### Documentation generated after implementation evidence

Only after all fresh gates pass and before any feature commit approval, produce an **untracked/local review bundle or user-visible evidence**, not a tracked review document unless separately approved.

---

## Interface Contract

### Schema

`InventoryBalanceRead` gains:

```python
class InventoryBalanceRead(ORMModel):
    # existing fields unchanged

    lot_version: int | None = Field(
        default=None,
        gt=0,
    )
    lot_is_frozen: bool | None = None
```

The two fields are derived read metadata. They are not ORM columns on `InventoryBalance`.

### Repository helper

Add in `inventory_ledger_repository.py`:

```python
LotConcurrencyState = tuple[int, bool]
```

and:

```python
def lot_state_by_balance(
    self,
    session: Session,
    tenant_id: str,
    balances: Sequence[InventoryBalance],
) -> dict[int, LotConcurrencyState]:
    ...
```

Return mapping:

```text
balance_id -> (lot_version, lot_is_frozen)
```

Only a balance with:

```text
balance.lot_id != None
matching InventoryLot.tenant_id == tenant_id
matching InventoryLot.id == balance.lot_id
matching InventoryLot.spare_part_id == balance.spare_part_id
```

gets an entry.

No-lot, cross-tenant, missing, or spare-part-mismatched relations are omitted.

### Service hydration

For list:

```python
balances, total = self.repository.list_balances(...)
lot_states = self.repository.lot_state_by_balance(
    session,
    actor.tenant_id,
    balances,
)
serial_ids = self.repository.serial_item_ids_by_balance(
    session,
    actor.tenant_id,
    balances,
)
```

For each balance:

```python
lot_state = lot_states.get(balance.id)

InventoryBalanceRead.model_validate(balance).model_copy(
    update={
        "serial_item_ids": ...,
        "serial_item_id": ...,
        "lot_version": (
            lot_state[0]
            if lot_state is not None
            else None
        ),
        "lot_is_frozen": (
            lot_state[1]
            if lot_state is not None
            else None
        ),
    }
)
```

Detail uses the same repository helper on `[balance]`.

---

# Pre-Implementation Documentation Gate

This implementation plan itself does **not** authorize repository writes.

After the user approves this plan, the recommended next action is a separately approved docs-only commit containing:

1. the approved amendment DESIGN;
2. this approved IMPLEMENTATION PLAN;
3. the previously approved Frontend Inventory Gap DESIGN;
4. the reconciled frontend plan is **not** included yet because backend amendment implementation must close first.

Suggested amendment plan path:

`docs/superpowers/plans/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment.md`

Suggested docs-only commit message:

```text
docs(maintenance): add inventory lot concurrency amendment
```

The docs commit requires a separate explicit approval.

---

# Task 0: Amendment Execution Preflight

**Files:** none.

**Consumes:**
- approved amendment design SHA;
- approved amendment implementation-plan SHA;
- branch/history state.

**Produces:**
- verified clean execution baseline.

- [ ] **Step 1: Verify worktree and branch**

Run from PowerShell:

```powershell
$repoRoot = "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-plan05-4b"
$git = "C:\Program Files\Git\cmd\git.exe"

& $git -C $repoRoot rev-parse --is-inside-work-tree
& $git -C $repoRoot branch --show-current
& $git -C $repoRoot rev-parse HEAD
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --cached --name-only
```

Expected:

```text
true
codex/maintenance-plan05-4b
```

HEAD may be the separately approved amendment docs commit; it must have
`4cc20eebf85d621d32d95143309b3925e96f349e` as an ancestor.

Working tree must be clean and staged area empty.

Any unrelated change → STOP.

- [ ] **Step 2: Verify frozen backend baseline is an ancestor**

```powershell
& $git -C $repoRoot merge-base --is-ancestor `
  4cc20eebf85d621d32d95143309b3925e96f349e `
  HEAD

if ($LASTEXITCODE -ne 0) {
    throw "Task 10.5 frozen backend baseline is not an ancestor."
}
```

Expected: exit 0.

- [ ] **Step 3: Verify amendment design SHA**

```powershell
$design = Join-Path $repoRoot `
  "docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment-design.md"

$actual = (
    Get-FileHash -LiteralPath $design -Algorithm SHA256
).Hash.ToLowerInvariant()

$expected = "d1cb92f29fea4a200882746927a9af9f53de9c3e671f46fed2696c9abdd4786a"

if ($actual -ne $expected) {
    throw "Amendment design SHA mismatch: $actual"
}
```

Expected: exact match.

- [ ] **Step 4: Verify Python runtime and backend environment**

Prefer the worktree venv if available; otherwise use the already-verified shared maintenance venv.

```powershell
$pythonCandidates = @(
  (Join-Path $repoRoot "extensions\maintenance-api\.venv\Scripts\python.exe"),
  "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api\.venv\Scripts\python.exe"
)

$python = $pythonCandidates |
  Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
  Select-Object -First 1

if (-not $python) {
    throw "No approved Python 3.11 venv was found."
}

& $python --version
& $python -c "import sys; assert sys.version_info[:2] == (3, 11); print(sys.version_info[:3])"
```

Expected Python: `3.11.9` or another already-approved Python 3.11 patch in the same environment; if runtime materially changed, record it before proceeding.

- [ ] **Step 5: Verify Alembic single head**

```powershell
$apiRoot = Join-Path $repoRoot "extensions\maintenance-api"

Push-Location $apiRoot
try {
    & $python -m alembic heads
    if ($LASTEXITCODE -ne 0) {
        throw "alembic heads failed"
    }
}
finally {
    Pop-Location
}
```

Expected:

```text
20260803_11 (head)
```

- [ ] **Step 6: Verify exact production baseline**

Read-only inspection:

```powershell
& $git -C $repoRoot grep -n "class InventoryBalanceRead" -- `
  extensions/maintenance-api/app/schemas/inventory_ledger.py

& $git -C $repoRoot grep -n "def list_balances" -- `
  extensions/maintenance-api/app/repositories/inventory_ledger_repository.py `
  extensions/maintenance-api/app/services/inventory_query_service.py

& $git -C $repoRoot grep -n "lot_version\|lot_is_frozen" -- `
  extensions/maintenance-api/app `
  extensions/maintenance-api/tests
```

Expected before RED:

- `InventoryBalanceRead` exists;
- no public `lot_version` / `lot_is_frozen` implementation already exists;
- no unexpected competing feature has landed.

If those fields already exist in production due another change → STOP and re-plan.

- [ ] **Step 7: STOP for Task 1 RED approval**

No file has changed.

---

# Task 1: RED — Freeze the Public Lot Concurrency Read Contract

**Files:**

- Modify only:
  `extensions/maintenance-api/tests/services/test_inventory_query_service.py`
- Modify only:
  `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`

**Production files in RED:** none.

**Produces:**
- exactly eight new failing behavioral/API assertions;
- no production implementation.

The existing Task 10.5 focused suite baseline is 55 tests. This plan adds exactly 8 non-parametrized tests, so the combined focused suite should collect 63 tests once GREEN.

## Task 1A: Service RED — five tests

- [ ] **Step 1: Add service test — list returns matching lot state**

Use the file's existing session/actor/factory patterns. Create:

- current tenant balance;
- matching current tenant lot;
- `balance.lot_id == lot.id`;
- `balance.spare_part_id == lot.spare_part_id`;
- explicit lot `version`, e.g. 7;
- `is_frozen=False`.

Required assertion:

```python
page = service.list_balances(
    session,
    actor,
    page=1,
    page_size=20,
)

item = next(
    item for item in page.items
    if item.id == balance.id
)

assert item.lot_id == lot.id
assert item.lot_version == 7
assert item.lot_is_frozen is False
```

Do not assert expiry/quality/freeze_reason.

- [ ] **Step 2: Add service test — detail returns matching frozen lot state**

Create a lot with:

```python
lot.version = 9
lot.is_frozen = True
```

Then:

```python
item = service.get_balance(
    session,
    actor,
    balance.id,
)

assert item.lot_version == 9
assert item.lot_is_frozen is True
```

- [ ] **Step 3: Add service test — no-lot balance returns null/null**

Create a balance with:

```python
lot_id = None
```

Assert list or detail:

```python
assert item.lot_id is None
assert item.lot_version is None
assert item.lot_is_frozen is None
```

- [ ] **Step 4: Add service test — tenant mismatch fails closed**

Create:

- actor tenant A;
- balance in tenant A referencing a numeric lot ID that is not safely resolvable in tenant A;
- a lot in tenant B whose ID or fixture arrangement would otherwise be tempting to match.

Assert:

```python
assert item.lot_version is None
assert item.lot_is_frozen is None
```

The test must never assert or reveal tenant B's version/state.

If FK constraints prevent constructing a literal cross-tenant relation through normal ORM, use the existing test's direct fixture strategy that can represent inconsistent legacy/corrupt data **without disabling production tenant predicates**. Do not weaken database constraints in production.

- [ ] **Step 5: Add service test — spare-part mismatch fails closed and page metadata/order stay unchanged**

Construct current-tenant balances that exercise the existing stable ordered page.

For the selected page, ensure one balance has a lot relation that does not match `spare_part_id` under the test's safe inconsistent-data fixture strategy.

Assert:

```python
before_ids = [expected_balance_ids_in_existing_task105_order]
after_ids = [item.id for item in page.items]

assert after_ids == before_ids
assert page.total == expected_total
assert page.page == 1
assert page.page_size == expected_page_size
assert page.pages == expected_pages

mismatched = next(
    item for item in page.items
    if item.id == mismatched_balance.id
)
assert mismatched.lot_version is None
assert mismatched.lot_is_frozen is None
```

This test proves hydration is not participating in parent sort/page/count.

## Task 1B: API/OpenAPI RED — three tests

- [ ] **Step 6: Add API test — balance list serializes fields**

Using existing authenticated viewer API test fixture:

```python
response = client.get(
    "/api/maintenance/v1/inventory/balances",
)
assert response.status_code == 200

item = find_balance(response.json(), balance.id)

assert item["lot_version"] == lot.version
assert item["lot_is_frozen"] is False
```

Also assert no unsupported field is introduced:

```python
assert "expiry_date" not in item
assert "quality_status" not in item
assert "freeze_reason" not in item
```

- [ ] **Step 7: Add API test — balance detail serializes fields**

```python
response = client.get(
    f"/api/maintenance/v1/inventory/balances/{balance.id}",
)
assert response.status_code == 200

data = response.json()["data"]

assert data["lot_version"] == lot.version
assert data["lot_is_frozen"] is True
```

No-lot behavior may be asserted here as an additional assertion only if it does not increase the planned test count; do not add a ninth test without updating this plan's expected count.

- [ ] **Step 8: Add OpenAPI test — schema gains exactly two fields and no new route/query contract**

Inspect OpenAPI:

```python
schema = client.get("/openapi.json").json()
```

Assert the `InventoryBalanceRead` schema has properties:

```text
lot_version
lot_is_frozen
```

and their nullable types are correct.

Also assert:

- `/api/maintenance/v1/inventory/lots/{lot_id}` does **not** exist;
- existing balances list path parameter names are unchanged;
- `sort_by` enum has no `lot_version` or `lot_is_frozen`;
- no `lot_is_frozen` filter exists.

- [ ] **Step 9: Run service RED**

```powershell
Push-Location `
  "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-plan05-4b\extensions\maintenance-api"
try {
    & $python -m pytest `
      tests/services/test_inventory_query_service.py `
      -q
}
finally {
    Pop-Location
}
```

Expected:

- new tests fail because `InventoryBalanceRead` has no `lot_version` / `lot_is_frozen`;
- existing service tests still pass;
- failure is contract absence, not fixture/syntax/import infrastructure.

- [ ] **Step 10: Run API RED**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/api/test_inventory_queries_api.py `
      -q
}
finally {
    Pop-Location
}
```

Expected:

- new API/OpenAPI tests fail only because the two fields are absent;
- existing API tests remain green.

- [ ] **Step 11: Run combined RED collection/result**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py `
      -q
}
finally {
    Pop-Location
}
```

Expected collection:

```text
63 tests
```

Expected result:

- exactly the new amendment tests fail;
- pre-existing Task 10.5 tests pass.

If test count differs because the two files have changed upstream, do not force 63; record current collection and STOP to reconcile the plan.

- [ ] **Step 12: Run Ruff on RED test files**

```powershell
Push-Location $apiRoot
try {
    & $python -m ruff check `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py
}
finally {
    Pop-Location
}
```

Expected: PASS.

- [ ] **Step 13: Verify RED scope and HEAD**

```powershell
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --name-only
& $git -C $repoRoot diff --cached --name-only
& $git -C $repoRoot rev-parse HEAD
```

Expected:

```text
 M extensions/maintenance-api/tests/api/test_inventory_queries_api.py
 M extensions/maintenance-api/tests/services/test_inventory_query_service.py
```

Production unchanged.

Staged empty.

HEAD unchanged from preflight.

- [ ] **Step 14: STOP and request explicit GREEN approval**

Do not modify production in RED.

---

# Task 2: GREEN — Add Page-Bounded Lot Concurrency Hydration

**Files:**

- Modify:
  `extensions/maintenance-api/app/schemas/inventory_ledger.py`
- Modify:
  `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Modify:
  `extensions/maintenance-api/app/services/inventory_query_service.py`
- Preserve the two RED test files unchanged except for a necessary test correction explicitly justified by RED evidence.

No fourth production file.

## Task 2A: Schema

- [ ] **Step 1: Add exactly two fields to `InventoryBalanceRead`**

In `app/schemas/inventory_ledger.py`:

```python
class InventoryBalanceRead(ORMModel):
    id: int
    warehouse_id: int
    location_id: int
    spare_part_id: int
    lot_id: int | None
    serial_item_id: int | None = None
    serial_item_ids: list[int] = Field(default_factory=list)
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    damaged_quantity: Decimal
    quarantined_quantity: Decimal
    in_transit_quantity: Decimal
    version: int

    lot_version: int | None = Field(
        default=None,
        gt=0,
    )
    lot_is_frozen: bool | None = None
```

Do not add lot expiry/quality/reason fields.

The exact field placement within the model may follow repository formatting, but names/types/defaults are fixed.

## Task 2B: Repository hydration

- [ ] **Step 2: Add the type alias**

Near repository module constants/imports:

```python
LotConcurrencyState = tuple[int, bool]
```

No new module/file.

- [ ] **Step 3: Add `lot_state_by_balance()`**

Implementation shape:

```python
def lot_state_by_balance(
    self,
    session: Session,
    tenant_id: str,
    balances: Sequence[InventoryBalance],
) -> dict[int, LotConcurrencyState]:
    candidate_balances = [
        balance
        for balance in balances
        if balance.lot_id is not None
    ]
    if not candidate_balances:
        return {}

    lot_ids = sorted({
        balance.lot_id
        for balance in candidate_balances
        if balance.lot_id is not None
    })

    rows = session.execute(
        select(
            InventoryLot.id,
            InventoryLot.spare_part_id,
            InventoryLot.version,
            InventoryLot.is_frozen,
        ).where(
            InventoryLot.tenant_id == tenant_id,
            InventoryLot.id.in_(lot_ids),
        )
    ).all()

    lots_by_id = {
        int(row.id): row
        for row in rows
    }

    result: dict[int, LotConcurrencyState] = {}
    for balance in candidate_balances:
        assert balance.lot_id is not None
        lot = lots_by_id.get(balance.lot_id)
        if lot is None:
            continue
        if lot.spare_part_id != balance.spare_part_id:
            continue
        result[balance.id] = (
            int(lot.version),
            bool(lot.is_frozen),
        )

    return result
```

Implementation requirements:

- query filters on `InventoryLot.tenant_id == tenant_id`;
- query is bounded to lot IDs from already-selected parent balances;
- no `join()` into `list_balances()`;
- no ordering/count changes;
- no N+1 per balance;
- no cross-tenant fallback;
- spare-part mismatch omitted.

If SQLAlchemy row typing requires local adaptation, preserve the same semantics.

## Task 2C: Query service hydration

- [ ] **Step 4: Hydrate list after parent page**

In `list_balances()`:

```python
balances, total = self.repository.list_balances(
    ...
)

lot_states = self.repository.lot_state_by_balance(
    session,
    actor.tenant_id,
    balances,
)

serial_ids = self.repository.serial_item_ids_by_balance(
    session,
    actor.tenant_id,
    balances,
)
```

Use a focused helper to avoid duplicating model-copy logic if it remains in the same service file.

Recommended private helper:

```python
def _balance_read(
    self,
    balance: InventoryBalance,
    *,
    serial_item_ids: list[int],
    lot_state: LotConcurrencyState | None,
) -> InventoryBalanceRead:
    return InventoryBalanceRead.model_validate(
        balance
    ).model_copy(
        update={
            "serial_item_ids": serial_item_ids,
            "serial_item_id": self._single_serial_id(
                serial_item_ids
            ),
            "lot_version": (
                lot_state[0]
                if lot_state is not None
                else None
            ),
            "lot_is_frozen": (
                lot_state[1]
                if lot_state is not None
                else None
            ),
        }
    )
```

If importing repository-local type alias would create an undesirable runtime dependency, annotate `lot_state` as `tuple[int, bool] | None` in the service. Do not create another file.

- [ ] **Step 5: Hydrate detail using the same path**

After existing tenant-safe balance lookup:

```python
lot_states = self.repository.lot_state_by_balance(
    session,
    actor.tenant_id,
    [balance],
)
serial_ids = self.repository.serial_item_ids_by_balance(
    session,
    actor.tenant_id,
    [balance],
)

ids = serial_ids.get(balance.id, [])

return self._balance_read(
    balance,
    serial_item_ids=ids,
    lot_state=lot_states.get(balance.id),
)
```

List and detail must not implement two subtly different lot matching rules.

- [ ] **Step 6: Do not touch write semantics**

Before testing, verify:

```powershell
& $git -C $repoRoot diff --name-only
```

Must not include:

```text
extensions/maintenance-api/app/api/v1/inventory/operations.py
extensions/maintenance-api/app/services/inventory_operation_service.py
extensions/maintenance-api/app/services/inventory_transaction_service.py
extensions/maintenance-api/app/models/**
extensions/maintenance-api/alembic/**
```

If any appears → STOP.

---

# Task 3: GREEN Focused Verification and Regression Ladder

## Task 3A: Syntax/Ruff

- [ ] **Step 1: Compile the three production files and two test files**

```powershell
Push-Location $apiRoot
try {
    & $python -m py_compile `
      app/schemas/inventory_ledger.py `
      app/repositories/inventory_ledger_repository.py `
      app/services/inventory_query_service.py `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py
}
finally {
    Pop-Location
}
```

Expected: PASS.

- [ ] **Step 2: Focused Ruff**

```powershell
Push-Location $apiRoot
try {
    & $python -m ruff check `
      app/schemas/inventory_ledger.py `
      app/repositories/inventory_ledger_repository.py `
      app/services/inventory_query_service.py `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py
}
finally {
    Pop-Location
}
```

Expected: PASS.

## Task 3B: Amendment focused tests

- [ ] **Step 3: Service GREEN**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/services/test_inventory_query_service.py `
      -q
}
finally {
    Pop-Location
}
```

Expected: all service query tests PASS.

- [ ] **Step 4: API/OpenAPI GREEN**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/api/test_inventory_queries_api.py `
      -q
}
finally {
    Pop-Location
}
```

Expected: all API query tests PASS.

- [ ] **Step 5: Combined Task 10.5 + amendment suite**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py `
      -q
}
finally {
    Pop-Location
}
```

Expected if repository baseline is unchanged from plan creation:

```text
63 passed
```

One known Starlette/httpx deprecation warning may remain.

If test collection changed upstream, record actual count; zero failures is mandatory.

## Task 3C: Existing Task 9 API/RBAC/OpenAPI regression

- [ ] **Step 6: Run the exact Task 9 regression family**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/api/test_inventory_api_closure.py `
      tests/api/test_inventory_queries_api.py `
      tests/api/test_inventory_reservations_api.py `
      tests/api/test_inventory_operations_api.py `
      tests/api/test_inventory_transfers_api.py `
      tests/api/test_inventory_stocktakes_api.py `
      tests/security/test_api_rbac.py `
      -q
}
finally {
    Pop-Location
}
```

Expected: PASS.

The historical Task 10.5 baseline was 149 passed; this amendment adds API tests in one included file, so the count may increase. Do not require the old exact count.

## Task 3D: Focused Inventory backend regression

- [ ] **Step 7: Run focused Inventory backend family**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/models/test_inventory_operation_models.py `
      tests/migrations/test_inventory_operations_migration.py `
      tests/schemas/test_inventory_operation_schemas.py `
      tests/repositories/test_inventory_ledger_immutability.py `
      tests/repositories/test_inventory_ledger_repository.py `
      tests/repositories/test_inventory_reservation_repository.py `
      tests/repositories/test_inventory_transfer_repository.py `
      tests/repositories/test_inventory_stocktake_repository.py `
      tests/services/test_inventory_mutation_plan.py `
      tests/services/test_inventory_transaction_service.py `
      tests/services/test_inventory_fefo_service.py `
      tests/services/test_inventory_reservation_service.py `
      tests/workers/test_inventory_reservation_expiry.py `
      tests/services/test_inventory_operation_preview.py `
      tests/services/test_inventory_freeze.py `
      tests/services/test_inventory_adjust.py `
      tests/services/test_inventory_reversal.py `
      tests/services/test_inventory_transfer_service.py `
      tests/services/test_inventory_stocktake_service.py `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py `
      tests/api/test_inventory_reservations_api.py `
      tests/api/test_inventory_operations_api.py `
      tests/api/test_inventory_transfers_api.py `
      tests/api/test_inventory_stocktakes_api.py `
      tests/api/test_inventory_api_closure.py `
      tests/security/test_api_rbac.py `
      tests/integration/test_inventory_operations_workflow.py `
      -q
}
finally {
    Pop-Location
}
```

Expected: PASS.

Historical Task 10.5 baseline was 395 passed. This amendment adds 8 query tests, so count should increase if no upstream test changes; zero failures is mandatory.

This regression is the proof that existing FREEZE/UNFREEZE tests pass **without modifying operation production code**.

## Task 3E: Full backend

- [ ] **Step 8: Full Ruff**

```powershell
Push-Location $apiRoot
try {
    & $python -m ruff check app tests
}
finally {
    Pop-Location
}
```

Expected:

```text
All checks passed!
```

- [ ] **Step 9: Full pytest**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest -q
}
finally {
    Pop-Location
}
```

Expected: zero failures.

Historical baseline at Task 10.5 was:

```text
1269 passed, 8 deselected
```

This amendment adds tests, so do not require exactly 1269.

Known historical warnings may include:

- Starlette TestClient/httpx deprecation;
- JWT insecure key length warning in wrong-algorithm integration coverage.

Any new warning caused by the amendment must be investigated.

## Task 3F: Migration and diff safety

- [ ] **Step 10: Recheck Alembic head**

```powershell
Push-Location $apiRoot
try {
    & $python -m alembic heads
}
finally {
    Pop-Location
}
```

Expected:

```text
20260803_11 (head)
```

- [ ] **Step 11: `git diff --check`**

```powershell
& $git -C $repoRoot diff --check
```

Expected: PASS.

- [ ] **Step 12: Verify exact five-file changed scope**

```powershell
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --name-only
& $git -C $repoRoot diff --cached --name-only
```

Expected exactly:

```text
extensions/maintenance-api/app/repositories/inventory_ledger_repository.py
extensions/maintenance-api/app/schemas/inventory_ledger.py
extensions/maintenance-api/app/services/inventory_query_service.py
extensions/maintenance-api/tests/api/test_inventory_queries_api.py
extensions/maintenance-api/tests/services/test_inventory_query_service.py
```

Staged must remain empty.

Any sixth implementation file → STOP.

---

# Task 4: Real PostgreSQL Focused Amendment Gate

This gate proves the page-bounded hydration query behaves correctly on the real PostgreSQL dialect and does not silently depend on SQLite behavior.

No tracked PostgreSQL fixture/harness file may be added.

## Task 4A: Environment discovery

- [ ] **Step 1: Verify PostgreSQL client/server capability**

Use the already-established PostgreSQL 17 installation where available:

```powershell
$pgBin = "D:\PostgreSQL\17\bin"

& "$pgBin\psql.exe" --version
```

Expected: PostgreSQL 17.x.

Use credentials through environment variables/prompt/local secure configuration. Do not print secrets into evidence.

- [ ] **Step 2: Create a disposable database**

Use a unique temporary database name, for example:

```text
maintenance_plan05_4b_lot_read_gate
```

Do not reuse production or developer data.

- [ ] **Step 3: Run Alembic upgrade to head in the disposable DB**

Expected final version:

```text
20260803_11
```

No migration file is created.

## Task 4B: PostgreSQL focused tests

- [ ] **Step 4: Run the two focused query files against PostgreSQL**

Use the same temporary test-harness technique already verified for Task 10.5, without modifying tracked `conftest.py`.

Run:

```text
tests/services/test_inventory_query_service.py
tests/api/test_inventory_queries_api.py
```

Expected baseline if no repository test drift:

```text
63 passed
```

Mandatory:

- PostgreSQL dialect is actually `postgresql`;
- driver is psycopg;
- no SQLite fallback;
- lot hydration tests pass;
- tenant/spare-part fail-closed tests pass;
- Task 10.5 filter/count/sort/page tests pass.

- [ ] **Step 5: Run focused FREEZE/UNFREEZE regression on PostgreSQL**

At minimum:

```text
tests/services/test_inventory_freeze.py
tests/services/test_inventory_operation_preview.py
tests/api/test_inventory_operations_api.py
```

Expected: PASS.

This proves the additive read contract did not alter existing write behavior.

- [ ] **Step 6: Clean the disposable database**

Drop the Gate database.

Verify it no longer exists.

No tracked or untracked repository fixture file is left behind.

## Task 4C: Post-PostgreSQL local recheck

- [ ] **Step 7: Re-run combined local focused suite**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py `
      -q

    & $python -m ruff check `
      app/schemas/inventory_ledger.py `
      app/repositories/inventory_ledger_repository.py `
      app/services/inventory_query_service.py `
      tests/services/test_inventory_query_service.py `
      tests/api/test_inventory_queries_api.py
}
finally {
    Pop-Location
}
```

Expected: PASS.

- [ ] **Step 8: Verify repository unchanged by PG harness**

```powershell
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --name-only
& $git -C $repoRoot diff --cached --name-only
```

Expected same exact five implementation files, staged empty.

No temporary harness/evidence file remains in repository paths.

---

# Task 5: Final Review Bundle and STOP Before Commit

**Files:** no new tracked implementation files.

**Consumes:** fresh Task 1–4 evidence.

**Produces:** a review summary for user approval.

- [ ] **Step 1: Capture final branch/HEAD/status**

```powershell
& $git -C $repoRoot branch --show-current
& $git -C $repoRoot rev-parse HEAD
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --cached --name-only
```

Record:

- branch;
- pre-feature-commit HEAD;
- exactly five changed files;
- staged empty.

- [ ] **Step 2: Capture diff stat and check**

```powershell
& $git -C $repoRoot diff --stat
& $git -C $repoRoot diff --check
```

Expected: PASS.

- [ ] **Step 3: Audit public contract diff**

Review schema/query service/repository diff and explicitly confirm:

```text
ADDED:
lot_version
lot_is_frozen

NOT ADDED:
new endpoint
new filter
new sort
expiry_date
quality_status
freeze_reason
risk
demand gap
migration
```

- [ ] **Step 4: Audit parent page preservation**

Confirm the diff does not add `InventoryLot` to the `list_balances()` parent select/count/order query.

The only lot query must be the post-page hydration helper.

- [ ] **Step 5: Audit tenant/spare-part predicates**

Confirm the helper includes:

```text
InventoryLot.tenant_id == tenant_id
```

and the returned state is only attached when:

```text
lot.id == balance.lot_id
lot.spare_part_id == balance.spare_part_id
```

- [ ] **Step 6: Audit write scope**

Confirm no diff in:

```text
app/api/v1/inventory/operations.py
app/services/inventory_operation_service.py
app/services/inventory_transaction_service.py
app/models/**
alembic/**
```

- [ ] **Step 7: Summarize fresh gates**

Report actual results for:

- service query tests;
- API/OpenAPI query tests;
- combined focused query tests;
- Task 9 API/RBAC/OpenAPI regression;
- focused Inventory regression;
- full Ruff;
- full backend pytest;
- Alembic head;
- real PostgreSQL focused query gate;
- real PostgreSQL FREEZE/UNFREEZE regression;
- post-PG local focused recheck;
- `git diff --check`;
- exact five-file scope.

Do not reuse old counts when new output exists.

- [ ] **Step 8: Required final marker**

When all gates pass, report:

```text
===== INVENTORY LOT CONCURRENCY READ AMENDMENT GREEN VERIFIED =====

Public fields:
  lot_version
  lot_is_frozen

Parent filter/count/sort/page semantics: UNCHANGED
FREEZE/UNFREEZE write semantics: UNCHANGED
Alembic head: 20260803_11
Production scope: exactly 3 files
Test scope: exactly 2 files
Working tree: five approved modified files
Staged: EMPTY

STOP: Do not commit, push, update PR, merge, or start frontend.
```

If any gate fails, do not print the VERIFIED marker.

- [ ] **Step 9: STOP and request feature commit approval**

No `git add` or commit in Task 5.

---

# Task 6: Feature Commit — Only After Separate Approval

This Task is documented now but must not run unless the user separately approves the commit after Task 5 GREEN verification.

**Approved commit scope if later authorized:**

Exactly five files:

```text
extensions/maintenance-api/app/repositories/inventory_ledger_repository.py
extensions/maintenance-api/app/schemas/inventory_ledger.py
extensions/maintenance-api/app/services/inventory_query_service.py
extensions/maintenance-api/tests/api/test_inventory_queries_api.py
extensions/maintenance-api/tests/services/test_inventory_query_service.py
```

Suggested commit message:

```text
feat(maintenance): expose inventory lot concurrency state
```

## Commit preflight

- [ ] **Step 1: Verify branch, expected pre-commit HEAD, exact five-file worktree scope, staged empty**

Any drift → STOP.

- [ ] **Step 2: Re-run before staging**

At minimum fresh:

```text
combined focused query tests
Ruff app/tests
Task 9 API/RBAC/OpenAPI regression
focused Inventory backend regression
git diff --check
```

Do not rely only on earlier Task 3/4 output.

- [ ] **Step 3: Stage exactly five files**

No docs/frontend/other backend file.

- [ ] **Step 4: Verify cached scope and no unstaged amendment change**

```powershell
git diff --cached --name-status
git diff --cached --check
git diff --name-only
```

Expected cached: exactly five `M` files.

Expected unstaged: empty.

- [ ] **Step 5: Create exactly one local commit**

```text
feat(maintenance): expose inventory lot concurrency state
```

- [ ] **Step 6: Post-commit verify**

Verify:

- new HEAD advanced once;
- parent equals approved pre-commit HEAD;
- subject exact;
- exactly five committed files;
- working tree clean;
- staged empty.

- [ ] **Step 7: STOP**

Do not push.

---

# Task 7: Push — Separate Approval Only

If later separately approved:

1. verify branch/head/clean/staged empty;
2. read remote same-name branch tip;
3. require remote tip to be an ancestor of local approved HEAD;
4. re-read remote tip immediately before push;
5. ordinary fast-forward push only;
6. no force;
7. post-push verify local/remote SHA equality;
8. STOP before PR update.

---

# Task 8: Frontend Plan Reconciliation — After Backend Amendment Push/Verification

This is **not** frontend implementation.

After the backend amendment is closed and pushed, return to the existing Frontend Inventory Gap implementation-plan draft.

Required reconciliation:

1. add to frontend `InventoryBalanceRead`:

```ts
lot_version: number | null
lot_is_frozen: boolean | null
```

2. Task 11A API tests preserve the two fields.
3. Task 12C removes the “lot version unavailable” backend-blocker STOP.
4. Task 12C high-risk lot state command uses freshly loaded balance detail:

```ts
{
  operation_type:
    balance.lot_is_frozen
      ? 'UNFREEZE'
      : 'FREEZE',
  balance_id: balance.id,
  expected_balance_version: balance.version,
  reason,
  deltas: null,
  lot_id: balance.lot_id,
  expected_lot_version: balance.lot_version,
}
```

5. Freeze/Unfreeze is unavailable when any lot concurrency field is null.
6. On version/state conflict:
   - preserve user reason/context;
   - discard preview confirmation state;
   - reload balance detail;
   - require a fresh preview.
7. Task 13 audit proves frontend never guesses lot version.

The reconciled frontend plan receives a new SHA256 and requires separate user approval before Task 11A RED.

---

# Plan Self-Review Checklist

Before presenting this plan for approval, verify:

- [ ] design SHA is exact;
- [ ] frozen baseline commit is exact;
- [ ] implementation is read-only additive;
- [ ] exactly two public fields are added;
- [ ] no new endpoint;
- [ ] no new filter/sort;
- [ ] no migration;
- [ ] no model change;
- [ ] no operation-service change;
- [ ] repository hydration happens after parent page;
- [ ] one bounded lot query, no N+1;
- [ ] tenant predicate is explicit;
- [ ] spare-part match is explicit;
- [ ] no-lot returns null/null;
- [ ] cross-tenant/mismatch fails closed;
- [ ] list order/count/page test is explicit;
- [ ] API and OpenAPI coverage is explicit;
- [ ] existing FREEZE/UNFREEZE regression is explicit;
- [ ] real PostgreSQL gate is explicit;
- [ ] PostgreSQL harness does not change tracked fixtures;
- [ ] production scope is exactly three files;
- [ ] test scope is exactly two files;
- [ ] RED stops before GREEN;
- [ ] GREEN stops before commit;
- [ ] commit stops before push;
- [ ] push stops before PR update;
- [ ] frontend remains blocked until backend amendment and plan reconciliation close;
- [ ] no unfinished placeholder markers;
- [ ] no destructive Git operations.

---

# Approval Boundary

Approval of this IMPLEMENTATION PLAN authorizes only this document as the execution blueprint.

It does **not** authorize:

- docs commit;
- RED;
- test modifications;
- GREEN;
- production modifications;
- feature commit;
- push;
- PR update;
- PR ready;
- merge;
- frontend RED or implementation.

After plan approval, the next recommended gate is a **docs-only commit approval** for the amendment DESIGN and this amendment IMPLEMENTATION PLAN.

After that docs commit is verified, request a separate **Task 1 RED approval**.

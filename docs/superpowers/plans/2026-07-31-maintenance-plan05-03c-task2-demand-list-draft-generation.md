# Plan 05-3C Task 2 Demand List Draft Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a complete, immutable-source-snapshot demand-list DRAFT from a terminal calculation group whose successful-result union has one valid saved decision per item, and support tenant-safe, idempotent creation plus optimistic DRAFT quantity updates.

**Architecture:** Reuse `CalculationGroupService.comparison()` as the authoritative successful-result union and saved-decision view. Query the selected current child result only to build immutable source snapshots; do not reimplement candidate union semantics. Extract the existing decision-risk rules into a pure shared policy used by both calculation decisions and demand-list DRAFT updates, preventing rule drift. `DemandListService` owns one transaction per create or update and returns typed decimal-string read models.

**Tech Stack:** Python 3.11, Pydantic 2, SQLAlchemy 2, pytest, Ruff.

## Global Constraints

- Work in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Target branch is `feature/maintenance-frontend-plan05`.
- Task 1 formal implementation baseline is `3bb66f54 feat: add versioned demand list persistence`.
- The local Task 1 closure documentation commit may remain ahead of `origin` while GitHub networking is unavailable; do not reset, rewrite, or force-push it.
- Task 2 does not add or modify API routes, lifecycle transitions, publication, derivation, voiding, frontend code, inventory reservation, review rules, allocation, or reports.
- Lifecycle remains exactly `DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED`; Task 2 creates and edits only `DRAFT`.
- Every generated item copies source result and saved-decision meaning into immutable snapshots.
- Demand quantities and all numeric snapshot values use `Decimal`; JSON output stores decimal strings, never floats.
- Tenant comes only from `ActorContext.tenant_id`.
- Viewer is read-only; contributor and admin may create and edit DRAFT lists.
- Creation requires a nonblank `Idempotency-Key`.
- DRAFT item updates use the aggregate list `expected_version`.
- Repository methods continue to flush without committing; the service commits exactly once per successful mutation.
- Every production behavior starts with a failing test.

---

## Refined File Map

### Create

```text
extensions/maintenance-api/app/services/demand_decision_policy.py
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/tests/services/test_demand_decision_policy.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
```

### Modify

```text
extensions/maintenance-api/app/services/calculation_group_service.py
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/tests/services/test_calculation_group_service.py
```

### Explicitly unchanged

```text
extensions/maintenance-api/app/models/demand_list.py
extensions/maintenance-api/app/repositories/demand_list_repository.py
extensions/maintenance-api/alembic/versions/20260731_07_add_demand_lists.py
extensions/maintenance-api/app/api/**
frontend/**
```

Task 1 persistence already exposes all fields and repository operations required by Task 2. No migration is added.

---

## Public Interfaces

### Shared decision-risk policy

```python
DEMAND_DECISION_RISK_RULE_VERSION = "DEMAND-DECISION-RISK-1"


@dataclass(frozen=True, slots=True)
class DecisionCandidateEvidence:
    child_id: int
    recommended_quantity: Decimal
    p50: Decimal | None
    p99: Decimal | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionRiskEvaluation:
    decision_type: CalculationDecisionType
    risk: str
    requires_admin_confirmation: bool
    rule_version: str
    changed_candidate: bool
    changed_quantity: bool


def evaluate_decision_risk(
    *,
    source_child_id: int,
    selected_child_id: int,
    source_quantity: Decimal,
    selected_quantity: Decimal,
    final_quantity: Decimal,
    criticality_level: str | None,
    successful_candidates: tuple[DecisionCandidateEvidence, ...],
) -> DecisionRiskEvaluation:
    ...
```

The shared policy preserves the existing rules:

- final quantity at least 10% below selected quantity;
- any reduction for HIGH or CRITICAL criticality;
- final quantity outside every successful candidate `[p50, p99]` interval;
- selecting a non-system candidate whose recommended quantity differs by at least 10% from the system quantity;
- material warning containing `MISSING`, `NON_CONVERGENCE`, `NOT_CONVERGED`, or `HIGH`.

Decision type remains:

```text
MANUAL_QUANTITY        when final quantity differs from selected quantity
ALTERNATIVE_CANDIDATE  when selected child differs from system child
SYSTEM_RECOMMENDATION  otherwise
```

### Demand-list service

```python
class DemandListService:
    def create_from_group(
        self,
        session: Session,
        actor: ActorContext,
        *,
        group_id: int,
        name: str,
        description: str | None,
        idempotency_key: str,
    ) -> DemandListRead:
        ...

    def get(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
    ) -> DemandListRead:
        ...

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int = 1,
        page_size: int = 20,
        status: DemandListStatus | None = None,
        lineage_id: str | None = None,
    ) -> PageData[DemandListSummaryRead]:
        ...

    def update_item(
        self,
        session: Session,
        actor: ActorContext,
        demand_list_id: int,
        item_id: int,
        *,
        expected_version: int,
        final_quantity: Decimal,
        adjustment_reason: str,
    ) -> DemandListRead:
        ...
```

Module singleton:

```python
demand_list_service = DemandListService()
```

### Schemas

```python
DemandListCreateRequest
DemandListItemUpdateRequest
DemandListItemRead
DemandListEventRead
DemandListSummaryRead
DemandListRead
```

All read-model Decimal fields serialize through the existing `DecimalString` alias.

---
# Task 2A: Extract the Shared Decision-Risk Policy

**Files:**
- Create: `extensions/maintenance-api/app/services/demand_decision_policy.py`
- Create: `extensions/maintenance-api/tests/services/test_demand_decision_policy.py`
- Modify: `extensions/maintenance-api/app/services/calculation_group_service.py`
- Modify: `extensions/maintenance-api/tests/services/test_calculation_group_service.py`

**Produces:** one pure risk evaluator used by calculation decisions and demand-list edits.

## RED

- [ ] Write focused tests for default LOW risk, 10% reduction, HIGH/CRITICAL reduction, outside-all-ranges, alternative candidate material difference, material warning, and decision type.
- [ ] Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api

& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_decision_policy.py `
  -v
```

Expected: `ModuleNotFoundError: app.services.demand_decision_policy`.

## GREEN

- [ ] Implement a pure module with frozen/slotted input and result dataclasses.
- [ ] Keep all arithmetic as `Decimal`.
- [ ] Make material-warning matching case-insensitive.
- [ ] Do not mark outside-all-ranges when no complete candidate interval exists.
- [ ] Run policy tests and confirm PASS.
- [ ] Refactor `CalculationGroupService.save_decision()` to call the policy.
- [ ] Preserve `CalculationGroupService.DECISION_RISK_RULE_VERSION` as an alias to the shared constant.
- [ ] Keep comparison lookup, reason requirement, expected-version check, repository writes, event append, and transaction control in `CalculationGroupService`.
- [ ] Extend calculation-group regression tests to prove existing decision type, risk, and rule version are unchanged.
- [ ] Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_decision_policy.py `
  tests\services\test_calculation_group_service.py `
  -v
```

Expected: PASS.

Do not commit yet; Task 2A–2G form one focused implementation commit.

---

# Task 2B: Define Complete Demand-List Schemas

**Files:**
- Modify: `extensions/maintenance-api/app/schemas/demand_list.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

## RED

- [ ] Add tests proving blank names, overlong names, negative quantities, and blank adjustment reasons are rejected.
- [ ] Add a typed read test proving `original_quantity` and `final_quantity` serialize as fixed-point strings.
- [ ] Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "schema or decimal" `
  -v
```

Expected: FAIL because schemas are missing.

## GREEN

- [ ] Add:

```python
class DemandListCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculation_group_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DemandListItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    final_quantity: DecimalString = Field(ge=0)
    adjustment_reason: str = Field(min_length=1, max_length=1000)
```

- [ ] Strip `name`, `description`, and `adjustment_reason`; reject whitespace-only required values.
- [ ] Add complete read schemas for item, event, summary, and aggregate.
- [ ] Include all Task 1 source IDs, identity snapshots, current decision scalars, immutable JSON snapshots, versions, actors, and timestamps.
- [ ] Run schema tests and confirm PASS.

---

# Task 2C: Generate a Complete Demand-List DRAFT

**Files:**
- Create: `extensions/maintenance-api/app/services/demand_list_service.py`
- Create/extend: `extensions/maintenance-api/tests/services/test_demand_list_service.py`

## Authoritative generation order

```text
1. normalize and validate name, description, and Idempotency-Key;
2. canonical-hash group_id, normalized name, and description;
3. tenant-scoped receipt lookup;
4. same key/hash replays stored response; different hash conflicts;
5. lock calculation-group row;
6. call CalculationGroupService.comparison();
7. require one saved decision per union item;
8. verify selected child is current, successful, and contains the item;
9. query selected current run and result;
10. construct all immutable snapshots in memory;
11. create one DRAFT list and all items;
12. append CREATED;
13. store the typed response snapshot;
14. commit once;
15. return DemandListRead.
```

Any failure rolls back the complete aggregate.

## RED

- [ ] Build real SQLAlchemy fixtures following `test_calculation_group_service.py`: published scenario, terminal group, multiple current children, successful runs, union-only items, fully populated result rows, and saved decisions.
- [ ] Write `test_create_draft_copies_complete_source_snapshot`.
- [ ] Assert status/version/version-number, item count, every source ID, model/mode, original/final quantities, decision fields, all intervals, parameters, warnings, inventory values, and decision ID/version.
- [ ] Assert every JSON numeric value is a string and no ORM object appears.
- [ ] Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "complete_source_snapshot" `
  -v
```

Expected: missing demand-list service.

## GREEN

- [ ] Add constructor injection for repositories and `CalculationGroupService`.
- [ ] Add explicit `_decimal_string()` and dictionary-building helpers.
- [ ] Never use `float()`, `vars(orm)`, or generic ORM serialization.
- [ ] Copy these snapshot groups:

`source_snapshot_json`
```text
calculation status
failure process mode
selected profile IDs
selection reason
target service level
expected demand
variance
standard deviation
target quantile
gross replacement demand
repair pipeline demand and peak
net consumption demand
recommended quantity
shortage risk
minimum inventory point
maximum simultaneous gap
common shock demand
```

`interval_snapshot_json`
```text
selected p50/p80/p90/p95/p99
all successful candidates: child ID, key, recommended quantity, p50, p99, warnings
system source child ID
selected child ID
```

`parameter_snapshot_json`
```text
copied selected-result parameter snapshot
```

`warning_snapshot_json`
```text
copied warning-code list
```

`inventory_snapshot_json`
```text
on hand
available
in transit
safety stock reserved
usable inventory
net demand gap
inventory coverage rate
```

`decision_snapshot_json`
```text
decision ID/version
source/selected child IDs
original/final quantity strings
decision type/reason/risk
admin flags
risk rule version
decision actor/request
created/updated timestamps
```

- [ ] Enforce contributor/admin writes with `InsufficientMaintenanceRoleError`; viewer remains read-only.
- [ ] Run the complete snapshot test and confirm PASS.

---
# Task 2D: Enforce Preconditions and Atomicity

## RED cases

- [ ] nonterminal group → `CALCULATION_GROUP_NOT_TERMINAL`
- [ ] no successful current child → `CALCULATION_GROUP_HAS_NO_RESULTS`
- [ ] missing decision → `DEMAND_LIST_DECISIONS_INCOMPLETE`
- [ ] selected child has no result for item → `DEMAND_LIST_DECISION_SOURCE_INVALID`
- [ ] selected child is stale/non-current → `DEMAND_LIST_DECISION_SOURCE_INVALID`
- [ ] cross-tenant group → safe `RESOURCE_NOT_FOUND`
- [ ] viewer create → `INSUFFICIENT_MAINTENANCE_ROLE`
- [ ] missing tenant-valid SparePart/unit → `DEMAND_LIST_SOURCE_INVALID`
- [ ] failure during validation leaves zero lists, items, and events

`DEMAND_LIST_DECISIONS_INCOMPLETE` details contain sorted missing `spare_part_ids`.

`DEMAND_LIST_DECISION_SOURCE_INVALID` details contain `spare_part_id`, `selected_child_id`, and `reason`.

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "rejects or rollback or tenant or viewer" `
  -v
```

Expected: FAIL before checks, then PASS after implementation.

## GREEN rules

- [ ] Idempotency replay precedes current source-state validation.
- [ ] Tenant and role checks precede inserts.
- [ ] Validate every source row and decision before creating `DemandList`.
- [ ] Build all item payloads in memory first.
- [ ] Roll back on every exception.

---

# Task 2E: Implement Idempotent Creation

## RED cases

- [ ] same tenant/key/hash returns exact stored `DemandListRead`
- [ ] only one list and one CREATED event exist
- [ ] same key with different normalized request → `IDEMPOTENCY_KEY_REUSED`
- [ ] different tenants may reuse the same key
- [ ] blank key → `IDEMPOTENCY_KEY_REQUIRED`
- [ ] malformed receipt never creates another list

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "idempot" `
  -v
```

## GREEN rules

- [ ] Use `snapshot_service.canonical_hash()` over:

```python
{
    "calculation_group_id": group_id,
    "name": normalized_name,
    "description": normalized_description,
}
```

- [ ] Exclude actor, request ID, and idempotency key from the hash.
- [ ] Receipt must be CREATED, have matching hash, and contain a valid response snapshot.
- [ ] Different hash raises:

```python
ConflictError(
    "idempotency key was reused",
    code="IDEMPOTENCY_KEY_REUSED",
    details={
        "conflict_object": "demand_list",
        "retryable": False,
    },
)
```

- [ ] Flush list/items/event, build typed aggregate, assign `event.response_snapshot_json`, flush, commit once.

---

# Task 2F: Add Tenant-Safe Get and List

## RED cases

- [ ] viewer/contributor/admin can read
- [ ] tenant B cannot get tenant A list
- [ ] tenant B list excludes tenant A
- [ ] status and lineage filters work
- [ ] items sort by ID
- [ ] events sort by `(occurred_at, id)`
- [ ] page metadata is exact

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "get or list or viewer_read" `
  -v
```

## GREEN

- [ ] Add deterministic `_read(row) -> DemandListRead`.
- [ ] Copy all JSON lists/dicts; do not expose mutable ORM containers.
- [ ] Missing/foreign list raises `NotFoundError("demand_list", id)`.
- [ ] Return `PageData[DemandListSummaryRead]` with correct page count.

---

# Task 2G: Update a DRAFT Item Optimistically

## Authoritative update order

```text
1. require contributor/admin;
2. validate nonnegative Decimal and nonblank reason;
3. lock tenant-scoped list;
4. require DRAFT;
5. compare list.version to expected_version;
6. lock item within list;
7. reconstruct policy evidence from immutable snapshots;
8. recalculate type/risk/admin requirement;
9. capture before summary;
10. update current scalar decision fields and final quantity;
11. reset confirmed_by_admin;
12. increment item.version and list.version once;
13. append ITEM_UPDATED;
14. commit once;
15. return reloaded DemandListRead.
```

## RED cases

- [ ] successful update changes quantity exactly
- [ ] list and item versions each increment once
- [ ] shared risk policy result is identical to calculation decision risk
- [ ] `confirmed_by_admin` resets false
- [ ] event before/after quantities are decimal strings
- [ ] exactly one commit
- [ ] stale version → `DEMAND_LIST_VERSION_CONFLICT`
- [ ] non-DRAFT → `DEMAND_LIST_NOT_EDITABLE`
- [ ] foreign list/item → `RESOURCE_NOT_FOUND`
- [ ] item from another list → `RESOURCE_NOT_FOUND`
- [ ] viewer update → `INSUFFICIENT_MAINTENANCE_ROLE`
- [ ] negative direct call → `DEMAND_LIST_QUANTITY_INVALID`
- [ ] blank reason direct call → `DEMAND_LIST_ADJUSTMENT_REASON_REQUIRED`

Version conflict details:

```python
{
    "expected_version": expected_version,
    "actual_version": locked.version,
    "conflict_object": "demand_list",
    "retryable": False,
}
```

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_list_service.py `
  -k "update_item or version_conflict or not_editable or risk_parity" `
  -v
```

## GREEN

- [ ] Reconstruct candidate intervals and warnings from `interval_snapshot_json`.
- [ ] Do not query mutable calculation results during update.
- [ ] Keep `decision_snapshot_json` unchanged as the original calculation decision.
- [ ] Store current adjustment in scalar fields and append-only ITEM_UPDATED event.
- [ ] Run update tests and confirm PASS.

---

# Task 2H: Verification and Commit

## Focused gate

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api

& .\.venv\Scripts\python.exe -m pytest `
  tests\services\test_demand_decision_policy.py `
  tests\services\test_demand_list_service.py `
  tests\services\test_calculation_group_service.py `
  tests\repositories\test_demand_list_repository.py `
  tests\migrations\test_demand_list_migration.py `
  -v

& .\.venv\Scripts\python.exe -m pytest `
  tests\repositories\test_demand_domain_tenant_scope.py `
  -v

& .\.venv\Scripts\python.exe -m ruff check `
  app\services\demand_decision_policy.py `
  app\services\demand_list_service.py `
  app\services\calculation_group_service.py `
  app\schemas\demand_list.py `
  tests\services\test_demand_decision_policy.py `
  tests\services\test_demand_list_service.py `
  tests\services\test_calculation_group_service.py
```

Then:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05

git diff --check
git status --short
git --no-pager diff --stat
```

Expected:

- focused tests pass;
- tenant regression passes;
- Ruff reports `All checks passed!`;
- `git diff --check` is silent;
- changed files match the approved map.

## Plan commit

Destination:

```text
docs/superpowers/plans/2026-07-31-maintenance-plan05-03c-task2-demand-list-draft-generation.md
```

Commit:

```powershell
git add -- `
  docs/superpowers/plans/2026-07-31-maintenance-plan05-03c-task2-demand-list-draft-generation.md

git commit -m "docs: detail plan05 demand list draft generation"
```

The plan commit may remain local while networking is unavailable. Do not force-push.

## Implementation commit

```powershell
git add -- `
  extensions/maintenance-api/app/services/demand_decision_policy.py `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/app/services/calculation_group_service.py `
  extensions/maintenance-api/app/schemas/demand_list.py `
  extensions/maintenance-api/tests/services/test_demand_decision_policy.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py `
  extensions/maintenance-api/tests/services/test_calculation_group_service.py

git diff --cached --check

git commit -m "feat: generate demand list drafts"
```

Do not include progress-ledger updates in the implementation commit.

## Evidence required before Task 3

```text
focused Task 2 test count and duration
tenant regression result
Ruff result
git diff --check result
implementation commit SHA
clean working tree
local ahead/behind state
```

Task 3 does not start until Task 2 evidence is reviewed and its closure record is committed.

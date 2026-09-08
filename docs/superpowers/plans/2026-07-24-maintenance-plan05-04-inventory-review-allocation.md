# Plan 05-4 Inventory, Review and Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the maintenance system from aggregate inventory display to auditable lot/serial stock operations, FEFO reservation, stocktake, substitution and kit validation, deterministic demand-list review, configurable priority rules, simulation, and user-confirmed multi-task allocation.

**Architecture:** Replace direct inventory quantity edits with an append-only transaction/ledger service that updates balance projections inside one database transaction. Keep the published demand list immutable; deterministic review creates findings and derived versions, while allocation plans reference a published list and current stock snapshots, support simulation and preview, and execute reservations only after version and inventory revalidation.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite/PostgreSQL-compatible SQL, pytest, Ruff, Vue 3.5, TypeScript 6, Pinia, TDesign, Node `tsx --test`.

## Global Constraints

- Phase 05-1 through 05-3 gates must be green.
- Every inventory change is represented by a transaction and one or more immutable ledger entries.
- Balance rows are projections protected by version checks; they are never the sole audit record.
- Quantities use `Decimal`/`Numeric` and cannot become negative.
- Normal items use lot and optional expiry tracking; key or repairable items use serial-level tracking.
- Expired, frozen, quarantined, damaged, configuration-inapplicable and already-reserved stock is excluded from allocation.
- FEFO is the default issue/reservation order; manual override requires a recorded reason.
- Reservation, issue, return, transfer, freeze, adjustment and stocktake confirmation require idempotency, expected versions and actor authorization.
- Published demand lists are not modified by review or inventory; review generates a derived list and allocation generates a separate plan.
- Substitution is recommended and confirmed; it never silently replaces the original calculated requirement.
- Rule simulation never creates reservations or changes inventory.
- Competition allocation uses hard rules before weighted scoring and requires user confirmation before reservation execution.
- Procurement workflow and financial valuation remain out of scope.

---

## File Map

**Create:**

```text
extensions/maintenance-api/app/models/inventory_operations.py
extensions/maintenance-api/app/models/substitution.py
extensions/maintenance-api/app/models/kit_rule.py
extensions/maintenance-api/app/models/demand_review.py
extensions/maintenance-api/app/models/allocation.py
extensions/maintenance-api/app/schemas/inventory_operations.py
extensions/maintenance-api/app/schemas/substitution.py
extensions/maintenance-api/app/schemas/kit_rule.py
extensions/maintenance-api/app/schemas/demand_review.py
extensions/maintenance-api/app/schemas/allocation.py
extensions/maintenance-api/app/repositories/inventory_balance_repository.py
extensions/maintenance-api/app/repositories/inventory_transaction_repository.py
extensions/maintenance-api/app/repositories/stocktake_repository.py
extensions/maintenance-api/app/repositories/substitution_repository.py
extensions/maintenance-api/app/repositories/kit_rule_repository.py
extensions/maintenance-api/app/repositories/demand_review_repository.py
extensions/maintenance-api/app/repositories/allocation_repository.py
extensions/maintenance-api/app/services/inventory_transaction_service.py
extensions/maintenance-api/app/services/fefo_service.py
extensions/maintenance-api/app/services/reservation_service.py
extensions/maintenance-api/app/services/stocktake_service.py
extensions/maintenance-api/app/services/substitution_service.py
extensions/maintenance-api/app/services/kit_rule_service.py
extensions/maintenance-api/app/services/demand_review_service.py
extensions/maintenance-api/app/services/allocation_rule_service.py
extensions/maintenance-api/app/services/allocation_simulation_service.py
extensions/maintenance-api/app/services/allocation_plan_service.py
extensions/maintenance-api/app/api/v1/inventory/__init__.py
extensions/maintenance-api/app/api/v1/inventory/router.py
extensions/maintenance-api/app/api/v1/inventory/balances.py
extensions/maintenance-api/app/api/v1/inventory/transactions.py
extensions/maintenance-api/app/api/v1/inventory/reservations.py
extensions/maintenance-api/app/api/v1/inventory/stocktakes.py
extensions/maintenance-api/app/api/v1/reviews/__init__.py
extensions/maintenance-api/app/api/v1/reviews/router.py
extensions/maintenance-api/app/api/v1/reviews/demand_lists.py
extensions/maintenance-api/app/api/v1/allocations/__init__.py
extensions/maintenance-api/app/api/v1/allocations/router.py
extensions/maintenance-api/app/api/v1/allocations/rules.py
extensions/maintenance-api/app/api/v1/allocations/plans.py
extensions/maintenance-api/alembic/versions/20260724_07_add_inventory_review_allocation.py
extensions/maintenance-api/tests/inventory/test_inventory_models.py
extensions/maintenance-api/tests/inventory/test_inventory_transactions.py
extensions/maintenance-api/tests/inventory/test_fefo_service.py
extensions/maintenance-api/tests/inventory/test_reservation_service.py
extensions/maintenance-api/tests/inventory/test_stocktake_service.py
extensions/maintenance-api/tests/reviews/test_substitution_service.py
extensions/maintenance-api/tests/reviews/test_kit_rule_service.py
extensions/maintenance-api/tests/reviews/test_demand_review_service.py
extensions/maintenance-api/tests/allocation/test_allocation_rule_service.py
extensions/maintenance-api/tests/allocation/test_allocation_simulation_service.py
extensions/maintenance-api/tests/allocation/test_allocation_plan_service.py
extensions/maintenance-api/tests/api/test_inventory_routes.py
extensions/maintenance-api/tests/api/test_review_routes.py
extensions/maintenance-api/tests/api/test_allocation_routes.py
extensions/maintenance-api/tests/integration/test_plan05_inventory_workflow.py
extensions/maintenance-api/tests/migrations/test_inventory_review_allocation_migration.py
frontend/src/api/maintenance/inventory.ts
frontend/src/api/maintenance/reviews.ts
frontend/src/api/maintenance/allocations.ts
frontend/src/stores/maintenance/inventory.ts
frontend/src/stores/maintenance/review.ts
frontend/src/stores/maintenance/allocation.ts
frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue
frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue
frontend/src/views/maintenance/inventory-gap/InventoryTransactionPage.vue
frontend/src/views/maintenance/inventory-gap/StocktakePage.vue
frontend/src/views/maintenance/reviews/ReviewList.vue
frontend/src/views/maintenance/reviews/ReviewDetail.vue
frontend/src/views/maintenance/inventory-gap/AllocationPlanDetail.vue
frontend/src/views/maintenance/inventory-gap/AllocationRulePage.vue
frontend/src/components/maintenance/inventory/InventorySummaryCards.vue
frontend/src/components/maintenance/inventory/InventoryBalanceTable.vue
frontend/src/components/maintenance/inventory/LotSerialSelector.vue
frontend/src/components/maintenance/inventory/InventoryImpactPreview.vue
frontend/src/components/maintenance/inventory/InventoryOperationDialog.vue
frontend/src/components/maintenance/inventory/InventoryLedgerTable.vue
frontend/src/components/maintenance/inventory/StocktakeWizard.vue
frontend/src/components/maintenance/review/ReviewFindingTable.vue
frontend/src/components/maintenance/review/ReviewDecisionDrawer.vue
frontend/src/components/maintenance/review/ReviewImpactSummary.vue
frontend/src/components/maintenance/allocation/AllocationRuleEditor.vue
frontend/src/components/maintenance/allocation/AllocationSimulationComparison.vue
frontend/src/components/maintenance/allocation/AllocationPlanTable.vue
frontend/src/components/maintenance/allocation/AllocationImpactPreview.vue
frontend/src/components/maintenance/allocation/AllocationConflictResolution.vue
frontend/src/components/maintenance/inventory/__tests__/fefo-display.test.ts
frontend/src/components/maintenance/review/__tests__/review-decisions.test.ts
frontend/src/components/maintenance/allocation/__tests__/allocation-score.test.ts
frontend/src/stores/maintenance/__tests__/inventory.test.ts
```

**Modify:**

```text
extensions/maintenance-api/app/models/inventory.py
extensions/maintenance-api/app/models/catalog.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/services/inventory_gap_service.py
extensions/maintenance-api/app/services/ai_review_engine.py
extensions/maintenance-api/app/services/ai_tool_adapters.py
extensions/maintenance-api/config/review-rules.yaml
extensions/maintenance-api/config/ai-tools.yaml
frontend/src/router/maintenance.ts
frontend/src/views/maintenance/master-data/SparePartDetail.vue
frontend/src/i18n/locales/zh-CN.json
frontend/src/i18n/locales/en-US.json
extensions/maintenance-api/README.md
```

---

### Task 1: Add Locations, Lots, Serials, Balances, Transactions and Ledger Models

**Files:**
- Create/modify inventory model files and migration
- Test: inventory model and migration tests

**Interfaces:**
- Produces: `WarehouseLocation`, `InventoryLot`, `SerializedItem`, `InventoryBalance`, `InventoryTransaction`, `InventoryLedgerEntry`.
- Consumed by: Tasks 2–5 and 10.

- [ ] **Step 1: Write failing model tests**

```python
def test_inventory_balance_business_key_includes_tenant_location_lot(session, warehouse, location, spare_part, lot):
    first = InventoryBalance(
        tenant_id="t-1", warehouse_id=warehouse.id, location_id=location.id,
        spare_part_id=spare_part.id, lot_id=lot.id, on_hand_quantity=Decimal("5"),
    )
    session.add(first)
    session.commit()
    duplicate = InventoryBalance(
        tenant_id="t-1", warehouse_id=warehouse.id, location_id=location.id,
        spare_part_id=spare_part.id, lot_id=lot.id, on_hand_quantity=Decimal("1"),
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()


def test_serial_item_has_single_current_location_and_state(serial_item):
    assert serial_item.quantity == Decimal("1")
    assert serial_item.status in {"IN_STOCK", "RESERVED", "ISSUED", "INSTALLED", "AWAITING_REPAIR", "IN_REPAIR", "REPAIRED", "SCRAPPED", "FROZEN"}


def test_ledger_entry_is_immutable(session, ledger_entry):
    ledger_entry.quantity_delta = Decimal("999")
    with pytest.raises(ImmutableResourceError):
        InventoryTransactionRepository().update_ledger_entry(session, "t-1", ledger_entry)
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/inventory/test_inventory_models.py tests/migrations/test_inventory_review_allocation_migration.py -v
```

Expected: FAIL because the detailed inventory schema does not exist.

- [ ] **Step 3: Implement the model contract**

Required tables:

```text
warehouse_locations:
id, tenant_id, warehouse_id, code, name, location_type, is_pickable,
is_active, version, created_at, updated_at

inventory_lots:
id, tenant_id, spare_part_id, lot_code, manufacture_date,
received_date, expiry_date, quality_status, is_frozen, freeze_reason,
version, created_at, updated_at

serialized_items:
id, tenant_id, spare_part_id, serial_number, lot_id, warehouse_id,
location_id, status, equipment_id, installation_position,
version, created_at, updated_at

inventory_balances:
id, tenant_id, warehouse_id, location_id, spare_part_id, lot_id,
on_hand_quantity, reserved_quantity, damaged_quantity,
quarantined_quantity, in_transit_quantity, version, updated_at

inventory_transactions:
id, tenant_id, transaction_type, status, idempotency_key,
reference_type, reference_id, reason, created_by, confirmed_by,
created_at, confirmed_at

inventory_ledger_entries:
id, tenant_id, transaction_id, spare_part_id, warehouse_id,
location_id, lot_id, serial_item_id, quantity_delta,
reserved_delta, damaged_delta, quarantined_delta, in_transit_delta,
resulting_balance_version, created_at
```

Checks:

- lot expiry cannot precede manufacture or receipt date;
- serial number is unique per tenant and spare part;
- serial-tracked item transactions use quantity one;
- balance components remain nonnegative and allocated quantities do not exceed on-hand;
- ledger entries have a nonzero delta in at least one quantity field;
- transaction status is `PREVIEWED`, `CONFIRMED`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, or `REVERSED`.

Migrate existing `warehouse_inventories` rows into default location `DEFAULT` and lot `NULL`, preserving quantities. Retain the old table as a compatibility view or remove it only after all services and tests use `inventory_balances`.

- [ ] **Step 4: Run migration and model tests**

```powershell
python -m alembic upgrade head
python -m pytest tests/inventory/test_inventory_models.py tests/migrations/test_inventory_review_allocation_migration.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
```

Expected: PASS with migrated aggregate balances preserved.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/inventory.py extensions/maintenance-api/app/models/inventory_operations.py extensions/maintenance-api/app/models/enums.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260724_07_add_inventory_review_allocation.py extensions/maintenance-api/tests/inventory/test_inventory_models.py extensions/maintenance-api/tests/migrations/test_inventory_review_allocation_migration.py
git commit -m "feat: add detailed inventory ledger schema"
```

---

### Task 2: Implement Transactional Inventory Operations

**Files:**
- Create: inventory operation schemas, repositories and service
- Test: `tests/inventory/test_inventory_transactions.py`

**Interfaces:**
- Produces: `InventoryTransactionService.preview(request)`, `execute(request, confirmation)`, operation types `RECEIPT`, `RESERVE`, `UNRESERVE`, `ISSUE`, `RETURN`, `TRANSFER`, `FREEZE`, `UNFREEZE`, `ADJUST`, `REVERSE`.
- Consumed by: Tasks 3–5 and frontend Task 10.

- [ ] **Step 1: Write failing transaction tests**

```python
def test_issue_updates_balance_and_creates_immutable_ledger(session, actor_contributor, balance):
    service = InventoryTransactionService()
    preview = service.preview(session, actor_contributor, issue_request(balance, Decimal("2")))
    result = service.execute(session, actor_contributor, preview.transaction_id, expected_versions={str(balance.id): balance.version}, confirmation_token=preview.confirmation_token)
    session.refresh(balance)
    assert result.status == "COMPLETED"
    assert balance.on_hand_quantity == Decimal("8")
    assert result.entries[0].quantity_delta == Decimal("-2")


def test_execute_revalidates_and_rejects_changed_balance(session, actor_contributor, balance):
    service = InventoryTransactionService()
    preview = service.preview(session, actor_contributor, issue_request(balance, Decimal("2")))
    balance.version += 1
    session.commit()
    with pytest.raises(VersionConflictError):
        service.execute(session, actor_contributor, preview.transaction_id, expected_versions={str(balance.id): preview.balance_versions[str(balance.id)]}, confirmation_token=preview.confirmation_token)


def test_duplicate_idempotency_key_does_not_issue_twice(session, actor_contributor, balance):
    first = execute_issue(session, actor_contributor, balance, key="k-1")
    second = execute_issue(session, actor_contributor, balance, key="k-1")
    assert first.transaction_id == second.transaction_id
    assert balance.on_hand_quantity == Decimal("8")
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/inventory/test_inventory_transactions.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement preview and execute services**

```python
class InventoryOperationLine(BaseModel):
    spare_part_id: int
    source_warehouse_id: int
    source_location_id: int
    source_lot_id: int | None = None
    serial_item_ids: list[int] = Field(default_factory=list)
    target_warehouse_id: int | None = None
    target_location_id: int | None = None
    quantity: Decimal = Field(gt=0)
    expected_balance_version: int
    manual_selection_reason: str | None = None


class InventoryOperationRequest(BaseModel):
    operation: InventoryOperationType
    reference_type: str
    reference_id: str
    reason: str = Field(min_length=1, max_length=500)
    lines: list[InventoryOperationLine] = Field(min_length=1)
```

Execution algorithm:

```text
load preview transaction by tenant
→ verify actor role and confirmation token
→ verify idempotency request hash
→ lock/reload all affected balances in deterministic ID order
→ verify expected versions and available quantities
→ validate lot, serial, freeze, expiry and configuration rules
→ append ledger entries
→ update balance projections and serial states
→ mark transaction completed or partially completed
→ audit in same database transaction
→ commit once
```

Use `SELECT ... FOR UPDATE` on PostgreSQL; on SQLite use `BEGIN IMMEDIATE` through a transaction helper so tests model write serialization.

- [ ] **Step 4: Run tests and lint**

```powershell
python -m pytest tests/inventory/test_inventory_transactions.py -v
python -m ruff check app/services/inventory_transaction_service.py app/repositories/inventory_transaction_repository.py tests/inventory/test_inventory_transactions.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/inventory_operations.py extensions/maintenance-api/app/repositories/inventory_balance_repository.py extensions/maintenance-api/app/repositories/inventory_transaction_repository.py extensions/maintenance-api/app/services/inventory_transaction_service.py extensions/maintenance-api/tests/inventory/test_inventory_transactions.py
git commit -m "feat: add transactional inventory operations"
```

---

### Task 3: Implement FEFO and Expiry Threshold Rules

**Files:**
- Create: `app/services/fefo_service.py`
- Modify: spare-part/catalog schemas and models for tracking mode and thresholds
- Test: `tests/inventory/test_fefo_service.py`

**Interfaces:**
- Produces: `FefoService.recommend(...) -> list[StockSelection]`, tenant/category/item expiry threshold resolution.
- Consumed by: Tasks 4 and 9.

- [ ] **Step 1: Write failing FEFO tests**

```python
def test_fefo_selects_earliest_valid_expiry(session, actor_viewer, stocked_lots):
    result = FefoService().recommend(session, actor_viewer, spare_part_id=stocked_lots.part_id, quantity=Decimal("6"), as_of=date(2026, 7, 24))
    assert [(line.lot_code, line.quantity) for line in result] == [("LOT-30D", Decimal("4")), ("LOT-90D", Decimal("2"))]


def test_fefo_excludes_expired_frozen_and_quarantined(session, actor_viewer, risky_lots):
    result = FefoService().recommend(session, actor_viewer, risky_lots.part_id, Decimal("2"), date(2026, 7, 24))
    assert {line.lot_code for line in result}.isdisjoint({"EXPIRED", "FROZEN", "QUARANTINED"})


def test_item_override_beats_category_and_system_thresholds(session, actor_viewer, expiry_settings):
    thresholds = ExpiryThresholdService().resolve(session, actor_viewer, expiry_settings.item_id)
    assert thresholds == [120, 60, 15]
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/inventory/test_fefo_service.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement deterministic selection**

```python
eligible.sort(key=lambda stock: (
    stock.expiry_date or date.max,
    stock.received_date or date.max,
    stock.lot_code or "",
    stock.balance_id,
))
```

Selection rules:

- filter tenant, active warehouse/location, pickable location, positive available quantity;
- reject expired, frozen, quarantined and damaged stock;
- reject incompatible equipment/configuration when allocation context provides it;
- allocate earliest expiry first, then earliest receipt, then stable IDs;
- non-expiring stock sorts after expiring valid stock;
- manual override must retain recommended selection and override reason in the eventual transaction.

Threshold precedence:

```text
item override → category setting → tenant setting → system defaults [180, 90, 30]
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/inventory/test_fefo_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/fefo_service.py extensions/maintenance-api/app/models/catalog.py extensions/maintenance-api/app/schemas/inventory_operations.py extensions/maintenance-api/tests/inventory/test_fefo_service.py
git commit -m "feat: recommend fefo inventory selections"
```

---

### Task 4: Add Reservation, Issue, Return and Transfer Workflows

**Files:**
- Create: reservation service and inventory routers
- Modify: transaction service
- Test: reservation and API tests

**Interfaces:**
- Produces: preview/execute endpoints for reserve, unreserve, issue, return, transfer, freeze and adjustment.
- Consumed by: Task 9 and frontend Task 10.

- [ ] **Step 1: Write failing reservation tests**

```python
def test_reservation_reduces_available_not_on_hand(session, actor_contributor, balance):
    result = ReservationService().reserve(session, actor_contributor, reservation_request(balance, Decimal("3")))
    session.refresh(balance)
    assert balance.on_hand_quantity == Decimal("10")
    assert balance.reserved_quantity == Decimal("3")
    assert balance.available_quantity == Decimal("7")
    assert result.status == "ACTIVE"


def test_issue_against_reservation_reduces_both_on_hand_and_reserved(session, actor_contributor, active_reservation):
    issue = ReservationService().issue_reserved(session, actor_contributor, active_reservation.id, Decimal("2"), expected_version=active_reservation.version)
    assert issue.status == "COMPLETED"
    assert issue.balance.on_hand_quantity == Decimal("8")
    assert issue.balance.reserved_quantity == Decimal("1")


def test_partial_batch_conflict_executes_uncontested_lines(session, actor_contributor, reservation_plan_with_one_stale_line):
    result = ReservationService().execute_plan(session, actor_contributor, reservation_plan_with_one_stale_line.id)
    assert result.status == "PARTIALLY_COMPLETED"
    assert [line.status for line in result.lines].count("COMPLETED") == 1
    assert [line.status for line in result.lines].count("CONFLICT") == 1
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/inventory/test_reservation_service.py tests/api/test_inventory_routes.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement reservation entities and endpoints**

Reservation records:

```text
inventory_reservations:
id, tenant_id, reference_type, reference_id, spare_part_id,
warehouse_id, location_id, lot_id, serial_item_id,
quantity, status, expires_at, created_by, released_by,
version, created_at, updated_at
```

Endpoints:

```text
GET  /api/v1/inventory/balances
GET  /api/v1/inventory/balances/{id}
GET  /api/v1/inventory/ledger
POST /api/v1/inventory/operations/preview
POST /api/v1/inventory/operations/{transaction_id}/execute
POST /api/v1/inventory/reservations/preview
POST /api/v1/inventory/reservations/{plan_id}/execute
POST /api/v1/inventory/reservations/{id}/release
POST /api/v1/inventory/reservations/{id}/issue
```

Role policy:

- viewer: GET only;
- contributor: reserve, unreserve, issue, return;
- admin: transfer, freeze, unfreeze, adjust and reverse.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/inventory/test_reservation_service.py tests/api/test_inventory_routes.py -v
python -m ruff check app/api/v1/inventory app/services/reservation_service.py tests/inventory/test_reservation_service.py tests/api/test_inventory_routes.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/reservation_service.py extensions/maintenance-api/app/api/v1/inventory extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/app/models/inventory_operations.py extensions/maintenance-api/app/schemas/inventory_operations.py extensions/maintenance-api/tests/inventory/test_reservation_service.py extensions/maintenance-api/tests/api/test_inventory_routes.py
git commit -m "feat: add maintenance inventory reservation workflows"
```

---

### Task 5: Add Basic Stocktake Tasks and Difference Confirmation

**Files:**
- Create: stocktake repository/service and API endpoints
- Test: `tests/inventory/test_stocktake_service.py`

**Interfaces:**
- Produces: stocktake lifecycle `DRAFT → COUNTING → DIFFERENCE_REVIEW → CONFIRMED → CANCELLED`.
- Consumed by: frontend Task 10.

- [ ] **Step 1: Write failing stocktake tests**

```python
def test_stocktake_snapshot_records_scope_and_balance_versions(session, actor_admin, stocktake_scope):
    task = StocktakeService().create(session, actor_admin, stocktake_scope)
    started = StocktakeService().start(session, actor_admin, task.id, expected_version=1)
    assert started.status == "COUNTING"
    assert all(line.snapshot_balance_version >= 1 for line in started.lines)


def test_confirmation_detects_intervening_inventory_transaction(session, actor_admin, counting_stocktake):
    transact_against(counting_stocktake.lines[0].balance_id, session)
    with pytest.raises(StocktakeConflictError) as exc:
        StocktakeService().confirm(session, actor_admin, counting_stocktake.id, expected_version=counting_stocktake.version)
    assert counting_stocktake.lines[0].balance_id in exc.value.conflicting_balance_ids


def test_confirmed_difference_creates_adjustment_ledger(session, actor_admin, reviewed_stocktake):
    result = StocktakeService().confirm(session, actor_admin, reviewed_stocktake.id, expected_version=reviewed_stocktake.version)
    assert result.status == "CONFIRMED"
    assert result.adjustment_transaction.transaction_type == "ADJUST"
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/inventory/test_stocktake_service.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement stocktake tables and state machine**

```text
stocktake_tasks:
id, tenant_id, code, scope_json, status, snapshot_at,
created_by, confirmed_by, version, created_at, updated_at

stocktake_lines:
id, tenant_id, task_id, balance_id, serial_item_id,
snapshot_balance_version, book_quantity, counted_quantity,
difference_quantity, reason_code, reason_text, status
```

Confirmation reloads current balances. If a balance version differs from the snapshot, return `409 STOCKTAKE_BALANCE_CHANGED` with affected lines and require recount/rebase. Differences are posted through `InventoryTransactionService` as one adjustment transaction.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/inventory/test_stocktake_service.py tests/api/test_inventory_routes.py -k stocktake -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/stocktake_repository.py extensions/maintenance-api/app/services/stocktake_service.py extensions/maintenance-api/app/models/inventory_operations.py extensions/maintenance-api/app/schemas/inventory_operations.py extensions/maintenance-api/app/api/v1/inventory/stocktakes.py extensions/maintenance-api/tests/inventory/test_stocktake_service.py
git commit -m "feat: add maintenance stocktake workflow"
```

---

### Task 6: Add Substitution and Kit Rule Management

**Files:**
- Create: substitution and kit model/schema/repository/service files
- Modify: models init and migration
- Test: substitution and kit tests

**Interfaces:**
- Produces: active substitution candidates and deterministic kit-rule evaluation.
- Consumed by: Task 7 and Task 9.

- [ ] **Step 1: Write failing rule tests**

```python
def test_one_way_substitution_does_not_reverse(session, actor_viewer, one_way_relation):
    service = SubstitutionService()
    assert service.candidates(session, actor_viewer, one_way_relation.source_id, context={})[0].spare_part_id == one_way_relation.target_id
    assert service.candidates(session, actor_viewer, one_way_relation.target_id, context={}) == []


def test_prohibited_co_use_creates_blocking_finding(session, actor_viewer, prohibited_relation):
    result = KitRuleService().evaluate(session, actor_viewer, demand_items([
        (prohibited_relation.left_id, 1), (prohibited_relation.right_id, 1),
    ]))
    assert result.findings[0].code == "PROHIBITED_CO_USE"
    assert result.findings[0].severity == "BLOCKING"


def test_ratio_rule_suggests_exact_adjustment(session, actor_viewer, ratio_rule):
    result = KitRuleService().evaluate(session, actor_viewer, demand_items([(ratio_rule.parent_id, 3), (ratio_rule.child_id, 4)]))
    finding = next(item for item in result.findings if item.code == "KIT_RATIO_SHORTAGE")
    assert finding.suggested_quantity == Decimal("6")
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/reviews/test_substitution_service.py tests/reviews/test_kit_rule_service.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement relationship contracts**

Substitution types:

```text
INTERCHANGEABLE
ONE_WAY
NEW_REPLACES_OLD
TEMPORARY
PROHIBITED_CO_USE
```

Fields include ratio, priority, equipment/configuration applicability, task stage, validity dates, evidence, risk and status.

Kit rule types:

```text
REQUIRED_COMPANION
KIT
QUANTITY_RATIO
MUTUALLY_EXCLUSIVE
CONDITIONAL_TRIGGER
SHARED_CONSTRAINT
```

Services return candidate or finding objects; they never mutate demand lists or inventory.

- [ ] **Step 4: Run tests and migration**

```powershell
python -m alembic upgrade head
python -m pytest tests/reviews/test_substitution_service.py tests/reviews/test_kit_rule_service.py tests/migrations/test_inventory_review_allocation_migration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/substitution.py extensions/maintenance-api/app/models/kit_rule.py extensions/maintenance-api/app/schemas/substitution.py extensions/maintenance-api/app/schemas/kit_rule.py extensions/maintenance-api/app/repositories/substitution_repository.py extensions/maintenance-api/app/repositories/kit_rule_repository.py extensions/maintenance-api/app/services/substitution_service.py extensions/maintenance-api/app/services/kit_rule_service.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260724_07_add_inventory_review_allocation.py extensions/maintenance-api/tests/reviews/test_substitution_service.py extensions/maintenance-api/tests/reviews/test_kit_rule_service.py
git commit -m "feat: add substitution and kit rules"
```

---

### Task 7: Add Deterministic Demand List Review and Derived Versions

**Files:**
- Create: demand review model/schema/repository/service/router
- Modify: review rules config and AI review adapter
- Test: demand review and API tests

**Interfaces:**
- Produces: review run, findings, decisions and `generate-derived-version`.
- Consumed by: frontend Task 11 and allocation Task 9.

- [ ] **Step 1: Write failing review tests**

```python
def test_review_finds_configuration_and_kit_problems(session, actor_contributor, published_demand_list):
    review = DemandReviewService().run(session, actor_contributor, published_demand_list.id)
    codes = {finding.rule_code for finding in review.findings}
    assert {"CONFIGURATION_INAPPLICABLE", "KIT_RATIO_SHORTAGE"} <= codes


def test_finding_decisions_do_not_modify_source_list(session, actor_contributor, review_with_suggestion):
    source_quantity = review_with_suggestion.source_list.items[0].selected_quantity
    DemandReviewService().decide(session, actor_contributor, review_with_suggestion.findings[0].id, decision="ACCEPT", edited_quantity=None, reason="Apply rule")
    session.refresh(review_with_suggestion.source_list.items[0])
    assert review_with_suggestion.source_list.items[0].selected_quantity == source_quantity


def test_generate_derived_version_applies_accepted_decisions(session, actor_contributor, completed_review):
    derived = DemandReviewService().generate_derived_version(session, actor_contributor, completed_review.id)
    assert derived.previous_version_id == completed_review.source_demand_list_id
    assert derived.status == "DRAFT"
    assert derived.items[0].source_type == "RULE_CORRECTION"
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/reviews/test_demand_review_service.py tests/api/test_review_routes.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement review workflow**

Review rules cover:

```text
DATA_INCOMPLETE
CONFIGURATION_INAPPLICABLE
KIT_REQUIRED_MISSING
KIT_RATIO_SHORTAGE
MUTUALLY_EXCLUSIVE
PROHIBITED_CO_USE
DUPLICATE_SHARED_ITEM
SUBSTITUTION_INVALID
RELIABILITY_PARAMETER_RISK
MODEL_RESULT_OUTLIER
INVENTORY_SUPPORT_RISK
EVIDENCE_MISSING_OR_STALE
```

Finding fields:

```text
rule_code, rule_version, severity, blocking,
spare_part_id, observed_json, expected_json,
evidence_refs, suggested_action, suggested_quantity,
decision(PENDING|ACCEPTED|REJECTED|EDITED),
decision_reason, decided_by, decided_at
```

A review may be saved with unresolved findings. `generate-derived-version` is blocked when any blocking finding is pending. AI may explain findings but cannot change rule result, severity or suggested numeric quantity.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/reviews/test_demand_review_service.py tests/api/test_review_routes.py tests/services/test_ai_review_engine.py -v
python -m ruff check app/services/demand_review_service.py app/api/v1/reviews tests/reviews tests/api/test_review_routes.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/demand_review.py extensions/maintenance-api/app/schemas/demand_review.py extensions/maintenance-api/app/repositories/demand_review_repository.py extensions/maintenance-api/app/services/demand_review_service.py extensions/maintenance-api/app/api/v1/reviews extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/config/review-rules.yaml extensions/maintenance-api/app/services/ai_review_engine.py extensions/maintenance-api/app/services/ai_tool_adapters.py extensions/maintenance-api/tests/reviews/test_demand_review_service.py extensions/maintenance-api/tests/api/test_review_routes.py
git commit -m "feat: add deterministic demand list review"
```

---

### Task 8: Add Versioned Allocation Rules and Safe Simulation

**Files:**
- Create: allocation model/schema/repository/rule/simulation files and routes
- Modify: migration and models init
- Test: allocation rule and simulation tests

**Interfaces:**
- Produces: rule lifecycle `DRAFT → SIMULATED → PUBLISHED → RETIRED`, deterministic score function, simulation comparison.
- Consumed by: Task 9 and frontend Task 12.

- [ ] **Step 1: Write failing rule and simulation tests**

```python
def test_hard_rule_excludes_frozen_and_below_safety_stock(session, actor_admin, allocation_context):
    result = AllocationRuleService().rank(session, actor_admin, allocation_context)
    assert all(not candidate.is_frozen for candidate in result.candidates)
    assert all(candidate.remaining_after >= candidate.minimum_safety_stock for candidate in result.candidates)


def test_weighted_score_is_reproducible(session, actor_admin, published_rule, candidate):
    first = AllocationRuleService().score(published_rule, candidate)
    second = AllocationRuleService().score(published_rule, candidate)
    assert first == second
    assert first.total == sum(component.weighted_value for component in first.components)


def test_simulation_does_not_write_reservations_or_balances(session, actor_admin, draft_rule, simulation_sample):
    before = inventory_fingerprint(session)
    simulation = AllocationSimulationService().run(session, actor_admin, draft_rule.id, simulation_sample)
    after = inventory_fingerprint(session)
    assert simulation.status == "COMPLETED"
    assert before == after


def test_rule_cannot_publish_without_successful_simulation(session, actor_admin, draft_rule):
    with pytest.raises(InvalidStateTransitionError):
        AllocationRuleService().publish(session, actor_admin, draft_rule.id, expected_version=draft_rule.version)
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/allocation/test_allocation_rule_service.py tests/allocation/test_allocation_simulation_service.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement rule and simulation contracts**

Rule fields:

```text
id, tenant_id, lineage_id, version_number, status,
hard_rules_json, weights_json, normalization_json,
applicable_task_types_json, applicable_categories_json,
effective_from, effective_to, change_reason,
created_by, published_by, version, created_at, updated_at
```

Default weights sum to 1.0:

```python
DEFAULT_WEIGHTS = {
    "support_level": Decimal("0.20"),
    "urgency": Decimal("0.20"),
    "planned_start": Decimal("0.15"),
    "item_criticality": Decimal("0.15"),
    "mission_impact": Decimal("0.15"),
    "current_fulfillment": Decimal("0.05"),
    "substitute_availability": Decimal("0.05"),
    "replenishment_time": Decimal("0.05"),
}
```

Simulation stores old/new result snapshots, affected tasks, fulfillment changes, safety-stock changes, largest differences, hard-rule violations and incomplete sample warnings. Publishing is blocked for hard-rule violation, invalid weight total, missing sample, high-priority degradation beyond configured tolerance, or incomplete simulation.

- [ ] **Step 4: Run tests and migration**

```powershell
python -m alembic upgrade head
python -m pytest tests/allocation/test_allocation_rule_service.py tests/allocation/test_allocation_simulation_service.py tests/migrations/test_inventory_review_allocation_migration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/allocation.py extensions/maintenance-api/app/schemas/allocation.py extensions/maintenance-api/app/repositories/allocation_repository.py extensions/maintenance-api/app/services/allocation_rule_service.py extensions/maintenance-api/app/services/allocation_simulation_service.py extensions/maintenance-api/app/api/v1/allocations extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260724_07_add_inventory_review_allocation.py extensions/maintenance-api/tests/allocation/test_allocation_rule_service.py extensions/maintenance-api/tests/allocation/test_allocation_simulation_service.py
git commit -m "feat: add simulated allocation rule versions"
```

---

### Task 9: Generate and Execute Allocation Plans

**Files:**
- Create: allocation plan service and routes
- Modify: inventory gap service and AI tools
- Test: allocation plan and API tests

**Interfaces:**
- Produces: allocation plan lifecycle `DRAFT → PREVIEWED → CONFIRMED → EXECUTING → COMPLETED|PARTIALLY_COMPLETED|FAILED|VOIDED`.
- Consumed by: frontend Task 12 and final acceptance.

- [ ] **Step 1: Write failing allocation tests**

```python
def test_plan_combines_original_substitute_in_transit_and_repair_supply(session, actor_contributor, published_list, stock_context):
    plan = AllocationPlanService().generate(session, actor_contributor, published_list.id)
    line = plan.line_for(stock_context.part_id)
    assert line.original_allocated == Decimal("4")
    assert line.substitute_recommended == Decimal("2")
    assert line.in_transit_quantity == Decimal("1")
    assert line.expected_repair_quantity == Decimal("1")
    assert line.remaining_gap == Decimal("0")


def test_substitute_is_not_counted_until_confirmed(session, actor_contributor, plan_with_substitute):
    line = plan_with_substitute.lines[0]
    assert line.substitute_confirmed_quantity == Decimal("0")
    assert line.fulfillment_status == "PARTIAL"
    updated = AllocationPlanService().confirm_substitute(session, actor_contributor, plan_with_substitute.id, line.id, quantity=line.substitute_recommended, reason="Approved equivalent", expected_version=plan_with_substitute.version)
    assert updated.lines[0].substitute_confirmed_quantity == line.substitute_recommended


def test_execute_revalidates_and_returns_line_conflicts(session, actor_contributor, plan_with_changed_stock):
    result = AllocationPlanService().execute(session, actor_contributor, plan_with_changed_stock.id, expected_version=plan_with_changed_stock.version)
    assert result.status == "PARTIALLY_COMPLETED"
    assert any(line.status == "CONFLICT" and line.error_code == "INVENTORY_VERSION_CHANGED" for line in result.lines)
    assert any(line.status == "COMPLETED" for line in result.lines)
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/allocation/test_allocation_plan_service.py tests/api/test_allocation_routes.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement plan generation and execution**

Plan line fields:

```text
spare_part_id, demand_quantity, available_quantity, net_gap,
original_allocated, substitute_recommended, substitute_confirmed,
in_transit_quantity, expected_repair_quantity,
recommended_selections_json, fulfillment_status,
other_task_impact_json, safety_stock_impact,
expiry_risk, transfer_risk, repair_risk,
manual_adjustment_json, status, error_code
```

Generation:

```text
load current published demand list
→ load published allocation rule version
→ aggregate eligible stock by FEFO
→ rank competing tasks with hard rules and score
→ compute original allocation
→ recommend substitutions without counting them as confirmed
→ expose in-transit and expected repair separately
→ calculate remaining gap and risks
→ snapshot balance versions and rule version
```

Execution calls `ReservationService` for each confirmed line. It revalidates all selections, allows nonconflicting lines to complete, and stores a differential regeneration link for conflict lines.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/allocation/test_allocation_plan_service.py tests/api/test_allocation_routes.py tests/inventory/test_reservation_service.py -v
python -m ruff check app/services/allocation_plan_service.py app/api/v1/allocations tests/allocation tests/api/test_allocation_routes.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/allocation_plan_service.py extensions/maintenance-api/app/api/v1/allocations/plans.py extensions/maintenance-api/app/services/inventory_gap_service.py extensions/maintenance-api/app/services/ai_tool_adapters.py extensions/maintenance-api/config/ai-tools.yaml extensions/maintenance-api/tests/allocation/test_allocation_plan_service.py extensions/maintenance-api/tests/api/test_allocation_routes.py
git commit -m "feat: generate and execute inventory allocation plans"
```

---

### Task 10: Build Inventory Balance, Operation, Ledger and Stocktake UI

**Files:**
- Create: inventory API/store/views/components listed in file map
- Modify: spare-part detail inventory tabs and routes
- Test: FEFO display and inventory store tests

**Interfaces:**
- Consumes: inventory APIs from Tasks 1–5.
- Produces: inventory gap workspace and operation dialogs.

- [ ] **Step 1: Write failing frontend tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { sortFefoSelections, operationCapabilities } from '../inventory-ui'


test('display sort matches backend FEFO order', () => {
  const rows = [
    { id: 2, expiry_date: '2027-01-01', received_date: '2026-01-01' },
    { id: 1, expiry_date: '2026-09-01', received_date: '2026-02-01' },
  ]
  assert.deepEqual(sortFefoSelections(rows).map(row => row.id), [1, 2])
})

test('contributor and admin operation capabilities differ', () => {
  assert.deepEqual(operationCapabilities('contributor'), ['reserve', 'unreserve', 'issue', 'return'])
  assert.deepEqual(operationCapabilities('admin'), ['reserve', 'unreserve', 'issue', 'return', 'transfer', 'freeze', 'unfreeze', 'adjust', 'stocktake'])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/components/maintenance/inventory/__tests__/fefo-display.test.ts src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement inventory screens**

`InventoryGapPage.vue` includes summary cards, filters, balance table, gap columns and links to allocation plans.

`InventoryOperationDialog.vue` flow:

```text
select operation
→ select item/location/lot/serial
→ show backend recommendation and FEFO reason
→ enter quantity and reason
→ call preview
→ display before/after and other-task impact
→ confirm
→ execute with idempotency key and expected versions
→ display per-line result
```

Stocktake wizard follows create scope → snapshot → count → differences → reasons → admin confirmation. It displays conflicts and does not hide changed balances.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/inventory/__tests__/fefo-display.test.ts src/stores/maintenance/__tests__/inventory.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/inventory.ts frontend/src/stores/maintenance/inventory.ts frontend/src/views/maintenance/inventory-gap frontend/src/components/maintenance/inventory frontend/src/views/maintenance/master-data/SparePartDetail.vue frontend/src/router/maintenance.ts
git commit -m "feat: add inventory operations and stocktake ui"
```

---

### Task 11: Build Demand Review UI

**Files:**
- Create: review API/store/views/components
- Test: review decision tests

**Interfaces:**
- Consumes: deterministic review API from Task 7.
- Produces: review list/detail, per-finding decisions and derived version action.

- [ ] **Step 1: Write failing decision reducer tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { reviewDecisionReducer } from '../review-decisions'


test('edited acceptance requires a positive quantity and reason', () => {
  const result = reviewDecisionReducer({ severity: 'HIGH', suggested_quantity: 6 }, { type: 'EDIT_ACCEPT', quantity: 0, reason: '' })
  assert.equal(result.valid, false)
})

test('blocking pending finding prevents derived version', () => {
  const result = canGenerateDerivedVersion([
    { blocking: true, decision: 'PENDING' },
    { blocking: false, decision: 'ACCEPTED' },
  ])
  assert.equal(result, false)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/review/__tests__/review-decisions.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement review screens**

Review detail displays:

- source demand-list version;
- finding counts by severity and blocking state;
- filterable finding table;
- observed/expected values, evidence and deterministic rule version;
- AI explanation as a separate non-authoritative panel;
- accept, reject, edit-and-accept and batch accept actions;
- impact summary before creating a derived version.

High-risk unresolved findings allow saving but keep the “生成调整版本” action disabled.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/review/__tests__/review-decisions.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/reviews.ts frontend/src/stores/maintenance/review.ts frontend/src/views/maintenance/reviews frontend/src/components/maintenance/review frontend/src/router/maintenance.ts
git commit -m "feat: add demand review decision ui"
```

---

### Task 12: Build Allocation Rule, Simulation and Plan UI

**Files:**
- Create: allocation API/store/views/components
- Test: allocation score/presentation tests

**Interfaces:**
- Consumes: rule/simulation/plan APIs from Tasks 8–9.
- Produces: admin rule editor, simulation comparison, allocation plan confirmation.

- [ ] **Step 1: Write failing score presentation tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { validateWeights, allocationStatusActions } from '../allocation-ui'


test('weights must sum to one', () => {
  assert.equal(validateWeights({ urgency: 0.5, criticality: 0.5 }).valid, true)
  assert.equal(validateWeights({ urgency: 0.5, criticality: 0.4 }).valid, false)
})

test('draft rule must simulate before publish action appears', () => {
  assert.deepEqual(allocationStatusActions({ role: 'admin', status: 'DRAFT', successfulSimulation: false }), ['edit', 'simulate', 'retire'])
  assert.deepEqual(allocationStatusActions({ role: 'admin', status: 'SIMULATED', successfulSimulation: true }), ['edit', 'simulate', 'publish', 'retire'])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/allocation/__tests__/allocation-score.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement allocation UI**

Rule page is admin-only for writes and includes hard-rule switches, weight editor, applicability conditions, version history and simulation sample selection.

Simulation comparison shows old/new allocations, fulfillment changes, safety-stock changes, benefited/damaged tasks, largest differences, hard-rule violations and publication blockers.

Allocation plan detail shows:

- demand, eligible original stock and gap;
- warehouse/location/lot/serial recommendations;
- substitute recommendation and confirmation state;
- in-transit and expected repair separately;
- other-task and safety-stock impact;
- conflict lines and regeneration action;
- second confirmation before reservation execution.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/allocation/__tests__/allocation-score.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/allocations.ts frontend/src/stores/maintenance/allocation.ts frontend/src/views/maintenance/inventory-gap/AllocationPlanDetail.vue frontend/src/views/maintenance/inventory-gap/AllocationRulePage.vue frontend/src/components/maintenance/allocation frontend/src/router/maintenance.ts
git commit -m "feat: add allocation simulation and confirmation ui"
```

---

### Task 13: Verify the Complete Inventory Workflow

**Files:**
- Create: `tests/integration/test_plan05_inventory_workflow.py`
- Modify: README and operational docs

**Interfaces:**
- Produces: verified published-list-to-reservation vertical slice.

- [ ] **Step 1: Write the full integration test**

```python
def test_published_list_review_allocation_and_inventory_execution(client, contributor_headers, admin_headers, published_demand_list, seeded_inventory):
    review = client.post(f"/api/v1/reviews/demand-lists/{published_demand_list.id}/run", headers=contributor_headers).json()["data"]
    decide_all_findings(client, contributor_headers, review)
    derived = client.post(f"/api/v1/reviews/{review['id']}/generate-derived-version", headers=contributor_headers).json()["data"]
    publish_demand_list(client, admin_headers, derived)

    plan = client.post("/api/v1/allocations/plans", headers=contributor_headers, json={"demand_list_id": derived["id"]}).json()["data"]
    confirm_substitutions(client, contributor_headers, plan)
    preview = client.post(f"/api/v1/allocations/plans/{plan['id']}/preview", headers=contributor_headers, json={"expected_version": plan["version"]}).json()["data"]
    executed = client.post(
        f"/api/v1/allocations/plans/{plan['id']}/execute",
        headers={**contributor_headers, "Idempotency-Key": "acceptance-plan-1"},
        json={"expected_version": preview["version"], "confirmation_token": preview["confirmation_token"]},
    ).json()["data"]
    assert executed["status"] in {"COMPLETED", "PARTIALLY_COMPLETED"}
    assert ledger_matches_reservations(client, contributor_headers, executed)
```

- [ ] **Step 2: Run and fix only approved-scope integration defects**

```powershell
cd extensions\maintenance-api
python -m pytest tests/integration/test_plan05_inventory_workflow.py -v
```

Expected: PASS.

- [ ] **Step 3: Document inventory invariants and operator recovery**

Document:

- quantity definitions;
- FEFO and override reasons;
- lot/serial states;
- preview/execute/idempotency behavior;
- partial conflicts and differential regeneration;
- stocktake conflict recovery;
- review and derived versions;
- rule simulation and publication blockers;
- allocation plan/reservation separation.

- [ ] **Step 4: Run final Phase 05-4 gate**

```powershell
cd extensions\maintenance-api
python -m alembic upgrade head
python -m pytest tests/inventory tests/reviews tests/allocation tests/api/test_inventory_routes.py tests/api/test_review_routes.py tests/api/test_allocation_routes.py tests/integration/test_plan05_inventory_workflow.py -v
python -m ruff check app tests
cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

Expected: all tests pass, Ruff clean, frontend build succeeds, no negative balance or duplicate execution test fails.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/tests/integration/test_plan05_inventory_workflow.py extensions/maintenance-api/README.md
git commit -m "test: verify inventory review allocation workflow"
```

## Phase Completion Evidence

Attach:

- lot, expiry and serial tracking screenshots;
- FEFO recommendation and manual override reason;
- reservation, issue, return and transfer before/after previews;
- partial conflict result and differential regeneration;
- stocktake difference and changed-balance conflict;
- review findings, decisions and derived version;
- old/new allocation rule simulation;
- multi-task competition allocation and user confirmation;
- inventory ledger entries matching all executed operations;
- complete test, migration, Ruff and frontend build output.

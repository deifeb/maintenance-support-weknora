# Plan 05-4B Inventory Lot Concurrency Read Contract Amendment Design

**Document status:** DRAFT — awaiting explicit user approval
**Design date:** 2026-08-16
**Target branch:** `codex/maintenance-plan05-4b`
**Frozen backend baseline:** `4cc20eebf85d621d32d95143309b3925e96f349e`
**Parent frontend design SHA256:** `fdd845a24cd1781e59dec5222d1861d52c86b7dc60f480abec3e06cb0b020b68`
**Affected frontend implementation-plan draft SHA256:** `36cb4941fb0855edb1d98dc37fe7cdc41bb63990df11177e4a46bd1d1a75caa1`
**Intended repository path:** `docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment-design.md`

---

## 1. Purpose

This amendment resolves one narrow public-contract gap discovered while writing the Plan 05-4B Frontend Inventory Gap implementation plan:

- `FREEZE` and `UNFREEZE` require a caller-supplied `expected_lot_version`;
- execute revalidates the tenant-scoped `InventoryLot.version`;
- the current public Inventory balance read contract exposes `lot_id` but not the lot's optimistic version;
- the current public Inventory/master-data API does not expose a separate lot-read endpoint;
- the frontend therefore cannot construct a correct `FREEZE`/`UNFREEZE` preview command without guessing or reaching into private state.

The amendment must make the current lot optimistic concurrency state readable without changing mutation semantics, FEFO behavior, database schema, or Task 10.5 server-side list ordering.

This amendment is intentionally smaller than reopening Plan 05-4B Task 6.

---

## 2. Verified current facts

### 2.1 InventoryLot already has independent optimistic versioning

`InventoryLot` uses `VersionedMixin`, so each lot has a positive integer `version` independent from `InventoryBalance.version`.

Lot state already includes at least:

- `id`;
- `tenant_id`;
- `spare_part_id`;
- `lot_code`;
- `expiry_date`;
- `quality_status`;
- `is_frozen`;
- `freeze_reason`;
- `version`.

No migration is required to obtain a lot version.

### 2.2 OperationPreviewCommand accepts expected_lot_version

The current public high-risk operation preview request contains:

```py
operation_type: Literal["ADJUST", "FREEZE", "UNFREEZE"]
balance_id: int
expected_balance_version: int
reason: str
deltas: dict[str, Any] | None
lot_id: int | None
expected_lot_version: int | None
```

Although the request field is syntactically optional because `ADJUST` does not use it, successful `FREEZE`/`UNFREEZE` execution requires it.

### 2.3 Execute revalidates lot version and lot state

For `FREEZE` / `UNFREEZE`, execute:

1. reads the stored preview command;
2. requires positive `lot_id`;
3. requires positive `expected_lot_version`;
4. loads the lot by both current tenant and lot ID;
5. refreshes current row state;
6. rejects a version mismatch;
7. rejects an invalid current frozen/unfrozen state;
8. acquires/refreshes the locked lot again through the transaction kernel;
9. rechecks version and state before writing.

Therefore `expected_lot_version` is not decorative metadata. It is part of the operation's concurrency safety.

### 2.4 The state mutation increments lot.version

The transaction kernel increments `target.version` for state writes.

A successful `FREEZE` or `UNFREEZE` therefore advances the lot version and makes any previously read lot concurrency token stale, as intended.

### 2.5 Current InventoryBalanceRead is insufficient

The public balance read currently exposes:

```text
id
warehouse_id
location_id
spare_part_id
lot_id
serial_item_id
serial_item_ids
on_hand_quantity
reserved_quantity
damaged_quantity
quarantined_quantity
in_transit_quantity
available_quantity
version
```

It does not expose:

```text
lot_version
lot_is_frozen
```

### 2.6 Existing list architecture already supports post-page hydration

`InventoryQueryService.list_balances()` currently:

1. obtains the already-filtered/sorted/paged parent balance rows;
2. loads serial IDs for only those parent rows;
3. copies hydration data into `InventoryBalanceRead`;
4. returns `PageData`.

This gives a safe extension point for lot concurrency hydration without changing:

```text
FILTER -> COUNT -> SORT -> PAGE
```

---

## 3. Design goals

The amendment must:

1. give frontend a legitimate current `expected_lot_version`;
2. give frontend enough state to choose between Freeze and Unfreeze affordances;
3. preserve tenant isolation;
4. preserve Task 10.5 filtering/count/sorting/pagination;
5. preserve all existing operation write semantics;
6. add no migration/table/index;
7. add no new top-level Inventory endpoint unless strictly necessary;
8. avoid exposing unrelated lot data merely because it exists;
9. keep no-lot balances valid;
10. keep frontend unable to author or infer lot state.

---

## 4. Alternatives

### Approach A — Add lot concurrency state to InventoryBalanceRead — RECOMMENDED

Add two optional read-only fields:

```py
lot_version: int | None = None
lot_is_frozen: bool | None = None
```

Hydrate them after balance paging using the current tenant and the balance's `lot_id` / `spare_part_id`.

For balances with no lot:

```json
{
  "lot_id": null,
  "lot_version": null,
  "lot_is_frozen": null
}
```

For tenant-matching lot balances:

```json
{
  "lot_id": 42,
  "lot_version": 7,
  "lot_is_frozen": false
}
```

**Advantages**

- smallest public API change;
- no new route;
- no new permissions;
- no write-semantic change;
- no migration;
- frontend already loads balance/detail before high-risk action;
- mirrors the existing serial-ID hydration architecture;
- preserves Task 10.5 parent-page semantics;
- immediately supports both concurrency token and correct Freeze/Unfreeze affordance.

**Trade-offs**

- balance read gains two lot-derived fields;
- query service/repository needs one page-bounded hydration query.

### Approach B — Add GET /inventory/lots/{lot_id}

Create a new tenant-scoped lot read response such as:

```json
{
  "id": 42,
  "spare_part_id": 11,
  "version": 7,
  "is_frozen": false
}
```

**Advantages**

- clean aggregate boundary;
- potentially reusable if full lot management becomes a later product feature.

**Disadvantages**

- expands the exact Inventory API surface;
- adds route/RBAC/OpenAPI/service/test surface for one immediate consumer;
- adds an extra frontend round trip before preview;
- creates a public lot domain that Plan 05-4B otherwise does not need.

Rejected for YAGNI.

### Approach C — Backend derives expected_lot_version during preview

Allow frontend to omit `expected_lot_version`; preview would load the lot and inject its current version into private preview storage.

**Advantages**

- no new read field;
- frontend need not know lot version.

**Disadvantages**

- changes existing high-risk write/preview semantics;
- changes who supplies the expected concurrency version;
- breaks the established symmetry where balance expected version is caller-observed;
- reopens Task 6 behavior rather than filling a read gap.

Rejected because the amendment should be additive read-only.

---

## 5. Approved contract if Approach A is accepted

### 5.1 InventoryBalanceRead additive fields

Add exactly:

```py
lot_version: int | None = None
lot_is_frozen: bool | None = None
```

No other lot fields are added by this amendment.

Explicitly not added:

```text
lot_code
manufacture_date
received_date
expiry_date
quality_status
freeze_reason
lot_updated_at
inventory risk
demand gap
```

Those remain outside this narrow concurrency amendment.

### 5.2 Semantics

For every public balance read:

#### lot_id is null

```text
lot_version = null
lot_is_frozen = null
```

#### lot_id is non-null and tenant/spare-part-matching lot exists

```text
lot_version = current InventoryLot.version
lot_is_frozen = current InventoryLot.is_frozen
```

#### lot_id is non-null but no tenant-safe matching lot is available

Fail closed on the derived lot fields:

```text
lot_version = null
lot_is_frozen = null
```

Do not query or reveal another tenant's lot state.

The balance itself remains governed by its existing tenant read contract.

---

## 6. Tenant-safe hydration contract

The repository hydration query must be constrained by:

```text
InventoryLot.tenant_id == actor.tenant_id
InventoryLot.id in page lot IDs
InventoryLot.spare_part_id == matching balance spare_part_id
```

A helper may return a map keyed by balance ID or lot ID, but it must preserve the spare-part match and tenant predicate.

Preferred conceptual result:

```py
{
    balance_id: {
        "lot_version": lot.version,
        "lot_is_frozen": lot.is_frozen,
    }
}
```

Cross-tenant or mismatched records do not populate the map.

---

## 7. List pipeline preservation

The amendment must not join `InventoryLot` into the parent list statement in a way that changes count/order/page semantics.

Required flow remains:

```text
tenant
  -> filters
  -> filtered COUNT
  -> validated sort
  -> stable ID tie-break
  -> OFFSET/LIMIT
  -> parent-page lot/serial hydration
  -> InventoryBalanceRead
  -> PageData
```

Lot hydration happens only after parent-page balances are selected.

Therefore:

- `total` is unchanged;
- `pages` is unchanged;
- list order is unchanged;
- stable pagination is unchanged;
- no new `sort_by=lot_version`;
- no new `sort_by=lot_is_frozen`;
- no new lot-state filter is introduced.

---

## 8. Detail contract

`GET /inventory/balances/{id}` returns the same additive fields.

Frontend high-risk operation flow must obtain the freshest balance detail immediately before preview or use a freshly loaded balance record whose generation is current.

The frontend then sends:

```json
{
  "operation_type": "FREEZE",
  "balance_id": 12,
  "expected_balance_version": 9,
  "reason": "quality hold",
  "deltas": null,
  "lot_id": 42,
  "expected_lot_version": 7
}
```

or:

```json
{
  "operation_type": "UNFREEZE",
  "balance_id": 12,
  "expected_balance_version": 10,
  "reason": "quality hold cleared",
  "deltas": null,
  "lot_id": 42,
  "expected_lot_version": 8
}
```

The backend remains authoritative and may still reject a race after the read.

---

## 9. Frontend affordance contract

Once these fields are available:

```text
lot_id == null
  -> Freeze/Unfreeze unavailable

lot_id != null AND lot_version == null
  -> Freeze/Unfreeze unavailable
  -> show "lot concurrency state unavailable; reload"

lot_id != null AND lot_version != null AND lot_is_frozen == false
  -> show Freeze
  -> do not show Unfreeze

lot_id != null AND lot_version != null AND lot_is_frozen == true
  -> show Unfreeze
  -> do not show Freeze
```

The UI must not toggle local lot state optimistically.

After successful execute:

1. refresh transaction evidence;
2. refresh balance detail;
3. refresh balance list;
4. consume the newly returned/read lot version.

---

## 10. Error and race behavior

No write-side error contract changes are required.

Existing version race:

```text
INVENTORY_VERSION_CONFLICT
conflict_object = inventory_lot
expected_version = caller-observed lot_version
actual_version = current lot.version
retryable = true
```

Frontend response:

1. preserve reason/form context;
2. discard stale preview confirmation state;
3. reload balance detail;
4. obtain new `lot_version` and `lot_is_frozen`;
5. require a new preview;
6. changed/new logical preview uses a new Idempotency-Key.

Existing state race:

```text
INVENTORY_OPERATION_STATE_CONFLICT
conflict_object = inventory_lot
actual_is_frozen = ...
retryable = false
```

Frontend reloads state and offers only the operation that now matches current public lot state.

---

## 11. Backend implementation boundary for the later implementation plan

Expected production scope is exactly three existing files:

```text
extensions/maintenance-api/app/schemas/inventory_ledger.py
extensions/maintenance-api/app/services/inventory_query_service.py
extensions/maintenance-api/app/repositories/inventory_ledger_repository.py
```

Expected test scope:

```text
extensions/maintenance-api/tests/services/test_inventory_query_service.py
extensions/maintenance-api/tests/api/test_inventory_queries_api.py
```

An operation-service production change is not expected.

An API-route production change is not expected because the existing response model references `InventoryBalanceRead`.

A fourth backend production file requirement is a STOP condition and must return for approval.

---

## 12. Required later RED coverage

The later implementation plan must include failing tests for all of the following before GREEN:

### Service list

A tenant balance with a matching lot returns:

```text
lot_version == lot.version
lot_is_frozen == lot.is_frozen
```

### Service detail

`get_balance()` returns the same fields.

### No-lot balance

Returns both fields as null.

### Frozen lot

Returns:

```text
lot_is_frozen == true
```

without changing quantity/list semantics.

### Tenant isolation

A cross-tenant or tenant-mismatched lot record must never populate lot concurrency fields.

### Spare-part match

A mismatched lot/spare-part relation must not populate derived fields.

### Page stability

Adding hydration must not change:

```text
items order
total
page
page_size
pages
```

for Task 10.5 list cases.

### API/OpenAPI

Both balance list and detail schemas expose:

```text
lot_version: integer | null
lot_is_frozen: boolean | null
```

No new query parameter or endpoint appears.

### Operation regression

Existing FREEZE/UNFREEZE tests remain unchanged and pass, proving write semantics were not modified.

---

## 13. Required later GREEN/regression gates

At minimum:

1. focused service amendment tests;
2. focused API/OpenAPI amendment tests;
3. existing Task 10.5 55-query suite;
4. existing Task 9 API/RBAC/OpenAPI regression;
5. focused Inventory Backend regression;
6. Ruff;
7. `git diff --check`;
8. full backend suite;
9. Alembic head remains `20260803_11`;
10. real PostgreSQL focused balance-query amendment gate;
11. post-PostgreSQL focused recheck;
12. exact changed-file scope.

No migration round-trip is needed beyond confirming Alembic head because this amendment has no migration.

---

## 14. Impact on the approved Frontend Inventory Gap design

The parent frontend design remains valid except for the narrow public balance-field statement.

Amend the conceptual public balance fields from:

```text
lot_id
...
version
```

to additionally include:

```text
lot_version
lot_is_frozen
```

This does not reopen:

- expiry;
- risk;
- demand gap;
- public rich preview;
- FEFO recommendation;
- inventory policy management.

---

## 15. Impact on the Frontend implementation-plan draft

After this amendment is implemented and verified, the frontend plan must be reconciled before Task 11A RED.

Required plan changes:

### Task 11A type

`InventoryBalanceRead` gains:

```ts
lot_version: number | null
lot_is_frozen: boolean | null
```

### Task 11A API tests

Balance list/detail fixtures assert the fields are preserved exactly.

### Task 12C

Remove the current STOP condition:

```text
If the frontend has no public lot version available...
```

Replace with:

```text
FREEZE/UNFREEZE require:
- balance.lot_id != null
- balance.lot_version != null
- balance.lot_is_frozen != null
```

Build preview command from fresh balance detail:

```ts
{
  operation_type: balance.lot_is_frozen
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

### Task 13 contract audit

Add explicit audit that:

- list/detail expose lot concurrency state;
- frontend never guesses lot version;
- frontend chooses Freeze vs Unfreeze from server state;
- frontend refreshes after execute/conflict.

The frontend implementation-plan draft SHA must be regenerated and re-approved after reconciliation.

---

## 16. What this amendment explicitly does not do

It does not:

- add a migration;
- change `InventoryLot` table;
- add a lot CRUD endpoint;
- add lot filters/sorts;
- expose expiry in balance read;
- expose quality status in balance read;
- expose freeze reason in balance read;
- change FEFO;
- change reserve/issue/release;
- change FREEZE/UNFREEZE execute semantics;
- change preview token semantics;
- infer expected lot version server-side;
- change tenant/RBAC rules;
- change frontend production;
- authorize RED/GREEN;
- authorize commit/push/PR update/merge.

---

## 17. Success criteria

The amendment is successfully implemented only when:

1. balance list/detail expose current tenant-safe `lot_version` and `lot_is_frozen`;
2. no-lot balances return null/null;
3. Task 10.5 list order/count/page behavior is unchanged;
4. no new endpoint/query/filter/sort is introduced;
5. existing FREEZE/UNFREEZE write tests pass unchanged;
6. a successful lot state mutation advances lot version as before;
7. frontend has enough public state to construct a valid preview without guessing;
8. backend full regression and focused PostgreSQL gate pass;
9. Alembic remains `20260803_11`;
10. changed production scope stays within the expected three files.

---

## 18. Approval boundary

Approval of this amendment authorizes only the next step:

> create a detailed implementation plan for this narrow backend read-contract amendment.

It does not authorize RED, backend production changes, frontend changes, commit, push, PR update, or merge.

After the amendment design is approved:

1. write the narrow backend amendment IMPLEMENTATION PLAN;
2. obtain explicit plan approval;
3. obtain explicit RED approval;
4. RED and STOP;
5. obtain GREEN approval;
6. GREEN/regression/PostgreSQL gate and STOP;
7. separately approve commit;
8. separately approve push;
9. reconcile and re-approve the Frontend Inventory Gap implementation plan;
10. only then return to Task 11A RED.

# Plan 05-4A Inventory Ledger Foundation Closure Review

## Decision

APPROVED

No Critical, Important, or Minor blocking findings remain in the approved Plan 05-4A scope.

## Reviewed Range

- Repository: `deifeb/maintenance-support-weknora`
- Branch: `codex/maintenance-plan05-4`
- Implementation base: `228d96dc74609b692efa1c3ff122f78ad5256a68`
- Committed implementation head: `d53fe56dc6ba6e33527d3903c06beedf91aac810`
- Task 7 candidate changes:
  - `extensions/maintenance-api/tests/integration/test_inventory_ledger_foundation.py`
  - `extensions/maintenance-api/tests/conftest.py`
- Production files changed by Task 7: none

The `tests/conftest.py` change is a test-harness isolation fix. Two migration tests intentionally replace `INTERNAL_JWT_SECRET` and clear the cached settings object; without an after-test cache clear, later API tests can validate tokens against stale settings and fail with `INTERNAL_TOKEN_INVALID`. The autouse fixture clears `get_settings()` before and after every test, restoring deterministic test isolation without altering runtime behavior.

## Approved Scope

Plan 05-4A establishes the inventory ledger foundation only:

- canonical warehouse locations, policies, balances, lots, serialized items, transactions, and append-only ledger entries;
- exact Decimal quantity contracts;
- tenant-scoped reads and writes;
- OPENING and ADJUST transaction authority;
- compatibility inventory API;
- dashboard, demand, AI, import, export, and seed consumers migrated to ledger-backed contracts;
- target-receipt and import-execution-principal remediation;
- migration lineage through `20260803_10`.

FEFO, reservation, issue/return, transfer, stocktake, review, allocation, frontend inventory-gap workflows, and all Plan 05-4B behavior remain excluded.

## Requirement-by-Requirement Findings

| Requirement | Finding |
|---|---|
| Authority model | APPROVED. Ledger models and services are the authoritative inventory fact; the runtime legacy aggregate model is absent. |
| Quantity contract | APPROVED. Quantities remain exact Decimal/Numeric values, available quantity is derived consistently, and invariants are covered by focused and full-suite tests. |
| Tenant isolation | APPROVED. Repository, API, dashboard, demand, export, receipt, and worker paths are tenant scoped. Foreign inventory identity reads return `404`; foreign exports contain no data rows. |
| Immutability | APPROVED. Ledger entries are append-only and repository immutability tests pass. |
| Write authority | APPROVED. Physical quantity changes exercised by Task 7 pass through the compatibility API and `InventoryTransactionService`; Task 7 changed no production path. |
| Idempotency | APPROVED. Exact adjustment replay is side-effect free, key reuse with a different request conflicts, and durable target receipts replay without duplicate effects. |
| Compatibility API | APPROVED. Create, get, adjust, and export contracts remain usable with ledger-backed state. |
| Consumers | APPROVED. Dashboard risk metrics, demand inventory snapshots, Excel export, import target adaptation, and ledger audit read the same authoritative fact. |
| Migrations | APPROVED. Legacy conservation, downgrade/re-upgrade, granular-fact downgrade refusal, legacy identity preservation, receipt migration, and execution-principal migration pass. |
| RBAC | APPROVED. Existing API/RBAC coverage remains green; inventory physical writes remain ADMIN-only. |
| Scope | APPROVED. No Plan 05-4B production behavior or frontend implementation was introduced. |

## Integration Contract Evidence

`tests/integration/test_inventory_ledger_foundation.py` adds three end-to-end contracts:

1. `test_authoritative_inventory_fact_flows_through_all_05_4a_consumers`
2. `test_authoritative_inventory_adjustment_replay_is_side_effect_free`
3. `test_authoritative_inventory_fact_is_hidden_from_foreign_tenant`

Fresh local Python 3.11 result:

- `3 passed, 1 warning in 23.82s`

The tests prove that one adjustment is observed consistently through:

- compatibility inventory create/get/adjust;
- dashboard inventory risk;
- demand calculation inventory snapshot;
- Excel inventory export;
- `InventoryTransaction`;
- `InventoryLedgerEntry`;
- `InventoryTargetReceipt`;
- same-request replay;
- different-request idempotency conflict;
- foreign-tenant hidden reads.

## Migration and Alembic Evidence

Fresh migration result:

- `26 passed, 1 warning in 159.25s`
- Alembic: `20260803_10 (head)`

Verified lineage:

```text
20260731_07
  -> 20260803_08 inventory ledger foundation
  -> 20260803_09 inventory target receipts
  -> 20260803_10 import execution principal
```

The suite covers:

- legacy aggregate quantity conservation;
- lossless downgrade and re-upgrade where allowed;
- downgrade rejection for granular facts;
- legacy inventory ID survival;
- target-receipt revision reversibility;
- execution-principal revision reversibility;
- one Alembic head.

## Tenant Isolation and RBAC Evidence

Task 7 verifies:

- tenant B receives `404` for tenant A's balance identity;
- tenant B's filtered inventory workbook has no data rows;
- tenant B's dashboard reports no tenant A inventory risk;
- tenant B reads create or modify no tenant B inventory facts.

The complete Plan 05-4A focused suite, including API RBAC tests, passed:

- `143 passed, 1 warning in 190.11s`

## Idempotency, Receipt, and Replay Evidence

The integration contract verifies:

- first adjustment creates one completed transaction and one ledger entry;
- exact replay returns the same decoded response;
- replay does not add transactions, ledger entries, or receipts;
- the persisted response snapshot is unchanged;
- the same key with a different reason returns `IDEMPOTENCY_KEY_REUSED`;
- the import-target receipt replays without physical quantity side effects.

Task 6's durable execution-principal recovery remains covered in the same focused Gate.

## Legacy Runtime Reference Scan

Runtime scan under `extensions/maintenance-api/app`:

```text
WarehouseInventory|warehouse_inventories
```

Result: no matches.

## Full Gate Results

Fresh local Python 3.11 Gate:

- Task 7 authoritative-fact integration: `3 passed, 1 warning in 23.82s`
- Complete Plan 05-4A focused suite: `143 passed, 1 warning in 190.11s`
- Migration round-trip and lineage: `26 passed, 1 warning in 159.25s`
- Full backend: `878 passed, 8 deselected, 2 warnings in 406.07s`
- Ruff: `All checks passed!`
- Alembic: `20260803_10 (head)`
- `git diff --check`: PASS
- Legacy runtime reference scan: PASS
- Exact Task 7 test-only scope before documentation: PASS

## Warnings

Two existing, non-blocking warnings remain:

1. Starlette's deprecation warning for the current `httpx` test-client integration.
2. `InsecureKeyLengthWarning` in the deliberate wrong-algorithm JWT integration test because its SHA384 test key is shorter than the RFC recommendation.

The Windows checkout also reports an LF-to-CRLF notice for `tests/conftest.py`; `git diff --check` passes.

## Residual Risks

Live PostgreSQL evidence was not executed in this environment:

- `psql available: False`
- `docker CLI available: True`
- no reachable disposable PostgreSQL test command was established by the Gate

Therefore live PostgreSQL migration execution, unique-conflict timing, and `SELECT ... FOR UPDATE` scheduling remain deployment-environment validation boundaries. SQLite tests, deterministic competing-session tests, and PostgreSQL dialect compilation do not replace that live evidence.

The progress ledger's earlier note about holistic composite tenant foreign keys remains outside the approved 05-4A schema scope. No new cross-tenant disclosure was found by Task 7's API and consumer integration contract.

## Future Migration Lineage

The original roadmap revision allocations are obsolete because `20260803_09` and `20260803_10` were consumed by Task 6 remediation.

Before Plan 05-4B implementation begins, its plans must be corrected to reserve:

```text
Plan 05-4B: 20260803_11
Plan 05-4C: 20260803_12
Plan 05-4D: 20260803_13
```

This is a planning correction only. It does not authorize any of those migrations or stages.

## Scope Exclusions

This closure does not approve or start:

- FEFO;
- reservation;
- issue or return;
- transfer;
- stocktake;
- authoritative demand review;
- allocation or assurance;
- frontend inventory-gap implementation;
- Plan 05-4B, 05-4C, or 05-4D.

## Closure Recommendation

Approve Plan 05-4A Task 7 and close Plan 05-4A at migration head `20260803_10`.

Proposed commit subject:

```text
test(maintenance): close plan05-4a inventory ledger
```

Commit, push, PR creation, merge, and Plan 05-4B remain separate approval boundaries.

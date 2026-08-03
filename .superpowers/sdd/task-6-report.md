# Plan 05-4A Task 6 Implementation Report

## Status

DONE

## TDD evidence

- Initial focused RED:
  `11 failed, 11 passed, 1 warning`. The failures covered the missing actor and
  task identity contract, contributor execution authorization, legacy seed
  writes, and empty ledger-only inventory exports.
- The first GREEN focused run reached `22 passed, 1 failed`; the remaining
  failure was an obsolete worker fixture passing a string instead of the
  existing `MaintenanceRole` type. After migrating that fixture, the focused
  suite passed.
- A policy-only/zero-quantity receipt regression was then added RED-first:
  `1 failed, 8 deselected, 1 warning`. The adapter now records a completed
  `TARGET` receipt without a ledger entry when no physical delta exists, so
  replay and changed-source collision rules also cover zero inventory.
- Final focused import/worker/tenant/export suite:
  `24 passed, 1 pre-existing warning`.

## Implementation

- Added `InventoryTargetAdapter`, the single target-state bridge used by
  compatibility import and seed paths. It creates the policy and DEFAULT
  identity, reads aggregate ledger state through `InventoryQueryService`, and
  applies non-zero physical differences only through
  `InventoryTransactionService.opening()` or `.adjust()`.
- Added stable source receipts using exact import keys
  `import:{task_id}:08_库存:{row_number}` and fixed seed keys
  `seed:inventory:{tenant}:{warehouse}:{part}`. Same-source replay returns the
  existing receipt; a changed normalized source raises
  `IDEMPOTENCY_KEY_REUSED` before recalculation.
- Serialized first-use target application with a tenant-scoped warehouse row
  lock and a receipt recheck. Identity, policy, balance, transaction, ledger,
  and receipt changes remain in the caller's database transaction.
- Preserved the legacy `08_库存` workbook fields while replacing direct
  physical-row writes with ledger transactions. Import rollback tests verify
  no partial identity, policy, balance, transaction, or ledger residue.
- Made synchronous and queued import execution ADMIN-only. The actual
  `ActorContext` and role are carried through API, queue, and worker boundaries;
  there is no internal contributor-to-admin promotion.
- Reimplemented compatibility inventory export from tenant-scoped ledger
  summaries, aggregating every location and lot while preserving the old
  worksheet name, columns, filters, and sort contract.
- Migrated seed inventory creation to the target adapter and fixed receipts,
  making repeated seed runs idempotent.
- Removed the legacy `WarehouseInventory` ORM/export/repository methods and
  renamed runtime schema/service types to `InventoryCreate`,
  `InventoryUpdate`, and `InventoryRead`. Existing HTTP URLs remain unchanged.

## Coverage added or migrated

- Opening and adjustment ledger creation, including five physical components.
- Aggregate target adjustment with pre-existing non-DEFAULT location state.
- Same-task replay, changed-payload collision, zero-quantity receipts, tenant
  isolation, and transaction rollback.
- Contributor denial with zero writes and successful ADMIN execution.
- Worker role propagation and direct non-admin worker refusal.
- Ledger-only compatibility export across multiple locations/lots and tenant
  isolation.
- Exact fixed seed receipts and duplicate-free reruns.
- Mapper registry and runtime-source removal of the legacy table/class.

## Verification

- Focused Task 6 suite: `24 passed, 1 pre-existing warning` in `9.72s`.
- API/RBAC contract suite: `20 passed, 1 pre-existing warning` in `8.89s`.
- Expanded Task 2-6 regression set: `210 passed, 1 pre-existing warning` in
  `106.67s`.
- Full backend: `834 passed, 8 deselected, 2 pre-existing warnings` in
  `245.86s`.
- Changed-file Ruff: `All checks passed!`.
- Runtime search under `app`: zero `WarehouseInventory` or
  `warehouse_inventories` references.
- `git diff --check`: clean apart from Git line-ending conversion notices.

## Remaining validation boundary

The production first-use serialization uses PostgreSQL `SELECT ... FOR
UPDATE`. Its logic is covered by deterministic service tests, but this task did
not add a live concurrent PostgreSQL integration test; the repository's normal
SQLite suite cannot exercise PostgreSQL row-lock scheduling.

## Commit

This report is included in the commit with subject:
`refactor(maintenance): migrate inventory import export to ledger`.

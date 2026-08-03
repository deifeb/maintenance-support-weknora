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

## Formal review remediation

The findings in `task-6-review.md` were remediated in five focused commits:

- `a4bc2f14` (`C1` plus unreachable-target preflight): introduced the
  tenant/idempotency-key unique `InventoryTargetReceipt` authority and reserves
  it in a savepoint before any target reads or writes. A committed same-source
  winner is replayed, a changed source raises `IDEMPOTENCY_KEY_REUSED`, and a
  pending or malformed result raises `IDEMPOTENT_RESPONSE_UNAVAILABLE`. Zero
  deltas complete the same receipt without creating a fake ledger transaction.
  Preflight now rejects any target that would force a non-DEFAULT physical
  component or DEFAULT allocation negative, before policy or identity mutation.
  RED: receipt/migration/concurrency cases failed because the table and atomic
  reservation did not exist (`1`, `1`, and `5` failures respectively), while
  five reachability cases returned the later generic negative-quantity error.
  GREEN: combined receipt/import/migration set `24 passed`; deterministic
  two-session stale-first-read coverage exercises the database unique-conflict
  and winner-recovery path for zero and non-zero winners.
- `0f0754f8` (`I1`): persists the actual ADMIN execution principal, roles,
  request/token identifiers and queue time on the task. Workers receive only
  task/tenant IDs, reload the durable principal tenant-wide, refuse an invalid
  or non-admin persisted principal, preserve the executor in transaction audit,
  and recover non-expired RUNNING work to QUEUED at startup. RED: service/API
  set had `3 failed, 1 passed`; worker set had `4 failed`. GREEN: combined
  API/worker/RBAC/migration set `33 passed`; model/task/migration set
  `41 passed`; worker audit/recovery set `8 passed`.
- `76af5cdf` (`I2`): synchronous task identity is now the SHA-256 of canonical
  normalized commands (template version, mapping, fixed sheet order, normalized
  rows) instead of raw ZIP bytes. Queued explicit UUID identity is unchanged.
  RED: two logically identical workbooks with different ZIP bytes did not
  replay. GREEN: the focused identity set `3 passed`, and all import tests
  `50 passed`.
- `c534b00b` (`I3`, `I4`, `M1`): inventory export now uses one tenant-scoped,
  filtered, grouped SQL query with `LIMIT max_rows + 1`; oversize detection is
  performed before workbook construction. Decimal quantities are written as
  fixed four-place strings, avoiding float coercion, and equal-key ties always
  use ascending warehouse/part IDs independently of primary sort direction.
  RED: export used `3` SELECTs; large values round-tripped as
  `12345678901234.57` / `100000000000000`; descending ties were `C/B/A`.
  GREEN: the focused cases `3 passed`, and exporter/API/query/repository
  regression `32 passed`.
- `3b23ec81`: added PostgreSQL dialect DDL compilation coverage for the source
  receipt unique constraint and state/hash checks (`1 passed`).

Fresh cumulative verification after remediation:

- Task 6 focused import/export/API/RBAC/migration set: `99 passed, 1 warning`
  in `29.32s`.
- Task 2-5 inventory regression set: `112 passed, 1 warning` in `107.31s`.
- Disposable migration up/down/up contract tests: `2 passed, 1 warning`; the
  only Alembic head is `20260803_10`.
- Full backend: `866 passed, 8 deselected, 2 warnings` in `301.66s`.
- Ruff over every Python file changed since the reviewed commit:
  `All checks passed!`.
- `git diff --check 28e89bfa..HEAD`: clean.
- Runtime search under `app`: zero `WarehouseInventory` or
  `warehouse_inventories` references.

## Remaining validation boundary

The production first-use serialization uses PostgreSQL `SELECT ... FOR
UPDATE`. Its logic is covered by deterministic service tests, but this task did
not add a live concurrent PostgreSQL integration test; the repository's normal
SQLite suite cannot exercise PostgreSQL row-lock scheduling.

The receipt table's PostgreSQL DDL compiles with its required unique and CHECK
constraints, but this workstation had neither `psql` nor a running Docker
daemon. Therefore live PostgreSQL migration execution, unique-conflict timing,
and row-lock scheduling remain an explicit deployment-environment validation
boundary.

## Commit

This report is included in the commit with subject:
`refactor(maintenance): migrate inventory import export to ledger`.
The formal-review evidence update is included in the commit with subject:
`docs(maintenance): record task 6 review remediation`.

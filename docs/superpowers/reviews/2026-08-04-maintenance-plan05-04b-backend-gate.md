# Plan 05-4B Backend Gate 1 Review

Generated from fresh local Gate output at: 2026-08-15T20:23:36+08:00

## Status

- Backend Gate 1 status: closed
- Local SQLite backend integration status: verified
- Production deployment status: blocked until PostgreSQL gate passes
- Real PostgreSQL Gate: NOT RUN
- Frontend Inventory Gap: NOT STARTED
- Branch: codex/maintenance-plan05-4b
- HEAD: c6603ad90a6b5dee75576215770004ba9f1378f2
- Staged changes at Gate completion: EMPTY

## Gate Scope

This Gate validates the Plan 05-4B backend through Task 10. Task 10 itself added only test/fixture stabilization, the integration workflow test, and this review evidence; it did not add or modify production behavior.

### Task 10 test/evidence files

- Modified: `extensions/maintenance-api/tests/conftest.py`
- Modified: `extensions/maintenance-api/tests/models/test_inventory_ledger_models.py` (Ruff import-formatting only)
- Modified: `extensions/maintenance-api/tests/models/test_tenant_models.py` (tenant registry test-only stabilization)
- Modified: `extensions/maintenance-api/tests/workers/test_inventory_reservation_expiry.py`
- Created: `extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py`
- Created: `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-backend-gate.md`

## Fresh Verification

### Focused Inventory Backend Gate

Command:

```
python -m pytest tests/models/test_inventory_operation_models.py tests/migrations/test_inventory_operations_migration.py tests/schemas/test_inventory_operation_schemas.py tests/repositories/test_inventory_ledger_immutability.py tests/repositories/test_inventory_ledger_repository.py tests/repositories/test_inventory_reservation_repository.py tests/repositories/test_inventory_transfer_repository.py tests/repositories/test_inventory_stocktake_repository.py tests/services/test_inventory_mutation_plan.py tests/services/test_inventory_transaction_service.py tests/services/test_inventory_fefo_service.py tests/services/test_inventory_reservation_service.py tests/workers/test_inventory_reservation_expiry.py tests/services/test_inventory_operation_preview.py tests/services/test_inventory_freeze.py tests/services/test_inventory_adjust.py tests/services/test_inventory_reversal.py tests/services/test_inventory_transfer_service.py tests/services/test_inventory_stocktake_service.py tests/api/test_inventory_queries_api.py tests/api/test_inventory_reservations_api.py tests/api/test_inventory_operations_api.py tests/api/test_inventory_transfers_api.py tests/api/test_inventory_stocktakes_api.py tests/api/test_inventory_api_closure.py tests/security/test_api_rbac.py tests/integration/test_inventory_operations_workflow.py -q
```

Result:

```
373 passed, 1 warning in 75.37s (0:01:15)
```

Coverage includes migration/model/schema, repositories, ledger immutability, mutation kernel, FEFO, reservation and expiry, high-risk preview/freeze/adjust/reverse, transfer, stocktake, API/RBAC/OpenAPI, and four integration workflows.

### Task 9 API/RBAC/OpenAPI Closure

Command:

```
python -m pytest tests/api/test_inventory_api_closure.py tests/api/test_inventory_queries_api.py tests/api/test_inventory_reservations_api.py tests/api/test_inventory_operations_api.py tests/api/test_inventory_transfers_api.py tests/api/test_inventory_stocktakes_api.py tests/security/test_api_rbac.py -q
```

Result:

```
127 passed, 1 warning in 55.34s
```

Expected and confirmed contract count: 127 passed.

### Four Integration Workflows

Command:

```
python -m pytest tests/integration/test_inventory_operations_workflow.py -q
```

Result:

```
4 passed, 1 warning in 6.78s
```

Verified workflows:

1. reserve -> partial issue -> return -> release;
2. transfer create -> dispatch preview/execute -> partial receive -> final receive;
3. stocktake -> version conflict -> partial confirm -> rebase/recount -> final confirm;
4. expired reservation -> worker wins -> request-side check -> exactly one UNRESERVE.

### Alembic Migration Gate

Single-head command:

```
python -m alembic heads
```

Observed head:

```
20260803_11 (head)
```

Isolated temporary SQLite round-trip:

Alembic subprocess environment:

- `APP_ENV=test`
- `DATABASE_URL=<temporary isolated SQLite file>`
- `INTERNAL_JWT_SECRET=<test-only secret, not persisted>`

```
python -m alembic upgrade 20260803_11
python -m alembic current
python -m alembic downgrade 20260803_10
python -m alembic current
python -m alembic upgrade 20260803_11
python -m alembic current
python -m alembic heads
```

Observed revisions:

- after first upgrade: `20260803_11 (head)`
- after downgrade: `20260803_10`
- after re-upgrade: `20260803_11 (head)`
- final head: `20260803_11 (head)`

The focused migration pytest also verifies schema constraints, round-trip preservation of 05-4A facts, downgrade protection when 05-4B business data exists, and PostgreSQL DDL compilation.

### Ruff Gate

Command:

```
python -m ruff check app tests
```

Result:

```
All checks passed!
```

### Full Backend Suite

Command:

```
python -m pytest -q
```

Result:

```
1227 passed, 8 deselected, 2 warnings in 344.66s (0:05:44)
```

No historical result was substituted for this run.

## Contract Traceability

- SQLite deterministic concurrency / fixed mutation ordering: mutation-plan, transaction-service, transfer and stocktake focused tests.
- Ledger append-only: `tests/repositories/test_inventory_ledger_immutability.py`.
- Tenant isolation: repository/API/RBAC focused tests and Inventory API closure.
- Idempotency replay/reuse: reservation, operation, transfer, stocktake, expiry and API focused tests.
- Version/conflict contracts: transaction/reservation/operation/transfer/stocktake service and API tests.
- Stable errors / retryable metadata / request correlation: Task 9 API closure and RBAC tests.
- Inventory API surface: exact 33 operations, Task 9 closure.
- `Idempotency-Key`: required in OpenAPI for all 23 Inventory write operations and stable runtime missing-header contract.
- Private preview/transaction fields: not exposed through Inventory-reachable OpenAPI schemas.

## Repository Scope

`git status --short` before writing this review:

```
 M extensions/maintenance-api/app/api/v1/router.py
 M extensions/maintenance-api/app/core/exceptions.py
 M extensions/maintenance-api/app/schemas/inventory_ledger.py
 M extensions/maintenance-api/app/services/inventory_operation_service.py
 M extensions/maintenance-api/app/services/inventory_query_service.py
 M extensions/maintenance-api/tests/conftest.py
 M extensions/maintenance-api/tests/models/test_inventory_ledger_models.py
 M extensions/maintenance-api/tests/models/test_tenant_models.py
 M extensions/maintenance-api/tests/security/test_api_rbac.py
 M extensions/maintenance-api/tests/workers/test_inventory_reservation_expiry.py
?? extensions/maintenance-api/app/api/v1/inventory/__init__.py
?? extensions/maintenance-api/app/api/v1/inventory/common.py
?? extensions/maintenance-api/app/api/v1/inventory/operations.py
?? extensions/maintenance-api/app/api/v1/inventory/queries.py
?? extensions/maintenance-api/app/api/v1/inventory/reservations.py
?? extensions/maintenance-api/app/api/v1/inventory/router.py
?? extensions/maintenance-api/app/api/v1/inventory/stocktakes.py
?? extensions/maintenance-api/app/api/v1/inventory/transfers.py
?? extensions/maintenance-api/tests/api/test_inventory_api_closure.py
?? extensions/maintenance-api/tests/api/test_inventory_operations_api.py
?? extensions/maintenance-api/tests/api/test_inventory_queries_api.py
?? extensions/maintenance-api/tests/api/test_inventory_reservations_api.py
?? extensions/maintenance-api/tests/api/test_inventory_stocktakes_api.py
?? extensions/maintenance-api/tests/api/test_inventory_transfers_api.py
?? extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py
```

`git diff --stat` before writing this review:

```
 extensions/maintenance-api/app/api/v1/router.py                  |  17 +-
 extensions/maintenance-api/app/core/exceptions.py                |  37 +-
 extensions/maintenance-api/app/schemas/inventory_ledger.py       |  87 +++-
 extensions/maintenance-api/app/services/inventory_operation_service.py | 391 ++++++++++++++++
 extensions/maintenance-api/app/services/inventory_query_service.py     |  56 +++
 extensions/maintenance-api/tests/conftest.py                     |  13 +-
 extensions/maintenance-api/tests/models/test_inventory_ledger_models.py |   1 -
 extensions/maintenance-api/tests/models/test_tenant_models.py     |   6 +
 extensions/maintenance-api/tests/security/test_api_rbac.py        | 149 ++++++
 extensions/maintenance-api/tests/workers/test_inventory_reservation_expiry.py |  72 +--
 10 files changed, 803 insertions(+), 26 deletions(-)
```

`git diff --name-only` before writing this review:

```
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/app/schemas/inventory_ledger.py
extensions/maintenance-api/app/services/inventory_operation_service.py
extensions/maintenance-api/app/services/inventory_query_service.py
extensions/maintenance-api/tests/conftest.py
extensions/maintenance-api/tests/models/test_inventory_ledger_models.py
extensions/maintenance-api/tests/models/test_tenant_models.py
extensions/maintenance-api/tests/security/test_api_rbac.py
extensions/maintenance-api/tests/workers/test_inventory_reservation_expiry.py
```

`git diff --check`: PASS

## TODO / FIXME / HACK Review

Command:

```
git grep -n -E "TODO|FIXME|HACK" -- extensions/maintenance-api/app extensions/maintenance-api/tests
```

Observed:

```
(none)
```

Any pre-existing marker listed above is evidence for residual-risk review and is not treated as proof of a new Task 10 product regression without a failing contract.

## Task 10 Harness Stabilization Evidence

H2 confirmed that SQLite `PRAGMA foreign_keys` is connection-scoped, QueuePool can retain mixed FK states, and a reverse-style self-FK cycle blocks bulk DELETE with FK enforcement enabled.

H1 then:

- made SQLite test cleanup deterministically disable FK for bulk cleanup;
- disposed pooled connections after cleanup so mixed FK state does not leak to the next test;
- replaced the worker's invalid `balance_id=999999` failure fixture with a controlled service `NotFoundError`;
- passed worker, FK-order, reverse-cleanup, and enhanced Task 1-9 regression gates.

These are test/fixture changes only. No production behavior was changed by H1.

L1 then removed one pre-existing extra blank line in `tests/models/test_inventory_ledger_models.py` so the repository-wide `ruff check app tests` Gate could pass. L1 changed no test assertion, fixture, or production behavior.

G1 fixed a cross-module validation-contract regression in `app/core/exceptions.py`: the stable `IDEMPOTENCY_KEY_REQUIRED` mapping is now scoped to `/api/v1/inventory/`, while non-Inventory required-header validation retains the existing `VALIDATION_ERROR` contract. The existing six Demand List RED tests passed without modification, and the Task 9 Inventory API/RBAC/OpenAPI closure remained green.

T1 updated only `TENANT_TABLES` in `tests/models/test_tenant_models.py` to include the six Plan 05-4B reservation, transfer, and stocktake tables already present in `Base.metadata`. T1 changed no production code.

## Residual Risks / Unexecuted Verification

1. Real PostgreSQL concurrency/locking Gate has NOT been executed.
2. Therefore production deployment remains blocked.
3. PostgreSQL DDL compilation is covered locally, but it is not a substitute for a real PostgreSQL runtime Gate.
4. Frontend Inventory Gap Task 11+ has not started.
5. No stage, commit, push, PR update, merge, or frontend work was performed by this Gate.

## Gate Decision

Backend Gate 1 is locally closed for SQLite-backed development and the API contract is frozen for the next approved frontend task.

**Production deployment status: blocked until PostgreSQL gate passes.**

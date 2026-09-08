# Task 6 Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close C1, I1-I4, M1, and the unreachable-target preflight finding without entering Task 7 or modifying `.superpowers/sdd/progress.md`.

**Architecture:** A typed `InventoryTargetReceipt` row becomes the sole tenant/key source-idempotency authority and is reserved before any inventory read or mutation. Import execution principals become durable task state loaded by workers, synchronous command identity derives from canonical normalized commands, and compatibility export moves to one bounded aggregate SQL query with exact Decimal text output and stable ordering.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, pytest, openpyxl, PostgreSQL/SQLite-compatible DDL.

## Global Constraints

- Every review item gets an independently observed failing test before production changes.
- Keep one Alembic head and verify disposable upgrade/downgrade/upgrade.
- Preserve queued immutable task UUID identity and old import/export HTTP/workbook contracts.
- Do not trust caller-supplied worker roles; execution identity comes from persisted task fields.
- Do not modify `.superpowers/sdd/progress.md` or any Task 7 scope.

---

### Task 1: C1 atomic typed source receipt and reachability preflight

**Files:**
- Create: `extensions/maintenance-api/alembic/versions/20260803_09_inventory_target_receipts.py`
- Modify: `extensions/maintenance-api/app/models/inventory_ledger.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/app/repositories/inventory_target_receipt_repository.py`
- Modify: `extensions/maintenance-api/app/services/inventory_target_adapter.py`
- Test: `extensions/maintenance-api/tests/imports/test_inventory_target_receipts.py`
- Test: `extensions/maintenance-api/tests/imports/test_inventory_import_ledger.py`
- Test: `extensions/maintenance-api/tests/migrations/test_inventory_target_receipt_migration.py`

**Interfaces:**
- Produces `InventoryTargetReceipt` with unique `(tenant_id, idempotency_key)`, typed `PENDING`/`COMPLETED` status, source hash, result JSON, actor audit, timestamps, and version.
- `InventoryTargetAdapter.apply_target()` reserves that row in a nested savepoint before policy/current reads and completes it only after a successful zero or physical target application.

- [ ] Write deterministic failing receipt tests for one-key cross-operation/cross-warehouse winner semantics, same-hash replay, changed-hash `IDEMPOTENCY_KEY_REUSED`, zero-delta no-transaction behavior, malformed/incomplete receipts, constraint-specific `IntegrityError` recovery, rollback, and PostgreSQL unique DDL compilation.
- [ ] Run only those tests and record the expected missing-model/table and double-winner failures.
- [ ] Add the typed model, repository, single-head migration, savepoint reservation/recovery, typed completed result validation, and remove `TARGET` inventory transactions.
- [ ] Add a preflight that computes non-DEFAULT component floors before any policy mutation/transaction; raise `INVENTORY_TARGET_UNREACHABLE` with tenant-neutral component details if target-minus-floor cannot form a valid DEFAULT balance.
- [ ] Run C1/preflight tests to GREEN and commit the receipt architecture.

### Task 2: I1 durable admin handoff, audit, and restart recovery

**Files:**
- Modify: `extensions/maintenance-api/app/models/import_task.py`
- Modify: `extensions/maintenance-api/app/repositories/import_task_repository.py`
- Modify: `extensions/maintenance-api/app/services/import_task_service.py`
- Modify: `extensions/maintenance-api/app/workers/import_executor.py`
- Modify: `extensions/maintenance-api/app/api/v1/master_data/imports.py`
- Modify: `extensions/maintenance-api/app/main.py`
- Test: `extensions/maintenance-api/tests/api/test_master_data_import_tasks.py`
- Test: `extensions/maintenance-api/tests/imports/test_import_task_worker.py`

**Interfaces:**
- Persists `execution_user_id`, `execution_roles_json`, `execution_request_id`, and `queued_at` at ADMIN queue transition.
- Worker `submit(task_id, tenant_id)` and `run_once(task_id, tenant_id)` load the execution principal exclusively from the task row.
- Startup recovery resets `RUNNING` to `QUEUED` under the documented policy and submits every durable `QUEUED` task.

- [ ] Write separate failing tests for contributor-to-different-admin handoff, cross-tenant 404, actor-aware `can_execute`, transaction audit attribution, ignored caller role markers/new signature, submit failure resubmission, and restart recovery.
- [ ] Run those tests and record RED.
- [ ] Implement tenant-admin lookup, durable principal fields and transitions, DB-loaded worker actor, actor-aware response mapping, and idempotent startup queue recovery.
- [ ] Run I1 tests to GREEN and commit durable execution authorization.

### Task 3: I2 canonical synchronous command identity

**Files:**
- Modify: `extensions/maintenance-api/app/services/import_service.py`
- Test: `extensions/maintenance-api/tests/imports/test_inventory_import_ledger.py`

**Interfaces:**
- Produces a SHA-256 identity from template version, canonical mapping, and the validated normalized command with explicit sheet/row ordering.
- Queued calls continue to use the immutable task UUID passed as `task_id`.

- [ ] Write failing tests proving logically identical but byte-different XLSX saves share keys, changed cells change identity, reordered rows have documented order-sensitive identity, and queued exact task replay remains unchanged.
- [ ] Run those tests and record RED.
- [ ] Implement canonical command hashing after validation and before apply, without hashing raw ZIP bytes.
- [ ] Run I2 tests to GREEN and commit normalized synchronous identity.

### Task 4: I3 bounded ledger-backed export SQL

**Files:**
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Modify: `extensions/maintenance-api/app/services/inventory_query_service.py`
- Modify: `extensions/maintenance-api/app/exporters/master_data_excel.py`
- Test: `extensions/maintenance-api/tests/exporters/test_master_data_excel.py`

**Interfaces:**
- Adds a compatibility export query accepting tenant, filters, keyword, sort field/order, and limit, returning at most `max_rows + 1` aggregate rows from one SQL result.

- [ ] Write failing query-shape/call-count tests showing filter/aggregate/order/`LIMIT max_rows + 1` are applied before workbook creation and oversized results abort before row writes.
- [ ] Run I3 tests and record RED.
- [ ] Implement one joined aggregate query and remove tenant-wide parent and summary materialization from the exporter.
- [ ] Run I3 tests to GREEN and commit bounded export querying.

### Task 5: I4 exact Decimal export and M1 stable sorting

**Files:**
- Modify: `extensions/maintenance-api/app/exporters/master_data_excel.py`
- Test: `extensions/maintenance-api/tests/exporters/test_master_data_excel.py`

**Interfaces:**
- Writes quantity/policy Decimal values as fixed scale-4 text.
- Orders requested value ascending/descending while always ordering warehouse/spare identifiers ascending for ties; `last_counted_at` null ordering is explicit.

- [ ] Write independent failing I4 max-`Numeric(18,4)` and representative round-trip tests.
- [ ] Run and record I4 RED, implement exact fixed-scale text, then run GREEN.
- [ ] Write independent failing M1 equal-value ascending/descending and null `last_counted_at` tests.
- [ ] Run and record M1 RED, implement direction-only primary sorting with ascending tie-breakers, then run GREEN.
- [ ] Commit Decimal and stable-sort compatibility fixes.

### Task 6: Integrated verification and review report

**Files:**
- Modify: `.superpowers/sdd/task-6-report.md`

- [ ] Run Task 6 focused, API/worker/RBAC, Task 2-5 regression, migration disposable up/down/up, full backend, changed-file Ruff, `git diff --check`, single-head check, and runtime legacy-reference scan.
- [ ] Append review RED/GREEN evidence, migration verification, residual PostgreSQL test availability, and fix commit SHAs to the Task 6 report.
- [ ] Commit the report without staging `.superpowers/sdd/progress.md`.

# Task 6 Import Execution Principal Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close the durable import execution-principal recovery gap without entering Plan 05-4A Task 7.

**Architecture:** Centralize persisted-principal validation, let a same-tenant ADMIN atomically reclaim invalid queued work, and convert invalid worker/restart states back to recoverable `PREVIEW_VALID`. Preserve a valid winning execution principal and never infer authority from the uploader.

**Tech Stack:** Python 3.11, SQLAlchemy 2, FastAPI, pytest, SQLite/PostgreSQL-compatible SQL.

## Global Constraints

- Write and observe failing tests before production changes.
- Keep all task lookup and updates tenant-scoped.
- Do not overwrite a valid persisted execution principal on duplicate execute.
- Do not modify Alembic revisions, `.superpowers/sdd/progress.md`, or Task 7 files.
- Keep the public worker signatures `submit(task_id, tenant_id)` and `run_once(task_id, tenant_id)` unchanged.

---

### Task 1: Shared persisted-principal contract and ADMIN reclaim

**Files:**
- Create: `extensions/maintenance-api/app/services/import_execution_principal.py`
- Modify: `extensions/maintenance-api/app/services/import_task_service.py`
- Test: `extensions/maintenance-api/tests/imports/test_import_execution_principal_recovery.py`

**Interfaces:**
- Produces: `execution_actor_from_task(task: MasterDataImportTask) -> ActorContext`
- Produces: `has_valid_execution_principal(task: MasterDataImportTask) -> bool`
- Preserves: `ImportTaskService.queue_for_execution(...) -> tuple[MasterDataImportTask, bool]`

- [x] Add tests that create `QUEUED` rows with null and contributor principals, execute as a same-tenant ADMIN, and assert the row is atomically rewritten with the ADMIN principal and `should_submit=True`.
- [x] Run the focused tests and verify they fail because `queue_for_execution()` returns the invalid row unchanged.
- [x] Add the shared principal helper and use it in `queue_for_execution()`.
- [x] Implement optimistic queued reclaim constrained by id, tenant, status, version, and expiry.
- [x] Add a duplicate-valid-principal test proving the original winner is not overwritten.
- [x] Run the focused tests to green.

### Task 2: Worker and startup recovery for invalid principals

**Files:**
- Modify: `extensions/maintenance-api/app/workers/import_executor.py`
- Test: `extensions/maintenance-api/tests/imports/test_import_execution_principal_recovery.py`
- Test: `extensions/maintenance-api/tests/imports/test_import_task_worker.py`

**Interfaces:**
- Produces stable recovery code `IMPORT_EXECUTION_PRINCIPAL_INVALID`.
- Invalid non-expired `QUEUED`/`RUNNING` rows become `PREVIEW_VALID` with principal fields cleared.
- Only valid queued rows are submitted by startup recovery.

- [x] Add a worker test proving an invalid principal currently raises while leaving the row `QUEUED`.
- [x] Add a startup test with valid queued/running and invalid queued/running rows.
- [x] Run the tests and verify the invalid rows remain stranded.
- [x] Replace worker-local principal parsing with the shared helper.
- [x] Add one recovery transition helper that clears principal/start/finish fields, increments version, and stores the stable error.
- [x] Use the transition in `run_once()` before re-raising authorization failure.
- [x] Partition startup recovery by shared principal validity and submit only valid queued rows.
- [x] Run focused worker/recovery tests to green.

### Task 3: Task 6 verification and report addendum

**Files:**
- Modify: `.superpowers/sdd/task-6-report.md`

**Interfaces:**
- Records the new review finding, RED/GREEN evidence, commit range, and remaining Python 3.11/PostgreSQL verification boundary.

- [x] Run focused tests for the new recovery file and existing worker tests.
- [x] Run Task 6 non-API focused regression tests available in the sandbox.
- [ ] Run Ruff on changed Python files.
- [x] Run `git diff --check` and confirm `.superpowers/sdd/progress.md` is untouched.
- [x] Append evidence to `.superpowers/sdd/task-6-report.md` without marking Plan 05-4A Task 7 complete.
- [x] Commit the implementation and report.

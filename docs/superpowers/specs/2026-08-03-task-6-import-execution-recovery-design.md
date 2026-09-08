# Task 6 Import Execution Principal Recovery Design

## Context

Task 6 persists the administrator execution principal on `master_data_import_tasks` and makes workers load that principal from the database. The migration intentionally leaves the new columns nullable so existing databases can upgrade without inventing an administrator identity.

That compatibility choice creates a recovery gap for pre-upgrade or malformed `QUEUED`/`RUNNING` rows:

- `queue_for_execution()` returns every `QUEUED` task without checking whether the persisted principal is usable;
- startup recovery only resubmits rows whose principal columns are non-null;
- `run_once()` validates the principal before entering its failure-persistence path;
- a missing or non-admin principal can therefore remain queued indefinitely.

This design closes that gap without entering Plan 05-4A Task 7.

## Requirements

1. A same-tenant ADMIN can reclaim a non-expired `QUEUED` task whose persisted execution principal is missing or invalid.
2. Reclaiming is optimistic and atomic: the current row version and `QUEUED` status must still match when the new principal is written.
3. A valid persisted principal remains authoritative. A duplicate execute request resubmits the existing task but does not overwrite the winning principal.
4. A worker that encounters an invalid persisted principal must persist a recoverable state instead of leaving the task silently queued.
5. Startup recovery must:
   - expire stale queued/running tasks as before;
   - reset valid interrupted `RUNNING` tasks to `QUEUED` and resubmit them;
   - reset invalid queued/running tasks to `PREVIEW_VALID` with a stable error code so an ADMIN can execute them again;
   - never infer execution authority from uploader identity.
6. Tenant isolation remains unchanged: all reclamation updates include `tenant_id`.
7. No schema migration is required.
8. `.superpowers/sdd/progress.md` and Plan 05-4A Task 7 scope remain untouched.

## Architecture

### Shared principal validation

Create `app/services/import_execution_principal.py` as the single authority for converting persisted task fields into an `ActorContext`.

- `execution_actor_from_task(task)` returns an ADMIN `ActorContext` or raises `InsufficientMaintenanceRoleError`.
- `has_valid_execution_principal(task)` returns a boolean using the same validation rules.

Both the task service and worker use these helpers so queueing, execution, and recovery cannot drift.

### Atomic administrator reclaim

`ImportTaskService.queue_for_execution()` handles `QUEUED` rows in two ways:

- valid principal: return the row with `should_submit=True` without changing audit identity;
- invalid principal: execute an optimistic `UPDATE` constrained by task id, tenant id, `QUEUED` status, version, and expiry. The update writes the current ADMIN principal, increments version, clears prior recovery errors, and refreshes `queued_at`.

If the update loses a race, reload the row. A valid queued winner is returned for resubmission; terminal states remain idempotent; other states raise `IMPORT_TASK_QUEUE_CONFLICT`.

### Recoverable worker rejection

Before starting a task, `run_once()` validates the persisted principal. When validation fails, it atomically changes a non-expired `QUEUED` or `RUNNING` row to `PREVIEW_VALID`, clears execution-principal fields and start/finish timestamps, increments version, and stores:

- `error_code = IMPORT_EXECUTION_PRINCIPAL_INVALID`
- `error_message = Import execution requires a persisted administrator principal`

The original authorization exception is then re-raised for direct callers. The task is no longer advertised as actively queued and can be safely queued again by an ADMIN.

### Startup recovery

`recover_stale_import_tasks()` partitions non-expired queued/running rows by shared principal validity:

- valid `RUNNING` rows become `QUEUED`;
- valid `QUEUED` rows stay queued;
- invalid `QUEUED` or `RUNNING` rows become recoverable `PREVIEW_VALID` rows with the stable error fields above;
- only valid queued rows are submitted after commit.

## Tests

Focused regression tests cover:

1. ADMIN reclaim of a legacy queued task with all principal fields null.
2. ADMIN reclaim of a queued task with a persisted contributor role.
3. Duplicate execute preserving a valid winning principal.
4. Optimistic reclaim race preserving the winner.
5. Worker invalid-principal rejection persisting `PREVIEW_VALID` and stable error fields.
6. Startup recovery resubmitting valid rows while converting invalid queued/running rows to `PREVIEW_VALID`.
7. Cross-tenant task lookup remains `RESOURCE_NOT_FOUND`.

Verification includes focused worker/service tests, Task 6 focused regressions, changed-file Ruff, and `git diff --check`. Python 3.11 API-suite evidence must be run in the user worktree because the sandbox Python/FastAPI versions do not match the project lock.

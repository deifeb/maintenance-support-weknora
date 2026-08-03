# Maintenance Plan05 Task 7.5A/7.5B Integration Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current uncommitted AI route migration into one reviewable Task 7.5A/7.5B atomic slice that enforces JWT-derived ActorContext on every AI route, preserves ActorContext through workers, derives tool permissions from role, applies dynamic admin escalation before active-task cancellation writes, and keeps recovery events consistent with persisted state.

**Architecture:** The slice keeps `Internal JWT -> role dependency -> AI router -> ActorContext -> service -> tenant-scoped repository`. Routers own static role floors; services own dynamic authorization and transactions; workers carry immutable `ActorContext`; tool permissions are derived centrally from `MaintenanceRole`. Existing review/report actor plumbing stays as enabling infrastructure, but Task 7.5C and Task 7.5D are not declared complete here.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy 2.x, Pytest, Ruff, PowerShell 5.1, Git.

## Global Constraints

- Worktree: `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Branch: `feature/maintenance-frontend-plan05`.
- API root: `extensions/maintenance-api`.
- Python: `E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe`.
- Preserve the current uncommitted Task 7.5 diff; do not reset or discard it.
- Keep the Git index empty until final review approval.
- Do not stage, commit, or push from RED/GREEN scripts.
- Every production fix must follow an observed failing test.
- Do not add compatibility shims for `created_by`, `resolved_by`, `user_id`, `permissions`, or payload identity.
- Do not synthesize a recovery actor.
- Dynamic authorization must happen before the first write.
- Cross-tenant resources remain 404/no existence leak.
- AI routers must not use `session.get()` for tenant-owned models.
- Every `/api/v1/ai/` endpoint must declare exactly one named role dependency.
- Task 7.5C review completeness and Task 7.5D report lifecycle completeness remain later gates.
- The final review package must include the untracked `tests/api/test_ai_actor_routes.py`.

---

## Current Review Findings to Resolve

1. `tests/api/test_ai_actor_routes.py` is untracked and absent from the exported `git diff`.
2. Worker and permission changes lack dedicated Task 7.5B tests.
3. Recovery can emit `RECOVERY_COMPLETED/PARTIALLY_COMPLETED` while the session remains `WAITING_ASYNC_TASK`.
4. Active-task cancellation lets a contributor create confirmation/state writes without first passing an admin check.
5. `tests/security/test_ai_no_arbitrary_tools.py` still calls authenticated AI routes without JWT headers.

---

### Task 1: Establish Missing RED Coverage

**Files:**
- Keep/Create: `extensions/maintenance-api/tests/api/test_ai_actor_routes.py`
- Create: `extensions/maintenance-api/tests/api/test_ai_sessions.py`
- Create: `extensions/maintenance-api/tests/api/test_ai_confirmations.py`
- Create: `extensions/maintenance-api/tests/workers/test_ai_executor.py`
- Modify: `extensions/maintenance-api/tests/services/test_ai_tool_registry.py`
- Modify: `extensions/maintenance-api/tests/workers/test_ai_recovery.py`
- Modify: `extensions/maintenance-api/tests/security/test_ai_no_arbitrary_tools.py`

**Interfaces:**
- Consumes `internal_auth_headers(...)`, `ActorContext`, `MaintenanceRole`.
- Covers `permissions_for_actor(actor)`, `submit_ai_session(session_id, actor)`, `submit_report_job(report_job_id, actor)`.

- [ ] **Step 1: Verify the existing untracked route test**

Run:

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api"
& $python -m pytest tests/api/test_ai_actor_routes.py --collect-only -q
```

Expected: `11 tests collected`.

- [ ] **Step 2: Add active-cancellation tests**

Create `tests/api/test_ai_sessions.py` with:

```python
from __future__ import annotations

from collections.abc import Callable

from app.models.enums import AISessionStatus
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.ai.factories import create_ai_session


def test_contributor_cannot_cancel_session_with_active_task(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.EXECUTING,
    )
    row.active_calculation_id = 91
    session.commit()

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="contributor-a",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.refresh(row)
    assert row.status is AISessionStatus.EXECUTING
    assert row.active_calculation_id == 91


def test_admin_active_cancel_creates_secondary_confirmation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    row = create_ai_session(
        session,
        tenant_id="tenant-a",
        status=AISessionStatus.EXECUTING,
    )
    row.active_report_job_id = 44
    session.commit()

    response = client.post(
        f"/api/v1/ai/sessions/{row.id}/cancel",
        headers=internal_auth_headers(
            tenant_id="tenant-a",
            user_id="admin-a",
            role=MaintenanceRole.ADMIN,
        ),
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["status"]
        == "CONFIRMATION_REQUIRED"
    )
    assert response.json()["data"]["confirmation_id"] > 0
```

Use real same-tenant linked rows if foreign keys reject raw IDs.

- [ ] **Step 3: Add worker ActorContext tests**

Create `tests/workers/test_ai_executor.py`:

```python
from inspect import signature

from app.workers.ai_executor import (
    submit_ai_session,
    submit_report_job,
)


def test_ai_worker_entrypoints_require_actor() -> None:
    session_parameters = signature(
        submit_ai_session
    ).parameters
    report_parameters = signature(
        submit_report_job
    ).parameters

    assert "actor" in session_parameters
    assert "user_id" not in session_parameters
    assert "permissions" not in session_parameters
    assert "actor" in report_parameters
```

Add immediate-executor tests that monkeypatch `SessionLocal`, `ai_task_executor`, orchestration/report methods, execute the closure synchronously, and assert the exact `actor_contributor` or `actor_admin` object is passed through unchanged.

- [ ] **Step 4: Add exact permission-matrix coverage**

Append to `tests/services/test_ai_tool_registry.py`:

```python
def test_tool_permissions_are_derived_from_actor_role(
    actor_context,
) -> None:
    viewer = actor_context(role=MaintenanceRole.VIEWER)
    contributor = actor_context(
        role=MaintenanceRole.CONTRIBUTOR
    )
    admin = actor_context(role=MaintenanceRole.ADMIN)

    assert permissions_for_actor(viewer) == frozenset()
    assert permissions_for_actor(contributor) == frozenset(
        {
            "SCENARIO_DRAFT",
            "CALCULATION_EXECUTE",
            "CALCULATION_CANCEL",
            "REPORT_CREATE",
            "REVIEW_EXECUTE",
        }
    )
    assert permissions_for_actor(admin) == (
        permissions_for_actor(contributor)
        | frozenset({"SCENARIO_PUBLISH"})
    )
```

- [ ] **Step 5: Add recovery consistency coverage**

Extend `tests/workers/test_ai_recovery.py` with a same-tenant `WAITING_ASYNC_TASK` session linked to a `PENDING` calculation. Assert:

```python
assert count == 0
assert row.status is AISessionStatus.WAITING_ASYNC_TASK
assert events[-1].payload_json["status"] == (
    AISessionStatus.WAITING_ASYNC_TASK.value
)
assert (
    events[-1].payload_json["resume_requires_actor"]
    is True
)
```

- [ ] **Step 6: Authenticate the arbitrary-tool test**

Modify `tests/security/test_ai_no_arbitrary_tools.py` so both requests use contributor headers:

```python
headers = internal_auth_headers(
    tenant_id="tenant-a",
    user_id="security-user",
    role=MaintenanceRole.CONTRIBUTOR,
)
```

Keep the assertions `TOOL_NOT_REGISTERED` and zero `AIToolCall` rows.

- [ ] **Step 7: Run RED**

Run:

```powershell
& $python -m pytest `
  tests/api/test_ai_sessions.py `
  tests/api/test_ai_confirmations.py `
  tests/workers/test_ai_executor.py `
  tests/services/test_ai_tool_registry.py `
  tests/workers/test_ai_recovery.py `
  tests/security/test_ai_no_arbitrary_tools.py `
  -v
```

Expected RED:
- contributor active cancellation is not yet 403/no-mutation;
- recovery event status does not match persisted waiting state;
- any missing worker continuity assertion fails for the concrete signature/actor reason.

Collection, syntax, or fixture failures do not count as valid RED.

---

### Task 2: Enforce Dynamic Admin Cancellation in the Service Layer

**Files:**
- Modify: `extensions/maintenance-api/app/services/ai_session_service.py`
- Modify: `extensions/maintenance-api/app/api/v1/ai/sessions.py`
- Test: `extensions/maintenance-api/tests/api/test_ai_sessions.py`

**Produces:**

```python
@dataclass(slots=True)
class AISessionCancelResult:
    session: AISession
    confirmation: AIConfirmationRequest | None = None
    confirmation_token: str | None = None
```

and:

```python
def cancel(
    self,
    session: Session,
    actor: ActorContext,
    session_id: int,
) -> AISessionCancelResult:
    ...
```

- [ ] **Step 1: Inject `AIConfirmationService` into `AISessionService`**

Add constructor dependency with default `ai_confirmation_service`.

- [ ] **Step 2: Implement authorization-before-write**

The service must:

```python
row = self.get(session, actor, session_id)
has_active_task = (
    row.active_calculation_id is not None
    or row.active_report_job_id is not None
)

if has_active_task:
    require_role(actor, MaintenanceRole.ADMIN)
    confirmation, token = (
        self.confirmation_service.create(
            session,
            actor,
            session_id=session_id,
            operation_name="cancel_active_ai_task",
            confirmation_level="SECONDARY",
            input_payload={
                "active_calculation_id": (
                    row.active_calculation_id
                ),
                "active_report_job_id": (
                    row.active_report_job_id
                ),
            },
            risk_level="HIGH",
        )
    )
    row.status = AISessionStatus.CONFIRMATION_REQUIRED
    session.commit()
```

`require_role()` must execute before confirmation creation, status mutation, flush, or commit.

Ordinary cancellation remains contributor-accessible and appends `CANCELLED`.

- [ ] **Step 3: Make the router serialization-only**

`cancel_session()` calls `ai_session_service.cancel(...)`, serializes either confirmation data or the cancelled session, and performs no direct commit.

- [ ] **Step 4: Run tests**

```powershell
& $python -m pytest tests/api/test_ai_sessions.py -v
& $python -m pytest tests/api/test_ai_actor_routes.py -v
```

Expected: all pass.

---

### Task 3: Keep Recovery State and Events Consistent

**Files:**
- Modify: `extensions/maintenance-api/app/workers/ai_recovery.py`
- Test: `extensions/maintenance-api/tests/workers/test_ai_recovery.py`

- [ ] **Step 1: Track final status per recovery event**

Use:

```python
sessions_with_events: list[
    tuple[str, int, AISessionStatus]
] = []
```

- [ ] **Step 2: Preserve waiting state when calculation is still active**

Set:

```python
if calculation.status in {
    CalculationStatus.PENDING,
    CalculationStatus.RUNNING,
}:
    final_status = AISessionStatus.WAITING_ASYNC_TASK
else:
    final_status = AISessionStatus.PARTIALLY_COMPLETED
```

Only increment `changed` when `row.status` actually changes.

- [ ] **Step 3: Flush before ownership lookups and emit matching payload**

Keep the existing protective `session.flush()` and emit:

```python
for tenant_id, session_id, final_status in (
    sessions_with_events
):
    ai_session_repository.append_event(
        session,
        tenant_id,
        session_id,
        "RECOVERY_COMPLETED",
        {
            "status": final_status.value,
            "resume_requires_actor": True,
        },
        visibility="SYSTEM",
    )
```

Do not call `submit_ai_session()` and do not construct a recovery actor.

- [ ] **Step 4: Run recovery tests**

```powershell
& $python -m pytest tests/workers/test_ai_recovery.py -v
```

Expected: interrupted rows become partially completed; still-active rows remain waiting; event payload equals persisted state.

---

### Task 4: Verify Worker and Permission Continuity

**Files:**
- Modify only when a RED test proves necessary:
  - `extensions/maintenance-api/app/services/ai_tool_registry.py`
  - `extensions/maintenance-api/app/workers/ai_executor.py`
  - `extensions/maintenance-api/app/api/v1/ai/confirmations.py`
- Test:
  - `extensions/maintenance-api/tests/workers/test_ai_executor.py`
  - `extensions/maintenance-api/tests/services/test_ai_tool_registry.py`
  - `extensions/maintenance-api/tests/api/test_ai_confirmations.py`
  - `extensions/maintenance-api/tests/security/test_ai_no_arbitrary_tools.py`

**Required signatures:**

```python
def permissions_for_actor(
    actor: ActorContext,
) -> frozenset[str]:
    ...


def submit_ai_session(
    session_id: int,
    actor: ActorContext,
    *,
    workspace_id: str = "default",
) -> Future[None] | None:
    ...


def submit_report_job(
    report_job_id: int,
    actor: ActorContext,
) -> Future[None] | None:
    ...
```

- [ ] **Step 1: Verify central role mapping**

Viewer has no write tool permissions; contributor has the five approved permissions; admin adds `SCENARIO_PUBLISH`.

- [ ] **Step 2: Verify exact actor forwarding**

`submit_ai_session()` passes the same actor to `execute_plan()` and derives `permissions` through `permissions_for_actor(actor)`.

`submit_report_job()` passes the same actor to `generate()` and `validate()`.

`confirmations.py` calls:

```python
submit_ai_session(row.session_id, actor)
```

- [ ] **Step 3: Run the focused worker/permission/security tests**

```powershell
& $python -m pytest `
  tests/workers/test_ai_executor.py `
  tests/services/test_ai_tool_registry.py `
  tests/api/test_ai_confirmations.py `
  tests/security/test_ai_no_arbitrary_tools.py `
  -v
```

Expected: all pass.

---

### Task 5: Run Final Gates and Export a Complete Review Package

**Review artifacts:**
- `D:\Desktop\maintenance-task075ab-review.diff`
- `D:\Desktop\maintenance-task075ab-review-untracked.diff`
- `D:\Desktop\maintenance-task075ab-review-files.txt`
- `D:\Desktop\maintenance-task075ab-final-gates-log.txt`

- [ ] **Step 1: Run focused Task 7.5A/7.5B**

```powershell
& $python -m pytest `
  tests/api/test_ai_actor_routes.py `
  tests/api/test_ai_sessions.py `
  tests/api/test_ai_confirmations.py `
  tests/workers/test_ai_executor.py `
  tests/workers/test_ai_recovery.py `
  tests/security/test_ai_no_arbitrary_tools.py `
  tests/services/test_ai_tool_registry.py `
  -v
```

- [ ] **Step 2: Run affected regression**

```powershell
& $python -m pytest `
  tests/security/test_internal_jwt.py `
  tests/security/test_permissions.py `
  tests/security/test_ai_no_arbitrary_tools.py `
  tests/test_responses.py `
  tests/services/test_ai_session_service.py `
  tests/services/test_ai_context_service.py `
  tests/services/test_ai_evidence_service.py `
  tests/services/test_ai_review_service.py `
  tests/services/test_ai_report_service.py `
  tests/services/test_ai_tool_registry.py `
  tests/workers/test_ai_executor.py `
  tests/workers/test_ai_recovery.py `
  -v
```

- [ ] **Step 3: Run retained Task 7.4C**

```powershell
& $python -m pytest `
  tests/services/test_ai_plan_service.py `
  tests/services/test_ai_orchestration_service.py `
  tests/services/test_ai_tool_registry.py `
  tests/services/test_ai_tool_adapters.py `
  tests/services/test_ai_orchestration_tenant_scope.py `
  tests/integration/test_ai_demand_assessment.py `
  -q
```

Expected: 16 passed.

- [ ] **Step 4: Run broad API/security/worker and static gates**

```powershell
& $python -m pytest tests/api tests/security tests/workers -q
& $python -m ruff check app tests
& $python -m compileall -q app tests
git diff --check
git diff --cached --name-only
```

Expected: tests pass, Ruff/compile pass, diff check passes, index is empty.

Use a temporary Python file, not `python -c`, for the AST/static scan. It must verify:
- 26 AI endpoints;
- exactly one named role dependency per endpoint;
- no `api-user`, `permissions={`, `session.get(`, `payload.actor`, `created_by=`, or `resolved_by=` in AI route modules;
- no worker `user_id`/`permissions` entrypoint parameters or `system-recovery`.

- [ ] **Step 5: Export tracked diff**

```powershell
git diff --binary --no-ext-diff |
  Set-Content `
    -LiteralPath "D:\Desktop\maintenance-task075ab-review.diff" `
    -Encoding UTF8
```

- [ ] **Step 6: Export the untracked route test**

```powershell
git diff --no-index -- NUL `
  "extensions/maintenance-api/tests/api/test_ai_actor_routes.py" |
  Set-Content `
    -LiteralPath "D:\Desktop\maintenance-task075ab-review-untracked.diff" `
    -Encoding UTF8
```

Exit code 1 is expected because differences exist. The exported file must be nonempty.

- [ ] **Step 7: Export file list and stop for review**

```powershell
git status --short |
  Set-Content `
    -LiteralPath "D:\Desktop\maintenance-task075ab-review-files.txt" `
    -Encoding UTF8
```

Upload all four review artifacts. Do not stage or commit before review approval.

---

### Task 6: Commit the Reviewed Atomic Slice

**Commit message:**

```text
feat: preserve actor context across ai routes and workers
```

- [ ] **Step 1: Re-run Task 5 gates after review fixes**
- [ ] **Step 2: Stage only explicit reviewed paths; do not use `git add .` or `git add -A`**
- [ ] **Step 3: Verify `git diff --cached --check`, `--name-status`, and `--stat`**
- [ ] **Step 4: Commit with the exact message**
- [ ] **Step 5: Verify `git show --stat --oneline HEAD` and a clean worktree**

## Self-Review Results

- All four code-review findings map to explicit RED/GREEN tasks.
- The untracked route test is explicitly included in the review and commit workflow.
- Dynamic admin authorization occurs before all active-cancel writes.
- Recovery never invents identity and its event payload matches persisted state.
- Worker and tool permission contracts use exact signatures across tasks.
- Task 7.5C and Task 7.5D are not falsely marked complete.

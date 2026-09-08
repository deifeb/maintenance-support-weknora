# Maintenance Plan 05-1 Task 7 Full-Suite Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the complete Plan 05-1 Python gate by making seed data explicitly tenant-scoped and migrating the remaining AI model/integration tests from the legacy single-tenant, unauthenticated assumptions.

**Architecture:** Treat the four failures as two connected boundary gaps. Seed scripts receive an explicit keyword-only `tenant_id`, include it in every lookup, insert, relationship query, and count, and expose an explicit `--tenant-id` CLI argument. AI behavior tests use the existing `authenticated_client` fixture and tenant-matching test data rather than weakening authentication or adding test-only production bypasses.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy 2.x, PyJWT, pytest, Ruff, SQLite, Windows PowerShell 5.1, Git.

## Global Constraints

- Worktree: `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`
- Branch: `feature/maintenance-frontend-plan05`
- Starting HEAD: `f847d7d44f17bfc606971863cb5aecd2a2007278`
- Python: `E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe`
- API root: `extensions/maintenance-api`
- Preserve the fail-closed internal JWT boundary; do not make `client` implicitly authenticated.
- Do not introduce a default production tenant for seed operations.
- `MAINTENANCE_LEGACY_TENANT_ID` remains reserved for explicit one-time migration/backfill and must not be reused by seed scripts.
- Every seed entry point requires an explicit tenant through `seed(tenant_id=...)` or CLI `--tenant-id`.
- Natural-key lookups, relationship queries, and returned counts must all include `tenant_id`.
- No `git add`, commit, push, reset, or clean before review approval.
- A Task 7 failure returns to the owning implementation task; do not update `.superpowers/sdd/progress.md` until the complete gate is green and reviewed.
- Do not push the feature branch during this recovery. Task 8 owns the final push.

---

### Task 0: Persist the Approved Recovery Plan

**Files:**
- Create: `docs/superpowers/plans/2026-07-27-maintenance-plan05-01-task7-full-suite-recovery.md`

**Interfaces:**
- Consumes: approved contents of this plan.
- Produces: a durable, reviewable recovery specification before production or test code changes.

- [ ] **Step 1: Verify the starting branch and clean worktree**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05"

git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
```

Expected:

```text
feature/maintenance-frontend-plan05
f847d7d44f17bfc606971863cb5aecd2a2007278
```

`git status --short` and `git diff --cached --name-only` must be empty.

- [ ] **Step 2: Copy the approved plan into the repository**

Copy this exact file to:

```text
docs/superpowers/plans/2026-07-27-maintenance-plan05-01-task7-full-suite-recovery.md
```

- [ ] **Step 3: Review only the plan file**

```powershell
git status --short
git diff -- `
  docs/superpowers/plans/2026-07-27-maintenance-plan05-01-task7-full-suite-recovery.md
git diff --check
```

Expected dirty scope:

```text
?? docs/superpowers/plans/2026-07-27-maintenance-plan05-01-task7-full-suite-recovery.md
```

- [ ] **Step 4: Commit the approved plan after review**

```powershell
git add `
  docs/superpowers/plans/2026-07-27-maintenance-plan05-01-task7-full-suite-recovery.md

git diff --cached --check
git commit -m "docs: plan Task 7 full-suite recovery"
```

Do not push.

---

### Task 1: Add Tenant-Scoped Seed RED Coverage

**Files:**
- Create: `extensions/maintenance-api/tests/integration/test_tenant_seed_scripts.py`
- Test: `extensions/maintenance-api/tests/integration/test_ai_full_workflow.py`

**Interfaces:**
- Consumes:
  - `app.scripts.seed_master_data.seed`
  - `app.scripts.seed_demand_scenarios.seed`
  - SQLAlchemy models with non-null `tenant_id`
- Produces:
  - a failing contract requiring explicit tenant arguments;
  - tenant-local idempotency;
  - duplicate natural codes allowed across distinct tenants without leakage.

- [ ] **Step 1: Create the focused seed contract**

Create `tests/integration/test_tenant_seed_scripts.py`:

```python
from sqlalchemy import func, select

from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
    EquipmentModel,
    Part,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
    WarehouseInventory,
)
from app.scripts.seed_demand_scenarios import (
    seed as seed_demand_scenarios,
)
from app.scripts.seed_master_data import (
    seed as seed_master_data,
)


TENANT_OWNED_SEED_MODELS = (
    EquipmentModel,
    ConfigurationVersion,
    ConfigurationItem,
    Part,
    SparePart,
    ReliabilityProfile,
    Warehouse,
    WarehouseInventory,
    Supplier,
    SupplierOffer,
    RepairProfile,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandFleetGroup,
    DemandAgeGroup,
    DemandScenarioStage,
    DemandStageFleetUsage,
    DemandCommonShockRule,
)


def _count_for_tenant(
    session,
    model,
    tenant_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count(model.id)).where(
                model.tenant_id == tenant_id,
            )
        )
        or 0
    )


def test_seed_scripts_are_tenant_scoped_and_idempotent(
    session,
) -> None:
    seed_master_data(tenant_id="tenant-a")
    seed_demand_scenarios(tenant_id="tenant-a")

    first_counts = {
        model: _count_for_tenant(
            session,
            model,
            "tenant-a",
        )
        for model in TENANT_OWNED_SEED_MODELS
    }
    assert all(count > 0 for count in first_counts.values())

    seed_master_data(tenant_id="tenant-a")
    seed_demand_scenarios(tenant_id="tenant-a")

    second_counts = {
        model: _count_for_tenant(
            session,
            model,
            "tenant-a",
        )
        for model in TENANT_OWNED_SEED_MODELS
    }
    assert second_counts == first_counts

    seed_master_data(tenant_id="tenant-b")
    seed_demand_scenarios(tenant_id="tenant-b")

    tenant_b_counts = {
        model: _count_for_tenant(
            session,
            model,
            "tenant-b",
        )
        for model in TENANT_OWNED_SEED_MODELS
    }
    assert tenant_b_counts == first_counts

    equipment_rows = set(
        session.execute(
            select(
                EquipmentModel.tenant_id,
                EquipmentModel.code,
            ).where(
                EquipmentModel.code == "EQ-001",
            )
        ).all()
    )
    assert equipment_rows == {
        ("tenant-a", "EQ-001"),
        ("tenant-b", "EQ-001"),
    }
```

- [ ] **Step 2: Run the focused RED**

```powershell
Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api"

$python = "E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe"

& $python -m pytest `
  tests/integration/test_tenant_seed_scripts.py `
  -v --tb=short
```

Expected: FAIL because the current seed functions do not accept `tenant_id`.

- [ ] **Step 3: Reproduce the four original failures without changing code**

```powershell
& $python -m pytest `
  tests/models/test_ai_models.py::test_session_and_event_constraints `
  tests/integration/test_ai_disconnect_resume.py::test_sse_disconnect_and_resume_returns_only_missing_events `
  tests/integration/test_ai_full_workflow.py::test_ai_api_full_workflow_reaches_calculation_review_and_docx `
  tests/integration/test_ai_rule_fallback_workflow.py::test_unavailable_llm_path_is_explicit_rule_fallback `
  -v --tb=short
```

Expected:

```text
test_session_and_event_constraints:
  NOT NULL constraint failed: ai_sessions.tenant_id

test_sse_disconnect_and_resume_returns_only_missing_events:
  INTERNAL_TOKEN_INVALID

test_ai_api_full_workflow_reaches_calculation_review_and_docx:
  NOT NULL constraint failed: equipment_models.tenant_id

test_unavailable_llm_path_is_explicit_rule_fallback:
  response has no data because authentication failed
```

Stop if the failures differ materially.

---

### Task 2: Make Master-Data Seeds Explicitly Tenant-Scoped

**Files:**
- Modify: `extensions/maintenance-api/app/scripts/seed_master_data.py`
- Test: `extensions/maintenance-api/tests/integration/test_tenant_seed_scripts.py`

**Interfaces:**
- Consumes: keyword-only `tenant_id: str`.
- Produces:
  - `seed(*, tenant_id: str) -> dict[str, int]`
  - `get_or_create(session, model, *, tenant_id: str, lookup: dict, defaults: dict)`
  - CLI: `python -m app.scripts.seed_master_data --tenant-id <tenant>`

- [ ] **Step 1: Add tenant normalization and explicit CLI parsing**

Add imports:

```python
import argparse
```

Add:

```python
def _normalize_tenant_id(tenant_id: str) -> str:
    normalized = tenant_id.strip()
    if not normalized:
        raise ValueError("tenant_id must not be blank")
    return normalized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Tenant that owns all seeded master data",
    )
    return parser.parse_args()
```

- [ ] **Step 2: Scope `get_or_create` by tenant**

Replace the helper with:

```python
def get_or_create(
    session,
    model,
    *,
    tenant_id: str,
    lookup: dict,
    defaults: dict,
):
    scoped_lookup = {
        "tenant_id": tenant_id,
        **lookup,
    }
    instance = session.scalar(
        select(model).filter_by(**scoped_lookup)
    )
    if instance is None:
        instance = model(
            **scoped_lookup,
            **defaults,
        )
        session.add(instance)
        session.flush()
    return instance
```

Every call must use named arguments:

```python
get_or_create(
    session,
    EquipmentModel,
    tenant_id=tenant_id,
    lookup={"code": f"EQ-{index:03d}"},
    defaults={...},
)
```

- [ ] **Step 3: Make `seed` require a tenant**

Change:

```python
def seed(*, tenant_id: str) -> dict[str, int]:
    tenant_id = _normalize_tenant_id(tenant_id)
    session = SessionLocal()
```

- [ ] **Step 4: Scope direct configuration-item operations**

Every direct `ConfigurationItem` query must include:

```python
ConfigurationItem.tenant_id == tenant_id
```

Every direct constructor must include:

```python
tenant_id=tenant_id,
```

The parent lookup must include both:

```python
ConfigurationItem.tenant_id == tenant_id,
ConfigurationItem.configuration_version_id == version.id,
```

- [ ] **Step 5: Return tenant-local counts**

Replace the unscoped count expression with:

```python
return {
    model.__tablename__: len(
        session.scalars(
            select(model).where(
                model.tenant_id == tenant_id,
            )
        ).all()
    )
    for model in models
}
```

- [ ] **Step 6: Require `--tenant-id` in `main`**

Replace `main` with:

```python
def main() -> None:
    args = _parse_args()
    counts = seed(tenant_id=args.tenant_id)
    for table, count in counts.items():
        print(f"{table}: {count}")
```

- [ ] **Step 7: Run the focused test**

```powershell
& $python -m pytest `
  tests/integration/test_tenant_seed_scripts.py `
  -v --tb=short
```

Expected: the test still fails in `seed_demand_scenarios`, while master-data creation no longer fails on `tenant_id`.

---

### Task 3: Make Demand-Scenario Seeds Explicitly Tenant-Scoped

**Files:**
- Modify: `extensions/maintenance-api/app/scripts/seed_demand_scenarios.py`
- Test: `extensions/maintenance-api/tests/integration/test_tenant_seed_scripts.py`

**Interfaces:**
- Consumes:
  - `seed_master_data(tenant_id=tenant_id)`
  - keyword-only `tenant_id: str`
- Produces:
  - `seed(*, tenant_id: str) -> dict[str, int]`
  - CLI: `python -m app.scripts.seed_demand_scenarios --tenant-id <tenant>`

- [ ] **Step 1: Add tenant normalization and CLI parsing**

Add:

```python
import argparse
```

Add the same `_normalize_tenant_id` and `_parse_args` contract as Task 2, with help text:

```text
Tenant that owns all seeded demand scenarios
```

- [ ] **Step 2: Scope `get_or_create` by tenant**

Use the same keyword-only helper contract:

```python
def get_or_create(
    session,
    model,
    *,
    tenant_id: str,
    lookup: dict,
    defaults: dict,
):
    scoped_lookup = {
        "tenant_id": tenant_id,
        **lookup,
    }
    instance = session.scalar(
        select(model).filter_by(**scoped_lookup)
    )
    if instance is None:
        instance = model(
            **scoped_lookup,
            **defaults,
        )
        session.add(instance)
        session.flush()
    return instance
```

- [ ] **Step 3: Pass the tenant into master-data seeding**

Change:

```python
def seed(*, tenant_id: str) -> dict[str, int]:
    tenant_id = _normalize_tenant_id(tenant_id)
    seed_master_data(tenant_id=tenant_id)
```

- [ ] **Step 4: Scope prerequisite queries**

`published_config` must include:

```python
ConfigurationVersion.tenant_id == tenant_id
```

`repairable_spares` must include:

```python
SparePart.tenant_id == tenant_id
```

- [ ] **Step 5: Pass `tenant_id` to every `get_or_create`**

Apply to:

```text
RepairProfile
DemandScenarioTemplate
DemandScenarioVersion
DemandFleetGroup
DemandAgeGroup
DemandScenarioStage
DemandStageFleetUsage
DemandCommonShockRule
```

Each call uses:

```python
tenant_id=tenant_id,
lookup={...},
defaults={...},
```

- [ ] **Step 6: Return tenant-local counts**

Replace unscoped `session.query(...).count()` calls with:

```python
def tenant_count(model) -> int:
    return int(
        session.scalar(
            select(func.count(model.id)).where(
                model.tenant_id == tenant_id,
            )
        )
        or 0
    )
```

Add:

```python
from sqlalchemy import func, select
```

Return:

```python
return {
    "repair_profiles": tenant_count(RepairProfile),
    "scenario_templates": tenant_count(
        DemandScenarioTemplate,
    ),
    "scenario_versions": tenant_count(
        DemandScenarioVersion,
    ),
    "scenario_stages": tenant_count(
        DemandScenarioStage,
    ),
}
```

- [ ] **Step 7: Require `--tenant-id` in the module entry point**

```python
def main() -> None:
    args = _parse_args()
    print(seed(tenant_id=args.tenant_id))


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the tenant seed GREEN**

```powershell
& $python -m pytest `
  tests/integration/test_tenant_seed_scripts.py `
  -v --tb=short
```

Expected: PASS for tenant-local idempotency and tenant-a/tenant-b separation.

---

### Task 4: Repair the AI Model Constraint Test

**Files:**
- Modify: `extensions/maintenance-api/tests/models/test_ai_models.py`

**Interfaces:**
- Consumes: tenant-owned `AISession` and `AIEvent`.
- Produces: explicit tenant ownership in the model constraint test.

- [ ] **Step 1: Add the same tenant to the session and event**

Change the `AISession` constructor to include:

```python
tenant_id="tenant-a",
```

Change the `AIEvent` constructor to include:

```python
tenant_id="tenant-a",
```

- [ ] **Step 2: Run the focused model test**

```powershell
& $python -m pytest `
  tests/models/test_ai_models.py::test_session_and_event_constraints `
  -v --tb=short
```

Expected: PASS.

---

### Task 5: Migrate Remaining AI Workflows to Authenticated Tenant Context

**Files:**
- Modify: `extensions/maintenance-api/tests/integration/test_ai_disconnect_resume.py`
- Modify: `extensions/maintenance-api/tests/integration/test_ai_full_workflow.py`
- Modify: `extensions/maintenance-api/tests/integration/test_ai_rule_fallback_workflow.py`

**Interfaces:**
- Consumes:
  - existing `authenticated_client` fixture;
  - fixture actor tenant `tenant-a`;
  - seed functions with `tenant_id="tenant-a"`.
- Produces: behavior tests that exercise the protected route stack without bypassing production authentication.

- [ ] **Step 1: Use `authenticated_client` in disconnect/resume**

Change the test signature:

```python
def test_sse_disconnect_and_resume_returns_only_missing_events(
    authenticated_client,
    session,
) -> None:
```

Replace all three `client` calls with `authenticated_client`.

Keep:

```python
create_ai_session_with_events(
    session,
    count=2,
    tenant_id="tenant-a",
)
```

- [ ] **Step 2: Use authenticated tenant context in the full workflow**

Change the signature:

```python
def test_ai_api_full_workflow_reaches_calculation_review_and_docx(
    authenticated_client,
    session,
    monkeypatch,
) -> None:
```

Add:

```python
tenant_id = "tenant-a"
```

Change:

```python
seed_demand_scenarios(
    tenant_id=tenant_id,
)
```

Scope the published scenario query:

```python
.where(
    DemandScenarioVersion.tenant_id == tenant_id,
    DemandScenarioVersion.status
    == ScenarioVersionStatus.PUBLISHED,
)
```

Change `_wait_for_calculation` to accept `tenant_id`:

```python
def _wait_for_calculation(
    session,
    *,
    tenant_id: str,
    timeout: float = 15.0,
) -> DemandCalculation:
```

Scope its query:

```python
select(DemandCalculation)
.where(
    DemandCalculation.tenant_id == tenant_id,
)
.order_by(DemandCalculation.id.desc())
```

Call it with:

```python
calculation = _wait_for_calculation(
    session,
    tenant_id=tenant_id,
)
```

Scope count assertions:

```python
assert (
    session.scalar(
        select(func.count(DemandCalculation.id)).where(
            DemandCalculation.tenant_id == tenant_id,
        )
    )
    == 1
)
```

and:

```python
assert (
    session.scalar(
        select(func.count(AIReviewRun.id)).where(
            AIReviewRun.tenant_id == tenant_id,
        )
    )
    == 1
)
```

Replace every `client` request with `authenticated_client`.

Scope the final model-call query:

```python
model_calls = list(
    session.scalars(
        select(AIModelCall).where(
            AIModelCall.tenant_id == tenant_id,
        )
    ).all()
)
```

- [ ] **Step 3: Use authenticated tenant context in fallback workflow**

Change the signature:

```python
def test_unavailable_llm_path_is_explicit_rule_fallback(
    authenticated_client,
    session,
    monkeypatch,
) -> None:
```

Replace all `client` calls with `authenticated_client`.

Assert creation succeeded before reading the body:

```python
assert created.status_code == 200
```

Replace `session.get` with a tenant-scoped query:

```python
from sqlalchemy import select

row = session.scalar(
    select(AISession).where(
        AISession.id == session_id,
        AISession.tenant_id == "tenant-a",
    )
)
assert row is not None
session.refresh(row)
```

- [ ] **Step 4: Run the three focused integration tests**

```powershell
& $python -m pytest `
  tests/integration/test_ai_disconnect_resume.py `
  tests/integration/test_ai_full_workflow.py `
  tests/integration/test_ai_rule_fallback_workflow.py `
  -v --tb=short
```

Expected: all pass. Authentication failures must not be hidden by changing production dependencies or making the default `client` authenticated.

---

### Task 6: Run Focused and Complete Recovery Gates

**Files:**
- No additional repository file changes.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: review-ready recovery evidence.

- [ ] **Step 1: Run the seven-file focused suite**

```powershell
& $python -m pytest `
  tests/integration/test_tenant_seed_scripts.py `
  tests/models/test_ai_models.py `
  tests/integration/test_ai_disconnect_resume.py `
  tests/integration/test_ai_full_workflow.py `
  tests/integration/test_ai_rule_fallback_workflow.py `
  -q -ra --tb=short
```

Expected: zero failures.

- [ ] **Step 2: Run the complete Python Plan 05-1 scope**

```powershell
& $python -m pytest `
  tests/security `
  tests/migrations `
  tests/models `
  tests/repositories `
  tests/services `
  tests/api `
  tests/workers `
  tests/integration `
  -q -ra --tb=short
```

Expected: zero failures. Record the exact collected and passed counts rather than assuming a count in advance.

- [ ] **Step 3: Run static checks**

```powershell
& $python -m ruff check `
  app/scripts/seed_master_data.py `
  app/scripts/seed_demand_scenarios.py `
  tests/integration/test_tenant_seed_scripts.py `
  tests/models/test_ai_models.py `
  tests/integration/test_ai_disconnect_resume.py `
  tests/integration/test_ai_full_workflow.py `
  tests/integration/test_ai_rule_fallback_workflow.py

& $python -m compileall -q `
  app/scripts/seed_master_data.py `
  app/scripts/seed_demand_scenarios.py `
  tests/integration/test_tenant_seed_scripts.py `
  tests/models/test_ai_models.py `
  tests/integration/test_ai_disconnect_resume.py `
  tests/integration/test_ai_full_workflow.py `
  tests/integration/test_ai_rule_fallback_workflow.py

Set-Location "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05"

git diff --check
git diff --cached --check
```

Expected: all exit 0 and the index remains empty.

- [ ] **Step 4: Verify exact dirty scope**

Expected modified files:

```text
extensions/maintenance-api/app/scripts/seed_master_data.py
extensions/maintenance-api/app/scripts/seed_demand_scenarios.py
extensions/maintenance-api/tests/integration/test_ai_disconnect_resume.py
extensions/maintenance-api/tests/integration/test_ai_full_workflow.py
extensions/maintenance-api/tests/integration/test_ai_rule_fallback_workflow.py
extensions/maintenance-api/tests/models/test_ai_models.py
```

Expected new file:

```text
extensions/maintenance-api/tests/integration/test_tenant_seed_scripts.py
```

The approved recovery-plan commit is already committed and must not appear dirty.

- [ ] **Step 5: Export recovery review evidence**

Create:

```text
D:\Desktop\maintenance-plan05-01-task7-full-suite-recovery-log.txt
D:\Desktop\maintenance-plan05-01-task7-full-suite-recovery-status.txt
D:\Desktop\maintenance-plan05-01-task7-full-suite-recovery-review.diff
D:\Desktop\maintenance-plan05-01-task7-full-suite-recovery-files.txt
```

Required status markers:

```text
PLAN05_01_TASK7_FULL_SUITE_RECOVERY=READY_FOR_REVIEW
TENANT_SEED_CONTRACT=PASS
AI_MODEL_TENANT_CONSTRAINT=PASS
AI_DISCONNECT_RESUME_AUTH=PASS
AI_FULL_WORKFLOW_AUTH_AND_TENANT=PASS
AI_RULE_FALLBACK_AUTH=PASS
COMPLETE_PYTHON_SECURITY_SCOPE=PASS
RUFF=PASS
COMPILE=PASS
DIFF_CHECK=PASS
INDEX_EMPTY=PASS
STAGED=0
COMMITTED=0
PUSHED=0
```

Stop for review.

---

### Task 7: Commit the Reviewed Recovery

**Files:**
- Commit the seven reviewed files from Tasks 1–5.

**Interfaces:**
- Consumes: approved Task 6 review package.
- Produces: one recovery commit used as the new Task 7 gate HEAD.

- [ ] **Step 1: Re-run focused verification immediately before staging**

Run Tasks 6 Steps 1–3 again. All commands must produce fresh exit code 0 evidence.

- [ ] **Step 2: Stage exactly seven paths**

```powershell
git add `
  extensions/maintenance-api/app/scripts/seed_master_data.py `
  extensions/maintenance-api/app/scripts/seed_demand_scenarios.py `
  extensions/maintenance-api/tests/integration/test_tenant_seed_scripts.py `
  extensions/maintenance-api/tests/integration/test_ai_disconnect_resume.py `
  extensions/maintenance-api/tests/integration/test_ai_full_workflow.py `
  extensions/maintenance-api/tests/integration/test_ai_rule_fallback_workflow.py `
  extensions/maintenance-api/tests/models/test_ai_models.py
```

- [ ] **Step 3: Verify staged scope**

```powershell
git diff --cached --name-only
git diff --cached --check
git diff --name-only
git ls-files --others --exclude-standard
```

Expected: exactly seven staged files; no unstaged or untracked files.

- [ ] **Step 4: Commit**

```powershell
git commit -m "fix: restore tenant-aware ai integration suite"
```

- [ ] **Step 5: Verify the commit and clean worktree**

```powershell
git log -1 --oneline
git diff-tree --no-commit-id --name-only -r HEAD
git status --short
git diff --cached --name-only
```

Expected: the commit contains exactly seven paths and the worktree/index are clean.

Do not push.

---

### Task 8: Re-run the Complete Plan 05-1 Task 7 Gate

**Files:**
- No repository file modification during the gate.

**Interfaces:**
- Consumes: the recovery commit from Task 7.
- Produces: the complete review package required before `.superpowers/sdd/progress.md` is modified.

- [ ] **Step 1: Regenerate the Task 7 gate script with the new exact HEAD**

Keep the existing Phase baseline:

```text
70c6f460981b8d841569881c4ed86006057b39ab
```

Change only the expected HEAD and append both recovery commits to the expected commit chain:

```text
docs: plan Task 7 full-suite recovery
fix: restore tenant-aware ai integration suite
```

- [ ] **Step 2: Run the complete gate**

The gate must include:

```text
Go security packages
Alembic upgrade -> downgrade base -> upgrade
focused security evidence
complete Python security scope
Ruff app and tests
compileall app and tests
127-route RBAC/actor metadata evidence
tenant isolation evidence
proxy identity evidence
production settings evidence
internal-only Compose evidence
complete phase review export
clean worktree and empty index
```

- [ ] **Step 3: Require final status**

```text
PLAN05_01_SECURITY_CLOSURE=READY_FOR_REVIEW
GO_SECURITY=PASS
ALEMBIC_ROUNDTRIP=PASS
PYTHON_SECURITY=PASS
ROUTE_RBAC_MATRIX=127_PASS
TENANT_ISOLATION=PASS
PROXY_IDENTITY=PASS
PRODUCTION_SETTINGS=PASS
DOCKER_COMPOSE=PASS
RUFF=PASS
COMPILE=PASS
DIFF_CHECK=PASS
WORKTREE_CLEAN=PASS
INDEX_EMPTY=PASS
STAGED=0
PUSHED=0
```

Stop for review. Do not modify `.superpowers/sdd/progress.md` until this package is approved.

---

### Task 9: Resume Original Task 8 Only After Gate Approval

**Files:**
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: approved Task 8 complete-gate evidence.
- Produces: durable Plan 05-1 completion, final ledger commit, push, and PR.

- [ ] **Step 1: Return to the approved original Plan 05-1 Task 8**

Follow:

```text
docs/superpowers/plans/2026-07-26-maintenance-plan05-01-security-closure.md
```

Record the recovery commits and final gate artifact hashes in the ledger.

- [ ] **Step 2: Preserve the existing final commit message**

```text
docs: complete maintenance security foundation
```

- [ ] **Step 3: Push only in original Task 8**

Push:

```text
feature/maintenance-frontend-plan05
```

Then verify local and remote HEAD equality and open the PR against:

```text
feature/demand-calculation-engine
```

---

## Self-Review

- Spec coverage: all four observed failures map to a task, and the seed scripts receive independent cross-tenant/idempotency coverage.
- Security boundary: no production authentication bypass, no implicit authentication in the default `client`, and no fallback/default tenant in seed entry points.
- Tenant consistency: tenant IDs are required at seed entry points and propagated through lookup, insert, relationship query, and count operations.
- Test consistency: the existing `authenticated_client` actor tenant and seed/factory tenant are all `tenant-a`.
- Operational safety: `MAINTENANCE_LEGACY_TENANT_ID` is not reused for normal seeding.
- Git safety: plan commit and implementation commit are independently reviewed; no push occurs before the original Task 8.
- Placeholder scan: no TBD, TODO, or unspecified implementation step remains.

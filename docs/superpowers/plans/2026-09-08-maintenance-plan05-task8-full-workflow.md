# Plan 05 Task 8 Full Workflow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic full-workflow and provider-disabled integration evidence for Plan 05 without altering business behavior.

**Architecture:** Reuse the existing tenant-aware integration fixtures and service/API helpers. One test owns allocation-to-report invariants; a second owns AI-disabled fallback behavior. Tests observe persisted/public results and use existing repositories rather than recreating domain logic.

**Tech Stack:** Python, pytest, SQLAlchemy test session, FastAPI test client, Ruff.

## Global Constraints

- Create only the two Task 8 integration tests; modify `tests/conftest.py` only for a missing reusable deterministic fixture.
- Do not change application behavior, schemas, migrations, APIs, C3 frontend, or Task 9/10 artifacts.
- Keep every test tenant-scoped and use no production credentials, JWTs, provider secrets, or absolute paths.
- Assert report lifecycle states currently defined by the backend; never assert generic `COMPLETED`.
- If an assertion demonstrates a product defect, stop and create a separate bounded repair plan.

---

### Task 1: Allocation-plan to finalized-report integration

**Files:**
- Create: `extensions/maintenance-api/tests/integration/test_plan05_full_workflow.py`

**Interfaces:**
- Consumes: existing `session`, authenticated tenant actors/clients, demand-review/allocation integration helpers, `ReportCenterFacadeService`, and report export services.
- Produces: one complete tenant-scoped workflow assertion with no new production interface.

- [ ] **Step 1: Write the failing integration test**

Create `test_full_plan05_workflow_preserves_authority_and_report_lineage`. Start from the existing cross-domain/allocation workflow helpers. Seed tenant-A master/inventory facts, produce a scenario/calculation/published demand-list/review/derived list/allocation plan, execute it, then create an `ALLOCATION_PLAN` report with the exact allocation-plan source reference. Assert tenant-B cannot read tenant-A facts.

- [ ] **Step 2: Run RED**

Run:

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan05_full_workflow.py -v
```

Expected: failure because the test module is absent or workflow is incomplete.

- [ ] **Step 3: Complete the composed workflow assertions**

Use existing service helpers; do not hand-build unsupported state. Assert published demand-list mutation is rejected, allocation execution preserves ledger balance/reservation integrity, source ref contains the allocation plan exact version, snapshot content remains unchanged after source mutation, and generate/validate/finalize yield current READY/FINAL states. Export DOCX and assert nonempty payload. Assert finalized report destructive generate/regenerate behavior is rejected with the existing typed error.

- [ ] **Step 4: Run GREEN and commit**

Run the Task 1 command and expect one passing integration test.

```powershell
git add extensions/maintenance-api/tests/integration/test_plan05_full_workflow.py
git commit -m "test(maintenance): cover plan05 full workflow"
```

### Task 2: Provider-disabled deterministic workflow and closure

**Files:**
- Create: `extensions/maintenance-api/tests/integration/test_plan05_ai_disabled.py`

**Interfaces:**
- Consumes: existing AI runtime/router seams, authenticated API client, report lifecycle/export API, and `RULE_FALLBACK` behavior.
- Produces: provider-disabled evidence that structured operations retain current report lifecycle semantics.

- [ ] **Step 1: Write failing fallback test**

Create `test_plan05_ai_disabled_workflow_uses_rule_fallback`. Monkeypatch the existing runtime factory/router so every remote/local provider is unavailable while the explicit rule fallback remains configured. Build a structured scenario, deterministic calculation, published demand list, deterministic review, and `DEMAND_REVIEW` report.

- [ ] **Step 2: Run RED**

Run:

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan05_ai_disabled.py -v
```

Expected: failure because the test module is absent.

- [ ] **Step 3: Assert fallback lifecycle and export**

Drive report generation, validation, finalization, and export through existing typed APIs/services. Assert `generation_mode == RULE_FALLBACK`, no provider secret/configuration appears in output, and the job/version state uses the current named lifecycle values. Assert tenant-scoped reads only expose the owner tenant.

- [ ] **Step 4: Run full Task 8 gates and commit**

Run:

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan05_full_workflow.py tests/integration/test_plan05_ai_disabled.py -v
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check app tests
git diff --check
```

Expected: all exit `0`.

```powershell
git add extensions/maintenance-api/tests/integration/test_plan05_ai_disabled.py
git commit -m "test(maintenance): cover plan05 ai-disabled workflow"
```

Record exact counts/warnings and scope confirmation in the Task 8 closure report. Close Task 8 only after independent review approves both tests.

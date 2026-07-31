# Plan 05-3B Calculation Recommendation and Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver deterministic reliability-model and execution-mode recommendation, independent multi-candidate calculations, durable group events with resumable SSE, partial-failure recovery, normalized comparison, and audited item-level decisions.

**Architecture:** Add a lightweight `CalculationGroup` aggregate around existing `DemandCalculation` records. Each group child owns one immutable candidate snapshot and one current calculation attempt; the existing calculation service remains responsible for deterministic engine execution and persistence. Add lifecycle observers so group events commit with calculation state, then expose pure frontend controllers for SSE, group state, comparison, and decisions.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, existing `demand-engine`, pytest, Ruff, Vue 3.5, TypeScript 6, Pinia 3, TDesign Vue Next, `@microsoft/fetch-event-source`, Node `tsx --test`.

## Global Constraints

- Plan 05-3A must be committed and its complete gate green before Task 1.
- Follow `docs/superpowers/specs/2026-07-31-maintenance-plan05-03-scenario-calculation-design.md`.
- Only `PUBLISHED` scenario versions may be recommended or calculated.
- `reliability_model` and `execution_mode` are separate fields and enums.
- A candidate key is the stable pair `<RELIABILITY_MODEL>:<EXECUTION_MODE>`.
- Model applicability and ranking are deterministic; LLM text cannot change them.
- One child failure never cancels successful siblings.
- Retry creates a new calculation attempt only for failed or interrupted current children.
- Group events are tenant-scoped, persisted, monotonically sequenced, and replayable.
- Original `DemandCalculation`, `DemandCalculationRun`, and item results remain immutable inputs to comparison decisions.
- Browser code never submits tenant fields or a direct Maintenance API URL.
- Decimal values cross JSON as decimal strings.
- Repository methods do not commit; service and execution observer boundaries own transactions.
- Every database migration must pass upgrade, downgrade one revision, and re-upgrade.
- No demand-list state machine is implemented in this plan; that belongs to 05-3C.

---

## File Map

### Backend create

```text
extensions/maintenance-api/app/models/calculation_group.py
extensions/maintenance-api/app/schemas/model_recommendation.py
extensions/maintenance-api/app/schemas/calculation_group.py
extensions/maintenance-api/app/repositories/calculation_group_repository.py
extensions/maintenance-api/app/services/model_recommendation_service.py
extensions/maintenance-api/app/services/calculation_group_service.py
extensions/maintenance-api/app/workers/calculation_group_executor.py
extensions/maintenance-api/app/api/v1/demand/model_recommendations.py
extensions/maintenance-api/app/api/v1/demand/calculation_groups.py
extensions/maintenance-api/alembic/versions/20260731_06_add_calculation_groups.py
extensions/maintenance-api/tests/services/test_model_recommendation_service.py
extensions/maintenance-api/tests/services/test_calculation_group_service.py
extensions/maintenance-api/tests/api/test_calculation_groups.py
extensions/maintenance-api/tests/workers/test_calculation_group_recovery.py
extensions/maintenance-api/tests/migrations/test_calculation_group_migration.py
```

### Backend modify

```text
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/repositories/__init__.py
extensions/maintenance-api/app/services/demand_calculation_service.py
extensions/maintenance-api/app/workers/recovery.py
extensions/maintenance-api/app/workers/task_registry.py
extensions/maintenance-api/app/api/v1/demand/router.py
```

### Frontend create

```text
frontend/src/api/maintenance/model-recommendations.ts
frontend/src/api/maintenance/calculation-groups.ts
frontend/src/api/maintenance/__tests__/calculation-groups.test.ts
frontend/src/composables/maintenance/useResumableSSE.ts
frontend/src/composables/maintenance/__tests__/resumable-sse.test.ts
frontend/src/stores/maintenance/calculationGroup.ts
frontend/src/stores/maintenance/__tests__/calculation-group.test.ts
frontend/src/components/maintenance/calculation/calculation-group-reducer.ts
frontend/src/components/maintenance/calculation/ModelRecommendationPanel.vue
frontend/src/components/maintenance/calculation/ModelSelectionTable.vue
frontend/src/components/maintenance/calculation/CalculationTaskProgress.vue
frontend/src/components/maintenance/calculation/ModelComparisonTable.vue
frontend/src/components/maintenance/calculation/DemandItemDecisionDrawer.vue
frontend/src/components/maintenance/calculation/__tests__/model-selection.test.ts
frontend/src/components/maintenance/calculation/__tests__/comparison-decisions.test.ts
frontend/src/views/maintenance/calculations/CalculationSetup.vue
frontend/src/views/maintenance/calculations/CalculationProgress.vue
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/views/maintenance/__tests__/calculation-navigation.test.ts
```

### Frontend modify

```text
frontend/src/views/maintenance/calculations/CalculationList.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/zh-CN.ts
frontend/src/i18n/locales/en-US.ts
frontend/src/i18n/locales/ko-KR.ts
frontend/src/i18n/locales/ru-RU.ts
extensions/maintenance-api/README.md
```

---

### Task 1: Add Calculation Group Persistence

**Files:**
- Create: `extensions/maintenance-api/app/models/calculation_group.py`
- Create: `extensions/maintenance-api/app/schemas/calculation_group.py`
- Create: `extensions/maintenance-api/app/repositories/calculation_group_repository.py`
- Create: `extensions/maintenance-api/alembic/versions/20260731_06_add_calculation_groups.py`
- Modify: `extensions/maintenance-api/app/models/enums.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Modify: `extensions/maintenance-api/app/repositories/__init__.py`
- Test: `extensions/maintenance-api/tests/migrations/test_calculation_group_migration.py`
- Test: `extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py`

**Interfaces:**
- Produces: `CalculationGroup`, `CalculationGroupChild`, `CalculationGroupEvent`, `CalculationItemDecision`.
- Produces: tenant-scoped repositories with no commit.
- Consumed by: Tasks 2–8 and Plan 05-3C.

- [ ] **Step 1: Write failing migration and tenant-scope tests**

```python
def test_calculation_group_schema_has_required_constraints(upgraded_connection):
    inspector = inspect(upgraded_connection)
    assert {
        "calculation_groups",
        "calculation_group_children",
        "calculation_group_events",
        "calculation_item_decisions",
    } <= set(inspector.get_table_names())
    assert has_unique(
        inspector,
        "calculation_group_children",
        ("tenant_id", "group_id", "candidate_key", "attempt_number"),
    )
    assert has_unique(
        inspector,
        "calculation_group_events",
        ("tenant_id", "group_id", "sequence"),
    )


def test_group_repository_never_returns_foreign_tenant(
    session, tenant_one_group, tenant_two_group
):
    repository = CalculationGroupRepository()
    assert repository.get(session, "tenant-one", tenant_two_group.id) is None
```

- [ ] **Step 2: Run tests and observe missing models and migration**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/migrations/test_calculation_group_migration.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -k "calculation_group" `
  -v
```

Expected: FAIL because group tables and repositories do not exist.

- [ ] **Step 3: Add exact enums and models**

```python
class CalculationGroupStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class CalculationDecisionType(StrEnum):
    SYSTEM_RECOMMENDATION = "SYSTEM_RECOMMENDATION"
    ALTERNATIVE_CANDIDATE = "ALTERNATIVE_CANDIDATE"
    MANUAL_QUANTITY = "MANUAL_QUANTITY"
```

`CalculationGroup` includes `scenario_version_id`, `status`, `primary_candidate_key`, recommendation and parameter snapshots, `last_event_sequence`, `version`, and actor timestamps.

`CalculationGroupChild` includes `candidate_key`, `reliability_model`, `execution_mode`, `calculation_id`, `attempt_number`, `is_current_attempt`, and selection metadata.

`CalculationGroupEvent` includes `sequence`, optional child ID, event type, payload, and timestamp.

`CalculationItemDecision` includes source and selected child IDs, original/final Decimal quantities, decision type, reason, risk, confirmation flag, rule version, and `version`.

- [ ] **Step 4: Implement tenant-scoped repositories**

Required methods:

```python
CalculationGroupRepository.get
CalculationGroupRepository.get_for_update
CalculationGroupRepository.list_page
CalculationGroupRepository.create
CalculationGroupRepository.append_event
CalculationGroupChildRepository.current_for_group
CalculationGroupChildRepository.create_attempt
CalculationItemDecisionRepository.get_for_update
CalculationItemDecisionRepository.upsert
```

`append_event()` locks the group row, increments `last_event_sequence`, inserts the event, and does not commit.

- [ ] **Step 5: Implement reversible migration**

Set:

```python
revision = "20260731_06"
down_revision = "20260729_05"
```

Upgrade creates all four tables and indexes. Downgrade drops them in dependency order:

```text
calculation_item_decisions
calculation_group_events
calculation_group_children
calculation_groups
```

- [ ] **Step 6: Run migration cycle and repository tests**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/migrations/test_calculation_group_migration.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  -k "calculation_group" `
  -v
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS, reversible migration, Ruff clean.

- [ ] **Step 7: Commit persistence**

```powershell
git add `
  extensions/maintenance-api/app/models/calculation_group.py `
  extensions/maintenance-api/app/schemas/calculation_group.py `
  extensions/maintenance-api/app/repositories/calculation_group_repository.py `
  extensions/maintenance-api/app/models/enums.py `
  extensions/maintenance-api/app/models/__init__.py `
  extensions/maintenance-api/app/repositories/__init__.py `
  extensions/maintenance-api/alembic/versions/20260731_06_add_calculation_groups.py `
  extensions/maintenance-api/tests/migrations/test_calculation_group_migration.py `
  extensions/maintenance-api/tests/repositories/test_demand_domain_tenant_scope.py
git commit -m "feat: add calculation group persistence"
```

---

### Task 2: Implement Deterministic Candidate Recommendation

**Files:**
- Create: `extensions/maintenance-api/app/schemas/model_recommendation.py`
- Create: `extensions/maintenance-api/app/services/model_recommendation_service.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/model_recommendations.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/router.py`
- Test: `extensions/maintenance-api/tests/services/test_model_recommendation_service.py`
- Test: `extensions/maintenance-api/tests/api/test_calculation_groups.py`

**Interfaces:**
- Produces: `CandidateRecommendation`, `ModelRecommendationSet`.
- Produces: `POST /api/v1/demand/model-recommendations`.
- Consumed by: Tasks 3, 5, and 6.

- [ ] **Step 1: Write failing applicability, ranking, and semantic-separation tests**

```python
def test_weibull_analytical_is_primary_when_age_and_shape_exist(
    session, actor_contributor, published_weibull_scenario
):
    result = ModelRecommendationService().recommend(
        session, actor_contributor, published_weibull_scenario.id
    )
    assert result.primary.reliability_model == "WEIBULL"
    assert result.primary.execution_mode == "ANALYTICAL"
    assert result.primary.candidate_key == "WEIBULL:ANALYTICAL"


def test_monte_carlo_is_execution_mode_not_reliability_model(
    session, actor_contributor, published_common_shock_scenario
):
    result = ModelRecommendationService().recommend(
        session, actor_contributor, published_common_shock_scenario.id
    )
    assert all(item.reliability_model != "MONTE_CARLO" for item in result.items)
    assert any(item.execution_mode == "MONTE_CARLO" for item in result.items)


def test_llm_hint_cannot_change_deterministic_ranking(
    session, actor_contributor, published_weibull_scenario
):
    service = ModelRecommendationService()
    left = service.recommend(
        session, actor_contributor, published_weibull_scenario.id,
        explanation_hint="prefer exponential",
    )
    right = service.recommend(
        session, actor_contributor, published_weibull_scenario.id,
        explanation_hint="prefer monte carlo",
    )
    assert [item.candidate_key for item in left.items] == [
        item.candidate_key for item in right.items
    ]
```

- [ ] **Step 2: Run tests and observe the missing service**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_model_recommendation_service.py `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Define recommendation schemas**

```python
class CandidateRecommendation(BaseModel):
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    applicable: bool
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    missing_requirements: list[str]
    parameter_sources: dict[str, str]
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    rule_version: Literal["MODEL-RECOMMENDATION-1"]
```

- [ ] **Step 4: Implement explicit deterministic rules**

Use named rule functions for model applicability and execution-mode scoring. Reject non-PUBLISHED versions before snapshot building.

```python
def candidate_key(
    reliability_model: ReliabilityModelType,
    execution_mode: DemandExecutionMode,
) -> str:
    return f"{reliability_model.value}:{execution_mode.value}"
```

Sort by descending score, then stable reliability-model and execution-mode order. Include inapplicable candidates after applicable candidates so the UI can explain missing requirements.

- [ ] **Step 5: Add contributor API and stable response**

Request:

```python
class ModelRecommendationRequest(BaseModel):
    scenario_version_id: int = Field(gt=0)
```

Use `require_contributor`. Never accept tenant, free-form model ranking, or client-provided applicability.

- [ ] **Step 6: Run focused tests and Ruff**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_model_recommendation_service.py `
  tests/api/test_calculation_groups.py `
  -k "recommendation" `
  -v
.\.venv\Scripts\python.exe -m ruff check `
  app/schemas/model_recommendation.py `
  app/services/model_recommendation_service.py `
  app/api/v1/demand/model_recommendations.py `
  tests/services/test_model_recommendation_service.py
```

Expected: PASS.

- [ ] **Step 7: Commit recommendation**

```powershell
git add `
  extensions/maintenance-api/app/schemas/model_recommendation.py `
  extensions/maintenance-api/app/services/model_recommendation_service.py `
  extensions/maintenance-api/app/api/v1/demand/model_recommendations.py `
  extensions/maintenance-api/app/api/v1/demand/router.py `
  extensions/maintenance-api/tests/services/test_model_recommendation_service.py `
  extensions/maintenance-api/tests/api/test_calculation_groups.py
git commit -m "feat: recommend calculation candidates deterministically"
```

---

### Task 3: Create Independent Candidate Calculations

**Files:**
- Create: `extensions/maintenance-api/app/services/calculation_group_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_calculation_service.py`
- Modify: `extensions/maintenance-api/app/schemas/calculation_group.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/calculation_groups.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/router.py`
- Test: `extensions/maintenance-api/tests/services/test_calculation_group_service.py`
- Test: `extensions/maintenance-api/tests/api/test_calculation_groups.py`

**Interfaces:**
- Produces: `CalculationGroupService.create/get/list`.
- Produces: trusted `submit_candidate` extension on `DemandCalculationService`.
- Produces: create/list/detail group APIs.
- Consumed by: Tasks 4–8.

- [ ] **Step 1: Write failing group creation tests**

```python
def test_group_creates_one_calculation_per_selected_candidate(
    session, actor_contributor, published_weibull_scenario
):
    group = CalculationGroupService().create(
        session,
        actor_contributor,
        scenario_version_id=published_weibull_scenario.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="group-create-1",
    )
    assert len(group.current_children) == 3
    assert len({child.calculation_id for child in group.current_children}) == 3
    assert all(child.attempt_number == 1 for child in group.current_children)


def test_group_rejects_unpublished_scenario(
    session, actor_contributor, draft_scenario_version
):
    with pytest.raises(ConflictError) as exc:
        CalculationGroupService().create(
            session,
            actor_contributor,
            scenario_version_id=draft_scenario_version.id,
            primary_candidate_key="WEIBULL:ANALYTICAL",
            selected_candidate_keys=["WEIBULL:ANALYTICAL"],
            idempotency_key="unpublished",
        )
    assert exc.value.code == "SCENARIO_NOT_PUBLISHED"
```

- [ ] **Step 2: Run tests and observe missing orchestration**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  -k "create or unpublished" `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Add trusted candidate snapshot construction**

Add an internal immutable spec:

```python
@dataclass(frozen=True, slots=True)
class CandidateExecutionSpec:
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    random_seed: int
```

`DemandCalculationService.submit_candidate()` must:

1. build the trusted scenario snapshot;
2. validate every parameter required by the selected reliability model;
3. apply the reliability-model override only to compatible items;
4. set `requested_mode` from `execution_mode`;
5. persist the immutable input snapshot and derived idempotency key;
6. never accept a client-provided temporary snapshot.

- [ ] **Step 4: Implement idempotent group creation**

Lock the scenario version, load server recommendation, verify all selected candidates are applicable and primary is selected, create the group, derive one calculation idempotency key per candidate, create children, append `group.created` and `child.queued` events, and commit once.

Same group idempotency key and request hash returns the same group. Reuse with a different request returns `409 IDEMPOTENCY_KEY_REUSED`.

- [ ] **Step 5: Add list/create/detail API**

Use `require_contributor` for create and `require_viewer` for list/detail. List supports server-side page, page size, and status. Return current children and current calculation status in detail.

- [ ] **Step 6: Run focused service/API and existing calculation tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/api/test_calculation_routes.py `
  tests/services/test_demand_calculation_service_tenant_scope.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: existing single-calculation behavior remains green.

- [ ] **Step 7: Commit group creation**

```powershell
git add `
  extensions/maintenance-api/app/services/calculation_group_service.py `
  extensions/maintenance-api/app/services/demand_calculation_service.py `
  extensions/maintenance-api/app/schemas/calculation_group.py `
  extensions/maintenance-api/app/api/v1/demand/calculation_groups.py `
  extensions/maintenance-api/app/api/v1/demand/router.py `
  extensions/maintenance-api/tests/services/test_calculation_group_service.py `
  extensions/maintenance-api/tests/api/test_calculation_groups.py
git commit -m "feat: create independent candidate calculations"
```

---

### Task 4: Add Group Execution, Events, Recovery, and SSE

**Files:**
- Create: `extensions/maintenance-api/app/workers/calculation_group_executor.py`
- Modify: `extensions/maintenance-api/app/services/demand_calculation_service.py`
- Modify: `extensions/maintenance-api/app/services/calculation_group_service.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/calculation_groups.py`
- Modify: `extensions/maintenance-api/app/workers/recovery.py`
- Modify: `extensions/maintenance-api/app/workers/task_registry.py`
- Test: `extensions/maintenance-api/tests/services/test_calculation_group_service.py`
- Test: `extensions/maintenance-api/tests/api/test_calculation_groups.py`
- Test: `extensions/maintenance-api/tests/workers/test_calculation_group_recovery.py`

**Interfaces:**
- Produces: execution observer hooks, durable group events, SSE, retry-failed, cancel-running.
- Consumed by: Task 5 and Task 7.

- [ ] **Step 1: Write failing partial-failure, retry, and event tests**

```python
def test_one_child_failure_preserves_successful_sibling(
    session, actor_contributor, mixed_result_group
):
    group = CalculationGroupService().refresh_status(
        session, actor_contributor, mixed_result_group.id
    )
    assert group.status.value == "PARTIALLY_COMPLETED"
    assert group.child("WEIBULL:ANALYTICAL").calculation.status.value == "SUCCEEDED"
    assert group.child("WEIBULL:MONTE_CARLO").calculation.status.value == "FAILED"


def test_retry_failed_creates_only_new_failed_attempt(
    session, actor_contributor, mixed_result_group
):
    retried = CalculationGroupService().retry_failed(
        session,
        actor_contributor,
        mixed_result_group.id,
        idempotency_key="retry-mixed-1",
    )
    assert retried.child("WEIBULL:ANALYTICAL").attempt_number == 1
    assert retried.child("WEIBULL:MONTE_CARLO").attempt_number == 2


def test_events_resume_after_sequence(
    authenticated_client, contributor_headers, completed_group
):
    response = authenticated_client.get(
        f"/api/v1/demand/calculation-groups/{completed_group.id}/events",
        params={"after_sequence": 2},
        headers=contributor_headers,
    )
    assert all(item["sequence"] > 2 for item in response.json()["data"])
```

- [ ] **Step 2: Run tests and observe missing observer and executor**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/workers/test_calculation_group_recovery.py `
  -k "failure or retry or event or recovery" `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Add optional calculation lifecycle observer**

```python
class DemandExecutionObserver(Protocol):
    def started(self, session: Session, calculation: DemandCalculation) -> None: ...
    def progress(
        self, session: Session, calculation: DemandCalculation, percent: Decimal
    ) -> None: ...
    def completed(self, session: Session, calculation: DemandCalculation) -> None: ...
    def failed(
        self, session: Session, calculation: DemandCalculation, error: Exception
    ) -> None: ...
```

`DemandCalculationService.run_internal()` accepts an optional observer. Call observer methods before the same commits that persist calculation transitions. On failure, preserve the existing rollback-first boundary: rollback the failed engine transaction, reload and mark the calculation failed, then invoke `observer.failed()` before committing that failed state so the calculation status and group event are atomic. Default `None` preserves existing executor behavior.

- [ ] **Step 4: Implement CalculationGroupExecutor**

The executor uses tenant-aware key `(tenant_id, group_child_id)`, creates a new DB session, calls `run_internal()` with a group observer, and unregisters in `finally`. Observer methods append group events and update the cached aggregate status without committing independently. Treat both calculation `SUCCEEDED` and `PARTIAL_SUCCESS` as a successful child when deriving the group status; candidate warnings remain visible in comparison instead of converting the child to failed.

- [ ] **Step 5: Implement retry, cancel, and recovery**

- retry only current children in `FAILED` or `INTERRUPTED`;
- create one new child attempt and one new `DemandCalculation`;
- cancel sets `cancel_requested` only on current `PENDING` or `RUNNING` calculations;
- recovery requeues `PENDING`;
- stale `RUNNING` becomes `INTERRUPTED` and emits `child.interrupted`;
- successful calculations never requeue.

- [ ] **Step 6: Add durable event list and SSE routes**

List route accepts `after_sequence >= 0`. Stream route accepts `last_event_sequence >= 0`, emits business event sequence as SSE `id`, sends transient heartbeat frames without advancing sequence, and stops after the group is terminal and all missing events are delivered.

- [ ] **Step 7: Run execution, recovery, SSE, and existing async tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/workers/test_calculation_group_recovery.py `
  tests/api/test_async_calculation.py `
  tests/workers/test_demand_executor_tenant_scope.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 8: Commit execution and SSE**

```powershell
git add `
  extensions/maintenance-api/app/workers/calculation_group_executor.py `
  extensions/maintenance-api/app/services/demand_calculation_service.py `
  extensions/maintenance-api/app/services/calculation_group_service.py `
  extensions/maintenance-api/app/api/v1/demand/calculation_groups.py `
  extensions/maintenance-api/app/workers/recovery.py `
  extensions/maintenance-api/app/workers/task_registry.py `
  extensions/maintenance-api/tests/services/test_calculation_group_service.py `
  extensions/maintenance-api/tests/api/test_calculation_groups.py `
  extensions/maintenance-api/tests/workers/test_calculation_group_recovery.py
git commit -m "feat: stream recoverable calculation groups"
```

---

### Task 5: Add Typed Group API, SSE Controller, and Store

**Files:**
- Create: `frontend/src/api/maintenance/model-recommendations.ts`
- Create: `frontend/src/api/maintenance/calculation-groups.ts`
- Create: `frontend/src/api/maintenance/__tests__/calculation-groups.test.ts`
- Create: `frontend/src/composables/maintenance/useResumableSSE.ts`
- Create: `frontend/src/composables/maintenance/__tests__/resumable-sse.test.ts`
- Create: `frontend/src/components/maintenance/calculation/calculation-group-reducer.ts`
- Create: `frontend/src/stores/maintenance/calculationGroup.ts`
- Create: `frontend/src/stores/maintenance/__tests__/calculation-group.test.ts`

**Interfaces:**
- Consumes: Tasks 2–4 APIs.
- Produces: `recommendationApi`, `calculationGroupApi`, `createResumableSSE`, `useCalculationGroupStore`.
- Consumed by: Tasks 6–8.

- [ ] **Step 1: Write failing exact-path and tenant-omission tests**

```ts
test('group API uses exact paths and idempotency headers', async () => {
  const calls: CapturedCall[] = []
  const api = createCalculationGroupApi(fakeClient(calls))
  await api.create(createRequest, 'group-key')
  await api.retryFailed(9, 'retry-key')
  await api.getEvents(9, 14)
  assert.equal(calls[0].path, '/v1/demand/calculation-groups')
  assert.equal(calls[1].path, '/v1/demand/calculation-groups/9/retry-failed')
  assert.equal(calls[2].path, '/v1/demand/calculation-groups/9/events?after_sequence=14')
  assert.equal(JSON.stringify(calls).includes('tenant'), false)
})
```

- [ ] **Step 2: Write failing SSE reducer tests**

```ts
test('duplicate and out-of-order events are ignored', () => {
  const state = reduceGroupEvent(initialState, event(4, 'child.progress'))
  assert.deepEqual(reduceGroupEvent(state, event(4, 'child.progress')), state)
  assert.deepEqual(reduceGroupEvent(state, event(3, 'child.started')), state)
})


test('visibility resume reconnects from last sequence', async () => {
  const source = createResumableSSE(fakeEnvironment())
  source.start({ groupId: 8, lastSequence: 12 })
  source.setVisible(false)
  source.setVisible(true)
  assert.equal(fakeEnvironment().connections.at(-1)?.lastSequence, 12)
})
```

- [ ] **Step 3: Run tests and observe missing modules**

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/calculation-groups.test.ts `
  src/composables/maintenance/__tests__/resumable-sse.test.ts `
  src/stores/maintenance/__tests__/calculation-group.test.ts
```

Expected: FAIL.

- [ ] **Step 4: Implement typed APIs and pure reducer**

Use decimal strings and exact enums. SSE URL is `/api/maintenance/v1/demand/calculation-groups/{id}/events/stream`; it remains inside the WeKnora proxy. Reducer requires matching group ID and strictly increasing sequence.

- [ ] **Step 5: Implement resumable SSE with polling fallback**

Use `fetchEventSource`, an abort controller per generation, visibility/activity gates, bounded reconnect backoff, and a fallback poller after repeated connection failures. Stop fallback polling immediately when SSE reconnects.

- [ ] **Step 6: Implement the Pinia group store**

Store owns group detail, current sequence, connection state, request generation, selected filters, normalized errors, and actions for create, load, retry failed, cancel running, and reconnect. Create/retry/cancel are mutually exclusive.

- [ ] **Step 7: Run focused tests and type-check**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/calculation-groups.test.ts `
  src/composables/maintenance/__tests__/resumable-sse.test.ts `
  src/stores/maintenance/__tests__/calculation-group.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 8: Commit client orchestration**

```powershell
git add `
  frontend/src/api/maintenance/model-recommendations.ts `
  frontend/src/api/maintenance/calculation-groups.ts `
  frontend/src/api/maintenance/__tests__/calculation-groups.test.ts `
  frontend/src/composables/maintenance/useResumableSSE.ts `
  frontend/src/composables/maintenance/__tests__/resumable-sse.test.ts `
  frontend/src/components/maintenance/calculation/calculation-group-reducer.ts `
  frontend/src/stores/maintenance/calculationGroup.ts `
  frontend/src/stores/maintenance/__tests__/calculation-group.test.ts
git commit -m "feat: add resumable calculation group client"
```

---

### Task 6: Build Calculation Setup and Progress UI

**Files:**
- Create: `frontend/src/components/maintenance/calculation/ModelRecommendationPanel.vue`
- Create: `frontend/src/components/maintenance/calculation/ModelSelectionTable.vue`
- Create: `frontend/src/components/maintenance/calculation/CalculationTaskProgress.vue`
- Create: `frontend/src/components/maintenance/calculation/__tests__/model-selection.test.ts`
- Create: `frontend/src/views/maintenance/calculations/CalculationSetup.vue`
- Create: `frontend/src/views/maintenance/calculations/CalculationProgress.vue`
- Modify: `frontend/src/views/maintenance/calculations/CalculationList.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Create: `frontend/src/views/maintenance/__tests__/calculation-navigation.test.ts`
- Modify: locale files under `frontend/src/i18n/locales/`

**Interfaces:**
- Consumes: recommendation and group stores.
- Produces: setup, list, and progress flows.
- Consumed by: Task 7.

- [ ] **Step 1: Write failing selection and route tests**

```ts
test('inapplicable candidates are visible but disabled', () => {
  const rows = buildCandidateRows(recommendationFixture)
  const weibull = rows.find(row => row.candidateKey === 'WEIBULL:ANALYTICAL')
  assert.equal(weibull?.disabled, true)
  assert.deepEqual(weibull?.missingRequirements, ['WEIBULL_SHAPE'])
})


test('progress route is authenticated and hidden from menu', () => {
  const route = findMaintenanceRoute('maintenanceCalculationProgress')
  assert.equal(route.meta.requiresAuth, true)
  assert.equal(route.meta.hideInMaintenanceMenu, true)
})
```

- [ ] **Step 2: Run tests and observe placeholder pages**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/model-selection.test.ts `
  src/views/maintenance/__tests__/calculation-navigation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement setup page**

Require a published `scenario_version_id`, show immutable input preview, load deterministic recommendation, preselect the primary candidate, allow applicable alternatives, record selection reasons, and submit one idempotent group request.

- [ ] **Step 4: Implement progress cards**

Each card displays candidate key, reliability model, execution mode, attempt, calculation status, progress, current stage, warnings, and terminal error. Successful cards remain available when siblings fail.

- [ ] **Step 5: Replace calculation list placeholder**

Use server paging and status filters. Actions route to progress for active groups and comparison for terminal groups with successful results.

- [ ] **Step 6: Add routes and locale keys**

Add hidden routes:

```text
calculations/new
calculations/:groupId/progress
calculations/:groupId/comparison
```

Add matching locale key shapes in all four existing TypeScript locale files.

- [ ] **Step 7: Run UI tests, full frontend tests, type-check, and build**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/model-selection.test.ts `
  src/views/maintenance/__tests__/calculation-navigation.test.ts `
  src/composables/maintenance/__tests__/resumable-sse.test.ts
npm run test
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit setup and progress UI**

```powershell
git add `
  frontend/src/components/maintenance/calculation/ModelRecommendationPanel.vue `
  frontend/src/components/maintenance/calculation/ModelSelectionTable.vue `
  frontend/src/components/maintenance/calculation/CalculationTaskProgress.vue `
  frontend/src/components/maintenance/calculation/__tests__/model-selection.test.ts `
  frontend/src/views/maintenance/calculations `
  frontend/src/views/maintenance/__tests__/calculation-navigation.test.ts `
  frontend/src/router/maintenance.ts `
  frontend/src/i18n/locales
git commit -m "feat: add multi candidate calculation workflow"
```

---

### Task 7: Normalize Comparison and Persist Item Decisions

**Files:**
- Modify: `extensions/maintenance-api/app/schemas/calculation_group.py`
- Modify: `extensions/maintenance-api/app/services/calculation_group_service.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/calculation_groups.py`
- Modify: `extensions/maintenance-api/tests/services/test_calculation_group_service.py`
- Modify: `extensions/maintenance-api/tests/api/test_calculation_groups.py`
- Create: `frontend/src/components/maintenance/calculation/ModelComparisonTable.vue`
- Create: `frontend/src/components/maintenance/calculation/DemandItemDecisionDrawer.vue`
- Create: `frontend/src/components/maintenance/calculation/__tests__/comparison-decisions.test.ts`
- Create: `frontend/src/views/maintenance/calculations/CalculationComparison.vue`

**Interfaces:**
- Produces: union-based group comparison and versioned `PUT .../decisions/{spare_part_id}`.
- Produces: risk rule `DEMAND-DECISION-RISK-1`.
- Consumed by: Plan 05-3C.

- [ ] **Step 1: Write failing backend comparison and decision tests**

```python
def test_comparison_uses_union_and_marks_missing_results(
    session, actor_contributor, uneven_completed_group
):
    comparison = CalculationGroupService().comparison(
        session, actor_contributor, uneven_completed_group.id
    )
    row = comparison.by_spare_part_id(77)
    assert row.candidates["WEIBULL:ANALYTICAL"].status == "SUCCEEDED"
    assert row.candidates["BINOMIAL:ANALYTICAL"].status == "NO_RESULT"


def test_high_risk_manual_reduction_requires_admin_confirmation(
    session, actor_contributor, completed_group
):
    decision = CalculationGroupService().save_decision(
        session,
        actor_contributor,
        completed_group.id,
        spare_part_id=11,
        expected_version=0,
        selected_child_id=completed_group.primary_child.id,
        final_quantity=Decimal("80"),
        reason="Accepted lower operational target",
    )
    assert decision.requires_admin_confirmation is True
    assert decision.risk_rule_version == "DEMAND-DECISION-RISK-1"
```

- [ ] **Step 2: Run backend tests and observe missing comparison contract**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  -k "comparison or decision" `
  -v
```

Expected: FAIL.

- [ ] **Step 3: Implement normalized union comparison**

Build rows from the union of successful current child item results. A missing child result is `NO_RESULT`, never zero. Persist no comparison copy; derive it from immutable results and current children.

- [ ] **Step 4: Implement versioned decision save and risk rules**

Require a successful current selected child and a non-empty reason for non-default choice or quantity change. Apply:

```text
critical/high-risk manual reduction
final quantity at least 10% below selected recommendation
quantity outside every successful prediction range
non-primary choice beyond deterministic difference threshold
missing-parameter, non-convergence, or high warning
```

Reject stale `expected_version` with `CALCULATION_DECISION_VERSION_CONFLICT`. Commit the decision and `decision.updated` event together.

- [ ] **Step 5: Write failing frontend decision tests**

```ts
test('missing candidate result renders NO_RESULT and is not selectable', () => {
  const cell = presentCandidateCell(noResultFixture)
  assert.equal(cell.label, 'NO_RESULT')
  assert.equal(cell.selectable, false)
})


test('alternative or manual quantity requires a reason', () => {
  assert.equal(validateDecision({
    selectedCandidateKey: 'EXPONENTIAL:ANALYTICAL',
    systemCandidateKey: 'WEIBULL:ANALYTICAL',
    finalQuantity: '12',
    originalQuantity: '14',
    reason: '',
  }).valid, false)
})
```

- [ ] **Step 6: Implement comparison table, decision drawer, and page**

Keep decimals as strings in state. Save through the group store request gate. Update the row only after the server returns the new decision version and risk evaluation.

- [ ] **Step 7: Run backend/frontend focused suites and full frontend gate**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\..\frontend
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/comparison-decisions.test.ts `
  src/stores/maintenance/__tests__/calculation-group.test.ts
npm run test
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit comparison and decisions**

```powershell
git add `
  extensions/maintenance-api/app/schemas/calculation_group.py `
  extensions/maintenance-api/app/services/calculation_group_service.py `
  extensions/maintenance-api/app/api/v1/demand/calculation_groups.py `
  extensions/maintenance-api/tests/services/test_calculation_group_service.py `
  extensions/maintenance-api/tests/api/test_calculation_groups.py `
  frontend/src/components/maintenance/calculation/ModelComparisonTable.vue `
  frontend/src/components/maintenance/calculation/DemandItemDecisionDrawer.vue `
  frontend/src/components/maintenance/calculation/__tests__/comparison-decisions.test.ts `
  frontend/src/views/maintenance/calculations/CalculationComparison.vue
git commit -m "feat: add calculation comparison decisions"
```

---

### Task 8: Run the Complete 05-3B Gate

**Files:**
- Modify: `extensions/maintenance-api/README.md`
- Test: all Plan 05-3B scopes.

**Interfaces:**
- Produces: verified published-scenario-to-decisions vertical slice.
- Unlocks: Plan 05-3C.

- [ ] **Step 1: Add an integration test for mixed candidate outcomes**

Extend `tests/integration/test_plan05_scenario_calculation.py` with a published scenario, three candidate children, one injected failure, SSE resume, retry only failed, union comparison, and persisted decisions.

- [ ] **Step 2: Document exact group and SSE operations**

Document candidate semantics, idempotency headers, group states, recovery rules, event sequence resume, polling fallback, decision reasons, and risk rule version.

- [ ] **Step 3: Run migration and backend gate**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_model_recommendation_service.py `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/workers/test_calculation_group_recovery.py `
  tests/migrations/test_calculation_group_migration.py `
  tests/integration/test_plan05_scenario_calculation.py `
  tests/api/test_calculation_routes.py `
  tests/api/test_async_calculation.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

- [ ] **Step 4: Run frontend and Go regression gate**

```powershell
cd ..\..\frontend
npm run test
npm run type-check
npm run build

cd ..
go test ./internal/maintenanceproxy ./internal/router
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Commit 05-3B evidence**

```powershell
git add `
  extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py `
  extensions/maintenance-api/README.md
git commit -m "test: verify calculation group workflow"
```

## Phase 05-3B Completion Evidence

Record:

- deterministic candidate ranking and rule version;
- explicit reliability-model/execution-mode separation;
- disabled inapplicable candidate with missing requirements;
- three independent calculation children;
- one-child failure with successful siblings preserved;
- retry creating only a new failed attempt;
- recovery after service restart;
- SSE sequence resume and duplicate suppression;
- polling fallback and return to SSE;
- union comparison with `NO_RESULT`;
- audited alternative candidate and manual quantity decisions;
- backend, migration, frontend, Ruff, Go, build, and diff outputs.

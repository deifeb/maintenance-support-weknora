# Plan 05-3 Scenario Wizard and Multi-Model Calculation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a recoverable six-step maintenance scenario wizard, deterministic model recommendation, independent multi-model execution with resumable SSE progress, result comparison, item-level decisions, and an immutable demand-list lifecycle.

**Architecture:** Reuse existing AI session snapshots and demand scenario/calculation services rather than creating a second scenario store. Add explicit draft APIs and version checks, persist field source/risk metadata, create a calculation group that owns independent model child tasks, stream group events through the existing event model, then transform confirmed item decisions into a versioned demand list whose published versions cannot be changed in place.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, existing `demand-engine`, existing `maintenance-ai`, pytest, Ruff, Vue 3.5, TypeScript 6, Pinia 3, Vue Router, TDesign, `@microsoft/fetch-event-source`, Node `tsx --test`.

## Global Constraints

- Phase 05-1 and 05-2 gates must be green.
- Scenario drafts are saved in Maintenance API AI session snapshots; browser-only state is not authoritative.
- Autosave uses optimistic versioning and never reports “saved” before the server returns the new version.
- High-risk required fields cannot enter formal calculation until confirmed.
- The LLM may propose a model, but model applicability and recommendation scores are deterministic.
- Primary and alternative models are independent tasks; one failure does not cancel successful children.
- SSE resume uses the last event sequence and does not duplicate completed steps.
- Formal demand quantities come only from completed deterministic model results or recorded user adjustments.
- A demand list has exactly the lifecycle `DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED`.
- Published demand lists are immutable; modifications create a derived draft version.
- Only one published demand list is current for one scenario lineage; older published versions remain readable and are marked superseded.
- No inventory reservation is executed in this phase; that belongs to 05-4.

---

## File Map

**Create:**

```text
extensions/maintenance-api/app/models/calculation_group.py
extensions/maintenance-api/app/models/demand_list.py
extensions/maintenance-api/app/schemas/scenario_draft.py
extensions/maintenance-api/app/schemas/model_recommendation.py
extensions/maintenance-api/app/schemas/calculation_group.py
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/app/repositories/calculation_group_repository.py
extensions/maintenance-api/app/repositories/demand_list_repository.py
extensions/maintenance-api/app/services/scenario_draft_service.py
extensions/maintenance-api/app/services/model_recommendation_service.py
extensions/maintenance-api/app/services/calculation_group_service.py
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py
extensions/maintenance-api/app/api/v1/demand/model_recommendations.py
extensions/maintenance-api/app/api/v1/demand/calculation_groups.py
extensions/maintenance-api/app/api/v1/demand/demand_lists.py
extensions/maintenance-api/alembic/versions/20260724_06_add_calculation_groups_and_demand_lists.py
extensions/maintenance-api/tests/api/test_scenario_draft_api.py
extensions/maintenance-api/tests/services/test_scenario_draft_service.py
extensions/maintenance-api/tests/services/test_model_recommendation_service.py
extensions/maintenance-api/tests/api/test_calculation_groups.py
extensions/maintenance-api/tests/services/test_calculation_group_service.py
extensions/maintenance-api/tests/api/test_demand_lists.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py
extensions/maintenance-api/tests/migrations/test_calculation_group_migration.py
frontend/src/api/maintenance/scenarios.ts
frontend/src/api/maintenance/calculations.ts
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/sse.ts
frontend/src/stores/maintenance/scenarioDraft.ts
frontend/src/stores/maintenance/calculation.ts
frontend/src/views/maintenance/scenarios/ScenarioList.vue
frontend/src/views/maintenance/scenarios/ScenarioWizard.vue
frontend/src/views/maintenance/scenarios/ScenarioDetail.vue
frontend/src/views/maintenance/calculations/CalculationList.vue
frontend/src/views/maintenance/calculations/CalculationSetup.vue
frontend/src/views/maintenance/calculations/CalculationProgress.vue
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/views/maintenance/calculations/DemandListDetail.vue
frontend/src/components/maintenance/scenario/ScenarioStepNavigation.vue
frontend/src/components/maintenance/scenario/ScenarioFieldShell.vue
frontend/src/components/maintenance/scenario/ScenarioBasicsStep.vue
frontend/src/components/maintenance/scenario/ScenarioConfigurationStep.vue
frontend/src/components/maintenance/scenario/ScenarioMissionStep.vue
frontend/src/components/maintenance/scenario/ScenarioReliabilityRepairStep.vue
frontend/src/components/maintenance/scenario/ScenarioCalculationStep.vue
frontend/src/components/maintenance/scenario/ScenarioConfirmationStep.vue
frontend/src/components/maintenance/calculation/ModelRecommendationPanel.vue
frontend/src/components/maintenance/calculation/ModelSelectionTable.vue
frontend/src/components/maintenance/calculation/CalculationTaskProgress.vue
frontend/src/components/maintenance/calculation/ModelComparisonTable.vue
frontend/src/components/maintenance/calculation/DemandItemDecisionDrawer.vue
frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
frontend/src/composables/maintenance/useDebouncedAutosave.ts
frontend/src/composables/maintenance/useResumableSSE.ts
frontend/src/composables/maintenance/__tests__/autosave.test.ts
frontend/src/composables/maintenance/__tests__/resumable-sse.test.ts
frontend/src/stores/maintenance/__tests__/scenario-draft.test.ts
frontend/src/stores/maintenance/__tests__/calculation.test.ts
```

**Modify:**

```text
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/api/v1/demand/router.py
extensions/maintenance-api/app/services/ai_session_service.py
extensions/maintenance-api/app/repositories/ai_session_repository.py
extensions/maintenance-api/app/services/demand_calculation_service.py
extensions/maintenance-api/app/workers/executor.py
extensions/maintenance-api/app/workers/task_registry.py
extensions/maintenance-api/app/schemas/demand_result.py
extensions/maintenance-api/app/services/ai_tool_adapters.py
extensions/maintenance-api/config/ai-tools.yaml
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/zh-CN.json
frontend/src/i18n/locales/en-US.json
extensions/maintenance-api/README.md
```

---

### Task 1: Add Versioned Scenario Draft Read and Save APIs

**Files:**
- Create: `app/schemas/scenario_draft.py`
- Create: `app/services/scenario_draft_service.py`
- Create: `app/api/v1/demand/scenario_drafts.py`
- Modify: AI session repository/service and demand router
- Test: `tests/services/test_scenario_draft_service.py`
- Test: `tests/api/test_scenario_draft_api.py`

**Interfaces:**
- Produces: `GET /api/v1/demand/scenario-drafts/{session_id}`, `PUT /api/v1/demand/scenario-drafts/{session_id}`.
- Data type: `ScenarioDraftEnvelope` with `session_id`, `snapshot_id`, `version`, `draft`, `field_sources`, `completion`, `blocking_fields`, `updated_at`.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Write failing draft service tests**

```python
def test_save_draft_creates_snapshot_and_increments_version(session, actor_contributor, ai_session):
    service = ScenarioDraftService()
    first = service.save(session, actor_contributor, ai_session.id, expected_version=0, payload=sample_draft())
    second = service.save(session, actor_contributor, ai_session.id, expected_version=1, payload=sample_draft(name="Revised"))
    assert first.version == 1
    assert second.version == 2
    assert second.draft["scenario_name"] == "Revised"


def test_stale_autosave_returns_version_conflict(session, actor_contributor, ai_session):
    service = ScenarioDraftService()
    service.save(session, actor_contributor, ai_session.id, expected_version=0, payload=sample_draft())
    with pytest.raises(VersionConflictError) as exc:
        service.save(session, actor_contributor, ai_session.id, expected_version=0, payload=sample_draft(name="Stale"))
    assert exc.value.actual == 1


def test_other_tenant_session_is_not_visible(session, actor_contributor, tenant_two_ai_session):
    with pytest.raises(NotFoundError):
        ScenarioDraftService().get(session, actor_contributor, tenant_two_ai_session.id)
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_scenario_draft_service.py tests/api/test_scenario_draft_api.py -v
```

Expected: FAIL because explicit draft read/save services are absent.

- [ ] **Step 3: Implement schemas and service**

```python
class ScenarioFieldState(BaseModel):
    value: Any | None = None
    source: str
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    risk: Literal["LOW", "MEDIUM", "HIGH", "BLOCKING"]
    confirmed: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class ScenarioDraftPayload(BaseModel):
    scenario_name: str = Field(min_length=1, max_length=200)
    fields: dict[str, ScenarioFieldState]
    current_step: int = Field(ge=1, le=6)


class ScenarioDraftSaveRequest(BaseModel):
    expected_version: int = Field(ge=0)
    draft: ScenarioDraftPayload
```

Service algorithm:

```python
def save(self, session, actor, session_id, expected_version, payload):
    ai_session = self._sessions.get_for_tenant(session, actor.tenant_id, session_id)
    latest = self._sessions.latest_snapshot(session, actor.tenant_id, session_id)
    actual_version = latest.version if latest else 0
    if actual_version != expected_version:
        raise VersionConflictError(expected_version, actual_version)
    completion, blocking = evaluate_draft(payload)
    snapshot = self._sessions.create_snapshot(
        session, actor.tenant_id, session_id,
        version=actual_version + 1,
        scenario_draft=payload.model_dump(mode="json"),
        field_sources={key: state.source for key, state in payload.fields.items()},
        execution_context={"completion": completion, "blocking_fields": blocking},
    )
    self._audit.record(...)
    session.commit()
    return self._to_envelope(snapshot)
```

Required high-risk blocking field keys:

```text
equipment_model_id, configuration_version_id, equipment_quantity,
mission_stages, utilization, reliability_parameter_source,
service_level, repair_turnaround_policy, common_shock_policy
```

- [ ] **Step 4: Run focused tests**

```powershell
python -m pytest tests/services/test_scenario_draft_service.py tests/api/test_scenario_draft_api.py -v
python -m ruff check app tests/services/test_scenario_draft_service.py tests/api/test_scenario_draft_api.py
```

Expected: PASS and Ruff clean.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/scenario_draft.py extensions/maintenance-api/app/services/scenario_draft_service.py extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py extensions/maintenance-api/app/services/ai_session_service.py extensions/maintenance-api/app/repositories/ai_session_repository.py extensions/maintenance-api/app/api/v1/demand/router.py extensions/maintenance-api/tests/services/test_scenario_draft_service.py extensions/maintenance-api/tests/api/test_scenario_draft_api.py
git commit -m "feat: add versioned scenario draft persistence"
```

---

### Task 2: Add Frontend Scenario Draft Store and Debounced Autosave

**Files:**
- Create: `frontend/src/api/maintenance/scenarios.ts`
- Create: `frontend/src/stores/maintenance/scenarioDraft.ts`
- Create: `frontend/src/composables/maintenance/useDebouncedAutosave.ts`
- Test: autosave and store tests listed in file map

**Interfaces:**
- Consumes: draft API from Task 1.
- Produces: `useScenarioDraftStore`, `createAutosaveController`.
- Consumed by: Tasks 3 and 4.

- [ ] **Step 1: Write failing autosave tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { createAutosaveController } from '../useDebouncedAutosave'


test('rapid edits collapse into one save using latest data', async () => {
  const saved: string[] = []
  const timers = fakeTimers()
  const controller = createAutosaveController<string>({
    delayMs: 800,
    save: async value => { saved.push(value); return { version: saved.length } },
    timers,
  })
  controller.schedule('a')
  controller.schedule('b')
  controller.schedule('c')
  await timers.advanceBy(799)
  assert.deepEqual(saved, [])
  await timers.advanceBy(1)
  assert.deepEqual(saved, ['c'])
})

test('failed save remains dirty and manual retry can succeed', async () => {
  let attempts = 0
  const controller = createAutosaveController({
    delayMs: 1,
    save: async value => { attempts += 1; if (attempts === 1) throw new Error('offline'); return { version: 2 } },
  })
  controller.schedule({ name: 'scenario' })
  await controller.flush()
  assert.equal(controller.state().status, 'error')
  assert.equal(controller.state().dirty, true)
  await controller.retry()
  assert.equal(controller.state().status, 'saved')
  assert.equal(controller.state().dirty, false)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/composables/maintenance/__tests__/autosave.test.ts src/stores/maintenance/__tests__/scenario-draft.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement explicit autosave states**

```ts
export type AutosaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict'

export interface ScenarioDraftState {
  sessionId: number | null
  version: number
  draft: ScenarioDraftPayload | null
  blockingFields: string[]
  completion: Record<string, boolean>
  saveStatus: AutosaveStatus
  lastSavedAt: string | null
  error: MaintenanceClientError | null
}
```

The store:

- loads by `session_id` query parameter;
- applies server draft and version;
- marks dirty on field change;
- schedules 800 ms autosave;
- sends `expected_version`;
- on 409 stores server version and enters `conflict` without overwriting local fields;
- offers `reloadServerDraft` and `saveAsNewDraft` actions;
- flushes pending save before route leave; if flush fails, route guard asks the user to stay or discard local changes.

- [ ] **Step 4: Run tests and type check**

```powershell
npm run test -- src/composables/maintenance/__tests__/autosave.test.ts src/stores/maintenance/__tests__/scenario-draft.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/scenarios.ts frontend/src/stores/maintenance/scenarioDraft.ts frontend/src/composables/maintenance/useDebouncedAutosave.ts frontend/src/composables/maintenance/__tests__/autosave.test.ts frontend/src/stores/maintenance/__tests__/scenario-draft.test.ts
git commit -m "feat: add scenario draft autosave"
```

---

### Task 3: Build the Six-Step Scenario Wizard

**Files:**
- Create: scenario views/components listed in file map
- Modify: `frontend/src/router/maintenance.ts`
- Test: `frontend/src/components/maintenance/scenario/__tests__/wizard-validation.test.ts`

**Interfaces:**
- Consumes: scenario draft store and master data APIs.
- Produces: `/platform/maintenance/scenarios`, `/scenarios/new`, `/scenarios/:scenarioId`.

- [ ] **Step 1: Write failing step validation tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { evaluateWizard } from '../wizard-validation'


test('blocking high risk field prevents confirmation', () => {
  const result = evaluateWizard({
    scenario_name: 'Task',
    fields: {
      equipment_model_id: { value: 1, source: 'MASTER_DATA', risk: 'LOW', confirmed: true },
      service_level: { value: 0.95, source: 'LLM_INFERRED', risk: 'HIGH', confirmed: false },
    },
    current_step: 6,
  })
  assert.deepEqual(result.blockingFields, ['service_level'])
  assert.equal(result.canSubmit, false)
})

test('all six step keys are present in order', () => {
  assert.deepEqual(WIZARD_STEPS.map(step => step.key), [
    'basics', 'configuration', 'mission', 'reliabilityRepair', 'calculation', 'confirmation',
  ])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/scenario/__tests__/wizard-validation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement the wizard**

`ScenarioFieldShell.vue` receives:

```ts
interface Props {
  fieldKey: string
  label: string
  required?: boolean
  source: ScenarioSource
  confidence?: number
  risk: ScenarioRisk
  confirmed: boolean
  evidenceRefs?: string[]
}
```

Step contents:

1. Basics: name, task code, start/end, description, task priority.
2. Configuration: equipment model, configuration version, fleet groups, quantities, age groups.
3. Mission: ordered stages, duration, utilization, environment and intensity factors.
4. Reliability/repair: parameter sources, failure process, repair turnaround, repair return, common shock.
5. Calculation: service levels, model mode, simulation settings, missing parameter policy.
6. Confirmation: field-source summary, assumptions, unresolved fields, change summary, publish draft action.

The final submit calls the existing scenario service to create a formal scenario/version only when the server draft response has no blocking fields and current local version equals the latest server version.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/scenario/__tests__/wizard-validation.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/maintenance/scenarios frontend/src/components/maintenance/scenario frontend/src/router/maintenance.ts frontend/src/i18n/locales
git commit -m "feat: add six step maintenance scenario wizard"
```

---

### Task 4: Connect AI Scenario Parsing to the Wizard

**Files:**
- Modify: `extensions/maintenance-api/app/services/ai_tool_adapters.py`
- Modify: `extensions/maintenance-api/config/ai-tools.yaml`
- Modify: `extensions/maintenance-api/app/services/ai_orchestration_service.py`
- Test: `extensions/maintenance-api/tests/integration/test_ai_scenario_wizard_handoff.py`
- Modify: `frontend/src/views/maintenance/scenarios/ScenarioWizard.vue`

**Interfaces:**
- Produces: a `ScenarioDraftCard` payload with `session_id`, `draft_version`, `status`, `blocking_fields`, and navigation URL.
- Consumed by: Phase 05-5 chat card renderer; wizard uses it immediately.

- [ ] **Step 1: Write failing handoff test**

```python
def test_ai_parse_persists_draft_and_returns_wizard_link(session, actor_contributor, deterministic_ai):
    result = run_ai_turn(
        session, actor_contributor,
        "为12台X型装备规划30天高强度任务，保障率95%",
        provider=deterministic_ai,
    )
    card = next(card for card in result.cards if card["type"] == "SCENARIO_DRAFT")
    assert card["session_id"] == result.session_id
    assert card["draft_version"] == 1
    assert card["navigation_url"] == f"/platform/maintenance/scenarios/new?session_id={result.session_id}"
    stored = ScenarioDraftService().get(session, actor_contributor, result.session_id)
    assert stored.draft["fields"]["equipment_quantity"]["value"] == 12
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/integration/test_ai_scenario_wizard_handoff.py -v
```

Expected: FAIL because current AI output is not guaranteed to persist a scenario draft/card contract.

- [ ] **Step 3: Implement fixed handoff tool behavior**

The composite tool `prepare_demand_scenario` must end by calling `ScenarioDraftService.save`; it does not call formal scenario publication. Return:

```python
{
    "type": "SCENARIO_DRAFT",
    "schema_version": "1.0",
    "session_id": ai_session.id,
    "draft_version": envelope.version,
    "status": "READY_FOR_PREVIEW" if not envelope.blocking_fields else "CLARIFICATION_REQUIRED",
    "blocking_fields": envelope.blocking_fields,
    "navigation_url": f"/platform/maintenance/scenarios/new?session_id={ai_session.id}",
}
```

The wizard validates `session_id` as an integer, loads through the actor-scoped API, and displays a banner indicating the content came from AI parsing and requires review.

- [ ] **Step 4: Run AI handoff and scenario tests**

```powershell
python -m pytest tests/integration/test_ai_scenario_wizard_handoff.py tests/api/test_scenario_draft_api.py tests/services/test_scenario_draft_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/ai_tool_adapters.py extensions/maintenance-api/app/services/ai_orchestration_service.py extensions/maintenance-api/config/ai-tools.yaml extensions/maintenance-api/tests/integration/test_ai_scenario_wizard_handoff.py frontend/src/views/maintenance/scenarios/ScenarioWizard.vue
git commit -m "feat: hand ai scenario drafts to wizard"
```

---

### Task 5: Implement Deterministic Model Recommendation

**Files:**
- Create: model recommendation schema/service/router
- Test: `tests/services/test_model_recommendation_service.py`

**Interfaces:**
- Produces: `POST /api/v1/demand/model-recommendations`, `ModelRecommendationSet`.
- Consumed by: Task 7.

- [ ] **Step 1: Write failing recommendation tests**

```python
def test_weibull_is_primary_for_age_and_shape_data(session, actor_contributor, weibull_ready_scenario):
    result = ModelRecommendationService().recommend(session, actor_contributor, weibull_ready_scenario.id)
    assert result.primary.model == "WEIBULL_RENEWAL"
    assert result.primary.applicable is True
    assert result.primary.reasons == ["AGE_DATA_AVAILABLE", "WEIBULL_SHAPE_AVAILABLE", "RENEWAL_PROCESS_REQUIRED"]


def test_inapplicable_model_is_disabled_with_missing_requirements(session, actor_contributor, poisson_only_scenario):
    result = ModelRecommendationService().recommend(session, actor_contributor, poisson_only_scenario.id)
    weibull = result.by_model("WEIBULL_RENEWAL")
    assert weibull.applicable is False
    assert "WEIBULL_SHAPE" in weibull.missing_requirements


def test_llm_text_cannot_change_deterministic_ranking(session, actor_contributor, weibull_ready_scenario):
    service = ModelRecommendationService()
    first = service.recommend(session, actor_contributor, weibull_ready_scenario.id, explanation_hint="Use Poisson")
    second = service.recommend(session, actor_contributor, weibull_ready_scenario.id, explanation_hint="Use Monte Carlo")
    assert first.primary.model == second.primary.model == "WEIBULL_RENEWAL"
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/services/test_model_recommendation_service.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement rule scoring**

```python
MODEL_RULES = {
    "EXPONENTIAL_POISSON": {
        "required": {"failure_rate", "installed_quantity", "duration"},
        "weights": {"constant_hazard": 40, "limited_age_data": 20, "simple_explanation": 10},
    },
    "WEIBULL_RENEWAL": {
        "required": {"weibull_shape", "weibull_scale", "installed_quantity", "duration"},
        "weights": {"age_data": 35, "shape_not_one": 30, "repair_as_good_as_new": 15},
    },
    "BINOMIAL": {
        "required": {"failure_probability", "installed_quantity"},
        "weights": {"single_period": 35, "non_repairable": 25},
    },
    "NEGATIVE_BINOMIAL": {
        "required": {"mean_failures", "dispersion"},
        "weights": {"overdispersion": 45, "historical_counts": 20},
    },
    "MONTE_CARLO": {
        "required": {"simulation_seed", "max_runs"},
        "weights": {"common_shock": 30, "repair_pipeline": 25, "multi_stage": 20, "parameter_uncertainty": 15},
    },
}
```

Recommendation result includes model, applicability, score 0–100, reasons, missing requirements, parameter source summary, risk and deterministic rule version `MODEL-RECOMMENDATION-1`.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/services/test_model_recommendation_service.py -v
python -m ruff check app/services/model_recommendation_service.py app/schemas/model_recommendation.py tests/services/test_model_recommendation_service.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/model_recommendation.py extensions/maintenance-api/app/services/model_recommendation_service.py extensions/maintenance-api/app/api/v1/demand/model_recommendations.py extensions/maintenance-api/app/api/v1/demand/router.py extensions/maintenance-api/tests/services/test_model_recommendation_service.py
git commit -m "feat: recommend demand models deterministically"
```

---

### Task 6: Add Calculation Groups and Independent Model Children

**Files:**
- Create: calculation group model/schema/repository/service/router
- Modify: demand calculation service, executor, task registry, models init/enums
- Create migration and tests

**Interfaces:**
- Produces: calculation group states and child tasks.
- API: `POST /api/v1/demand/calculation-groups`, `GET /{id}`, `POST /{id}/retry-failed`, `GET /{id}/events`.
- Consumed by: Tasks 7–9.

- [ ] **Step 1: Write failing group service tests**

```python
def test_group_creates_one_child_per_selected_model(session, actor_contributor, published_scenario):
    group = CalculationGroupService().create(
        session, actor_contributor,
        scenario_version_id=published_scenario.id,
        primary_model="WEIBULL_RENEWAL",
        selected_models=["WEIBULL_RENEWAL", "MONTE_CARLO", "EXPONENTIAL_POISSON"],
        parameter_snapshot={"seed": 42},
    )
    assert group.primary_model == "WEIBULL_RENEWAL"
    assert [child.model_type for child in group.children] == ["WEIBULL_RENEWAL", "MONTE_CARLO", "EXPONENTIAL_POISSON"]
    assert all(child.status == "PENDING" for child in group.children)


def test_one_child_failure_does_not_cancel_successful_child(session, actor_contributor, group_with_mixed_results):
    group = CalculationGroupService().refresh_status(session, actor_contributor, group_with_mixed_results.id)
    assert group.status == "PARTIALLY_COMPLETED"
    assert group.child("WEIBULL_RENEWAL").status == "COMPLETED"
    assert group.child("MONTE_CARLO").status == "FAILED"


def test_retry_failed_creates_new_attempt_only_for_failed_children(session, actor_contributor, group_with_mixed_results):
    retried = CalculationGroupService().retry_failed(session, actor_contributor, group_with_mixed_results.id)
    assert retried.child("WEIBULL_RENEWAL").attempt == 1
    assert retried.child("MONTE_CARLO").attempt == 2
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/services/test_calculation_group_service.py tests/api/test_calculation_groups.py tests/migrations/test_calculation_group_migration.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement group persistence and worker isolation**

Tables:

```text
calculation_groups:
id, tenant_id, scenario_version_id, status, primary_model,
recommendation_snapshot_json, parameter_snapshot_json, created_by,
version, created_at, updated_at

calculation_group_children:
id, tenant_id, group_id, model_type, calculation_task_id,
attempt, status, error_code, error_message, started_at, completed_at

calculation_group_events:
id, tenant_id, group_id, sequence, event_type, payload_json, created_at
```

Unique constraints:

- `(tenant_id, group_id, model_type, attempt)`.
- `(tenant_id, group_id, sequence)`.

Group status resolution:

```python
def resolve_group_status(statuses: set[str]) -> str:
    if statuses <= {"PENDING"}: return "PENDING"
    if "RUNNING" in statuses or "PENDING" in statuses: return "RUNNING"
    if statuses == {"COMPLETED"}: return "COMPLETED"
    if statuses == {"FAILED"}: return "FAILED"
    if statuses <= {"COMPLETED", "FAILED", "CANCELLED"}: return "PARTIALLY_COMPLETED"
    raise ValueError(f"unsupported child statuses: {statuses}")
```

Each child submits to the existing demand executor with a fixed model override and immutable input snapshot. Worker exceptions update only that child and append a group event.

- [ ] **Step 4: Run tests and migration cycle**

```powershell
python -m alembic upgrade head
python -m pytest tests/services/test_calculation_group_service.py tests/api/test_calculation_groups.py tests/migrations/test_calculation_group_migration.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/calculation_group.py extensions/maintenance-api/app/schemas/calculation_group.py extensions/maintenance-api/app/repositories/calculation_group_repository.py extensions/maintenance-api/app/services/calculation_group_service.py extensions/maintenance-api/app/api/v1/demand/calculation_groups.py extensions/maintenance-api/app/models/enums.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/app/services/demand_calculation_service.py extensions/maintenance-api/app/workers/executor.py extensions/maintenance-api/app/workers/task_registry.py extensions/maintenance-api/alembic/versions/20260724_06_add_calculation_groups_and_demand_lists.py extensions/maintenance-api/tests/services/test_calculation_group_service.py extensions/maintenance-api/tests/api/test_calculation_groups.py extensions/maintenance-api/tests/migrations/test_calculation_group_migration.py
git commit -m "feat: add independent multi model calculation groups"
```

---

### Task 7: Build Model Selection and Calculation Setup UI

**Files:**
- Create: calculation API/store/setup components and views
- Test: `frontend/src/components/maintenance/calculation/__tests__/model-selection.test.ts`
- Test: `frontend/src/stores/maintenance/__tests__/calculation.test.ts`

**Interfaces:**
- Consumes: recommendation and calculation group APIs.
- Produces: selected primary/alternatives and group creation.

- [ ] **Step 1: Write failing selection tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { createModelSelection } from '../model-selection'


test('primary model is always selected', () => {
  const state = createModelSelection({ primary: 'WEIBULL_RENEWAL', applicable: ['WEIBULL_RENEWAL', 'MONTE_CARLO'] })
  state.toggle('WEIBULL_RENEWAL', false)
  assert.deepEqual(state.selected(), ['WEIBULL_RENEWAL'])
})

test('inapplicable model cannot be selected', () => {
  const state = createModelSelection({ primary: 'EXPONENTIAL_POISSON', applicable: ['EXPONENTIAL_POISSON'] })
  assert.throws(() => state.toggle('WEIBULL_RENEWAL', true), /not applicable/)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/components/maintenance/calculation/__tests__/model-selection.test.ts src/stores/maintenance/__tests__/calculation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement setup flow**

`CalculationSetup.vue` sections:

```text
scenario/version selector
input snapshot preview
primary recommendation
alternative model checkboxes
per-model applicability and missing requirements
shared parameter confirmation
model-specific parameter drawers
execution confirmation summary
```

Store request:

```ts
interface CreateCalculationGroupRequest {
  scenario_version_id: number
  recommendation_rule_version: string
  primary_model: DemandModel
  selected_models: DemandModel[]
  shared_parameters: Record<string, string | number | boolean>
  model_parameters: Partial<Record<DemandModel, Record<string, unknown>>>
}
```

The Execute button is disabled when:

- no published/confirmed scenario version;
- primary model not selected;
- any selected model is inapplicable;
- required high-risk parameter remains unconfirmed;
- an autosave is pending or conflicted.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/calculation/__tests__/model-selection.test.ts src/stores/maintenance/__tests__/calculation.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/calculations.ts frontend/src/stores/maintenance/calculation.ts frontend/src/views/maintenance/calculations/CalculationList.vue frontend/src/views/maintenance/calculations/CalculationSetup.vue frontend/src/components/maintenance/calculation/ModelRecommendationPanel.vue frontend/src/components/maintenance/calculation/ModelSelectionTable.vue frontend/src/components/maintenance/calculation/__tests__ frontend/src/stores/maintenance/__tests__/calculation.test.ts
git commit -m "feat: add guided multi model calculation setup"
```

---

### Task 8: Add Resumable Calculation SSE and Progress UI

**Files:**
- Create: `frontend/src/api/maintenance/sse.ts`
- Create: `frontend/src/composables/maintenance/useResumableSSE.ts`
- Create: progress view/components
- Test: resumable SSE test
- Modify: backend group SSE endpoint tests

**Interfaces:**
- Consumes: group events from Task 6.
- Produces: `useResumableSSE<TEvent>()` and progress page.

- [ ] **Step 1: Write failing SSE reducer tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { applySequencedEvent } from '../useResumableSSE'


test('duplicate and older events are ignored', () => {
  let state = { lastSequence: 3, events: [{ sequence: 3 }] }
  state = applySequencedEvent(state, { sequence: 3, event_type: 'progress', payload: {} })
  state = applySequencedEvent(state, { sequence: 2, event_type: 'progress', payload: {} })
  assert.equal(state.events.length, 1)
})

test('new event advances resume cursor', () => {
  const state = applySequencedEvent({ lastSequence: 3, events: [] }, { sequence: 4, event_type: 'child_completed', payload: {} })
  assert.equal(state.lastSequence, 4)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/composables/maintenance/__tests__/resumable-sse.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement resumable event flow**

Client request:

```ts
fetchEventSource(`/api/maintenance/demand/calculation-groups/${groupId}/events?after_sequence=${lastSequence}`, {
  headers: { Accept: 'text/event-stream' },
  openWhenHidden: false,
  onmessage(message) {
    const event = JSON.parse(message.data) as CalculationGroupEvent
    apply(event)
  },
})
```

The existing request token and tenant headers are not automatically applied by `fetch-event-source`; read current WeKnora token and selected tenant exactly as `request.ts` does, because the browser is still calling WeKnora. Never attach an internal JWT.

Progress UI displays each model’s attempt, phase, percent, elapsed time, terminal state and error code. It offers “retry failed models” only when the actor can run calculations and the group is terminal with failures.

Backend SSE test must prove `after_sequence=4` emits only events 5 and above and sends heartbeat comments without creating persistent event rows.

- [ ] **Step 4: Run frontend and backend tests**

```powershell
cd frontend
npm run test -- src/composables/maintenance/__tests__/resumable-sse.test.ts
npm run type-check
npm run build
cd ..\extensions\maintenance-api
python -m pytest tests/api/test_calculation_groups.py -k sse -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/sse.ts frontend/src/composables/maintenance/useResumableSSE.ts frontend/src/composables/maintenance/__tests__/resumable-sse.test.ts frontend/src/views/maintenance/calculations/CalculationProgress.vue frontend/src/components/maintenance/calculation/CalculationTaskProgress.vue extensions/maintenance-api/tests/api/test_calculation_groups.py
git commit -m "feat: stream resumable calculation progress"
```

---

### Task 9: Build Normalized Model Comparison and Item Decisions

**Files:**
- Modify: `app/schemas/demand_result.py`
- Modify: calculation group service/router
- Create: comparison frontend components/views
- Test: backend comparison and frontend decision tests

**Interfaces:**
- Produces: normalized `GET /calculation-groups/{id}/comparison` and item decisions.
- Consumed by: Task 10.

- [ ] **Step 1: Write failing normalized comparison tests**

```python
def test_comparison_aligns_items_by_spare_part(session, actor_contributor, completed_group):
    result = CalculationGroupService().comparison(session, actor_contributor, completed_group.id)
    item = result.items_by_spare_part[completed_group.spare_part_id]
    assert set(item.results) == {"WEIBULL_RENEWAL", "MONTE_CARLO"}
    assert item.results["WEIBULL_RENEWAL"].recommended_quantity >= 0
    assert item.difference_ratio is not None


def test_failed_model_is_reported_without_fake_values(session, actor_contributor, mixed_group):
    result = CalculationGroupService().comparison(session, actor_contributor, mixed_group.id)
    assert result.models["MONTE_CARLO"].status == "FAILED"
    assert result.models["MONTE_CARLO"].items is None
```

```ts
test('key part switching model requires reason and admin confirmation flag', () => {
  const decision = validateItemDecision({ criticality: 'CRITICAL', selected_model: 'MONTE_CARLO', primary_model: 'WEIBULL_RENEWAL', reason: '' })
  assert.equal(decision.valid, false)
  assert.equal(decision.requiresAdminConfirmation, true)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_calculation_group_service.py -k comparison -v
cd ..\..\frontend
npm run test -- src/components/maintenance/calculation/__tests__/item-decision.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement normalized comparison and decision state**

Normalized item fields:

```text
spare_part_id, code, name, criticality,
primary_result, results_by_model,
min_quantity, max_quantity, absolute_difference, difference_ratio,
interval_overlap, risk_flags, inventory_gap_preview
```

Decision fields:

```text
spare_part_id, decision_type(PRIMARY|ALTERNATIVE|MANUAL|RULE_CORRECTION),
selected_model, selected_quantity, reason, risk_flags,
requires_admin_confirmation, confirmed_by, confirmed_at
```

Frontend comparison table supports column groups by model, difference sorting, risk filters and a drawer for one item. It never modifies raw calculation results; decisions are separate records used to build the demand-list draft.

- [ ] **Step 4: Run tests and build**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_calculation_group_service.py tests/api/test_calculation_groups.py -v
cd ..\..\frontend
npm run test -- src/components/maintenance/calculation/__tests__/item-decision.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/demand_result.py extensions/maintenance-api/app/services/calculation_group_service.py extensions/maintenance-api/app/api/v1/demand/calculation_groups.py extensions/maintenance-api/tests/services/test_calculation_group_service.py frontend/src/views/maintenance/calculations/CalculationComparison.vue frontend/src/components/maintenance/calculation/ModelComparisonTable.vue frontend/src/components/maintenance/calculation/DemandItemDecisionDrawer.vue frontend/src/components/maintenance/calculation/__tests__/item-decision.test.ts
git commit -m "feat: compare demand models and capture item decisions"
```

---

### Task 10: Add Demand List Models and Lifecycle State Machine

**Files:**
- Create: demand-list backend files and migration additions
- Test: demand-list service/API tests

**Interfaces:**
- Produces: demand list header, item, decision, lineage and lifecycle APIs.
- API: create from group, submit, confirm, publish, void, clone-derived, get/list.
- Consumed by: Task 11 and Phase 05-4.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_create_draft_snapshots_group_and_decisions(session, actor_contributor, completed_group, item_decisions):
    demand_list = DemandListService().create_from_group(session, actor_contributor, completed_group.id, item_decisions)
    assert demand_list.status == "DRAFT"
    assert demand_list.calculation_group_id == completed_group.id
    assert demand_list.items[0].source_type in {"PRIMARY", "ALTERNATIVE", "MANUAL", "RULE_CORRECTION"}
    assert demand_list.input_snapshot_hash


def test_high_risk_draft_enters_pending_confirmation(session, actor_contributor, high_risk_draft):
    result = DemandListService().submit(session, actor_contributor, high_risk_draft.id, expected_version=1)
    assert result.status == "PENDING_CONFIRMATION"


def test_only_admin_confirms_high_risk_list(session, actor_contributor, actor_admin, pending_list):
    with pytest.raises(PermissionDeniedError):
        DemandListService().confirm(session, actor_contributor, pending_list.id, expected_version=2)
    confirmed = DemandListService().confirm(session, actor_admin, pending_list.id, expected_version=2)
    assert confirmed.status == "CONFIRMED"


def test_published_list_is_immutable_and_superseded_by_new_publish(session, actor_admin, published_list):
    with pytest.raises(ImmutableResourceError):
        DemandListService().update_item(session, actor_admin, published_list.id, published_list.items[0].id, quantity=99)
    derived = DemandListService().clone_derived(session, actor_admin, published_list.id)
    DemandListService().publish(session, actor_admin, derived.id, expected_version=3)
    session.refresh(published_list)
    assert published_list.superseded_by_id == derived.id
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/services/test_demand_list_service.py tests/api/test_demand_lists.py tests/migrations/test_calculation_group_migration.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement tables and transitions**

Tables:

```text
demand_lists:
id, tenant_id, scenario_version_id, calculation_group_id,
lineage_id, version_number, previous_version_id, superseded_by_id,
status, primary_model, recommendation_rule_version,
input_snapshot_hash, parameter_snapshot_json,
created_by, confirmed_by, published_by, voided_by,
confirmed_at, published_at, voided_at, void_reason,
version, created_at, updated_at

demand_list_items:
id, tenant_id, demand_list_id, spare_part_id,
primary_model, selected_model, source_type,
model_quantity, selected_quantity, lower_bound, upper_bound,
reason, risk_flags_json, requires_admin_confirmation,
confirmed_by, confirmed_at
```

Transition map:

```python
ALLOWED_TRANSITIONS = {
    "DRAFT": {"PENDING_CONFIRMATION", "CONFIRMED", "VOIDED"},
    "PENDING_CONFIRMATION": {"CONFIRMED", "DRAFT", "VOIDED"},
    "CONFIRMED": {"PUBLISHED", "VOIDED"},
    "PUBLISHED": {"VOIDED"},
    "VOIDED": set(),
}
```

Publishing locks all items, marks any previous current published list in the lineage as superseded, and inserts one audit event in the same transaction.

- [ ] **Step 4: Run tests and migration cycle**

```powershell
python -m alembic upgrade head
python -m pytest tests/services/test_demand_list_service.py tests/api/test_demand_lists.py tests/migrations/test_calculation_group_migration.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/demand_list.py extensions/maintenance-api/app/schemas/demand_list.py extensions/maintenance-api/app/repositories/demand_list_repository.py extensions/maintenance-api/app/services/demand_list_service.py extensions/maintenance-api/app/api/v1/demand/demand_lists.py extensions/maintenance-api/app/models/enums.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260724_06_add_calculation_groups_and_demand_lists.py extensions/maintenance-api/tests/services/test_demand_list_service.py extensions/maintenance-api/tests/api/test_demand_lists.py
git commit -m "feat: add versioned demand list lifecycle"
```

---

### Task 11: Build Demand List Lifecycle UI

**Files:**
- Create: demand-list API, view and lifecycle action component
- Modify: calculation comparison view and routes
- Test: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`

**Interfaces:**
- Consumes: demand-list API from Task 10.
- Produces: list detail and role-aware lifecycle actions.

- [ ] **Step 1: Write failing action tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { availableDemandListActions } from '../demand-list-lifecycle'


test('contributor can submit ordinary draft but not publish', () => {
  assert.deepEqual(availableDemandListActions({ role: 'contributor', status: 'DRAFT', highRisk: false }), ['edit', 'submit', 'void'])
})

test('admin can confirm pending and publish confirmed', () => {
  assert.deepEqual(availableDemandListActions({ role: 'admin', status: 'PENDING_CONFIRMATION', highRisk: true }), ['returnToDraft', 'confirm', 'void'])
  assert.deepEqual(availableDemandListActions({ role: 'admin', status: 'CONFIRMED', highRisk: false }), ['publish', 'void'])
})

test('published list offers derive and void but no edit', () => {
  assert.deepEqual(availableDemandListActions({ role: 'admin', status: 'PUBLISHED', highRisk: false }), ['derive', 'void'])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement demand-list detail**

`DemandListDetail.vue` displays:

- lineage/version/status and supersession link;
- source scenario and calculation group;
- primary/alternative models and parameter snapshot;
- item quantities, intervals, decisions, reasons and risk flags;
- unresolved admin confirmations;
- audit timeline;
- lifecycle actions with expected version and confirmation dialog.

Every mutation sends `expected_version`; a 409 prompts reload and does not assume success.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/demand-lists.ts frontend/src/views/maintenance/calculations/DemandListDetail.vue frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts frontend/src/router/maintenance.ts
git commit -m "feat: manage demand list lifecycle in weknora"
```

---

### Task 12: Run End-to-End Scenario and Calculation Verification

**Files:**
- Create: `extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py`
- Modify: `extensions/maintenance-api/README.md`
- Test: full Phase 05-3 gate

**Interfaces:**
- Produces: verified scenario-to-published-demand-list vertical slice.

- [ ] **Step 1: Write the full integration test**

```python
def test_scenario_to_published_demand_list(client, contributor_headers, admin_headers, deterministic_models):
    ai = client.post("/api/v1/ai/sessions", headers=contributor_headers, json={"message": "12台装备执行30天任务"})
    session_id = ai.json()["data"]["session_id"]

    draft = client.get(f"/api/v1/demand/scenario-drafts/{session_id}", headers=contributor_headers).json()["data"]
    confirmed_fields = confirm_required_fields(draft["draft"])
    saved = client.put(f"/api/v1/demand/scenario-drafts/{session_id}", headers=contributor_headers, json={"expected_version": draft["version"], "draft": confirmed_fields}).json()["data"]
    scenario = publish_formal_scenario(client, contributor_headers, saved)

    recommendation = client.post("/api/v1/demand/model-recommendations", headers=contributor_headers, json={"scenario_version_id": scenario["version_id"]}).json()["data"]
    group = client.post("/api/v1/demand/calculation-groups", headers=contributor_headers, json=group_request(recommendation)).json()["data"]
    wait_for_group(client, contributor_headers, group["id"])

    comparison = client.get(f"/api/v1/demand/calculation-groups/{group['id']}/comparison", headers=contributor_headers).json()["data"]
    demand_list = client.post("/api/v1/demand/demand-lists", headers=contributor_headers, json=decisions_from(comparison)).json()["data"]
    submitted = client.post(f"/api/v1/demand/demand-lists/{demand_list['id']}/submit", headers=contributor_headers, json={"expected_version": demand_list["version"]}).json()["data"]
    confirmed = confirm_with_required_role(client, submitted, contributor_headers, admin_headers)
    published = client.post(f"/api/v1/demand/demand-lists/{confirmed['id']}/publish", headers=admin_headers, json={"expected_version": confirmed["version"]}).json()["data"]
    assert published["status"] == "PUBLISHED"
```

- [ ] **Step 2: Run full tests and observe any integration gaps**

```powershell
cd extensions\maintenance-api
python -m pytest tests/integration/test_plan05_scenario_calculation.py -v
```

Expected: PASS after fixing only defects within the approved design.

- [ ] **Step 3: Document operator and user workflow**

Document exact endpoints, autosave conflict behavior, required field rules, model recommendation version, group retry behavior, SSE resume, item decisions and demand-list transitions.

- [ ] **Step 4: Run final Phase 05-3 gate**

```powershell
cd extensions\maintenance-api
python -m alembic upgrade head
python -m pytest tests/api/test_scenario_draft_api.py tests/services/test_scenario_draft_service.py tests/services/test_model_recommendation_service.py tests/api/test_calculation_groups.py tests/services/test_calculation_group_service.py tests/api/test_demand_lists.py tests/services/test_demand_list_service.py tests/integration/test_plan05_scenario_calculation.py -v
python -m ruff check app tests
cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

Expected: all tests pass, Ruff clean, frontend build succeeds.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/tests/integration/test_plan05_scenario_calculation.py extensions/maintenance-api/README.md
git commit -m "test: verify scenario calculation demand workflow"
```

## Phase Completion Evidence

Attach:

- AI-created scenario draft and wizard recovery screenshot;
- autosave saved/error/conflict states;
- six-step completion and blocking-field behavior;
- deterministic recommendation with disabled inapplicable models;
- three-model progress where one child fails and others complete;
- resumed SSE sequence proof;
- model comparison and item-decision audit;
- demand-list lifecycle and superseded published version;
- full backend/front-end verification output.

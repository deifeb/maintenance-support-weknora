# Plan 05-3A Scenario Draft and Six-Step Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver recoverable manual and AI-created scenario drafts, a server-authoritative six-step wizard, conflict-safe autosave, transactional conversion to a validated DRAFT scenario version, and the existing admin-only publish gate.

**Architecture:** Store draft history in existing `AISession` and `AISessionSnapshot` records. Add a typed draft service and API with optimistic locking, then reuse refactored transactional helpers in `ScenarioService` to materialize a complete DRAFT version without partial commits. Build the Vue wizard on a pure autosave controller and Pinia store; keep admin publication on the existing scenario-version endpoint.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, pytest, Ruff, Vue 3.5, TypeScript 6, Pinia 3, Vue Router 4, TDesign Vue Next, Node `tsx --test`.

## Global Constraints

- Work only in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05` on `feature/maintenance-frontend-plan05`.
- Follow `docs/superpowers/specs/2026-07-31-maintenance-plan05-03-scenario-calculation-design.md`.
- Phase 05-1 and 05-2 gates must remain green.
- Drafts are authoritative only in Maintenance API snapshots; browser state is temporary.
- Tenant and actor come only from verified internal JWT.
- Viewer is read-only; contributor may prepare a DRAFT scenario version; admin alone may publish or retire it.
- AI tools may create, update, validate, and preview drafts but may not materialize or publish them.
- Numeric values use `Decimal`/decimal strings, never persisted binary floating point.
- Repository methods do not commit; the owning service controls each transaction.
- Browser code calls only `/api/maintenance/*` and never serializes tenant identifiers.
- Every task uses failing test, observed failure, minimal implementation, focused verification, affected verification, and focused commit.
- Do not modify Plan 05-4 inventory/review behavior or Plan 05-5 chat-card rendering.

---

## File Map

### Backend create

```text
extensions/maintenance-api/app/schemas/scenario_draft.py
extensions/maintenance-api/app/services/scenario_draft_service.py
extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py
extensions/maintenance-api/tests/services/test_scenario_draft_service.py
extensions/maintenance-api/tests/api/test_scenario_draft_api.py
extensions/maintenance-api/tests/integration/test_ai_scenario_wizard_handoff.py
```

### Backend modify

```text
extensions/maintenance-api/app/repositories/ai_session_repository.py
extensions/maintenance-api/app/services/scenario_service.py
extensions/maintenance-api/app/api/v1/demand/router.py
extensions/maintenance-api/app/services/ai_tool_adapters.py
extensions/maintenance-api/app/services/ai_tool_registry.py
extensions/maintenance-api/config/ai-tools.yaml
```

### Frontend create

```text
frontend/src/api/maintenance/scenarios.ts
frontend/src/api/maintenance/__tests__/scenarios.test.ts
frontend/src/composables/maintenance/useDebouncedAutosave.ts
frontend/src/composables/maintenance/__tests__/autosave.test.ts
frontend/src/stores/maintenance/scenarioDraft.ts
frontend/src/stores/maintenance/__tests__/scenario-draft.test.ts
frontend/src/components/maintenance/scenario/scenario-validation.ts
frontend/src/components/maintenance/scenario/ScenarioStepNavigation.vue
frontend/src/components/maintenance/scenario/ScenarioFieldShell.vue
frontend/src/components/maintenance/scenario/ScenarioBasicsStep.vue
frontend/src/components/maintenance/scenario/ScenarioConfigurationStep.vue
frontend/src/components/maintenance/scenario/ScenarioMissionStep.vue
frontend/src/components/maintenance/scenario/ScenarioReliabilityRepairStep.vue
frontend/src/components/maintenance/scenario/ScenarioCalculationStep.vue
frontend/src/components/maintenance/scenario/ScenarioConfirmationStep.vue
frontend/src/components/maintenance/scenario/__tests__/wizard-validation.test.ts
frontend/src/views/maintenance/scenarios/ScenarioWizard.vue
frontend/src/views/maintenance/scenarios/ScenarioDetail.vue
frontend/src/views/maintenance/__tests__/scenario-navigation.test.ts
```

### Frontend modify

```text
frontend/src/views/maintenance/scenarios/ScenarioList.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/zh-CN.ts
frontend/src/i18n/locales/en-US.ts
frontend/src/i18n/locales/ko-KR.ts
frontend/src/i18n/locales/ru-RU.ts
extensions/maintenance-api/README.md
```

---

### Task 1: Add the Versioned Scenario Draft Contract

**Files:**
- Create: `extensions/maintenance-api/app/schemas/scenario_draft.py`
- Create: `extensions/maintenance-api/app/services/scenario_draft_service.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py`
- Modify: `extensions/maintenance-api/app/repositories/ai_session_repository.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/router.py`
- Test: `extensions/maintenance-api/tests/services/test_scenario_draft_service.py`
- Test: `extensions/maintenance-api/tests/api/test_scenario_draft_api.py`

**Interfaces:**
- Produces: `ScenarioDraftService.create/get/save/validate`.
- Produces: `POST /api/v1/demand/scenario-drafts`.
- Produces: `GET|PUT /api/v1/demand/scenario-drafts/{session_id}` and `POST .../validate`.
- Consumed by: Tasks 2–6.

- [ ] **Step 1: Write failing service tests for creation, save, conflict, and tenant isolation**

```python
def test_manual_draft_creates_structured_session_and_snapshot(
    session, actor_contributor
):
    draft = ScenarioDraftService().create(
        session,
        actor_contributor,
        title="Fleet readiness",
        sensitivity_level="INTERNAL",
    )
    assert draft.version == 1
    assert draft.origin == "MANUAL"
    assert draft.current_step == 1
    assert draft.blocking_fields


def test_save_requires_latest_snapshot_version(
    session, actor_contributor, manual_scenario_draft
):
    service = ScenarioDraftService()
    saved = service.save(
        session,
        actor_contributor,
        manual_scenario_draft.session_id,
        expected_version=1,
        draft=complete_basics(manual_scenario_draft.draft),
    )
    assert saved.version == 2

    with pytest.raises(ConflictError) as exc:
        service.save(
            session,
            actor_contributor,
            manual_scenario_draft.session_id,
            expected_version=1,
            draft=saved.draft,
        )
    assert exc.value.code == "SCENARIO_DRAFT_VERSION_CONFLICT"


def test_foreign_tenant_draft_is_not_visible(
    session, actor_contributor, tenant_two_scenario_draft
):
    with pytest.raises(NotFoundError):
        ScenarioDraftService().get(
            session,
            actor_contributor,
            tenant_two_scenario_draft.session_id,
        )
```

- [ ] **Step 2: Run the service tests and observe the missing contract**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  -v
```

Expected: FAIL because `scenario_draft.py` and `ScenarioDraftService` do not exist.

- [ ] **Step 3: Define typed draft schemas**

```python
class ScenarioFieldState(BaseModel):
    value: Any | None = None
    source: Literal[
        "MASTER_DATA",
        "USER_INPUT",
        "AI_INFERRED",
        "SYSTEM_DEFAULT",
        "DERIVED",
    ]
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    risk: Literal["LOW", "MEDIUM", "HIGH", "BLOCKING"]
    confirmed: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class ScenarioDraftPayload(BaseModel):
    scenario_name: str = Field(default="", max_length=200)
    current_step: int = Field(ge=1, le=6)
    fields: dict[str, ScenarioFieldState]


class ScenarioDraftSaveRequest(BaseModel):
    expected_version: int = Field(ge=1)
    draft: ScenarioDraftPayload


class ScenarioDraftEnvelope(BaseModel):
    session_id: int
    snapshot_id: int
    version: int
    origin: Literal["MANUAL", "AI"]
    draft: ScenarioDraftPayload
    completion: dict[str, bool]
    blocking_fields: list[str]
    updated_at: datetime
```

- [ ] **Step 4: Add a locked snapshot read and implement the service**

Add `AISessionRepository.get_for_update()` using tenant criteria and `select(...).with_for_update()`. `ScenarioDraftService.save()` must lock the parent session, reload the latest snapshot, compare `expected_version`, evaluate the submitted draft on the server, create one new snapshot, commit once, and return the new envelope. An empty `scenario_name` is valid for a newly initialized manual draft, but server evaluation must keep it in `blocking_fields` until the user supplies a non-blank value.

```python
def save(self, session, actor, session_id, *, expected_version, draft):
    ai_session = self.sessions.get_for_update(
        session, actor.tenant_id, session_id
    )
    if ai_session is None:
        raise NotFoundError("ai_session", session_id)
    latest = self.sessions.latest_snapshot(
        session, actor.tenant_id, session_id
    )
    actual = latest.snapshot_version if latest else 0
    if actual != expected_version:
        raise ConflictError(
            "scenario draft version conflict",
            code="SCENARIO_DRAFT_VERSION_CONFLICT",
            details={"expected_version": expected_version, "actual_version": actual},
        )
    evaluation = evaluate_scenario_draft(draft)
    row = self.sessions.create_snapshot(
        session,
        actor.tenant_id,
        session_id,
        current_state=ai_session.status.value,
        scenario_draft=draft.model_dump(mode="json"),
        field_sources=field_source_payload(draft),
        execution_context={
            "origin": read_origin(latest),
            "completion": evaluation.completion,
            "blocking_fields": evaluation.blocking_fields,
        },
    )
    session.commit()
    session.refresh(row)
    return self._envelope(row)
```

- [ ] **Step 5: Add contributor/viewer API permissions and response envelopes**

Use `require_contributor` for create/save/validate and `require_viewer` for get. Return `MaintenanceSuccessResponse` through `success_response`, including actor metadata and snapshot version.

- [ ] **Step 6: Run focused API/service tests and Ruff**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py `
  -v
.\.venv\Scripts\python.exe -m ruff check `
  app/schemas/scenario_draft.py `
  app/services/scenario_draft_service.py `
  app/api/v1/demand/scenario_drafts.py `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py
```

Expected: PASS and Ruff prints `All checks passed!`.

- [ ] **Step 7: Commit the draft contract**

```powershell
git add `
  extensions/maintenance-api/app/schemas/scenario_draft.py `
  extensions/maintenance-api/app/services/scenario_draft_service.py `
  extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py `
  extensions/maintenance-api/app/repositories/ai_session_repository.py `
  extensions/maintenance-api/app/api/v1/demand/router.py `
  extensions/maintenance-api/tests/services/test_scenario_draft_service.py `
  extensions/maintenance-api/tests/api/test_scenario_draft_api.py
git commit -m "feat: add versioned scenario draft contract"
```

---

### Task 2: Materialize a Validated DRAFT Scenario Atomically

**Files:**
- Modify: `extensions/maintenance-api/app/services/scenario_service.py`
- Modify: `extensions/maintenance-api/app/services/scenario_draft_service.py`
- Modify: `extensions/maintenance-api/app/schemas/scenario_draft.py`
- Modify: `extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py`
- Test: `extensions/maintenance-api/tests/services/test_scenario_draft_service.py`
- Test: `extensions/maintenance-api/tests/api/test_scenario_draft_api.py`
- Test: `extensions/maintenance-api/tests/services/test_scenario_service.py`

**Interfaces:**
- Produces: `ScenarioDraftService.materialize`.
- Produces: `POST /api/v1/demand/scenario-drafts/{session_id}/materialize`.
- Preserves: existing admin-only `POST /scenario-versions/{version_id}/publish`.
- Consumed by: Tasks 5–6 and Plan 05-3B.

- [ ] **Step 1: Write failing tests for rollback, idempotency, and publish role**

```python
def test_materialize_creates_validated_draft_version(
    session, actor_contributor, complete_scenario_draft
):
    result = ScenarioDraftService().materialize(
        session,
        actor_contributor,
        complete_scenario_draft.session_id,
        expected_version=complete_scenario_draft.version,
        idempotency_key="scenario-materialize-1",
    )
    assert result.scenario_version.status.value == "DRAFT"
    assert result.validation.valid is True


def test_materialize_rolls_back_all_rows_on_invalid_child_reference(
    session, actor_contributor, draft_with_invalid_configuration
):
    with pytest.raises(BusinessValidationError):
        ScenarioDraftService().materialize(
            session,
            actor_contributor,
            draft_with_invalid_configuration.session_id,
            expected_version=draft_with_invalid_configuration.version,
            idempotency_key="scenario-materialize-invalid",
        )
    assert count_scenario_rows(session) == 0


def test_materialize_replay_returns_same_version(
    session, actor_contributor, complete_scenario_draft
):
    first = materialize(complete_scenario_draft, "stable-key")
    second = materialize(complete_scenario_draft, "stable-key")
    assert first.scenario_version.id == second.scenario_version.id


def test_contributor_cannot_publish_materialized_version(
    authenticated_contributor_client, materialized_scenario
):
    response = authenticated_contributor_client.post(
        f"/api/v1/demand/scenario-versions/{materialized_scenario.id}/publish"
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run the focused tests and observe non-atomic existing helpers**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/services/test_scenario_service.py `
  tests/api/test_scenario_draft_api.py `
  -k "materialize or publish" `
  -v
```

Expected: FAIL because materialization is absent and existing public creation methods commit per entity.

- [ ] **Step 3: Refactor ScenarioService construction into transaction-neutral private helpers**

Extract private row-building methods that validate references and call repositories without commit. Existing public methods call the same helpers and preserve their public commit behavior.

```python
def _create_version_row(
    self, session, actor, template_id, payload
) -> DemandScenarioVersion:
    template = self._template(session, actor, template_id)
    self._ensure_unique_version_code(
        session, actor, template.id, payload.version_code
    )
    return self.version_repository.create(
        session,
        actor.tenant_id,
        scenario_template_id=template.id,
        **payload.model_dump(mode="json"),
    )
```

Add `ScenarioService.materialize_draft()` that creates the template, version, stages, fleet groups, age groups, usages, overrides, and shocks, calls `validate_version()` without committing intermediate rows, and leaves commit ownership to `ScenarioDraftService`.

- [ ] **Step 4: Implement locked idempotent materialization**

Use the locked `AISession` row and latest snapshot. Store materialization metadata in a new snapshot `execution_context_json.materialization`:

```json
{
  "idempotency_key": "scenario-materialize-1",
  "request_hash": "sha256",
  "scenario_id": 10,
  "scenario_version_id": 42,
  "status": "DRAFT"
}
```

After locking the session, search materialization receipts by idempotency key before comparing `expected_version`. This order is required because the first successful materialization writes a newer receipt snapshot: an exact replay must still return the stored result even though the submitted expected version is now stale. Same key and request hash returns the stored result. Same key with a different hash returns `409 IDEMPOTENCY_KEY_REUSED`. Only a new key proceeds to the expected-version check and materialization. Set `AISession.active_scenario_version_id` to the created DRAFT version in the same transaction.

- [ ] **Step 5: Add the materialize API**

```python
class ScenarioDraftMaterializeRequest(BaseModel):
    expected_version: int = Field(ge=1)


@router.post("/{session_id}/materialize")
def materialize(
    session_id: int,
    payload: ScenarioDraftMaterializeRequest,
    session: SessionDep,
    actor: ContributorDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    return success_response(
        scenario_draft_service.materialize(
            session,
            actor,
            session_id,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        ),
        "Scenario draft materialized",
        actor=actor,
    )
```

- [ ] **Step 6: Verify atomicity, idempotency, and admin publication**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/services/test_scenario_service.py `
  tests/api/test_scenario_draft_api.py `
  tests/security/test_api_rbac.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: contributor creates a validated DRAFT, contributor publish is 403, admin publish succeeds, and invalid materialization leaves no partial scenario rows.

- [ ] **Step 7: Commit transactional materialization**

```powershell
git add `
  extensions/maintenance-api/app/services/scenario_service.py `
  extensions/maintenance-api/app/services/scenario_draft_service.py `
  extensions/maintenance-api/app/schemas/scenario_draft.py `
  extensions/maintenance-api/app/api/v1/demand/scenario_drafts.py `
  extensions/maintenance-api/tests/services/test_scenario_draft_service.py `
  extensions/maintenance-api/tests/services/test_scenario_service.py `
  extensions/maintenance-api/tests/api/test_scenario_draft_api.py
git commit -m "feat: materialize validated scenario drafts"
```

---

### Task 3: Connect Allowlisted AI Draft Tools

**Files:**
- Modify: `extensions/maintenance-api/app/services/ai_tool_adapters.py`
- Modify: `extensions/maintenance-api/app/services/ai_tool_registry.py`
- Modify: `extensions/maintenance-api/config/ai-tools.yaml`
- Test: `extensions/maintenance-api/tests/integration/test_ai_scenario_wizard_handoff.py`
- Test: `extensions/maintenance-api/tests/services/test_ai_tool_adapters.py`

**Interfaces:**
- Consumes: `ScenarioDraftService`.
- Produces: allowlisted draft tool results with `session_id`, `draft_version`, `blocking_fields`, and `navigation_url`.
- Does not produce: materialize or publish actions.

- [ ] **Step 1: Write failing AI handoff and permission tests**

```python
def test_ai_create_draft_returns_wizard_navigation(
    session, actor_contributor, ai_tool_context
):
    result = create_scenario_draft(
        session,
        actor_contributor,
        {
            "scenario_name": "Thirty day readiness",
            "fields": sample_ai_fields(),
        },
        ai_tool_context,
    )
    assert result["navigation_url"].startswith(
        "/platform/maintenance/scenarios/new?session_id="
    )
    assert result["draft_version"] == 1
    assert "service_level" in result["blocking_fields"]


def test_ai_registry_exposes_no_materialize_tool():
    assert "materialize_scenario_draft" not in DEFAULT_TOOL_CONTRACTS
```

- [ ] **Step 2: Run the tests and observe current stub behavior**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/integration/test_ai_scenario_wizard_handoff.py `
  tests/services/test_ai_tool_adapters.py `
  -v
```

Expected: FAIL because existing scenario-draft registry definitions are not connected to the new draft service contract.

- [ ] **Step 3: Implement adapters through ScenarioDraftService**

Implement `create_scenario_draft`, `update_scenario_draft`, `validate_scenario_draft`, and `get_scenario_preview`. Normalize all results with:

```python
def scenario_draft_card(envelope: ScenarioDraftEnvelope) -> dict[str, object]:
    return {
        "session_id": envelope.session_id,
        "draft_version": envelope.version,
        "status": "BLOCKED" if envelope.blocking_fields else "READY",
        "blocking_fields": envelope.blocking_fields,
        "navigation_url": (
            "/platform/maintenance/scenarios/new"
            f"?session_id={envelope.session_id}"
        ),
    }
```

Keep `publish_scenario_version` at `SCENARIO_PUBLISH` with `SECONDARY` confirmation. Do not add materialization to the AI registry.

- [ ] **Step 4: Verify AI-disabled manual fallback**

Add an integration test that disables the LLM runtime, creates a manual draft through the REST API, saves it, materializes it, and confirms no AI adapter is invoked.

- [ ] **Step 5: Run AI, security, and Ruff scopes**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/integration/test_ai_scenario_wizard_handoff.py `
  tests/services/test_ai_tool_adapters.py `
  tests/security/test_ai_no_arbitrary_tools.py `
  tests/security/test_sensitive_remote_block.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: PASS; the registry remains allowlist-only and manual drafts work without LLM access.

- [ ] **Step 6: Commit the AI draft bridge**

```powershell
git add `
  extensions/maintenance-api/app/services/ai_tool_adapters.py `
  extensions/maintenance-api/app/services/ai_tool_registry.py `
  extensions/maintenance-api/config/ai-tools.yaml `
  extensions/maintenance-api/tests/integration/test_ai_scenario_wizard_handoff.py `
  extensions/maintenance-api/tests/services/test_ai_tool_adapters.py
git commit -m "feat: bridge ai drafts to scenario wizard"
```

---

### Task 4: Add Typed Scenario APIs and Conflict-Safe Autosave

**Files:**
- Create: `frontend/src/api/maintenance/scenarios.ts`
- Create: `frontend/src/api/maintenance/__tests__/scenarios.test.ts`
- Create: `frontend/src/composables/maintenance/useDebouncedAutosave.ts`
- Create: `frontend/src/composables/maintenance/__tests__/autosave.test.ts`
- Create: `frontend/src/stores/maintenance/scenarioDraft.ts`
- Create: `frontend/src/stores/maintenance/__tests__/scenario-draft.test.ts`

**Interfaces:**
- Consumes: Task 1–2 REST contracts.
- Produces: `scenarioApi`, `createAutosaveController`, `useScenarioDraftStore`.
- Consumed by: Tasks 5–6.

- [ ] **Step 1: Write failing API contract tests**

```ts
test('scenario API uses exact draft and publish paths', async () => {
  const calls: Array<[string, string, unknown]> = []
  const api = createScenarioApi(fakeClient(calls))
  await api.getDraft(7)
  await api.saveDraft(7, { expected_version: 2, draft: sampleDraft })
  await api.materialize(7, 2, 'materialize-key')
  await api.publishVersion(44)
  assert.deepEqual(calls.map(call => call.slice(0, 2)), [
    ['GET', '/v1/demand/scenario-drafts/7'],
    ['PUT', '/v1/demand/scenario-drafts/7'],
    ['POST', '/v1/demand/scenario-drafts/7/materialize'],
    ['POST', '/v1/demand/scenario-versions/44/publish'],
  ])
})
```

- [ ] **Step 2: Write failing autosave tests**

```ts
test('rapid edits save only the latest generation', async () => {
  const saved: string[] = []
  const timers = createFakeTimers()
  const controller = createAutosaveController<string>({
    delayMs: 800,
    timers,
    save: async value => {
      saved.push(value)
      return { version: saved.length + 1 }
    },
  })
  controller.schedule('a')
  controller.schedule('b')
  controller.schedule('c')
  await timers.advanceBy(800)
  assert.deepEqual(saved, ['c'])
})


test('conflict remains dirty and never overwrites local data', async () => {
  const controller = createAutosaveController({
    delayMs: 1,
    save: async () => {
      throw {
        code: 'SCENARIO_DRAFT_VERSION_CONFLICT',
        details: { actual_version: 4 },
      }
    },
  })
  controller.schedule(sampleDraft)
  await controller.flush()
  assert.equal(controller.state().status, 'conflict')
  assert.equal(controller.state().dirty, true)
  assert.deepEqual(controller.state().pendingValue, sampleDraft)
})
```

- [ ] **Step 3: Run focused frontend tests and observe missing modules**

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/scenarios.test.ts `
  src/composables/maintenance/__tests__/autosave.test.ts `
  src/stores/maintenance/__tests__/scenario-draft.test.ts
```

Expected: FAIL because the typed API, controller, and store do not exist.

- [ ] **Step 4: Implement the typed API**

Define decimal fields as strings and exact server enums. Pass the materialization idempotency key through the existing client config:

```ts
materialize(sessionId, expectedVersion, key) {
  return client.post<ScenarioMaterializeResult>(
    `/v1/demand/scenario-drafts/${encodeURIComponent(sessionId)}/materialize`,
    { expected_version: expectedVersion },
    { headers: { 'Idempotency-Key': key } },
  )
}
```

Do not accept any `tenant_id` parameter.

- [ ] **Step 5: Implement the serialized autosave controller**

The controller must expose:

```ts
type AutosaveStatus =
  | 'idle'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'error'
  | 'conflict'

interface AutosaveController<T> {
  schedule(value: T): void
  flush(): Promise<void>
  retry(): Promise<void>
  reset(): void
  dispose(): void
  state(): AutosaveState<T>
}
```

Only one save may run at a time. If edits arrive during a save, execute one subsequent save with the newest value. `dispose()` invalidates pending timers and generations.

- [ ] **Step 6: Implement the Pinia draft store**

The store loads by session ID, owns version and server evaluation, schedules saves after field edits, exposes `reloadServerDraft`, `retrySave`, `discardLocalChanges`, `materialize`, and `publishVersion`, and rejects responses whose session ID or generation no longer matches. Views expose `publishVersion` only when the server permission payload includes the admin publish capability.

- [ ] **Step 7: Run focused tests and type-check**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/scenarios.test.ts `
  src/composables/maintenance/__tests__/autosave.test.ts `
  src/stores/maintenance/__tests__/scenario-draft.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 8: Commit typed APIs and autosave**

```powershell
git add `
  frontend/src/api/maintenance/scenarios.ts `
  frontend/src/api/maintenance/__tests__/scenarios.test.ts `
  frontend/src/composables/maintenance/useDebouncedAutosave.ts `
  frontend/src/composables/maintenance/__tests__/autosave.test.ts `
  frontend/src/stores/maintenance/scenarioDraft.ts `
  frontend/src/stores/maintenance/__tests__/scenario-draft.test.ts
git commit -m "feat: add scenario draft autosave"
```

---

### Task 5: Build the Six-Step Wizard

**Files:**
- Create: `frontend/src/components/maintenance/scenario/scenario-validation.ts`
- Create: `frontend/src/components/maintenance/scenario/ScenarioStepNavigation.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioFieldShell.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioBasicsStep.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioConfigurationStep.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioMissionStep.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioReliabilityRepairStep.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioCalculationStep.vue`
- Create: `frontend/src/components/maintenance/scenario/ScenarioConfirmationStep.vue`
- Create: `frontend/src/components/maintenance/scenario/__tests__/wizard-validation.test.ts`
- Create: `frontend/src/views/maintenance/scenarios/ScenarioWizard.vue`
- Modify: locale files under `frontend/src/i18n/locales/`

**Interfaces:**
- Consumes: `useScenarioDraftStore`.
- Produces: a six-step editor with server evaluation and local immediate validation.
- Consumed by: Task 6.

- [ ] **Step 1: Write failing pure validation tests**

```ts
test('wizard exposes the exact six ordered steps', () => {
  assert.deepEqual(WIZARD_STEPS.map(step => step.key), [
    'basics',
    'configuration',
    'mission',
    'reliabilityRepair',
    'calculation',
    'confirmation',
  ])
})


test('unconfirmed blocking field prevents materialization', () => {
  const result = evaluateWizard({
    ...completeDraft,
    fields: {
      ...completeDraft.fields,
      service_level: {
        value: '0.95',
        source: 'AI_INFERRED',
        risk: 'BLOCKING',
        confirmed: false,
        evidence_refs: [],
      },
    },
  })
  assert.deepEqual(result.blockingFields, ['service_level'])
  assert.equal(result.canMaterialize, false)
})
```

- [ ] **Step 2: Run the validation tests and observe missing modules**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/scenario/__tests__/wizard-validation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement field and navigation primitives**

`ScenarioFieldShell` accepts:

```ts
interface ScenarioFieldShellProps {
  fieldKey: string
  label: string
  required: boolean
  source: ScenarioSource
  confidence: string | null
  risk: ScenarioRisk
  confirmed: boolean
  evidenceRefs: string[]
  disabled: boolean
}
```

It emits only user intent (`update:value`, `confirm`, `open-evidence`). The parent store remains the state owner.

- [ ] **Step 4: Implement each focused step component**

Each step receives a typed slice and emits field-level patches. Do not duplicate save logic in step components. Use existing master-data APIs for equipment, configurations, spare parts, reliability, and repair selectors.

- [ ] **Step 5: Implement ScenarioWizard orchestration**

The page:

- creates a manual draft when no `session_id` is present;
- loads an AI draft when `session_id` is present;
- renders save status and last-saved time;
- blocks navigation to confirmation when required prior steps are incomplete;
- flushes before route leave;
- displays conflict comparison without overwriting either version;
- calls materialize only when local and server versions match and server blocking fields are empty.

- [ ] **Step 6: Add locale keys in all four existing locale files**

Add identical key structure under `maintenance.scenario` for steps, sources, risks, autosave states, conflicts, materialization, admin publication, empty states, and errors. Use the existing TypeScript locale files, not JSON files.

- [ ] **Step 7: Run component tests, full frontend tests, type-check, and build**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/scenario/__tests__/wizard-validation.test.ts `
  src/composables/maintenance/__tests__/autosave.test.ts `
  src/stores/maintenance/__tests__/scenario-draft.test.ts
npm run test
npm run type-check
npm run build
```

Expected: all tests pass, type-check passes, and Vite build succeeds.

- [ ] **Step 8: Commit the wizard**

```powershell
git add `
  frontend/src/components/maintenance/scenario `
  frontend/src/views/maintenance/scenarios/ScenarioWizard.vue `
  frontend/src/i18n/locales/zh-CN.ts `
  frontend/src/i18n/locales/en-US.ts `
  frontend/src/i18n/locales/ko-KR.ts `
  frontend/src/i18n/locales/ru-RU.ts
git commit -m "feat: add six step scenario wizard"
```

---

### Task 6: Complete Scenario Navigation, Detail, and Admin Publish

**Files:**
- Modify: `frontend/src/views/maintenance/scenarios/ScenarioList.vue`
- Create: `frontend/src/views/maintenance/scenarios/ScenarioDetail.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Create: `frontend/src/views/maintenance/__tests__/scenario-navigation.test.ts`
- Modify: `extensions/maintenance-api/README.md`

**Interfaces:**
- Produces: scenario list, new wizard, version detail, and admin-only publish flow.
- Produces routes: `/scenarios/new`, `/scenarios/:scenarioId`, `/scenarios/:scenarioId/versions/:versionId`.
- Completes: Plan 05-3A.

- [ ] **Step 1: Write failing navigation and capability tests**

```ts
test('scenario detail routes are authenticated and hidden from menu', () => {
  const routes = flattenMaintenanceRoutes(maintenanceRouteRecords)
  for (const name of [
    'maintenanceScenarioNew',
    'maintenanceScenarioDetail',
    'maintenanceScenarioVersionDetail',
  ]) {
    const route = routes.find(item => item.name === name)
    assert.equal(route?.meta?.requiresAuth, true)
    assert.equal(route?.meta?.requiresInit, true)
    assert.equal(route?.meta?.hideInMaintenanceMenu, true)
  }
})


test('contributor materializes but only admin sees publish', () => {
  assert.deepEqual(
    scenarioDraftActions('contributor', 'READY'),
    ['materialize'],
  )
  assert.deepEqual(
    scenarioVersionActions('admin', 'DRAFT'),
    ['publish'],
  )
  assert.deepEqual(
    scenarioVersionActions('contributor', 'DRAFT'),
    [],
  )
})
```

- [ ] **Step 2: Run the tests and observe placeholder pages**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/views/maintenance/__tests__/scenario-navigation.test.ts
```

Expected: FAIL because detail routes and action helpers are absent.

- [ ] **Step 3: Replace ScenarioList placeholder**

Use `useServerTable` with existing `/v1/demand/scenarios` paging. Show code, name, category, current version summary, status, updated time, and role-aware actions. Preserve server ordering and stale-response protection.

- [ ] **Step 4: Add routes and ScenarioDetail**

`ScenarioDetail` loads template, versions, and selected full version. DRAFT versions expose edit for contributor. Publish and retire controls require `confirmHighRisk` and invoke the existing admin endpoints. Published versions are read-only.

- [ ] **Step 5: Document user and operator workflow**

Update `extensions/maintenance-api/README.md` with exact draft endpoints, autosave conflict behavior, AI/manual modes, DRAFT materialization, admin publication, and the rule that only PUBLISHED versions enter Plan 05-3B.

- [ ] **Step 6: Run the complete 05-3A gate**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py `
  tests/integration/test_ai_scenario_wizard_handoff.py `
  tests/services/test_scenario_service.py `
  tests/security/test_api_rbac.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\..\frontend
npm run test
npm run type-check
npm run build

cd ..
go test ./internal/maintenanceproxy ./internal/router
git diff --check
```

Expected: backend scope passes, Ruff is clean, frontend tests/type-check/build pass, Go proxy regression passes, and diff check is clean.

- [ ] **Step 7: Commit 05-3A navigation and evidence**

```powershell
git add `
  frontend/src/views/maintenance/scenarios/ScenarioList.vue `
  frontend/src/views/maintenance/scenarios/ScenarioDetail.vue `
  frontend/src/router/maintenance.ts `
  frontend/src/views/maintenance/__tests__/scenario-navigation.test.ts `
  extensions/maintenance-api/README.md
git commit -m "feat: complete scenario draft workflow"
```

## Phase 05-3A Completion Evidence

Record:

- manual draft creation;
- AI draft navigation payload;
- six-step validation and blocking fields;
- autosave saved/error/conflict states;
- stale response protection;
- contributor materialization to DRAFT;
- contributor publish rejection;
- admin publication to PUBLISHED;
- cross-tenant 404 behavior;
- AI-disabled manual workflow;
- complete backend, frontend, Ruff, Go, build, and diff outputs.

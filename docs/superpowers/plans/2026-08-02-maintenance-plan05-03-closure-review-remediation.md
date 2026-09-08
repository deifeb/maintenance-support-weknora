# Plan 05-3 Closure Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four Plan 05-3 review findings without a schema migration or public route change, then reproduce the complete Plan 05-3 gate.

**Architecture:** `DemandListService` remains the authoritative creation, replay, and audit boundary; it rejects empty comparisons, stores normalized non-recursive receipts, and emits complete item-decision summaries. The Pinia demand-list Store becomes the only owner of logical-command idempotency keys, while the two pages invoke semantic Store actions without constructing keys.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, pytest, Vue 3, Pinia, TypeScript, Node test runner, Vite.

## Global Constraints

- Work only in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05` on `feature/maintenance-frontend-plan05`.
- The remediation baseline is `027de0bf7eda07f845b1555d063603e072ecb7d0` plus the approved documentation commit.
- Do not add a database migration, dependency, public route, tenant selector, or Plan 05-4 behavior.
- Do not merge PR #4, rebase, force-push, reset, stash, or clean the worktree.
- Each production change requires a focused RED test that fails for the expected behavioral reason.
- Preserve exact idempotent replay, tenant isolation, optimistic concurrency, RBAC, Decimal-string handling, and the existing lifecycle state machine.
- Implementation and push are separate approval boundaries.

---

## File Map

| Path | Responsibility |
|---|---|
| `extensions/maintenance-api/app/services/demand_list_service.py` | Empty-result authority check, normalized replay receipts, complete item-update audit summaries |
| `extensions/maintenance-api/tests/services/test_demand_list_service.py` | RED/GREEN service contracts for all three backend findings |
| `frontend/src/stores/maintenance/demandList.ts` | Logical-command fingerprinting, idempotency-key retention and release |
| `frontend/src/stores/maintenance/__tests__/demand-list.test.ts` | Retryable/non-retryable, success, changed-input, and dispose key contracts |
| `frontend/src/views/maintenance/calculations/CalculationComparison.vue` | Call Store create without constructing a key |
| `frontend/src/views/maintenance/calculations/DemandListDetail.vue` | Call Store lifecycle actions without constructing keys |
| `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts` | Static page-to-Store ownership contract |

No other production path is expected.

### Task 1: Reject Empty Comparison Results Before Aggregate Creation

**Files:**
- Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py:2133-2155`

**Interfaces:**
- Consumes: `CalculationComparisonRead.rows` returned by `CalculationGroupService.comparison`.
- Produces: `BusinessValidationError(code="DEMAND_LIST_EMPTY")` before any demand aggregate write.

- [ ] **Step 1: Add the failing no-write service test**

Add beside the Task 2D creation-validation tests:

```python
def test_closure_rejects_empty_comparison_before_aggregate_write(
    session,
    actor_contributor,
    monkeypatch,
) -> None:
    from app.core.exceptions import BusinessValidationError

    service = _demand_list_service()
    group, _, _, _ = _completed_group_with_decisions(
        session,
        actor_contributor,
    )
    comparison = service.calculation_group_service.comparison(
        session,
        actor_contributor,
        group.id,
    )
    empty_comparison = comparison.model_copy(
        update={"rows": []},
    )
    monkeypatch.setattr(
        service.calculation_group_service,
        "comparison",
        lambda *_args, **_kwargs: empty_comparison,
    )

    with pytest.raises(BusinessValidationError) as captured:
        service.create_from_group(
            session,
            actor_contributor,
            calculation_group_id=group.id,
            name="Empty comparison must fail",
            description=None,
            idempotency_key="closure-empty-comparison",
        )

    assert captured.value.code == "DEMAND_LIST_EMPTY"
    _task2d_assert_no_demand_aggregate(session)
```

- [ ] **Step 2: Run the exact test and verify RED**

Run from `extensions/maintenance-api`:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py::test_closure_rejects_empty_comparison_before_aggregate_write `
  -v
```

Expected: FAIL because the current implementation creates an empty DRAFT instead of raising `DEMAND_LIST_EMPTY`.

- [ ] **Step 3: Add the authoritative guard**

Immediately after `comparison(...)` returns and before `incomplete = sorted(...)`, add:

```python
            if not comparison.rows:
                raise BusinessValidationError(
                    "demand list cannot be empty",
                    code="DEMAND_LIST_EMPTY",
                )
```

- [ ] **Step 4: Run Task 1 GREEN and the adjacent creation tests**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py `
  -k 'closure_rejects_empty_comparison or task2d or task2e' `
  -v
```

Expected: selected tests PASS with no skipped or xfailed test.

- [ ] **Step 5: Commit the independently reviewable fix**

```powershell
git add -- `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git diff --cached --check
git commit -m "fix(maintenance): reject empty demand list creation"
```

Expected: one commit containing only the two Task 1 paths.

### Task 2: Store Non-Recursive Exact-Replay Snapshots

**Files:**
- Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py:438-460, 875-894, 2490-2507`

**Interfaces:**
- Consumes: a fully materialized `DemandListRead`.
- Produces: a deep-copied `DemandListRead` whose `events[*].response_snapshot_json` values are all `None`; the same object shape is stored and returned.

- [ ] **Step 1: Add the failing normalized-receipt regression**

Add after the existing Task 3G exact-replay tests:

```python
def test_closure_lifecycle_receipts_are_non_recursive_and_exact(
    session,
    actor_contributor,
    actor_admin,
) -> None:
    from app.models import DemandListEvent
    from app.schemas.demand_list import DemandListRead

    service, confirmed = _task3_confirmed_list(
        session,
        actor_contributor,
        actor_admin,
        source_key="closure-normalized-source",
        submit_key="closure-normalized-submit",
        confirm_key="closure-normalized-confirm",
    )
    key = "closure-normalized-publish"

    first = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=key,
    )
    receipt = session.query(DemandListEvent).filter(
        DemandListEvent.tenant_id == actor_admin.tenant_id,
        DemandListEvent.idempotency_key == key,
    ).one()
    stored = DemandListRead.model_validate(
        receipt.response_snapshot_json,
    )
    replay = service.publish(
        session,
        actor_admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key=key,
    )

    assert all(
        event.response_snapshot_json is None
        for event in stored.events
    )
    assert first.model_dump(mode="json") == (
        stored.model_dump(mode="json")
    )
    assert replay.model_dump(mode="json") == (
        first.model_dump(mode="json")
    )
```

- [ ] **Step 2: Run the exact test and verify RED**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py::test_closure_lifecycle_receipts_are_non_recursive_and_exact `
  -v
```

Expected: FAIL because at least one earlier event inside the stored response still contains a response snapshot.

- [ ] **Step 3: Add one normalization helper**

Place beside `_read_model`:

```python
    @staticmethod
    def _normalized_replay_snapshot(
        response: DemandListRead,
    ) -> DemandListRead:
        normalized = response.model_copy(deep=True)
        for event in normalized.events:
            event.response_snapshot_json = None
        return normalized
```

- [ ] **Step 4: Normalize lifecycle command storage and first response**

Replace the response body inside `_response_with_event_snapshot` with:

```python
        response = self._normalized_replay_snapshot(
            self._read_model(loaded)
        )
        event.response_snapshot_json = (
            response.model_dump(mode="json")
        )
        session.flush()
        return response
```

- [ ] **Step 5: Normalize create storage and first response**

Replace the create response block with:

```python
            response = self._normalized_replay_snapshot(
                self._read_model(loaded)
            )
            event.response_snapshot_json = (
                response.model_dump(mode="json")
            )
            session.flush()
            session.commit()
            return response
```

- [ ] **Step 6: Run replay GREEN and all exact-replay/race contracts**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py `
  -k 'closure_lifecycle_receipts or replay or task3g' `
  -v
```

Expected: all selected tests PASS; first response, stored receipt, sequential replay, and race recovery remain equal.

- [ ] **Step 7: Commit the independently reviewable fix**

```powershell
git add -- `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git diff --cached --check
git commit -m "fix(maintenance): normalize demand list replay snapshots"
```

### Task 3: Preserve Complete ITEM_UPDATED Decision History

**Files:**
- Modify: `extensions/maintenance-api/tests/services/test_demand_list_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py:1050-1233`

**Interfaces:**
- Consumes: mutable fields on `DemandListItem` before and after risk re-evaluation.
- Produces: stable before/after dictionaries containing all mutable decision state.

- [ ] **Step 1: Add the failing consecutive-update audit test**

Add beside `test_task2g_event_uses_decimal_strings_and_preserves_origin`:

```python
def test_closure_item_update_preserves_complete_decision_history(
    session,
    actor_contributor,
) -> None:
    service, created = _task2g_create_draft(
        session,
        actor_contributor,
        key="closure-item-audit",
    )
    target = created.items[0]
    expected_keys = {
        "item_id",
        "original_quantity",
        "final_quantity",
        "decision_reason",
        "decision_type",
        "decision_risk",
        "requires_admin_confirmation",
        "confirmed_by_admin",
        "risk_rule_version",
        "version",
    }

    first = service.update_item(
        session,
        actor_contributor,
        created.id,
        target.id,
        expected_version=created.version,
        final_quantity=Decimal("9"),
        adjustment_reason="First reviewed adjustment",
    )
    first_item = next(
        item for item in first.items if item.id == target.id
    )
    second = service.update_item(
        session,
        actor_contributor,
        first.id,
        target.id,
        expected_version=first.version,
        final_quantity=Decimal("7"),
        adjustment_reason="Second reviewed adjustment",
    )
    events = [
        event
        for event in second.events
        if event.event_type.value == "ITEM_UPDATED"
    ]

    assert len(events) == 2
    assert set(events[0].before_summary_json) == expected_keys
    assert set(events[0].after_summary_json) == expected_keys
    assert events[0].after_summary_json == (
        events[1].before_summary_json
    )
    assert events[0].after_summary_json["decision_reason"] == (
        "First reviewed adjustment"
    )
    assert events[1].after_summary_json["decision_reason"] == (
        "Second reviewed adjustment"
    )
    assert events[1].after_summary_json["final_quantity"] == (
        "7.000000"
    )
    assert events[0].after_summary_json["decision_type"] == (
        first_item.decision_type.value
        if first_item.decision_type is not None
        else None
    )
    assert events[0].after_summary_json["decision_risk"] == (
        first_item.decision_risk
    )
    assert events[0].after_summary_json[
        "requires_admin_confirmation"
    ] is first_item.requires_admin_confirmation
    assert events[0].after_summary_json[
        "confirmed_by_admin"
    ] is first_item.confirmed_by_admin
    assert events[0].after_summary_json[
        "risk_rule_version"
    ] == first_item.risk_rule_version
```

- [ ] **Step 2: Run the exact test and verify RED**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py `
  -k 'closure_item_update_preserves_complete_decision_history' `
  -v
```

Expected: FAIL because the current summaries expose only `item_id`, `final_quantity`, and `version`.

- [ ] **Step 3: Add the complete summary helper**

Place beside `_item_counts`:

```python
    @staticmethod
    def _item_decision_summary(
        item: DemandListItem,
    ) -> dict[str, Any]:
        return {
            "item_id": item.id,
            "original_quantity": _decimal_string(
                item.original_quantity
            ),
            "final_quantity": _decimal_string(
                item.final_quantity
            ),
            "decision_reason": item.decision_reason,
            "decision_type": _enum_value(
                item.decision_type
            ),
            "decision_risk": item.decision_risk,
            "requires_admin_confirmation": (
                item.requires_admin_confirmation
            ),
            "confirmed_by_admin": (
                item.confirmed_by_admin
            ),
            "risk_rule_version": (
                item.risk_rule_version
            ),
            "version": item.version,
        }
```

- [ ] **Step 4: Capture before and after around the mutation**

Immediately before changing `item.final_quantity`, capture:

```python
            before_summary = self._item_decision_summary(
                item
            )
```

After `item.version += 1`, replace the inline event dictionaries with:

```python
                before_summary=before_summary,
                after_summary=(
                    self._item_decision_summary(item)
                ),
```

Remove the now-unused `previous_quantity` and `previous_item_version` locals.

- [ ] **Step 5: Run Task 3 GREEN and item/lifecycle audit regressions**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py `
  -k 'item_update or item_updated or task3h' `
  -v
```

Expected: all selected tests PASS. In `test_task2g_event_uses_decimal_strings_and_preserves_origin`, replace its two three-field equality assertions with `set(summary) == expected_keys`, exact quantity/version assertions, and exact `decision_reason == "Event evidence"`; retain every actor, request, and immutable `decision_snapshot_json` assertion.

- [ ] **Step 6: Commit the independently reviewable fix**

```powershell
git add -- `
  extensions/maintenance-api/app/services/demand_list_service.py `
  extensions/maintenance-api/tests/services/test_demand_list_service.py
git diff --cached --check
git commit -m "fix(maintenance): preserve demand item decision audit history"
```

### Task 4: Retain Idempotency Keys for Retryable Frontend Commands

**Files:**
- Modify: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`
- Modify: `frontend/src/stores/maintenance/demandList.ts`
- Modify: `frontend/src/views/maintenance/calculations/CalculationComparison.vue`
- Modify: `frontend/src/views/maintenance/calculations/DemandListDetail.vue`
- Modify: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`

**Interfaces:**
- Consumes: `MaintenanceClientError.retryable`, normalized command inputs, current aggregate id/version.
- Produces: semantic Store methods with no public key argument and stable API keys across uncertain retries.

- [ ] **Step 1: Add deterministic retryable create and submit RED tests**

Add a deterministic key factory and a retryable error fixture:

```ts
function keyFactory(...keys: string[]): () => string {
  let index = 0
  return () => keys[index++] ?? `unexpected-key-${index}`
}

const retryableFailure = {
  status: 503,
  error: {
    code: 'SERVICE_UNAVAILABLE',
    message: 'Response outcome is unknown',
    details: { retryable: true },
  },
  meta: { request_id: 'retryable-request' },
}
```

Add these contracts. The calls with a second factory dependency intentionally do not compile until the expected RED is observed:

```ts
test('retryable create failure reuses the same logical-command key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      create: async (_request, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({ id: 51 }))
      },
    }),
    keyFactory('create-key-1', 'create-key-2'),
  )
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Created list',
    description: null,
  }

  await assert.rejects(() => state.create(request))
  await state.create(request)
  await state.create({ ...request, name: 'Another list' })

  assert.deepEqual(captured, [
    'create-key-1',
    'create-key-1',
    'create-key-2',
  ])
})

test('retryable submit failure reuses the same current-version key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      submit: async (_id, _version, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({
          status: 'PENDING_CONFIRMATION',
          version: 8,
        }))
      },
    }),
    keyFactory('submit-key-1', 'submit-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.submit())
  await state.submit()

  assert.deepEqual(captured, [
    'submit-key-1',
    'submit-key-1',
  ])
})
```

- [ ] **Step 2: Add RED contracts for release conditions and all action wiring**

Add the non-retryable release test:

```ts
test('non-retryable failure releases the logical-command key', async () => {
  const captured: string[] = []
  let calls = 0
  const conflict = {
    status: 409,
    error: {
      code: 'DEMAND_LIST_VERSION_CONFLICT',
      message: 'Demand list version conflict',
      details: { retryable: false },
    },
    meta: { request_id: 'conflict-request' },
  }
  const state = createDemandListState(
    apiStub({
      submit: async (_id, _version, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw conflict
        return result(demandList({
          status: 'PENDING_CONFIRMATION',
          version: 8,
        }))
      },
    }),
    keyFactory('submit-key-1', 'submit-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.submit())
  await state.submit()

  assert.deepEqual(captured, [
    'submit-key-1',
    'submit-key-2',
  ])
})
```

Add the dispose release test:

```ts
test('dispose abandons a retryable pending command key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      create: async (_request, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({ id: 52 }))
      },
    }),
    keyFactory('create-key-1', 'create-key-2'),
  )
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Disposable create',
    description: null,
  }

  await assert.rejects(() => state.create(request))
  state.dispose()
  await state.create(request)

  assert.deepEqual(captured, [
    'create-key-1',
    'create-key-2',
  ])
})
```

Add the changed confirmation-note fingerprint test:

```ts
test('a changed confirmation note starts a new logical command', async () => {
  const captured: string[] = []
  const state = createDemandListState(
    apiStub({
      get: async () => result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 8,
      })),
      confirm: async (_id, _version, _note, key) => {
        captured.push(key)
        throw retryableFailure
      },
    }),
    keyFactory('confirm-key-1', 'confirm-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.confirm('First note'))
  await assert.rejects(() => state.confirm('Second note'))

  assert.deepEqual(captured, [
    'confirm-key-1',
    'confirm-key-2',
  ])
})
```

Add one wiring test for the remaining actions:

```ts
test('publish derive and void use action-owned command keys', async () => {
  const captured: Array<[string, string]> = []
  const state = createDemandListState(
    apiStub({
      publish: async (_id, _version, key) => {
        captured.push(['publish', key])
        return result(demandList({
          status: 'PUBLISHED',
          version: 8,
        }))
      },
      derive: async (_id, _version, key) => {
        captured.push(['derive', key])
        return result(demandList({ id: 42, version: 1 }))
      },
      void: async (_id, _version, key) => {
        captured.push(['void', key])
        return result(demandList({
          id: 42,
          status: 'VOIDED',
          version: 2,
        }))
      },
    }),
    (action) => `${action}-owned-key`,
  )

  await state.load(41)
  await state.publish()
  await state.derive()
  await state.voidList()

  assert.deepEqual(captured, [
    ['publish', 'publish-owned-key'],
    ['derive', 'derive-owned-key'],
    ['void', 'void-owned-key'],
  ])
})
```

Expected RED reasons are missing Store key ownership and current public key parameters.

- [ ] **Step 3: Run frontend Store tests and verify RED**

From `frontend`:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/stores/maintenance/__tests__/demand-list.test.ts
```

Expected: compilation/test failure because Store methods still require caller-supplied keys and no retained-command state exists.

- [ ] **Step 4: Add command types, fingerprinting, and the injected key factory**

Add to `demandList.ts`:

```ts
type DemandListCommandAction =
  | 'create'
  | 'submit'
  | 'confirm'
  | 'publish'
  | 'derive'
  | 'void'

interface PendingDemandListCommand {
  fingerprint: string
  idempotencyKey: string
}

function defaultCommandKey(
  action: DemandListCommandAction,
): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `demand-list:${action}:${suffix}`
}
```

Change the factory signature and initialize the command map:

```ts
export function createDemandListState(
  api: DemandListStoreApi = demandListApi,
  commandKeyFactory: (
    action: DemandListCommandAction,
  ) => string = defaultCommandKey,
) {
  const pendingCommands = new Map<
    DemandListCommandAction,
    PendingDemandListCommand
  >()
```

- [ ] **Step 5: Add one shared idempotent mutation wrapper**

Add below `runMutation`:

```ts
  function acquireCommandKey(
    action: DemandListCommandAction,
    fingerprint: string,
  ): string {
    const pending = pendingCommands.get(action)
    if (pending?.fingerprint === fingerprint) {
      return pending.idempotencyKey
    }
    const idempotencyKey = commandKeyFactory(action)
    pendingCommands.set(action, {
      fingerprint,
      idempotencyKey,
    })
    return idempotencyKey
  }

  function releaseCommandKey(
    action: DemandListCommandAction,
    idempotencyKey: string,
  ): void {
    if (
      pendingCommands.get(action)?.idempotencyKey
      === idempotencyKey
    ) {
      pendingCommands.delete(action)
    }
  }

  async function runIdempotentMutation(
    action: DemandListCommandAction,
    fingerprint: string,
    operation: (
      idempotencyKey: string,
    ) => Promise<MaintenanceResult<DemandList>>,
    options: {
      sourceId: number | null
      allowResultIdChange: boolean
    },
  ): Promise<DemandList> {
    const idempotencyKey = acquireCommandKey(
      action,
      fingerprint,
    )
    try {
      const response = await runMutation(
        () => operation(idempotencyKey),
        options,
      )
      releaseCommandKey(action, idempotencyKey)
      return response
    } catch (value) {
      if (!normalizeMaintenanceError(value).retryable) {
        releaseCommandKey(action, idempotencyKey)
      }
      throw value
    }
  }
```

- [ ] **Step 6: Route all six semantic commands through the wrapper**

Replace the six idempotent Store methods with the complete semantic methods below:

```ts
  function create(
    request: DemandListCreateRequest,
  ): Promise<DemandList> {
    const normalizedRequest = {
      ...request,
      name: request.name.trim(),
      description: request.description?.trim() || null,
    }
    const fingerprint = JSON.stringify([
      normalizedRequest.calculation_group_id,
      normalizedRequest.name,
      normalizedRequest.description,
    ])
    return runIdempotentMutation(
      'create',
      fingerprint,
      (key) => api.create(normalizedRequest, key),
      { sourceId: null, allowResultIdChange: true },
    )
  }

  function submit(): Promise<DemandList> {
    const source = requireCurrent()
    return runIdempotentMutation(
      'submit',
      JSON.stringify([source.id, source.version]),
      (key) => api.submit(
        source.id,
        source.version,
        key,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function confirm(
    confirmationNote: string,
  ): Promise<DemandList> {
    const source = requireCurrent()
    return runIdempotentMutation(
      'confirm',
      JSON.stringify([
        source.id,
        source.version,
        confirmationNote,
      ]),
      (key) => api.confirm(
        source.id,
        source.version,
        confirmationNote,
        key,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function publish(): Promise<DemandList> {
    const source = requireCurrent()
    return runIdempotentMutation(
      'publish',
      JSON.stringify([source.id, source.version]),
      (key) => api.publish(
        source.id,
        source.version,
        key,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function derive(): Promise<DemandList> {
    const source = requireCurrent()
    return runIdempotentMutation(
      'derive',
      JSON.stringify([source.id, source.version]),
      (key) => api.derive(
        source.id,
        source.version,
        key,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: true,
      },
    )
  }

  function voidList(): Promise<DemandList> {
    const source = requireCurrent()
    return runIdempotentMutation(
      'void',
      JSON.stringify([source.id, source.version]),
      (key) => api.void(
        source.id,
        source.version,
        key,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function dispose(): void {
    requestGeneration += 1
    pendingCommands.clear()
  }
```

- [ ] **Step 7: Remove page-owned key generation**

In `CalculationComparison.vue`, delete `requestKey()` and call:

```ts
    const created = await demandListStore.create({
      calculation_group_id: groupId,
      name,
      description: description || null,
    })
```

In `DemandListDetail.vue`, delete `requestKey()` and use:

```ts
await store.submit()
await store.publish()
const derived = await store.derive()
await store.voidList()
await store.confirm(note)
```

Do not change dialog, routing, capability, or error-presentation behavior.

- [ ] **Step 8: Update static navigation ownership assertions**

Replace the confirmation assertion with:

```ts
assert.match(
  detail,
  /store\.confirm\(\s*note\s*\)/s,
)
```

Add:

```ts
assert.doesNotMatch(comparison, /function requestKey/)
assert.doesNotMatch(detail, /function requestKey/)
assert.doesNotMatch(detail, /requestKey\(/)
```

In the pre-existing Store tests, make these mechanical signature updates: `state.create(request, 'create-key')` becomes `state.create(request)`; `state.submit('submit-key')` becomes `state.submit()`; `state.confirm(note, 'confirm-key')` becomes `state.confirm(note)`; and publish, derive, and void calls lose their literal key argument. Where an existing assertion checks the forwarded key, pass `() => 'expected-key'` as the second `createDemandListState` dependency and keep the exact key assertion.

- [ ] **Step 9: Run focused frontend GREEN**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: all selected tests PASS with no skipped or deferred test case.

- [ ] **Step 10: Run TypeScript and production-build validation**

```powershell
npm run type-check
npm run build
```

Expected: both commands exit 0. The existing chunk-size warning is non-blocking.

- [ ] **Step 11: Commit the independently reviewable frontend fix**

From the repository root:

```powershell
git add -- `
  frontend/src/stores/maintenance/demandList.ts `
  frontend/src/stores/maintenance/__tests__/demand-list.test.ts `
  frontend/src/views/maintenance/calculations/CalculationComparison.vue `
  frontend/src/views/maintenance/calculations/DemandListDetail.vue `
  frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
git diff --cached --check
git commit -m "fix(frontend): retain demand list command keys on retry"
```

### Task 5: Reproduce Plan 05-3 Gate and Perform Closure Review

**Files:**
- Verify: the seven approved remediation paths.
- Do not modify: production or test files during this task.

**Interfaces:**
- Consumes: Tasks 1-4 commits.
- Produces: complete local evidence and a new closure-review decision for PR #4.

- [ ] **Step 1: Verify branch, commit chain, clean tree, and exact scope**

```powershell
git branch --show-current
git status --short --branch
git log -6 --oneline --decorate
git diff --check HEAD~4 HEAD
git diff --name-only HEAD~4 HEAD
```

Expected remediation feature paths:

```text
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/views/maintenance/calculations/DemandListDetail.vue
frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

The tree and index must be clean. Documentation files are outside this four-feature-commit comparison because they precede implementation approval.

- [ ] **Step 2: Run the complete demand-list service and API suites**

From `extensions/maintenance-api`:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/services/test_demand_list_service.py `
  tests/api/test_demand_lists.py `
  -v
```

Expected: all tests PASS with no skipped or xfailed test.

- [ ] **Step 3: Run the complete Plan 05-3 backend gate**

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' `
  -m pytest `
  tests/api/test_scenario_draft_api.py `
  tests/api/test_calculation_groups.py `
  tests/api/test_demand_lists.py `
  tests/integration/test_plan05_scenario_calculation.py `
  -v
```

Expected: all selected tests PASS.

- [ ] **Step 4: Run complete frontend verification**

From `frontend`:

```powershell
npm run test
npm run type-check
npm run build
```

Expected: full tests, type-check, and build exit 0. Record the exact passing test count and build duration; the chunk-size warning remains non-blocking.

- [ ] **Step 5: Run targeted static closure checks**

From the repository root:

```powershell
$service = Get-Content -Raw -Encoding UTF8 `
  'extensions/maintenance-api/app/services/demand_list_service.py'
$store = Get-Content -Raw -Encoding UTF8 `
  'frontend/src/stores/maintenance/demandList.ts'
$comparison = Get-Content -Raw -Encoding UTF8 `
  'frontend/src/views/maintenance/calculations/CalculationComparison.vue'
$detail = Get-Content -Raw -Encoding UTF8 `
  'frontend/src/views/maintenance/calculations/DemandListDetail.vue'

foreach ($marker in @(
  '_normalized_replay_snapshot',
  '_item_decision_summary',
  'code="DEMAND_LIST_EMPTY"'
)) {
  if (-not $service.Contains($marker)) {
    throw "Missing backend closure marker: $marker"
  }
}
foreach ($marker in @(
  'runIdempotentMutation',
  'pendingCommands.clear()',
  'normalizeMaintenanceError(value).retryable'
)) {
  if (-not $store.Contains($marker)) {
    throw "Missing Store closure marker: $marker"
  }
}
if ($comparison.Contains('function requestKey')) {
  throw 'Comparison still owns idempotency keys'
}
if ($detail.Contains('function requestKey')) {
  throw 'Detail still owns idempotency keys'
}
```

Expected: command exits without error.

- [ ] **Step 6: Perform a fresh closure code review**

Review the exact remediation range against the four findings. Confirm:

```text
same logical command retains one key after uncertain failure
all six idempotent frontend commands use the shared Store path
stored snapshots terminate recursion at nested event snapshots
first response and every replay remain exact
ITEM_UPDATED before/after captures every mutable decision field
empty comparison fails before list/item/event writes
no migration, route expansion, RBAC regression, or Plan 05-4 scope
```

Any new Important or Moderate finding returns to the relevant task with a new RED regression before code changes.

- [ ] **Step 7: Verify repository terminal state**

```powershell
git diff --check
git status --short --branch
git rev-list --left-right --count `
  'origin/feature/maintenance-frontend-plan05...HEAD'
```

Expected before push approval: clean tree, empty index, and only the approved local documentation/remediation commits ahead of origin.

- [ ] **Step 8: Stop at the push and PR-update boundary**

Do not push or update PR #4 automatically. Request the separate approval phrase:

```text
批准推送 Plan 05-3 Closure Review Remediation 并更新 PR #4
```

After a strict fast-forward push, attach complete Gate evidence and the closure-review result to PR #4. Merge and Plan 05-4 remain separate decisions.

## Plan Self-Review

- Spec coverage: each of the four closure findings maps to one independently testable task and the final Gate.
- Placeholder scan: every production change has an exact path, contract, command, expected result, and commit boundary.
- Type consistency: Store actions, command names, backend error code, summary keys, and `DemandListRead` usage are consistent across tasks.
- Scope consistency: the plan requires exactly seven remediation feature paths and no migration or Plan 05-4 work.
- TDD consistency: every task begins with an executable RED contract and forbids production changes before the expected failure is observed.
- Approval consistency: this document authorizes planning only; TDD implementation and push each require separate approval.

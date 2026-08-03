# Plan 05-3C Task 5 Typed Demand List Client, Permissions, and Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the typed, capability-driven, concurrency-safe frontend foundation for the Task 4 demand-list lifecycle API without adding routes, views, Vue components, or backend behavior.

**Architecture:** Mirror the verified backend demand-list schemas and nine HTTP routes in one typed API module, extend the existing fail-closed maintenance capability matrix with two demand-list capabilities, derive lifecycle actions through a pure status/capability resolver, and manage one currently viewed aggregate through a Pinia-compatible state factory. Reads use a generation token so stale route responses cannot overwrite newer state; all writes share one mutation gate and always use the latest server aggregate version.

**Tech Stack:** Vue 3.5, TypeScript 6, Pinia 3, Node 22 `node:test` through `tsx --test`, Vue TSC 3, Vite 7, the existing maintenance request client, and PowerShell 5.1 execution wrappers.

## Global Constraints

- Repository: `https://github.com/deifeb/maintenance-support-weknora`.
- Worktree: `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Branch: `feature/maintenance-frontend-plan05`.
- Baseline commit: `1edf45cdd8b092148f544f41c36f094b1e14c91c`.
- Draft PR: `https://github.com/deifeb/maintenance-support-weknora/pull/4`.
- Follow the approved design `docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md`.
- The approved design artifact SHA256 is `ff785d26e100f3420cbe7d2affd5a53705a381350fd74954bf86c3a097d43c82`.
- Task 5 is frontend-only.
- Create exactly six production/test files and modify exactly two existing files.
- Do not modify `frontend/src/router/**`, `frontend/src/views/**`, `frontend/src/i18n/**`, or any `.vue` file.
- Do not modify `extensions/maintenance-api/**`, `internal/**`, migrations, backend schemas, or backend routes.
- Do not add a tenant selector to a path, query, body, header, type, store, or component contract.
- Decimal quantities remain strings from HTTP response through state and outgoing request.
- Confirmation sends `confirmation_note`; the obsolete field `note` is forbidden.
- Create, submit, confirm, publish, derive, and void send `Idempotency-Key`.
- Viewer is read-only.
- Contributor may edit DRAFT items and submit DRAFT lists.
- Admin and owner may also confirm, publish, derive, and void.
- The lifecycle resolver consumes capabilities, never raw role names.
- Item editing is allowed only for `DRAFT`.
- One shared mutation gate covers update, submit, confirm, publish, derive, and void.
- Every existing-list mutation uses `current.version` from the latest successful server aggregate.
- Stale reads and stale mutations cannot overwrite a newer route context.
- Errors use `normalizeMaintenanceError`; parsing error message text is forbidden.
- Every implementation stage is TDD-first.
- The approved commit structure is one documentation commit followed by one feature commit.
- Do not stage or commit feature files until final regression evidence is reviewed and explicit commit approval is given.
- Do not push without a separate explicit push approval.
- Do not use `git reset`, `git stash`, `git clean`, force push, rebase, or unrelated refactoring.

---

## File Map

### Documentation create

```text
docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md
docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store.md
```

### Feature create

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

### Feature modify

```text
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

### Forbidden feature paths

```text
frontend/src/router/**
frontend/src/views/**
frontend/src/i18n/**
frontend/src/components/**/*.vue
extensions/maintenance-api/**
internal/**
```

---

## Stable Interfaces Produced by Task 5

### Typed API factory

```ts
createDemandListApi(
  client?: DemandListApiClient,
): {
  create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  list(
    query?: DemandListListQuery,
  ): Promise<MaintenanceResult<PageData<DemandListSummary>>>
  get(
    demandListId: number,
  ): Promise<MaintenanceResult<DemandList>>
  updateItem(
    demandListId: number,
    itemId: number,
    request: DemandListItemUpdateRequest,
  ): Promise<MaintenanceResult<DemandList>>
  submit(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  confirm(
    demandListId: number,
    expectedVersion: number,
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  publish(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  derive(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  void(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
}
```

### Capability matrix additions

```ts
editDemandList: boolean
publishDemandList: boolean
```

### Pure lifecycle interfaces

```ts
demandListActions(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): DemandListAction[]

canEditDemandListItem(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): boolean
```

### Store factory

```ts
createDemandListState(
  api?: DemandListStoreApi,
): {
  current: Ref<DemandList | null>
  loading: Ref<boolean>
  mutating: Ref<boolean>
  error: Ref<MaintenanceClientError | null>
  create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<DemandList>
  load(demandListId: number): Promise<DemandList>
  updateItem(
    itemId: number,
    finalQuantity: DecimalString,
    adjustmentReason: string,
  ): Promise<DemandList>
  submit(idempotencyKey: string): Promise<DemandList>
  confirm(
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<DemandList>
  publish(idempotencyKey: string): Promise<DemandList>
  derive(idempotencyKey: string): Promise<DemandList>
  voidList(idempotencyKey: string): Promise<DemandList>
  dispose(): void
}
```

---

### Task 0: Land the Approved Design and Implementation Plan

**Files:**
- Create: `docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md`
- Create: `docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store.md`

**Interfaces:**
- Consumes: approved design artifact SHA256 `ff785d26e100f3420cbe7d2affd5a53705a381350fd74954bf86c3a097d43c82`.
- Produces: the authoritative Task 5 spec and executable implementation plan.
- Consumed by: Tasks 1–5.

- [ ] **Step 1: Verify the implementation baseline**

Run from the worktree root:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
git rev-list `
  --left-right `
  --count `
  refs/remotes/origin/feature/maintenance-frontend-plan05...HEAD
```

Expected:

```text
branch = feature/maintenance-frontend-plan05
HEAD = 1edf45cdd8b092148f544f41c36f094b1e14c91c
working tree = clean
index = empty
behind = 0
ahead = 0
```

Stop without writing files if any value differs.

- [ ] **Step 2: Create the approved design file byte-for-byte**

Create:

```text
docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md
```

The file must match the approved design artifact. Verify:

```powershell
(
    Get-FileHash `
        -LiteralPath `
        docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md `
        -Algorithm SHA256
).Hash.ToLowerInvariant()
```

Expected:

```text
ff785d26e100f3420cbe7d2affd5a53705a381350fd74954bf86c3a097d43c82
```

- [ ] **Step 3: Create this implementation plan**

Create:

```text
docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store.md
```

The repository file must be byte-for-byte identical to the approved plan artifact supplied with this plan review.

- [ ] **Step 4: Run documentation scope and whitespace gates**

```powershell
git status --short
git diff --check
git diff --name-only
git diff --cached --name-only
```

Expected:

```text
exactly two untracked documentation files
no tracked changes
no staged files
no whitespace error
```

- [ ] **Step 5: Commit only the two documentation files**

This commit is executed only after the user approves this written plan.

```powershell
git add -- `
  docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md `
  docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store.md

git diff --cached --check
git diff --cached --name-only

git commit -m "docs: plan plan05 demand list lifecycle client"
```

Expected committed paths:

```text
docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store-design.md
docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task5-demand-list-client-store.md
```

- [ ] **Step 6: Verify the documentation commit**

```powershell
git show --stat --oneline HEAD
git diff-tree --no-commit-id --name-only -r HEAD
git status --short
git diff --cached --name-only
```

Expected:

```text
subject = docs: plan plan05 demand list lifecycle client
parent = 1edf45cdd8b092148f544f41c36f094b1e14c91c
exactly two committed documentation paths
working tree clean
index empty
push not performed
```

---

### Task 1: Establish the Task 5 RED Contracts

**Files:**
- Create: `frontend/src/api/maintenance/__tests__/demand-lists.test.ts`
- Create: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`
- Create: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`

**Interfaces:**
- Consumes: existing `MaintenanceResult<T>`, permission-matrix behavior, and Task 4 backend contract.
- Produces: failing executable contracts for the API, capabilities, resolver, and store.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Add the permission RED expectations**

Extend every exact `MaintenancePermissions` fixture in:

```text
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

Add to `denied` and `viewer`:

```ts
editDemandList: false,
publishDemandList: false,
```

Add to `contributor`:

```ts
editDemandList: true,
publishDemandList: false,
```

Add to `admin`:

```ts
editDemandList: true,
publishDemandList: true,
```

Add this fail-closed hierarchy test:

```ts
test('auth hierarchy removes demand-list admin authority', () => {
  const contributorOnly = (
    minimum: TenantRole,
  ): boolean => (
    minimum === 'viewer'
    || minimum === 'contributor'
  )

  assert.deepEqual(
    permissionsForAuth('admin', contributorOnly),
    contributor,
  )
})
```

Do not modify `permission-matrix.ts` yet.

- [ ] **Step 2: Run the permission RED gate**

```powershell
cd frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: FAIL because the production permission objects do not contain `editDemandList` or `publishDemandList`.

Record:

```text
test command
exit code
failing assertion names
working-tree status
```

- [ ] **Step 3: Create the API RED test file**

Create:

```text
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
```

Use these shared helpers:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createDemandListApi,
  type DemandListCreateRequest,
} from '../demand-lists.ts'
import type {
  MaintenanceResult,
  PageData,
} from '../types.ts'

interface CapturedCall {
  method: string
  path: string
  body?: unknown
  config?: unknown
}

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
      version: 7,
    },
  }
}

function fakeClient(calls: CapturedCall[]) {
  return {
    async get<T>(
      path: string,
    ): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result({} as T)
    },

    async post<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'POST',
        path,
        body,
        config,
      })
      return result({} as T)
    },

    async put<T>(
      path: string,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'PUT',
        path,
        body,
      })
      return result({} as T)
    },
  }
}

function headersOf(
  call: CapturedCall | undefined,
): Record<string, string> {
  return (
    call?.config as {
      headers: Record<string, string>
    }
  ).headers
}
```

Add exact-path and body tests:

```ts
test('demand-list client uses exact create/list/get/update routes', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Readiness demand',
    description: 'Task 5 contract',
  }

  await api.create(request, 'create-list-key')
  await api.list({
    page: 2,
    page_size: 50,
    status: 'PUBLISHED',
    lineage_id: '11111111-2222-3333-4444-555555555555',
  })
  await api.get(41)
  await api.updateItem(41, 501, {
    expected_version: 7,
    final_quantity: '9007199254740993.125000',
    adjustment_reason: 'Approved exact quantity',
  })

  assert.deepEqual(calls[0], {
    method: 'POST',
    path: '/v1/demand/demand-lists',
    body: request,
    config: {
      headers: {
        'Idempotency-Key': 'create-list-key',
      },
    },
  })
  assert.equal(
    calls[1]?.path,
    (
      '/v1/demand/demand-lists'
      + '?page=2&page_size=50&status=PUBLISHED'
      + '&lineage_id=11111111-2222-3333-4444-555555555555'
    ),
  )
  assert.equal(
    calls[2]?.path,
    '/v1/demand/demand-lists/41',
  )
  assert.deepEqual(calls[3], {
    method: 'PUT',
    path: '/v1/demand/demand-lists/41/items/501',
    body: {
      expected_version: 7,
      final_quantity: '9007199254740993.125000',
      adjustment_reason: 'Approved exact quantity',
    },
  })
})
```

Add lifecycle tests:

```ts
test('lifecycle routes send versions, confirmation_note, and keys', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))

  await api.submit(41, 7, 'submit-key')
  await api.confirm(
    41,
    8,
    'Approved by administrator',
    'confirm-key',
  )
  await api.publish(41, 9, 'publish-key')
  await api.derive(41, 10, 'derive-key')
  await api.void(41, 11, 'void-key')

  assert.deepEqual(calls.map((call) => call.path), [
    '/v1/demand/demand-lists/41/submit',
    '/v1/demand/demand-lists/41/confirm',
    '/v1/demand/demand-lists/41/publish',
    '/v1/demand/demand-lists/41/derive',
    '/v1/demand/demand-lists/41/void',
  ])
  assert.deepEqual(calls[0]?.body, {
    expected_version: 7,
  })
  assert.deepEqual(calls[1]?.body, {
    expected_version: 8,
    confirmation_note: 'Approved by administrator',
  })
  assert.equal(
    Object.hasOwn(
      calls[1]?.body as object,
      'note',
    ),
    false,
  )
  assert.deepEqual(calls.slice(2).map((call) => call.body), [
    { expected_version: 9 },
    { expected_version: 10 },
    { expected_version: 11 },
  ])
  assert.deepEqual(calls.map(headersOf), [
    { 'Idempotency-Key': 'submit-key' },
    { 'Idempotency-Key': 'confirm-key' },
    { 'Idempotency-Key': 'publish-key' },
    { 'Idempotency-Key': 'derive-key' },
    { 'Idempotency-Key': 'void-key' },
  ])
})
```

Add tenant and Decimal tests:

```ts
test('demand-list calls never expose tenant selection', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))

  await api.create({
    calculation_group_id: 9,
    name: 'No tenant input',
  }, 'create-key')
  await api.list()
  await api.get(41)
  await api.submit(41, 7, 'submit-key')

  const serialized = JSON.stringify(calls)
  assert.equal(serialized.includes('tenant_id'), false)
  assert.equal(serialized.includes('X-Tenant-ID'), false)
  assert.equal(serialized.includes('"tenant"'), false)
})

test('demand-list decimal strings retain exact precision', () => {
  const serialized = JSON.parse(JSON.stringify({
    original_quantity: '9007199254740993.125000',
    final_quantity: '12345678901234567890.654321',
  })) as Record<string, unknown>

  assert.equal(
    serialized.original_quantity,
    '9007199254740993.125000',
  )
  assert.equal(
    serialized.final_quantity,
    '12345678901234567890.654321',
  )
  assert.equal(
    typeof serialized.final_quantity,
    'string',
  )
})

test('list result retains PageData and response metadata separation', async () => {
  const calls: CapturedCall[] = []
  const page: PageData<never> = {
    items: [],
    page: 1,
    page_size: 20,
    total: 0,
    pages: 0,
  }
  const api = createDemandListApi({
    ...fakeClient(calls),
    async get<T>(
      path: string,
    ): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result(page as T)
    },
  })

  const response = await api.list()

  assert.deepEqual(response.data, page)
  assert.equal(response.meta.tenant_id, 'tenant-a')
  assert.equal(
    Object.hasOwn(response.data as object, 'tenant_id'),
    false,
  )
})
```

- [ ] **Step 4: Create the lifecycle resolver RED test file**

Create:

```text
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Use exact permission fixtures:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix.ts'
import {
  canEditDemandListItem,
  demandListActions,
} from '../demand-list-lifecycle.ts'

const viewer: MaintenancePermissions = {
  view: true,
  exportData: true,
  editMasterData: false,
  importMasterData: false,
  runCalculation: false,
  handleReview: false,
  reserveInventory: false,
  issueReturnInventory: false,
  transferInventory: false,
  adjustInventory: false,
  confirmHighRisk: false,
  publishRules: false,
  editDemandList: false,
  publishDemandList: false,
}

const contributor: MaintenancePermissions = {
  ...viewer,
  editDemandList: true,
}

const admin: MaintenancePermissions = {
  ...contributor,
  publishDemandList: true,
}
```

Add the exact matrix:

```ts
test('demand-list actions follow exact status and capabilities', () => {
  assert.deepEqual(
    demandListActions('DRAFT', viewer),
    [],
  )
  assert.deepEqual(
    demandListActions('DRAFT', contributor),
    ['edit', 'submit'],
  )
  assert.deepEqual(
    demandListActions('DRAFT', admin),
    ['edit', 'submit'],
  )
  assert.deepEqual(
    demandListActions('PENDING_CONFIRMATION', contributor),
    [],
  )
  assert.deepEqual(
    demandListActions('PENDING_CONFIRMATION', admin),
    ['confirm'],
  )
  assert.deepEqual(
    demandListActions('CONFIRMED', admin),
    ['publish'],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', contributor),
    [],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', admin),
    ['derive', 'void'],
  )
  assert.deepEqual(
    demandListActions('VOIDED', admin),
    [],
  )
})

test('item editing is limited to capable users on DRAFT', () => {
  assert.equal(
    canEditDemandListItem('DRAFT', contributor),
    true,
  )
  assert.equal(
    canEditDemandListItem('DRAFT', admin),
    true,
  )
  assert.equal(
    canEditDemandListItem('DRAFT', viewer),
    false,
  )

  for (const status of [
    'PENDING_CONFIRMATION',
    'CONFIRMED',
    'PUBLISHED',
    'VOIDED',
  ] as const) {
    assert.equal(
      canEditDemandListItem(status, admin),
      false,
    )
  }
})
```

- [ ] **Step 5: Create the store RED test file**

Create:

```text
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
```

The complete store tests are specified in Task 4. At this RED stage, include all tests before creating `demandList.ts`.

Use this fixture foundation:

```ts
import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  DecimalString,
  DemandList,
  DemandListCreateRequest,
  DemandListItemUpdateRequest,
} from '../../../api/maintenance/demand-lists.ts'
import type {
  MaintenanceResult,
} from '../../../api/maintenance/types.ts'
import {
  createDemandListState,
  type DemandListStoreApi,
} from '../demandList.ts'

function result<T>(
  data: T,
): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
      version: (
        typeof data === 'object'
        && data !== null
        && 'version' in data
        && typeof data.version === 'number'
      )
        ? data.version
        : undefined,
    },
  }
}
```

Define a full aggregate fixture factory whose fields exactly match `DemandList`:

```ts
function demandList(
  overrides: Partial<DemandList> = {},
): DemandList {
  return {
    id: 41,
    name: 'Demand list 41',
    description: 'Task 5 fixture',
    lineage_id: '11111111-2222-3333-4444-555555555555',
    version_number: 1,
    derived_from_id: null,
    scenario_version_id: 3,
    calculation_group_id: 9,
    status: 'DRAFT',
    is_current: false,
    superseded_by_id: null,
    superseded_at: null,
    version: 7,
    created_by_user_id: 'user-a',
    created_by_request_id: 'request-a',
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
    submitted_by_user_id: null,
    submitted_by_request_id: null,
    submitted_at: null,
    confirmed_by_user_id: null,
    confirmed_by_request_id: null,
    confirmed_at: null,
    published_by_user_id: null,
    published_by_request_id: null,
    published_at: null,
    voided_by_user_id: null,
    voided_by_request_id: null,
    voided_at: null,
    items: [],
    events: [],
    ...overrides,
  }
}
```

Define a deferred helper:

```ts
function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return {
    promise,
    resolve,
    reject,
  }
}
```

Define a complete API stub factory so every test overrides only the method it exercises:

```ts
function apiStub(
  overrides: Partial<DemandListStoreApi> = {},
): DemandListStoreApi {
  return {
    async create(
      _request: DemandListCreateRequest,
      _idempotencyKey: string,
    ) {
      return result(demandList())
    },
    async get(_demandListId: number) {
      return result(demandList())
    },
    async updateItem(
      _demandListId: number,
      _itemId: number,
      _request: DemandListItemUpdateRequest,
    ) {
      return result(demandList())
    },
    async submit(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 8,
      }))
    },
    async confirm(
      _demandListId: number,
      _expectedVersion: number,
      _confirmationNote: string,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'CONFIRMED',
        version: 9,
      }))
    },
    async publish(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'PUBLISHED',
        is_current: true,
        version: 10,
      }))
    },
    async derive(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        id: 42,
        version_number: 2,
        derived_from_id: 41,
        status: 'DRAFT',
        is_current: false,
        version: 1,
      }))
    },
    async void(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'VOIDED',
        is_current: false,
        version: 11,
      }))
    },
    ...overrides,
  }
}
```

Task 4 supplies all required test bodies.

- [ ] **Step 6: Run the complete RED gate**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected failures:

```text
demand-lists.ts module missing
demandList.ts module missing
demand-list-lifecycle.ts module missing
permission objects missing two properties
```

Reject the RED stage if failures are caused by syntax errors, malformed imports, unrelated existing tests, or an invalid fixture.

- [ ] **Step 7: Verify RED scope**

From the repository root:

```powershell
git status --short
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --name-only
```

Expected:

```text
modified:
  frontend/src/stores/maintenance/__tests__/permissions.test.ts

untracked:
  frontend/src/api/maintenance/__tests__/demand-lists.test.ts
  frontend/src/stores/maintenance/__tests__/demand-list.test.ts
  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts

no production file
no staged file
HEAD unchanged
push not performed
```

Stop for RED evidence review before creating production files.

---

### Task 2: Implement the Typed Demand List API Client

**Files:**
- Create: `frontend/src/api/maintenance/demand-lists.ts`
- Test: `frontend/src/api/maintenance/__tests__/demand-lists.test.ts`

**Interfaces:**
- Consumes: `maintenanceGet`, `maintenancePost`, `maintenancePut`, `buildQuery`, `MaintenanceResult`, `PageData`, and `ReliabilityModel`.
- Produces: all demand-list types, `DemandListApiClient`, `createDemandListApi`, and `demandListApi`.
- Consumed by: Task 4 and Task 6.

- [ ] **Step 1: Create exact enum and request types**

Start `frontend/src/api/maintenance/demand-lists.ts` with:

```ts
import {
  buildQuery,
  maintenanceGet,
  maintenancePost,
  maintenancePut,
} from './client'
import type {
  MaintenanceResult,
  PageData,
} from './types'
import type {
  ReliabilityModel,
} from './model-recommendations'

export type DecimalString = string

export type DemandListStatus =
  | 'DRAFT'
  | 'PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'VOIDED'

export type DemandListEventType =
  | 'CREATED'
  | 'ITEM_UPDATED'
  | 'SUBMITTED'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'DERIVED'
  | 'VOIDED'

export type DemandListDecisionType =
  | 'SYSTEM_RECOMMENDATION'
  | 'ALTERNATIVE_CANDIDATE'
  | 'MANUAL_QUANTITY'

export type DemandExecutionMode =
  | 'AUTO'
  | 'ANALYTICAL'
  | 'MONTE_CARLO'
  | 'COMPARE'
```

Request types:

```ts
export interface DemandListCreateRequest {
  calculation_group_id: number
  name: string
  description?: string | null
}

export interface DemandListItemUpdateRequest {
  expected_version: number
  final_quantity: DecimalString
  adjustment_reason: string
}

export interface DemandListListQuery {
  page?: number
  page_size?: number
  status?: DemandListStatus
  lineage_id?: string
}
```

- [ ] **Step 2: Add exhaustive read models**

Add:

```ts
export interface DemandListItem {
  id: number
  demand_list_id: number
  spare_part_id: number
  spare_part_code_snapshot: string
  spare_part_name_snapshot: string
  spare_part_unit_snapshot: string
  criticality_level_snapshot: string | null
  source_calculation_group_id: number | null
  source_group_child_id: number | null
  source_calculation_id: number | null
  source_calculation_run_id: number | null
  source_result_id: number | null
  reliability_model: ReliabilityModel | null
  execution_mode: DemandExecutionMode | null
  original_quantity: DecimalString
  final_quantity: DecimalString
  decision_type: DemandListDecisionType | null
  decision_reason: string | null
  decision_risk: string | null
  requires_admin_confirmation: boolean
  confirmed_by_admin: boolean
  risk_rule_version: string | null
  source_snapshot_json: Record<string, unknown>
  decision_snapshot_json: Record<string, unknown> | null
  interval_snapshot_json: Record<string, unknown> | null
  parameter_snapshot_json: Record<string, unknown> | null
  warning_snapshot_json: string[] | null
  inventory_snapshot_json: Record<string, unknown> | null
  version: number
  created_at: string
  updated_at: string
}

export interface DemandListEvent {
  id: number
  demand_list_id: number
  event_type: DemandListEventType
  actor_user_id: string
  actor_roles_json: string[]
  request_id: string
  idempotency_key: string | null
  request_hash: string | null
  before_summary_json: Record<string, unknown> | null
  after_summary_json: Record<string, unknown> | null
  response_snapshot_json: Record<string, unknown> | null
  occurred_at: string
}

export interface DemandListSummary {
  id: number
  name: string
  description: string | null
  lineage_id: string
  version_number: number
  derived_from_id: number | null
  scenario_version_id: number
  calculation_group_id: number
  status: DemandListStatus
  is_current: boolean
  superseded_by_id: number | null
  superseded_at: string | null
  version: number
  created_by_user_id: string
  created_by_request_id: string
  created_at: string
  updated_at: string
}

export interface DemandList extends DemandListSummary {
  submitted_by_user_id: string | null
  submitted_by_request_id: string | null
  submitted_at: string | null
  confirmed_by_user_id: string | null
  confirmed_by_request_id: string | null
  confirmed_at: string | null
  published_by_user_id: string | null
  published_by_request_id: string | null
  published_at: string | null
  voided_by_user_id: string | null
  voided_by_request_id: string | null
  voided_at: string | null
  items: DemandListItem[]
  events: DemandListEvent[]
}
```

Do not add `tenant_id` to any domain interface.

- [ ] **Step 3: Add client dependency and helpers**

```ts
export interface DemandListApiClient {
  get<T>(
    path: string,
  ): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
  put<T>(
    path: string,
    body: unknown,
  ): Promise<MaintenanceResult<T>>
}

const defaultClient: DemandListApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
}

const BASE_PATH = '/v1/demand/demand-lists'

function identifier(value: number): string {
  return encodeURIComponent(String(value))
}

function idempotencyConfig(
  idempotencyKey: string,
): {
  headers: Record<string, string>
} {
  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  }
}

function transitionBody(
  expectedVersion: number,
): {
  expected_version: number
} {
  return {
    expected_version: expectedVersion,
  }
}
```

- [ ] **Step 4: Implement create/list/get/update methods**

```ts
export function createDemandListApi(
  client: DemandListApiClient = defaultClient,
) {
  return {
    create(
      request: DemandListCreateRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        BASE_PATH,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    list(
      query: DemandListListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<DemandListSummary>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
        lineage_id: query.lineage_id,
      })

      return client.get<
        PageData<DemandListSummary>
      >(
        BASE_PATH + (suffix ? `?${suffix}` : ''),
      )
    },

    get(
      demandListId: number,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.get<DemandList>(
        `${BASE_PATH}/${identifier(demandListId)}`,
      )
    },

    updateItem(
      demandListId: number,
      itemId: number,
      request: DemandListItemUpdateRequest,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.put<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + `/items/${identifier(itemId)}`
        ),
        request,
      )
    },
```

- [ ] **Step 5: Implement exact lifecycle methods**

Continue the returned object:

```ts
    submit(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/submit'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    confirm(
      demandListId: number,
      expectedVersion: number,
      confirmationNote: string,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/confirm'
        ),
        {
          expected_version: expectedVersion,
          confirmation_note: confirmationNote,
        },
        idempotencyConfig(idempotencyKey),
      )
    },

    publish(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/publish'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    derive(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/derive'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    void(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/void'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },
  }
}

export const demandListApi = createDemandListApi()
```

- [ ] **Step 6: Run the API GREEN gate**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts
```

Expected:

```text
all demand-list API tests pass
no skipped or xfailed test
```

- [ ] **Step 7: Run API-specific static checks**

```powershell
& '.\node_modules\.bin\vue-tsc.cmd' `
  --noEmit `
  --pretty false `
  --project tsconfig.app.json
```

At this point, the command may still fail because `demandList.ts` and `demand-list-lifecycle.ts` have not yet been created and their RED tests import them. Any other TypeScript error is a Task 2 defect and must be fixed before proceeding.

- [ ] **Step 8: Verify Task 2 scope**

Expected feature state:

```text
new production:
  frontend/src/api/maintenance/demand-lists.ts

existing RED changes:
  four Task 1 test paths

no store production
no resolver production
no permission production change
no stage
no commit
```

Stop for API implementation review.

---

### Task 3: Implement Demand List Capabilities and Pure Lifecycle Resolution

**Files:**
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`
- Create: `frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts`
- Test: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`

**Interfaces:**
- Consumes: `DemandListStatus` and `MaintenancePermissions`.
- Produces: `editDemandList`, `publishDemandList`, `DemandListAction`, `demandListActions`, and `canEditDemandListItem`.
- Consumed by: Task 4 tests and Task 6 UI.

- [ ] **Step 1: Extend `MaintenancePermissions`**

Add after `publishRules`:

```ts
editDemandList: boolean
publishDemandList: boolean
```

Add both as `false` in `DENIED_PERMISSIONS`.

`VIEWER_PERMISSIONS` inherits both `false`.

Add to `CONTRIBUTOR_PERMISSIONS`:

```ts
editDemandList: true,
```

Add to `ADMIN_PERMISSIONS`:

```ts
publishDemandList: true,
```

Because admin spreads contributor permissions, admin and owner receive both capabilities.

- [ ] **Step 2: Extend fail-closed auth resolution**

In `permissionsForAuth()`, add:

```ts
editDemandList:
  rolePermissions.editDemandList && canMaintain,

publishDemandList:
  rolePermissions.publishDemandList && canAdminister,
```

The complete return object must still contain every `MaintenancePermissions` key exactly once.

- [ ] **Step 3: Run the permission GREEN gate**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: all permission tests pass, including the new admin-to-contributor hierarchy reduction.

- [ ] **Step 4: Create the pure resolver**

Create:

```text
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
```

Exact implementation:

```ts
import type {
  DemandListStatus,
} from '../../../api/maintenance/demand-lists'
import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix'

export type DemandListAction =
  | 'edit'
  | 'submit'
  | 'confirm'
  | 'publish'
  | 'derive'
  | 'void'

export function demandListActions(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): DemandListAction[] {
  if (status === 'DRAFT') {
    return permissions.editDemandList
      ? ['edit', 'submit']
      : []
  }

  if (!permissions.publishDemandList) {
    return []
  }

  if (status === 'PENDING_CONFIRMATION') {
    return ['confirm']
  }

  if (status === 'CONFIRMED') {
    return ['publish']
  }

  if (status === 'PUBLISHED') {
    return ['derive', 'void']
  }

  return []
}

export function canEditDemandListItem(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): boolean {
  return (
    status === 'DRAFT'
    && permissions.editDemandList
  )
}
```

Do not import Vue, Pinia, auth stores, or raw role types.

- [ ] **Step 5: Run resolver and permission GREEN gates together**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: all tests pass.

- [ ] **Step 6: Add a static raw-role prohibition check**

Run:

```powershell
$path = "src/components/maintenance/calculation/demand-list-lifecycle.ts"
$text = Get-Content -LiteralPath $path -Raw

foreach ($forbidden in @(
    "TenantRole",
    "'viewer'",
    "'contributor'",
    "'admin'",
    "'owner'",
    "useAuth",
    "defineStore",
    "from 'vue'"
)) {
    if ($text.Contains($forbidden)) {
        throw "Forbidden resolver coupling found: $forbidden"
    }
}
```

Expected: no forbidden coupling.

- [ ] **Step 7: Verify Task 3 scope**

Expected production changes now include only:

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
```

All four RED test paths remain present. No store production file yet. No stage, commit, or push.

Stop for capability/resolver review.

---

### Task 4: Implement the Concurrency-Safe Demand List Store

**Files:**
- Create: `frontend/src/stores/maintenance/demandList.ts`
- Test: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`

**Interfaces:**
- Consumes: `demandListApi`, demand-list domain types, `normalizeMaintenanceError`, `MaintenanceClientError`, and `MaintenanceResult`.
- Produces: `DemandListStoreApi`, `createDemandListState`, and `useDemandListStore`.
- Consumed by: Task 6 detail and lifecycle UI.

- [ ] **Step 1: Define the store API interface**

Create `frontend/src/stores/maintenance/demandList.ts`:

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  demandListApi,
  type DecimalString,
  type DemandList,
  type DemandListCreateRequest,
  type DemandListItemUpdateRequest,
} from '../../api/maintenance/demand-lists'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
} from '../../api/maintenance/types'

export interface DemandListStoreApi {
  create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  get(
    demandListId: number,
  ): Promise<MaintenanceResult<DemandList>>
  updateItem(
    demandListId: number,
    itemId: number,
    request: DemandListItemUpdateRequest,
  ): Promise<MaintenanceResult<DemandList>>
  submit(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  confirm(
    demandListId: number,
    expectedVersion: number,
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  publish(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  derive(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  void(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
}
```

- [ ] **Step 2: Add state and read-generation logic**

```ts
export function createDemandListState(
  api: DemandListStoreApi = demandListApi,
) {
  const current = ref<DemandList | null>(null)
  const loading = ref(false)
  const mutating = ref(false)
  const error = ref<MaintenanceClientError | null>(
    null,
  )

  let requestGeneration = 0

  function apply(
    value: DemandList,
  ): void {
    current.value = value
  }

  async function load(
    demandListId: number,
  ): Promise<DemandList> {
    const generation = ++requestGeneration
    loading.value = true
    error.value = null

    try {
      const response = await api.get(demandListId)
      if (generation === requestGeneration) {
        apply(response.data)
      }
      return response.data
    } catch (value) {
      if (generation === requestGeneration) {
        error.value = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      if (generation === requestGeneration) {
        loading.value = false
      }
    }
  }
```

The stale response still resolves to its caller but cannot update `current`, `error`, or the current loading flag.

- [ ] **Step 3: Add exact mutation preconditions**

```ts
  function beginMutation(): void {
    if (mutating.value) {
      throw new Error(
        'Demand list mutation is already in progress',
      )
    }

    mutating.value = true
    error.value = null
  }

  function requireCurrent(): DemandList {
    const value = current.value
    if (value === null) {
      throw new Error('Demand list is not loaded')
    }
    return value
  }
```

`requireCurrent()` must run before `beginMutation()` for existing-list actions. Otherwise a missing aggregate would leave `mutating` set to `true`.

- [ ] **Step 4: Add one common mutation executor**

```ts
  async function runMutation(
    operation: () => Promise<
      MaintenanceResult<DemandList>
    >,
    options: {
      sourceId: number | null
      allowResultIdChange: boolean
    },
  ): Promise<DemandList> {
    const generation = requestGeneration
    beginMutation()

    try {
      const response = await operation()

      if (generation === requestGeneration) {
        const active = current.value
        const sourceMatches = (
          options.sourceId === null
          || active?.id === options.sourceId
        )
        const resultMatches = (
          options.allowResultIdChange
          || options.sourceId === null
          || response.data.id === options.sourceId
        )

        if (sourceMatches && resultMatches) {
          apply(response.data)
        }
      }

      return response.data
    } catch (value) {
      if (generation === requestGeneration) {
        error.value = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      mutating.value = false
    }
  }
```

The server aggregate is authoritative. Do not increment `version` locally or patch only one item/status field.

- [ ] **Step 5: Implement create**

```ts
  function create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<DemandList> {
    return runMutation(
      () => api.create(request, idempotencyKey),
      {
        sourceId: null,
        allowResultIdChange: true,
      },
    )
  }
```

Create may start without `current`.

- [ ] **Step 6: Implement update using the current server version**

```ts
  function updateItem(
    itemId: number,
    finalQuantity: DecimalString,
    adjustmentReason: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.updateItem(
        source.id,
        itemId,
        {
          expected_version: source.version,
          final_quantity: finalQuantity,
          adjustment_reason: adjustmentReason,
        },
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }
```

- [ ] **Step 7: Implement lifecycle actions**

```ts
  function submit(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.submit(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function confirm(
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.confirm(
        source.id,
        source.version,
        confirmationNote,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function publish(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.publish(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function derive(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.derive(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: true,
      },
    )
  }

  function voidList(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.void(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }
```

- [ ] **Step 8: Add disposal and exports**

```ts
  function dispose(): void {
    requestGeneration += 1
  }

  return {
    current,
    loading,
    mutating,
    error,
    create,
    load,
    updateItem,
    submit,
    confirm,
    publish,
    derive,
    voidList,
    dispose,
  }
}

export const useDemandListStore = defineStore(
  'maintenanceDemandList',
  () => createDemandListState(),
)
```

Do not add route or component dependencies.

- [ ] **Step 9: Add the stale-load tests**

Append to `demand-list.test.ts`:

```ts
test('a slower first load cannot overwrite a newer route', async () => {
  const first = deferred<MaintenanceResult<DemandList>>()
  const second = deferred<MaintenanceResult<DemandList>>()
  let call = 0

  const state = createDemandListState(apiStub({
    get: async () => {
      call += 1
      return call === 1
        ? first.promise
        : second.promise
    },
  }))

  const loadingFirst = state.load(41)
  const loadingSecond = state.load(42)

  second.resolve(result(demandList({
    id: 42,
    name: 'New route',
  })))
  await loadingSecond

  first.resolve(result(demandList({
    id: 41,
    name: 'Stale route',
  })))
  await loadingFirst

  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.name, 'New route')
  assert.equal(state.loading.value, false)
})

test('dispose invalidates an in-flight load', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()
  const state = createDemandListState(apiStub({
    get: async () => pending.promise,
  }))

  const loading = state.load(41)
  state.dispose()
  pending.resolve(result(demandList({
    id: 41,
  })))
  await loading

  assert.equal(state.current.value, null)
})
```

- [ ] **Step 10: Add mutation-gate and missing-current tests**

```ts
test('all demand-list mutations are mutually exclusive', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()
  let submitCalls = 0

  const state = createDemandListState(apiStub({
    updateItem: async () => pending.promise,
    submit: async () => {
      submitCalls += 1
      return result(demandList())
    },
  }))

  await state.load(41)
  const updating = state.updateItem(
    501,
    '12.500000',
    'Approved',
  )

  await assert.rejects(
    () => state.submit('submit-key'),
    /mutation is already in progress/,
  )
  assert.equal(submitCalls, 0)

  pending.resolve(result(demandList({
    version: 8,
  })))
  await updating
  assert.equal(state.mutating.value, false)
})

test('mutation without a loaded aggregate is rejected before API use', async () => {
  let calls = 0
  const state = createDemandListState(apiStub({
    submit: async () => {
      calls += 1
      return result(demandList())
    },
  }))

  await assert.rejects(
    () => state.submit('submit-key'),
    /Demand list is not loaded/,
  )
  assert.equal(calls, 0)
  assert.equal(state.mutating.value, false)
})
```

- [ ] **Step 11: Add version-propagation tests**

```ts
test('update and submit use successive server versions', async () => {
  const captured: Array<{
    operation: string
    version: number
  }> = []

  const state = createDemandListState(apiStub({
    updateItem: async (
      _listId,
      _itemId,
      request,
    ) => {
      captured.push({
        operation: 'update',
        version: request.expected_version,
      })
      return result(demandList({
        version: 8,
      }))
    },
    submit: async (
      _listId,
      expectedVersion,
    ) => {
      captured.push({
        operation: 'submit',
        version: expectedVersion,
      })
      return result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 9,
      }))
    },
  }))

  await state.load(41)
  await state.updateItem(
    501,
    '12.500000',
    'Approved',
  )
  await state.submit('submit-key')

  assert.deepEqual(captured, [
    { operation: 'update', version: 7 },
    { operation: 'submit', version: 8 },
  ])
  assert.equal(state.current.value?.version, 9)
})
```

- [ ] **Step 12: Add confirmation, publication, derivation, and void tests**

```ts
test('confirm forwards the exact note and current version', async () => {
  let captured:
    | {
        id: number
        version: number
        note: string
        key: string
      }
    | undefined

  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'PENDING_CONFIRMATION',
      version: 8,
    })),
    confirm: async (
      id,
      version,
      note,
      key,
    ) => {
      captured = { id, version, note, key }
      return result(demandList({
        status: 'CONFIRMED',
        version: 9,
      }))
    },
  }))

  await state.load(41)
  await state.confirm(
    'Approved by administrator',
    'confirm-key',
  )

  assert.deepEqual(captured, {
    id: 41,
    version: 8,
    note: 'Approved by administrator',
    key: 'confirm-key',
  })
  assert.equal(
    state.current.value?.status,
    'CONFIRMED',
  )
})

test('publish replaces state with the complete server aggregate', async () => {
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'CONFIRMED',
      version: 9,
    })),
    publish: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      published_by_user_id: 'admin-a',
      published_at: '2026-08-01T13:00:00Z',
      version: 10,
      events: [{
        id: 700,
        demand_list_id: 41,
        event_type: 'PUBLISHED',
        actor_user_id: 'admin-a',
        actor_roles_json: ['admin'],
        request_id: 'request-publish',
        idempotency_key: 'publish-key',
        request_hash: 'hash-a',
        before_summary_json: {
          status: 'CONFIRMED',
        },
        after_summary_json: {
          status: 'PUBLISHED',
        },
        response_snapshot_json: {
          id: 41,
          version: 10,
        },
        occurred_at: '2026-08-01T13:00:00Z',
      }],
    })),
  }))

  await state.load(41)
  const published = await state.publish(
    'publish-key',
  )

  assert.equal(published.status, 'PUBLISHED')
  assert.equal(state.current.value?.is_current, true)
  assert.equal(
    state.current.value?.events.at(-1)?.event_type,
    'PUBLISHED',
  )
})

test('derive replaces current with the returned new DRAFT id', async () => {
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      version: 10,
    })),
    derive: async () => result(demandList({
      id: 42,
      version_number: 2,
      derived_from_id: 41,
      status: 'DRAFT',
      version: 1,
    })),
  }))

  await state.load(41)
  const derived = await state.derive('derive-key')

  assert.equal(derived.id, 42)
  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.status, 'DRAFT')
})

test('voidList forwards the current version', async () => {
  let capturedVersion = 0
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      version: 10,
    })),
    void: async (
      _id,
      version,
    ) => {
      capturedVersion = version
      return result(demandList({
        status: 'VOIDED',
        is_current: false,
        version: 11,
      }))
    },
  }))

  await state.load(41)
  await state.voidList('void-key')

  assert.equal(capturedVersion, 10)
  assert.equal(state.current.value?.status, 'VOIDED')
})
```

- [ ] **Step 13: Add stale-mutation and structured-error tests**

```ts
test('route change during mutation prevents stale state replacement', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()

  const state = createDemandListState(apiStub({
    get: async (id) => result(demandList({
      id,
      name: `List ${id}`,
    })),
    updateItem: async () => pending.promise,
  }))

  await state.load(41)
  const updating = state.updateItem(
    501,
    '12.500000',
    'Approved',
  )

  await state.load(42)
  pending.resolve(result(demandList({
    id: 41,
    name: 'Stale mutation result',
    version: 8,
  })))
  await updating

  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.name, 'List 42')
})

test('mutation failure preserves aggregate and structured conflict details', async () => {
  const conflict = {
    status: 409,
    error: {
      code: 'DEMAND_LIST_VERSION_CONFLICT',
      message: 'Demand list version conflict',
      details: {
        expected_version: 7,
        actual_version: 8,
        conflict_object: 'demand_list',
        retryable: false,
      },
    },
    meta: {
      request_id: 'request-conflict',
    },
  }

  const state = createDemandListState(apiStub({
    updateItem: async () => {
      throw conflict
    },
  }))

  await state.load(41)
  const before = state.current.value

  await assert.rejects(
    () => state.updateItem(
      501,
      '12.500000',
      'Approved',
    ),
  )

  assert.equal(state.current.value, before)
  assert.equal(
    state.error.value?.code,
    'DEMAND_LIST_VERSION_CONFLICT',
  )
  assert.deepEqual(
    state.error.value?.details,
    conflict.error.details,
  )
  assert.equal(
    state.error.value?.request_id,
    'request-conflict',
  )
  assert.equal(state.mutating.value, false)
})
```

- [ ] **Step 14: Run the complete Task 5 focused GREEN gate**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected:

```text
all Task 5 focused tests pass
no skipped test
no xfailed test
no xpassed test
```

- [ ] **Step 15: Run TypeScript validation**

```powershell
npm run type-check
```

Expected: PASS.

- [ ] **Step 16: Verify exact eight-file feature scope**

From the repository root:

```powershell
git status --short
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --name-only
git diff --check
```

Expected feature paths:

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

Expected:

```text
exactly eight feature paths
no staged feature file
HEAD remains the documentation commit
no push
```

Stop for focused GREEN review.

---

### Task 5: Run Full Regression, Static Review, and Commit Gates

**Files:**
- Test: all eight Task 5 feature files.
- Test: complete frontend suite.
- No additional production file.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: final evidence for the atomic feature commit.
- Completes: Plan 05-3C Task 5.

- [ ] **Step 1: Re-run the focused Task 5 gate with verbose output**

```powershell
cd frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Record the exact passing count. Do not hardcode a guessed count in the verification script.

- [ ] **Step 2: Run the complete frontend test suite**

```powershell
npm run test
```

Expected:

```text
all existing and Task 5 tests pass
no skipped, xfailed, or xpassed test
passing count is greater than the previously recorded 377-test baseline
```

A lower passing count requires investigation even when the command exits successfully.

- [ ] **Step 3: Run type-check and production build**

```powershell
npm run type-check
npm run build
```

Expected: both commands pass.

- [ ] **Step 4: Run exact source-content static checks**

From the repository root:

```powershell
$apiPath = "frontend/src/api/maintenance/demand-lists.ts"
$storePath = "frontend/src/stores/maintenance/demandList.ts"
$resolverPath = "frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts"

$apiText = Get-Content -LiteralPath $apiPath -Raw
$storeText = Get-Content -LiteralPath $storePath -Raw
$resolverText = Get-Content -LiteralPath $resolverPath -Raw
```

Required API markers:

```powershell
foreach ($marker in @(
    "export type DemandListStatus",
    "export interface DemandListItem",
    "export interface DemandListEvent",
    "export interface DemandListSummary",
    "export interface DemandList extends DemandListSummary",
    "export function createDemandListApi",
    "'Idempotency-Key'",
    "confirmation_note",
    "lineage_id"
)) {
    if (-not $apiText.Contains($marker)) {
        throw "Missing API marker: $marker"
    }
}
```

Forbidden API markers:

```powershell
foreach ($marker in @(
    "tenant_id:",
    "X-Tenant-ID",
    "confirmationNote:",
    "note:",
    "Number(",
    "parseFloat(",
    "parseInt("
)) {
    if ($apiText.Contains($marker)) {
        throw "Forbidden API marker: $marker"
    }
}
```

Required store markers:

```powershell
foreach ($marker in @(
    "let requestGeneration = 0",
    "Demand list mutation is already in progress",
    "Demand list is not loaded",
    "normalizeMaintenanceError",
    "source.version",
    "allowResultIdChange",
    "function voidList",
    "function dispose"
)) {
    if (-not $storeText.Contains($marker)) {
        throw "Missing store marker: $marker"
    }
}
```

Forbidden store markers:

```powershell
foreach ($marker in @(
    "current.value.version +",
    "current.value.version++",
    "error.message.includes",
    "String(error)",
    "TenantRole",
    "tenant_id"
)) {
    if ($storeText.Contains($marker)) {
        throw "Forbidden store marker: $marker"
    }
}
```

Required resolver markers:

```powershell
foreach ($marker in @(
    "permissions.editDemandList",
    "permissions.publishDemandList",
    "['edit', 'submit']",
    "['derive', 'void']"
)) {
    if (-not $resolverText.Contains($marker)) {
        throw "Missing resolver marker: $marker"
    }
}
```

Forbidden resolver markers:

```powershell
foreach ($marker in @(
    "TenantRole",
    "'viewer'",
    "'contributor'",
    "'admin'",
    "'owner'",
    "defineStore",
    "from 'vue'"
)) {
    if ($resolverText.Contains($marker)) {
        throw "Forbidden resolver marker: $marker"
    }
}
```

- [ ] **Step 5: Run exact diff-scope gates**

From the repository root:

```powershell
git diff --check
git diff --cached --check

$tracked = @(git diff --name-only)
$untracked = @(git ls-files --others --exclude-standard)
$staged = @(git diff --cached --name-only)
```

Expected tracked paths:

```text
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

Expected untracked paths:

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Expected:

```text
tracked count = 2
untracked count = 6
staged count = 0
no path outside the approved eight
```

- [ ] **Step 6: Verify forbidden repository scopes remain untouched**

```powershell
$allChanged = @($tracked + $untracked)

foreach ($path in $allChanged) {
    if ($path -like "frontend/src/router/*") {
        throw "Router change is forbidden in Task 5: $path"
    }
    if ($path -like "frontend/src/views/*") {
        throw "View change is forbidden in Task 5: $path"
    }
    if ($path -like "frontend/src/i18n/*") {
        throw "Locale change is forbidden in Task 5: $path"
    }
    if (
        $path -like "frontend/src/components/*.vue"
        -or $path -like "frontend/src/components/**/*.vue"
    ) {
        throw "Vue component change is forbidden in Task 5: $path"
    }
    if ($path -like "extensions/maintenance-api/*") {
        throw "Backend change is forbidden in Task 5: $path"
    }
    if ($path -like "internal/*") {
        throw "Go change is forbidden in Task 5: $path"
    }
}
```

- [ ] **Step 7: Capture final pre-commit evidence**

Evidence must include:

```text
branch and HEAD
documentation commit SHA
focused test output
full frontend test output
type-check output
build output
static marker review
exact tracked/untracked/staged paths
complete working diff including untracked files
SHA256 manifest
```

The evidence gate must state:

```text
feature commit not performed
push not performed
```

- [ ] **Step 8: Stop for explicit feature-commit approval**

Do not stage feature files at the end of regression.

Required approval phrase:

```text
批准提交 Plan 05-3C Task 5
```

- [ ] **Step 9: Stage exactly eight feature files after approval**

```powershell
git add -- `
  frontend/src/api/maintenance/demand-lists.ts `
  frontend/src/api/maintenance/__tests__/demand-lists.test.ts `
  frontend/src/stores/maintenance/demandList.ts `
  frontend/src/stores/maintenance/__tests__/demand-list.test.ts `
  frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts `
  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  frontend/src/stores/maintenance/permission-matrix.ts `
  frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

Verify:

```powershell
git diff --cached --check
git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
```

Expected:

```text
exactly eight staged paths
no unstaged tracked path
no untracked path
```

- [ ] **Step 10: Create the atomic Task 5 feature commit**

```powershell
git commit -m "feat: add demand list lifecycle client"
```

- [ ] **Step 11: Verify the local feature commit**

```powershell
git log -1 --format="%H%n%P%n%s"
git diff-tree --no-commit-id --name-only -r HEAD
git diff-tree --check HEAD^ HEAD
git status --short
git diff --cached --name-only
```

Expected:

```text
subject = feat: add demand list lifecycle client
parent = the Task 5 documentation commit
exactly eight committed feature paths
working tree clean
index empty
push not performed
```

- [ ] **Step 12: Run post-commit focused integration verification**

Re-run:

```powershell
cd frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts

npm run test
npm run type-check
npm run build
```

Expected: the committed tree reproduces all pre-commit results.

- [ ] **Step 13: Stop at the push boundary**

Do not push automatically.

Required separate approval phrase:

```text
批准推送 Plan 05-3C Task 5 并更新 PR #4
```

---

## Task 5 Acceptance Checklist

- [ ] Documentation commit contains only the approved design and plan.
- [ ] API module mirrors all Task 4 response fields.
- [ ] API module exposes all nine Task 4 routes.
- [ ] List query uses `page`, `page_size`, `status`, and `lineage_id`.
- [ ] Create and five lifecycle actions send `Idempotency-Key`.
- [ ] Confirmation sends `confirmation_note`.
- [ ] No request or domain type contains a tenant selector.
- [ ] Decimal quantities remain strings.
- [ ] Permission matrix adds exactly `editDemandList` and `publishDemandList`.
- [ ] Viewer receives neither capability.
- [ ] Contributor receives edit but not publish capability.
- [ ] Admin and owner receive both capabilities.
- [ ] Auth hierarchy reductions fail closed.
- [ ] Resolver consumes capabilities rather than raw roles.
- [ ] DRAFT resolves to edit/submit only when edit capability exists.
- [ ] Pending resolves to confirm only for publish capability.
- [ ] Confirmed resolves to publish only for publish capability.
- [ ] Published resolves to derive/void only for publish capability.
- [ ] Voided resolves to no action.
- [ ] Item editing is restricted to capable users on DRAFT.
- [ ] Store has one current aggregate and no list-page state.
- [ ] Store load uses `requestGeneration`.
- [ ] Store dispose invalidates in-flight responses.
- [ ] Store has one shared mutation gate.
- [ ] Existing-list mutations fail before API use when no list is loaded.
- [ ] Update uses the current server version.
- [ ] Later mutations use the version returned by the preceding mutation.
- [ ] Derive accepts a returned new aggregate ID.
- [ ] Stale reads cannot replace a newer route.
- [ ] Stale mutations cannot replace a newer route.
- [ ] Failed mutations preserve the previous aggregate.
- [ ] Structured error details remain available.
- [ ] Mutation state resets after success and failure.
- [ ] Focused tests pass.
- [ ] Full frontend tests pass above the 377-test historical baseline.
- [ ] Type-check passes.
- [ ] Production build passes.
- [ ] Diff whitespace check passes.
- [ ] Exactly eight feature paths are changed.
- [ ] Router, views, locales, Vue components, backend, and Go remain untouched.
- [ ] Feature files are not staged or committed before explicit approval.
- [ ] Push is not performed before separate explicit approval.

## Deferred to Task 6

Task 6 remains responsible for:

```text
DemandListLifecycleActions.vue
DemandListDetail.vue
calculation-comparison generation button
maintenanceDemandListDetail route
confirmation dialogs
item editor rendering and form validation
timeline rendering
current/superseded presentation
locale keys
navigation tests
menu behavior
browser acceptance evidence
```

## Plan Self-Review

- Spec coverage: every approved Task 5 requirement maps to a task and an executable gate.
- Placeholder scan: no unresolved placeholder or open design decision remains.
- Type consistency: API, store, resolver, and test signatures use one set of names and exact backend field spellings.
- Scope consistency: Task 5 remains non-visual and frontend-only.
- Concurrency consistency: read generation and mutation generation behavior is defined for success, failure, disposal, and route changes.
- Permission consistency: capabilities remain fail-closed and no raw role name reaches the resolver.
- Commit consistency: documentation and feature commits remain separate; feature staging waits for explicit approval.

# Plan 05-3C Task 6 Demand List Lifecycle UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the guarded calculation-to-demand-list generation entry, hidden demand-list detail route, Decimal-safe DRAFT item editing, complete five-state lifecycle controls, lineage/audit display, and four-locale UI required by Plan 05-3C Task 6.

**Architecture:** Extend the existing pure lifecycle helper with conservative generation eligibility, keep `DemandListLifecycleActions.vue` presentation-only, and let `DemandListDetail.vue` orchestrate route validation, the Task 5 Pinia store, item-edit state, dialogs, messages, and navigation. The backend remains authoritative for lifecycle, structural validation, tenant scope, optimistic versions, and Decimal semantics.

**Tech Stack:** Vue 3.5, TypeScript 6, Pinia 3, Vue Router 4, Vue I18n 11, TDesign Vue Next 1.19, Node `tsx --test`, `vue-tsc --build`, Vite 7, PowerShell 5.1.

## Global Constraints

- Work only in `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Work only on branch `feature/maintenance-frontend-plan05`.
- The implementation baseline before the documentation commit is `d38e00f43d3b3f3245d7069f821be55d1fe86777`.
- The approved design SHA256 is `ff79a95dba9b094ee571b7903e7aba4491f0c094f408fa85e89f85fbea1b0531`.
- Task 5 API, store, permission matrix, and their tests are consumed as-is; do not modify them.
- Scope is calculation comparison generation, hidden detail route, detail UI, item editing, lifecycle actions, audit/lineage display, and centralized calculation locales.
- Do not add a demand-list list/search page or maintenance-menu entry.
- Do not modify backend, Go, database migrations, inventory, procurement, review, or report code.
- Tenant scope comes only from the existing authenticated maintenance client; do not add tenant fields, query values, paths, or headers.
- Demand quantities remain exact strings. Do not use `Number`, `parseFloat`, `parseInt`, unary plus, or arithmetic formatting on quantity values.
- The client generation helper is a conservative presentation gate. The backend create endpoint remains authoritative.
- Lifecycle actions are derived only from `DemandListStatus` and `MaintenancePermissions`; do not inspect raw role names.
- Published, pending, confirmed, and voided items are read-only even for administrators.
- All mutations use the Task 5 store and server-returned versions; do not increment versions locally.
- Derived navigation uses the ID returned by `store.derive()`.
- Stale load and mutation responses must not overwrite a newer route.
- English and Simplified Chinese receive complete copy; Korean and Russian preserve the existing English-spread pattern and override core visible copy.
- The Task 5 full frontend baseline is 398 tests. Final Task 6 test count must be greater than 398 with zero failures, cancellations, skips, or todo tests.
- The approved project workflow is documentation commit first, TDD checkpoints without intermediate feature commits, final verification, explicit feature-commit approval, and separate push approval.
- No network operation is required during implementation. The existing two unpushed Task 5 commits remain local until a separate push operation is approved and succeeds.

---

## File Map

### Create

```text
frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
frontend/src/views/maintenance/calculations/DemandListDetail.vue
frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

### Modify

```text
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/maintenance-calculation.ts
```

### Documentation boundary

```text
docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui-design.md
docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui.md
```

### Explicitly unchanged

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
extensions/maintenance-api/**
internal/**
```

---

### Task 0: Commit the Approved Design and Implementation Plan

**Files:**
- Add: `docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui-design.md`
- Add: `docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui.md`

**Interfaces:**
- Consumes: approved Task 6 design and this implementation plan.
- Produces: one local documentation commit that becomes the immutable implementation baseline for Tasks 1–7.

- [ ] **Step 1: Verify the exact pre-documentation state**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05

git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
```

Expected:

```text
branch = feature/maintenance-frontend-plan05
HEAD = d38e00f43d3b3f3245d7069f821be55d1fe86777
untracked paths = exactly the design and plan documents
staged paths = none
```

Reject any feature source change or additional untracked path.

- [ ] **Step 2: Verify document hashes and content gates**

Run:

```powershell
$design = "docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui-design.md"
$plan = "docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui.md"

(Get-FileHash -LiteralPath $design -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLowerInvariant()

Select-String -LiteralPath $design, $plan -Pattern "\bT[B]D\b|\bT[O]DO\b|\bP[L]ACEHOLDER\b"
git diff --check -- $design $plan
```

Expected:

```text
design SHA256 = ff79a95dba9b094ee571b7903e7aba4491f0c094f408fa85e89f85fbea1b0531
plan SHA256 = the exact SHA256 recorded when this plan file is generated
placeholder search = no matches
diff check = exit 0
```

- [ ] **Step 3: Obtain explicit documentation-commit approval**

Required approval phrase:

```text
批准提交 Plan 05-3C Task 6 设计与实施计划文档
```

Do not stage or commit before that approval.

- [ ] **Step 4: Stage only the two documentation files**

Run:

```powershell
git add -- `
  docs/superpowers/specs/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui-design.md `
  docs/superpowers/plans/2026-08-01-maintenance-plan05-03c-task6-demand-list-lifecycle-ui.md

git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --check
```

Expected:

```text
staged paths = exactly two approved documentation files
unstaged paths = none
untracked paths = none
cached diff check = exit 0
```

- [ ] **Step 5: Create the local documentation commit**

Run:

```powershell
git commit -m "docs: plan plan05 demand list lifecycle ui"
```

Expected: one commit whose parent is `d38e00f43d3b3f3245d7069f821be55d1fe86777`.

- [ ] **Step 6: Verify the documentation commit boundary**

Run:

```powershell
git log -1 --format="%H%n%P%n%s"
git diff-tree --no-commit-id --name-status -r --no-renames HEAD
git status --short
git rev-list --left-right --count `
  refs/remotes/origin/feature/maintenance-frontend-plan05...HEAD
```

Expected:

```text
subject = docs: plan plan05 demand list lifecycle ui
commit paths = exactly the design and plan documents
worktree = clean
index = empty
behind = 0
ahead = 3
push = not performed
```

Record the resulting documentation commit SHA. Every implementation script and evidence gate must lock to that exact SHA until the final feature commit.

---

### Task 1: Establish the Unified RED Contracts

**Files:**
- Modify: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`
- Create: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`

**Interfaces:**
- Consumes:
  - `DemandListStatus`
  - `MaintenancePermissions`
  - `maintenanceRouteRecords`
  - `maintenanceCalculationLocales`
- Produces:
  - failing contracts for `canOfferDemandListGeneration`;
  - failing route and source contracts for the action component, comparison entry, detail page, derive navigation, and locale shape.

- [ ] **Step 1: Extend lifecycle test imports without requiring a missing named export**

Replace the direct helper imports with a namespace import:

```ts
import type {
  CalculationGroupStatus,
} from '../../../api/maintenance/calculation-groups.ts'
import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix.ts'
import * as lifecycle from '../demand-list-lifecycle.ts'

const {
  canEditDemandListItem,
  demandListActions,
} = lifecycle

type GenerationComparison = {
  group_status: CalculationGroupStatus
  rows: Array<{
    decision: Record<string, unknown> | null
    candidates: Record<
      string,
      { status: 'SUCCEEDED' | 'NO_RESULT' }
    >
  }>
}

type GenerationHelper = (
  comparison: GenerationComparison | null,
  permissions: MaintenancePermissions,
) => boolean

function generationHelper(): GenerationHelper {
  return (
    lifecycle as unknown as Record<string, unknown>
  ).canOfferDemandListGeneration as GenerationHelper
}
```

This keeps the test module loadable while the helper is absent. The new tests fail inside the test body with `canOfferDemandListGeneration is not a function`, while the two existing Task 5 tests continue to pass.

- [ ] **Step 2: Add generation fixtures**

Add:

```ts
function eligibleComparison(
  overrides: Partial<GenerationComparison> = {},
): GenerationComparison {
  return {
    group_status: 'COMPLETED',
    rows: [
      {
        decision: { id: 1 },
        candidates: {
          primary: { status: 'SUCCEEDED' },
          alternative: { status: 'NO_RESULT' },
        },
      },
    ],
    ...overrides,
  }
}
```

- [ ] **Step 3: Add the conservative generation tests**

Add:

```ts
test('generation requires demand-list edit capability and terminal status', () => {
  const canGenerate = generationHelper()

  assert.equal(
    canGenerate(eligibleComparison(), viewer),
    false,
  )
  assert.equal(
    canGenerate(eligibleComparison(), contributor),
    true,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({ group_status: 'RUNNING' }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({ group_status: 'PENDING' }),
      admin,
    ),
    false,
  )
})

test('generation requires rows, saved decisions, and a successful cell per row', () => {
  const canGenerate = generationHelper()

  assert.equal(
    canGenerate(
      eligibleComparison({ rows: [] }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({
        rows: [
          {
            decision: null,
            candidates: {
              primary: { status: 'SUCCEEDED' },
            },
          },
        ],
      }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({
        rows: [
          {
            decision: { id: 1 },
            candidates: {
              primary: { status: 'NO_RESULT' },
            },
          },
        ],
      }),
      contributor,
    ),
    false,
  )
})

test('generation accepts every terminal group status when row evidence is complete', () => {
  const canGenerate = generationHelper()

  for (const group_status of [
    'COMPLETED',
    'PARTIALLY_COMPLETED',
    'FAILED',
    'CANCELLED',
    'INTERRUPTED',
  ] as const) {
    assert.equal(
      canGenerate(
        eligibleComparison({ group_status }),
        contributor,
      ),
      true,
    )
  }
})
```

- [ ] **Step 4: Create the navigation and source-contract test file**

Create `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`:

```ts
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { maintenanceRouteRecords } from '../../../router/maintenance.ts'
import {
  maintenanceCalculationLocales,
} from '../../../i18n/locales/maintenance-calculation.ts'

function flattenMaintenanceRoutes() {
  const parent = maintenanceRouteRecords[0]
  return [parent, ...(parent.children ?? [])]
}

function source(
  relative: string,
): string {
  return readFileSync(
    new URL(relative, import.meta.url),
    'utf8',
  )
}

function keyPaths(
  value: unknown,
  prefix = '',
): string[] {
  if (
    value === null
    || typeof value !== 'object'
    || Array.isArray(value)
  ) {
    return [prefix]
  }

  return Object.entries(
    value as Record<string, unknown>,
  ).flatMap(([key, child]) => {
    const next = prefix ? `${prefix}.${key}` : key
    return keyPaths(child, next)
  }).sort()
}

test('demand-list route is authenticated, initialized, hidden, and stable', () => {
  const route = flattenMaintenanceRoutes().find(
    (item) => item.name === 'maintenanceDemandListDetail',
  )

  assert.equal(
    route?.path,
    'calculations/demand-lists/:listId',
  )
  assert.equal(route?.meta?.requiresAuth, true)
  assert.equal(route?.meta?.requiresInit, true)
  assert.equal(
    route?.meta?.hideInMaintenanceMenu,
    true,
  )
})

test('comparison uses the conservative gate and routes with the created aggregate id', () => {
  const comparison = source(
    '../calculations/CalculationComparison.vue',
  )

  assert.match(
    comparison,
    /canOfferDemandListGeneration/,
  )
  assert.match(
    comparison,
    /useDemandListStore/,
  )
  assert.match(
    comparison,
    /demandListStore\.create/,
  )
  assert.match(
    comparison,
    /params:\s*\{\s*listId:\s*created\.id\s*\}/s,
  )
  assert.doesNotMatch(
    comparison,
    /tenant[_-]?id/i,
  )
})

test('lifecycle action component is presentation-only', () => {
  const actions = source(
    '../../../components/maintenance/calculation/DemandListLifecycleActions.vue',
  )

  assert.match(actions, /demandListActions/)
  assert.match(actions, /emit\('select', action\)/)
  assert.doesNotMatch(actions, /useDemandListStore/)
  assert.doesNotMatch(
    actions,
    /useMaintenancePermissionsStore/,
  )
  assert.doesNotMatch(actions, /useRouter|useRoute/)
  assert.doesNotMatch(actions, /DialogPlugin|MessagePlugin/)
  assert.doesNotMatch(actions, /viewer|contributor|admin|owner/)
})

test('detail validates route ids and disposes stale requests', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /positiveInteger/)
  assert.match(detail, /invalidRoute/)
  assert.match(detail, /store\.load\(targetId\)/)
  assert.match(detail, /watch\(/)
  assert.match(detail, /onBeforeUnmount\(store\.dispose\)/)
  assert.match(detail, /maintenanceCalculations/)
})

test('detail item editing preserves decimal strings', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /canEditDemandListItem/)
  assert.match(detail, /type="text"/)
  assert.match(detail, /inputmode="decimal"/)
  assert.match(
    detail,
    /store\.updateItem\(\s*selectedItem\.value\.id,\s*quantity,\s*reason/s,
  )
  assert.doesNotMatch(
    detail,
    /Number\(\s*editQuantity/,
  )
  assert.doesNotMatch(
    detail,
    /parseFloat\(\s*editQuantity/,
  )
  assert.doesNotMatch(
    detail,
    /parseInt\(\s*editQuantity/,
  )
})

test('detail owns explicit lifecycle confirmations and exact confirmation note forwarding', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /DemandListLifecycleActions/)
  assert.match(detail, /DialogPlugin\.confirm/)
  assert.match(detail, /confirmationNote/)
  assert.match(
    detail,
    /store\.confirm\(\s*note,\s*requestKey\('confirm'\)\s*\)/s,
  )
  assert.match(detail, /store\.submit/)
  assert.match(detail, /store\.publish/)
  assert.match(detail, /store\.voidList/)
  assert.doesNotMatch(
    detail,
    /confirmation_note/,
  )
})

test('derive routes to the aggregate id returned by the store', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(
    detail,
    /const derived = await store\.derive/,
  )
  assert.match(
    detail,
    /params:\s*\{\s*listId:\s*derived\.id\s*\}/s,
  )
})

test('demand-list locale shapes match in all calculation locales', () => {
  const locales = Object.values(
    maintenanceCalculationLocales,
  )
  const expected = keyPaths(
    locales[0].demandList,
  )

  for (const locale of locales) {
    assert.deepEqual(
      keyPaths(locale.demandList),
      expected,
    )
  }
})
```

- [ ] **Step 5: Run the RED suite**

Run:

```powershell
cd frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected RED profile:

```text
existing Task 5 action test = PASS
existing Task 5 item-edit test = PASS
new generation tests = FAIL because helper is absent
route test = FAIL because route is absent
comparison source test = FAIL because generation entry is absent
action component test = FAIL because file is absent
detail source tests = FAIL because file is absent
locale shape test = FAIL because demandList locale section is absent
no syntax or transform error
no unrelated test failure
```

- [ ] **Step 6: Capture RED evidence and stop**

Capture:

```text
branch
documentation commit SHA
git status --short
test command
complete TAP output
test file SHA256 values
```

Expected working paths:

```text
M  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
?? frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Do not modify production source, stage, commit, or push.

---

### Task 2: Implement the Pure Generation Gate and Hidden Route GREEN

**Files:**
- Modify: `frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts`
- Modify: `frontend/src/router/maintenance.ts`
- Test: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`
- Test: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`

**Interfaces:**
- Consumes:
  - `CalculationGroupStatus`
  - `MaintenancePermissions`
- Produces:

```ts
export interface DemandListGenerationComparison
export function canOfferDemandListGeneration(
  comparison: DemandListGenerationComparison | null,
  permissions: MaintenancePermissions,
): boolean

route name: maintenanceDemandListDetail
route path: calculations/demand-lists/:listId
```

- [ ] **Step 1: Add imports and the generation comparison interface**

Add to `demand-list-lifecycle.ts`:

```ts
import type {
  CalculationGroupStatus,
} from '../../../api/maintenance/calculation-groups'
```

Add:

```ts
export interface DemandListGenerationComparison {
  group_status: CalculationGroupStatus
  rows: ReadonlyArray<{
    decision: unknown | null
    candidates: Readonly<Record<
      string,
      {
        status: 'SUCCEEDED' | 'NO_RESULT'
      }
    >>
  }>
}
```

Do not import the complete `CalculationGroupComparison` type. The helper consumes the smallest structural interface needed by the UI and tests.

- [ ] **Step 2: Implement the conservative generation helper**

Add:

```ts
const TERMINAL_GROUP_STATUSES:
ReadonlySet<CalculationGroupStatus> = new Set([
  'COMPLETED',
  'PARTIALLY_COMPLETED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
])

export function canOfferDemandListGeneration(
  comparison: DemandListGenerationComparison | null,
  permissions: MaintenancePermissions,
): boolean {
  if (
    !permissions.editDemandList
    || comparison === null
    || !TERMINAL_GROUP_STATUSES.has(
      comparison.group_status,
    )
    || comparison.rows.length === 0
  ) {
    return false
  }

  return comparison.rows.every((row) => (
    row.decision !== null
    && Object.values(row.candidates).some(
      (cell) => cell.status === 'SUCCEEDED',
    )
  ))
}
```

The function must not:

```text
call an API
read a store
inspect role strings
inspect tenant data
claim backend structural validity
```

- [ ] **Step 3: Add the hidden route**

Insert after `maintenanceCalculationComparison` in `frontend/src/router/maintenance.ts`:

```ts
{
  path: 'calculations/demand-lists/:listId',
  name: 'maintenanceDemandListDetail',
  component: () => import(
    '@/views/maintenance/calculations/DemandListDetail.vue'
  ),
  meta: {
    ...maintenanceRouteMeta,
    hideInMaintenanceMenu: true,
  },
},
```

The target file does not exist yet. Do not run full type-check at this checkpoint.

- [ ] **Step 4: Run only the helper and route contracts**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="generation|route is authenticated" `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 5: Run Task 5 lifecycle regression**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="actions follow|item editing" `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Expected: both existing Task 5 tests pass.

- [ ] **Step 6: Verify exact scope and stop**

Expected changed paths through Task 2:

```text
M  frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
M  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
M  frontend/src/router/maintenance.ts
?? frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

No stage, commit, network, or push.

---

### Task 3: Build the Presentation-Only Lifecycle Action Component GREEN

**Files:**
- Create: `frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue`
- Test: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`

**Interfaces:**
- Consumes:

```ts
DemandListStatus
MaintenancePermissions
DemandListAction
demandListActions(status, permissions)
```

- Produces:

```ts
props:
  status: DemandListStatus
  permissions: MaintenancePermissions
  busy: boolean

emit:
  select(action: DemandListAction): void
```

- [ ] **Step 1: Create the component template**

Create:

```vue
<template>
  <div
    v-if="actions.length"
    class="demand-list-lifecycle-actions"
  >
    <button
      v-for="action in actions"
      :key="action"
      type="button"
      :class="{
        'demand-list-lifecycle-actions__danger': (
          action === 'void'
        ),
      }"
      :disabled="busy"
      @click="emit('select', action)"
    >
      {{
        t(
          `maintenance.calculation.demandList.actions.${action}`,
        )
      }}
    </button>
  </div>
</template>
```

- [ ] **Step 2: Add the presentation-only script**

Add:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  DemandListStatus,
} from '@/api/maintenance/demand-lists'
import {
  demandListActions,
  type DemandListAction,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
import type {
  MaintenancePermissions,
} from '@/stores/maintenance/permission-matrix'

const props = defineProps<{
  status: DemandListStatus
  permissions: MaintenancePermissions
  busy: boolean
}>()

const emit = defineEmits<{
  select: [action: DemandListAction]
}>()

const { t } = useI18n()

const actions = computed(() => demandListActions(
  props.status,
  props.permissions,
))
</script>
```

- [ ] **Step 3: Add minimal scoped styling**

Add:

```vue
<style scoped>
.demand-list-lifecycle-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.demand-list-lifecycle-actions button {
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.demand-list-lifecycle-actions button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.demand-list-lifecycle-actions__danger {
  color: var(--td-error-color) !important;
}
</style>
```

- [ ] **Step 4: Run the component source contract**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="action component" `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected: PASS.

- [ ] **Step 5: Perform a forbidden dependency scan**

Run:

```powershell
$path = "src/components/maintenance/calculation/DemandListLifecycleActions.vue"
Select-String -LiteralPath $path -Pattern `
  "useDemandListStore|useMaintenancePermissionsStore|useAuthStore|useRouter|useRoute|DialogPlugin|MessagePlugin|viewer|contributor|admin|owner"
```

Expected: no matches.

- [ ] **Step 6: Verify exact scope and stop**

New path:

```text
?? frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
```

No stage, commit, network, or push.

---

### Task 4: Add the Calculation Comparison Generation Entry GREEN

**Files:**
- Modify: `frontend/src/views/maintenance/calculations/CalculationComparison.vue`
- Test: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`
- Regression: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`

**Interfaces:**
- Consumes:

```ts
canOfferDemandListGeneration(comparison, permissions)
useDemandListStore()
store.create(request, idempotencyKey): Promise<DemandList>
maintenanceDemandListDetail route
```

- Produces:
  - trimmed create request;
  - unique idempotency key;
  - navigation to the server-returned list ID.

- [ ] **Step 1: Add generation panel markup**

Insert after the existing comparison summary and before the comparison table:

```vue
<section
  v-if="comparison"
  class="calculation-comparison__demand-list"
>
  <header>
    <div>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.generation.eyebrow',
          )
        }}
      </span>
      <h2>
        {{
          t(
            'maintenance.calculation.demandList.generation.title',
          )
        }}
      </h2>
      <p>
        {{
          t(
            'maintenance.calculation.demandList.generation.description',
          )
        }}
      </p>
    </div>
  </header>

  <form @submit.prevent="createDemandList">
    <label>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.generation.name',
          )
        }}
      </span>
      <input
        v-model="demandListName"
        maxlength="200"
        required
      >
    </label>

    <label>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.generation.notes',
          )
        }}
      </span>
      <textarea
        v-model="demandListDescription"
        maxlength="2000"
      />
    </label>

    <button
      type="submit"
      :disabled="(
        demandListMutating
        || !canGenerateDemandList
        || !demandListName.trim()
      )"
    >
      {{
        demandListMutating
          ? t(
              'maintenance.calculation.demandList.generation.creating',
            )
          : t(
              'maintenance.calculation.demandList.generation.create',
            )
      }}
    </button>
  </form>

  <p
    v-if="!canGenerateDemandList"
    class="calculation-comparison__demand-list-hint"
  >
    {{
      t(
        'maintenance.calculation.demandList.generation.unavailable',
      )
    }}
  </p>

  <MaintenanceErrorState
    v-if="demandListError"
    :error="demandListError"
    :locale="locale"
    @retry="createDemandList"
  />
</section>
```

The retry action may call `createDemandList` only when the current form remains valid. The function itself must guard invalid state.

- [ ] **Step 2: Add imports and separate store refs**

Add imports:

```ts
import {
  canOfferDemandListGeneration,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
import { useDemandListStore } from '@/stores/maintenance/demandList'
```

Rename the existing calculation store variable for clarity:

```ts
const calculationStore = useCalculationGroupStore()
const demandListStore = useDemandListStore()
```

Use separate refs:

```ts
const {
  comparison,
  loading,
  mutating,
  error,
} = storeToRefs(calculationStore)

const {
  mutating: demandListMutating,
  error: demandListError,
} = storeToRefs(demandListStore)
```

Update existing calls from `store` to `calculationStore`.

- [ ] **Step 3: Add form state and conservative capability**

Add:

```ts
const demandListName = ref('')
const demandListDescription = ref('')

const canGenerateDemandList = computed(() => (
  canOfferDemandListGeneration(
    comparison.value,
    permissionStore.permissions,
  )
))
```

Do not derive capability from `runCalculation` or raw roles.

- [ ] **Step 4: Add idempotency key generation**

Add:

```ts
function requestKey(action: string): string {
  return (
    `${action}:${groupId}:`
    + (
      globalThis.crypto?.randomUUID?.()
      ?? Date.now()
    )
  )
}
```

- [ ] **Step 5: Implement guarded creation and returned-ID navigation**

Add:

```ts
async function createDemandList(): Promise<void> {
  const name = demandListName.value.trim()
  const description = (
    demandListDescription.value.trim()
  )

  if (
    !canGenerateDemandList.value
    || demandListMutating.value
    || !name
  ) {
    return
  }

  try {
    const created = await demandListStore.create(
      {
        calculation_group_id: groupId,
        name,
        description: description || null,
      },
      requestKey('create-demand-list'),
    )

    await router.push({
      name: 'maintenanceDemandListDetail',
      params: {
        listId: created.id,
      },
    })
  } catch {
    // The Task 5 store retains the normalized error.
  }
}
```

Do not use the route group ID or a locally generated value as the new list ID.

- [ ] **Step 6: Dispose both route-owned stores**

Replace:

```ts
onBeforeUnmount(store.dispose)
```

with:

```ts
onBeforeUnmount(() => {
  calculationStore.dispose()
  demandListStore.dispose()
})
```

- [ ] **Step 7: Add local panel styling**

Add focused styles:

```css
.calculation-comparison__demand-list {
  margin: 18px 0;
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-comparison__demand-list form {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(280px, 2fr) auto;
  gap: 14px;
  align-items: end;
}

.calculation-comparison__demand-list label {
  display: grid;
  gap: 6px;
}

.calculation-comparison__demand-list input,
.calculation-comparison__demand-list textarea {
  width: 100%;
  min-height: 38px;
  box-sizing: border-box;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.calculation-comparison__demand-list-hint {
  color: var(--td-text-color-secondary);
}
```

Add a mobile rule that changes the form grid to one column.

- [ ] **Step 8: Run the comparison contract**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="comparison uses" `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected: PASS.

- [ ] **Step 9: Run Task 5 create/store regressions**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="create applies|decimal-string" `
  src/stores/maintenance/__tests__/demand-list.test.ts
```

Expected: PASS.

- [ ] **Step 10: Verify exact scope and stop**

`CalculationComparison.vue` is the only new production modification in this task.

No stage, commit, network, or push.

---

### Task 5: Build the Demand-List Detail, Facts, Timeline, and DRAFT Item Editor GREEN

**Files:**
- Create: `frontend/src/views/maintenance/calculations/DemandListDetail.vue`
- Test: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`
- Regression: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`

**Interfaces:**
- Consumes:

```ts
useDemandListStore()
store.load(listId)
store.updateItem(itemId, quantityString, reason)
canEditDemandListItem(status, permissions)
DemandList
DemandListItem
DemandListEvent
```

- Produces:
  - validated route loading;
  - aggregate facts;
  - lifecycle strip;
  - item table;
  - audit timeline;
  - Decimal-safe DRAFT item editor.

Lifecycle mutation controls are added in Task 6.

- [ ] **Step 1: Create the route/loading shell**

Start the component with:

```vue
<template>
  <main class="demand-list-detail">
    <button
      type="button"
      class="demand-list-detail__back"
      @click="back"
    >
      ← {{
        t(
          'maintenance.calculation.demandList.detail.back',
        )
      }}
    </button>

    <section
      v-if="invalidRoute"
      class="demand-list-detail__invalid"
      role="alert"
    >
      <h1>
        {{
          t(
            'maintenance.calculation.demandList.errors.invalidRoute',
          )
        }}
      </h1>
    </section>

    <template v-else>
      <MaintenanceErrorState
        v-if="error"
        :error="error"
        :locale="locale"
        @retry="load"
      />

      <div
        v-if="loading && !current"
        class="demand-list-detail__loading"
      >
        {{
          t(
            'maintenance.calculation.demandList.detail.loading',
          )
        }}
      </div>

      <template v-if="current">
        <!-- Facts, lifecycle, items, and timeline added below. -->
      </template>
    </template>
  </main>
</template>
```

The HTML comment is only an intermediate construction instruction. Do not leave it in the final Task 5 file.

- [ ] **Step 2: Add exact imports and route state**

Use:

```vue
<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'

import type {
  DemandListItem,
  DemandListStatus,
} from '@/api/maintenance/demand-lists'
import {
  canEditDemandListItem,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import { useDemandListStore } from '@/stores/maintenance/demandList'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const store = useDemandListStore()
const permissionStore = useMaintenancePermissionsStore()

const {
  current,
  loading,
  mutating,
  error,
} = storeToRefs(store)

const selectedItem = ref<DemandListItem | null>(null)
const editQuantity = ref('')
const editReason = ref('')
const itemTable = ref<HTMLElement | null>(null)
```

- [ ] **Step 3: Add positive route parsing and stale-safe load**

Add:

```ts
function positiveInteger(
  value: unknown,
): number | null {
  const raw = Array.isArray(value)
    ? value[0]
    : value
  const parsed = Number(raw)

  return (
    Number.isInteger(parsed)
    && parsed > 0
      ? parsed
      : null
  )
}

const listId = computed(() => (
  positiveInteger(route.params.listId)
))

const invalidRoute = computed(() => (
  listId.value === null
))

async function load(): Promise<void> {
  const targetId = listId.value

  if (targetId === null) {
    store.dispose()
    return
  }

  try {
    await store.load(targetId)
  } catch {
    // The Task 5 store retains normalized error state.
  }
}

watch(
  () => route.params.listId,
  () => {
    closeItemEditor()
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(store.dispose)
```

The allowed `Number(raw)` converts only the route identifier. It must not be reused for quantities.

- [ ] **Step 4: Add back and related-list navigation**

Add:

```ts
function back(): void {
  if (current.value) {
    void router.push({
      name: 'maintenanceCalculationComparison',
      params: {
        groupId: current.value.calculation_group_id,
      },
    })
    return
  }

  void router.push({
    name: 'maintenanceCalculations',
  })
}

function openDemandList(
  demandListId: number,
): void {
  void router.push({
    name: 'maintenanceDemandListDetail',
    params: {
      listId: demandListId,
    },
  })
}

function openComparison(): void {
  if (!current.value) return

  void router.push({
    name: 'maintenanceCalculationComparison',
    params: {
      groupId: current.value.calculation_group_id,
    },
  })
}
```

- [ ] **Step 5: Add header and aggregate facts**

Inside `v-if="current"` add:

```vue
<MaintenancePageHeader
  :eyebrow="
    t(
      'maintenance.calculation.demandList.detail.eyebrow',
    )
  "
  :title="current.name"
  :description="current.description || '—'"
>
  <template #secondaryActions>
    <MaintenanceStatusTag :status="current.status" />
  </template>
</MaintenancePageHeader>

<section class="demand-list-detail__facts">
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.listId',
        )
      }}
    </span>
    <strong>#{{ current.id }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.versionNumber',
        )
      }}
    </span>
    <strong>{{ current.version_number }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.optimisticVersion',
        )
      }}
    </span>
    <strong>{{ current.version }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.lineage',
        )
      }}
    </span>
    <strong>{{ current.lineage_id }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.scenarioVersion',
        )
      }}
    </span>
    <strong>#{{ current.scenario_version_id }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.calculationGroup',
        )
      }}
    </span>
    <button type="button" @click="openComparison">
      #{{ current.calculation_group_id }}
    </button>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.currentPublished',
        )
      }}
    </span>
    <strong>
      {{
        current.is_current
          ? t('common.yes')
          : t('common.no')
      }}
    </strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.createdBy',
        )
      }}
    </span>
    <strong>{{ current.created_by_user_id }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.createdAt',
        )
      }}
    </span>
    <strong>{{ formatDate(current.created_at) }}</strong>
  </article>
  <article>
    <span>
      {{
        t(
          'maintenance.calculation.demandList.detail.updatedAt',
        )
      }}
    </span>
    <strong>{{ formatDate(current.updated_at) }}</strong>
  </article>
</section>

<section
  v-if="(
    current.derived_from_id
    || current.superseded_by_id
  )"
  class="demand-list-detail__lineage-links"
>
  <button
    v-if="current.derived_from_id"
    type="button"
    @click="openDemandList(current.derived_from_id)"
  >
    {{
      t(
        'maintenance.calculation.demandList.detail.openDerivedFrom',
        { id: current.derived_from_id },
      )
    }}
  </button>
  <button
    v-if="current.superseded_by_id"
    type="button"
    @click="openDemandList(current.superseded_by_id)"
  >
    {{
      t(
        'maintenance.calculation.demandList.detail.openSupersededBy',
        { id: current.superseded_by_id },
      )
    }}
  </button>
</section>
```

- [ ] **Step 6: Add the five-state lifecycle strip**

Add script state:

```ts
const lifecycleStatuses = [
  'DRAFT',
  'PENDING_CONFIRMATION',
  'CONFIRMED',
  'PUBLISHED',
  'VOIDED',
] as const satisfies readonly DemandListStatus[]

function statusReached(
  status: DemandListStatus,
): boolean {
  const currentIndex = lifecycleStatuses.indexOf(
    current.value?.status ?? 'DRAFT',
  )
  const targetIndex = lifecycleStatuses.indexOf(status)

  return targetIndex <= currentIndex
}
```

Add template:

```vue
<section class="demand-list-detail__lifecycle">
  <h2>
    {{
      t(
        'maintenance.calculation.demandList.detail.lifecycle',
      )
    }}
  </h2>
  <ol>
    <li
      v-for="status in lifecycleStatuses"
      :key="status"
      :class="{
        'demand-list-detail__lifecycle--reached': (
          statusReached(status)
        ),
        'demand-list-detail__lifecycle--current': (
          current.status === status
        ),
      }"
    >
      {{
        t(
          `maintenance.calculation.demandList.status.${status}`,
        )
      }}
    </li>
  </ol>
</section>
```

The strip displays state progression only. Audit actor/time facts come from events.

- [ ] **Step 7: Add item-edit authorization and editor functions**

Add:

```ts
const canEditItems = computed(() => (
  current.value !== null
  && canEditDemandListItem(
    current.value.status,
    permissionStore.permissions,
  )
))

function openItemEditor(
  item: DemandListItem,
): void {
  if (!canEditItems.value || mutating.value) {
    return
  }

  selectedItem.value = item
  editQuantity.value = item.final_quantity
  editReason.value = ''
}

function closeItemEditor(): void {
  selectedItem.value = null
  editQuantity.value = ''
  editReason.value = ''
}

async function saveItem(): Promise<void> {
  if (
    selectedItem.value === null
    || !canEditItems.value
    || mutating.value
  ) {
    return
  }

  const quantity = editQuantity.value.trim()
  const reason = editReason.value.trim()

  if (!quantity || !reason) {
    return
  }

  try {
    await store.updateItem(
      selectedItem.value.id,
      quantity,
      reason,
    )
    closeItemEditor()
    MessagePlugin.success(
      t(
        'maintenance.calculation.demandList.items.saved',
      ),
    )
  } catch {
    // Preserve editor values and the last successful aggregate.
  }
}

async function focusItems(): Promise<void> {
  await nextTick()
  itemTable.value?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}
```

- [ ] **Step 8: Add the item table**

Add:

```vue
<section
  ref="itemTable"
  class="demand-list-detail__items"
>
  <header>
    <div>
      <h2>
        {{
          t(
            'maintenance.calculation.demandList.items.title',
          )
        }}
      </h2>
      <p>
        {{
          t(
            'maintenance.calculation.demandList.items.description',
          )
        }}
      </p>
    </div>
    <span>{{ current.items.length }}</span>
  </header>

  <div class="demand-list-detail__table-wrap">
    <table>
      <thead>
        <tr>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.part',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.unit',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.criticality',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.model',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.mode',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.original',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.final',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.decision',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.risk',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.confirmed',
              )
            }}
          </th>
          <th>
            {{
              t(
                'maintenance.calculation.demandList.items.actions',
              )
            }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in current.items"
          :key="item.id"
        >
          <td>
            <strong>
              {{ item.spare_part_code_snapshot }}
            </strong>
            <span>
              {{ item.spare_part_name_snapshot }}
            </span>
          </td>
          <td>{{ item.spare_part_unit_snapshot }}</td>
          <td>
            {{ item.criticality_level_snapshot || '—' }}
          </td>
          <td>{{ item.reliability_model || '—' }}</td>
          <td>{{ item.execution_mode || '—' }}</td>
          <td>{{ item.original_quantity }}</td>
          <td>{{ item.final_quantity }}</td>
          <td>{{ item.decision_type || '—' }}</td>
          <td>{{ item.decision_risk || '—' }}</td>
          <td>
            {{
              item.confirmed_by_admin
                ? t('common.yes')
                : t('common.no')
            }}
          </td>
          <td>
            <button
              v-if="canEditItems"
              type="button"
              :disabled="mutating"
              @click="openItemEditor(item)"
            >
              {{
                t(
                  'maintenance.calculation.demandList.actions.edit',
                )
              }}
            </button>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

- [ ] **Step 9: Add the page-owned item editor**

Add:

```vue
<div
  v-if="selectedItem"
  class="demand-list-detail__dialog-backdrop"
>
  <section
    class="demand-list-detail__dialog"
    role="dialog"
    aria-modal="true"
    :aria-label="
      t(
        'maintenance.calculation.demandList.items.editTitle',
      )
    "
  >
    <header>
      <div>
        <span>
          {{ selectedItem.spare_part_code_snapshot }}
        </span>
        <h2>
          {{ selectedItem.spare_part_name_snapshot }}
        </h2>
      </div>
      <button
        type="button"
        :disabled="mutating"
        @click="closeItemEditor"
      >
        ×
      </button>
    </header>

    <dl>
      <div>
        <dt>
          {{
            t(
              'maintenance.calculation.demandList.items.original',
            )
          }}
        </dt>
        <dd>{{ selectedItem.original_quantity }}</dd>
      </div>
      <div>
        <dt>
          {{
            t(
              'maintenance.calculation.demandList.items.currentFinal',
            )
          }}
        </dt>
        <dd>{{ selectedItem.final_quantity }}</dd>
      </div>
    </dl>

    <label>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.items.newFinal',
          )
        }}
      </span>
      <input
        v-model="editQuantity"
        type="text"
        inputmode="decimal"
        autocomplete="off"
      >
    </label>

    <label>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.items.reason',
          )
        }}
      </span>
      <textarea
        v-model="editReason"
        maxlength="1000"
      />
    </label>

    <footer>
      <button
        type="button"
        :disabled="mutating"
        @click="closeItemEditor"
      >
        {{ t('common.cancel') }}
      </button>
      <button
        type="button"
        :disabled="(
          mutating
          || !editQuantity.trim()
          || !editReason.trim()
        )"
        @click="saveItem"
      >
        {{
          mutating
            ? t(
                'maintenance.calculation.demandList.items.saving',
              )
            : t(
                'maintenance.calculation.demandList.items.save',
              )
        }}
      </button>
    </footer>
  </section>
</div>
```

- [ ] **Step 10: Add the audit timeline**

Add:

```vue
<section class="demand-list-detail__timeline">
  <header>
    <h2>
      {{
        t(
          'maintenance.calculation.demandList.timeline.title',
        )
      }}
    </h2>
  </header>

  <ol v-if="current.events.length">
    <li
      v-for="event in current.events"
      :key="event.id"
    >
      <header>
        <strong>
          {{
            t(
              `maintenance.calculation.demandList.timeline.events.${event.event_type}`,
            )
          }}
        </strong>
        <time>{{ formatDate(event.occurred_at) }}</time>
      </header>
      <dl>
        <div>
          <dt>
            {{
              t(
                'maintenance.calculation.demandList.timeline.actor',
              )
            }}
          </dt>
          <dd>{{ event.actor_user_id }}</dd>
        </div>
        <div>
          <dt>
            {{
              t(
                'maintenance.calculation.demandList.timeline.roles',
              )
            }}
          </dt>
          <dd>{{ event.actor_roles_json.join(', ') }}</dd>
        </div>
        <div>
          <dt>
            {{
              t(
                'maintenance.calculation.demandList.timeline.request',
              )
            }}
          </dt>
          <dd>{{ event.request_id }}</dd>
        </div>
        <div v-if="event.idempotency_key">
          <dt>
            {{
              t(
                'maintenance.calculation.demandList.timeline.idempotency',
              )
            }}
          </dt>
          <dd>{{ event.idempotency_key }}</dd>
        </div>
      </dl>
      <details
        v-if="(
          event.before_summary_json
          || event.after_summary_json
        )"
      >
        <summary>
          {{
            t(
              'maintenance.calculation.demandList.timeline.details',
            )
          }}
        </summary>
        <pre v-if="event.before_summary_json">{{
          JSON.stringify(
            event.before_summary_json,
            null,
            2,
          )
        }}</pre>
        <pre v-if="event.after_summary_json">{{
          JSON.stringify(
            event.after_summary_json,
            null,
            2,
          )
        }}</pre>
      </details>
    </li>
  </ol>

  <p v-else>
    {{
      t(
        'maintenance.calculation.demandList.timeline.empty',
      )
    }}
  </p>
</section>
```

`JSON.stringify` is allowed for audit summary objects. It must not be used to transform Decimal item quantities.

- [ ] **Step 11: Add date formatting**

Add:

```ts
function formatDate(
  value: string,
): string {
  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(
        locale.value,
        {
          dateStyle: 'medium',
          timeStyle: 'short',
        },
      ).format(date)
}
```

- [ ] **Step 12: Add complete scoped styling for layout, table, timeline, and dialogs**

Required layout behaviors:

```text
max width 1480px
desktop facts grid
horizontal table overflow
visible focus and disabled states
dialog backdrop and centered panel
mobile one-column facts
mobile full-width action buttons
```

Use existing TDesign CSS variables and no hard-coded tenant/role color semantics.

- [ ] **Step 13: Run the route and decimal editor contracts**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="detail validates|detail item editing" `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Expected: selected tests pass.

- [ ] **Step 14: Run store stale-load and item-update regressions**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  --test-name-pattern="slower first load|dispose invalidates|update and submit|mutation failure preserves|decimal-string" `
  src/stores/maintenance/__tests__/demand-list.test.ts
```

Expected: PASS.

- [ ] **Step 15: Verify exact scope and stop**

At this checkpoint, the detail page exists and item editing works. Lifecycle buttons and transition interactions remain intentionally absent until Task 6.

No stage, commit, network, or push.

---

### Task 6: Add Lifecycle Interactions, Returned-ID Derivation, and Four-Locale GREEN

**Files:**
- Modify: `frontend/src/views/maintenance/calculations/DemandListDetail.vue`
- Modify: `frontend/src/i18n/locales/maintenance-calculation.ts`
- Test: `frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts`
- Test: `frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts`
- Regression: `frontend/src/stores/maintenance/__tests__/demand-list.test.ts`

**Interfaces:**
- Consumes:

```ts
DemandListLifecycleActions
DemandListAction
store.submit(key)
store.confirm(note, key)
store.publish(key)
store.derive(key)
store.voidList(key)
```

- Produces:
  - explicit lifecycle confirmation UI;
  - exact confirmation-note forwarding;
  - derive navigation to returned ID;
  - complete `demandList` locale shape in four languages.

- [ ] **Step 1: Add lifecycle imports and confirmation state**

Add imports:

```ts
import {
  DialogPlugin,
  MessagePlugin,
} from 'tdesign-vue-next'
import DemandListLifecycleActions from '@/components/maintenance/calculation/DemandListLifecycleActions.vue'
import type {
  DemandListAction,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
```

`MessagePlugin` already exists from Task 5; merge imports into one TDesign import.

Add:

```ts
const confirmationNoteOpen = ref(false)
const confirmationNote = ref('')
```

- [ ] **Step 2: Render lifecycle actions in the page header**

Replace the status-only secondary action arrangement with:

```vue
<template #secondaryActions>
  <MaintenanceStatusTag :status="current.status" />
</template>

<template #primaryActions>
  <DemandListLifecycleActions
    :status="current.status"
    :permissions="permissionStore.permissions"
    :busy="mutating"
    @select="selectLifecycleAction"
  />
</template>
```

- [ ] **Step 3: Add action selection**

Add:

```ts
function selectLifecycleAction(
  action: DemandListAction,
): void {
  if (mutating.value) return

  if (action === 'edit') {
    void focusItems()
    return
  }

  if (action === 'confirm') {
    confirmationNote.value = ''
    confirmationNoteOpen.value = true
    return
  }

  confirmLifecycle(action)
}
```

- [ ] **Step 4: Add unique mutation keys**

Add:

```ts
function requestKey(
  action: string,
): string {
  const id = current.value?.id ?? listId.value ?? 'unknown'

  return (
    `${action}:${id}:`
    + (
      globalThis.crypto?.randomUUID?.()
      ?? Date.now()
    )
  )
}
```

- [ ] **Step 5: Add simple transition execution**

Add:

```ts
type ConfirmableLifecycleAction =
  | 'submit'
  | 'publish'
  | 'derive'
  | 'void'

async function runLifecycle(
  action: ConfirmableLifecycleAction,
): Promise<void> {
  try {
    if (action === 'submit') {
      await store.submit(requestKey('submit'))
    } else if (action === 'publish') {
      await store.publish(requestKey('publish'))
    } else if (action === 'derive') {
      const derived = await store.derive(
        requestKey('derive'),
      )
      await router.push({
        name: 'maintenanceDemandListDetail',
        params: {
          listId: derived.id,
        },
      })
    } else {
      await store.voidList(requestKey('void'))
    }

    MessagePlugin.success(
      t(
        `maintenance.calculation.demandList.actions.${action}Success`,
      ),
    )
  } catch {
    // The store preserves the aggregate and normalized error.
  }
}
```

- [ ] **Step 6: Add explicit confirmation dialogs for submit, publish, derive, and void**

Add:

```ts
function confirmLifecycle(
  action: Exclude<DemandListAction, 'edit' | 'confirm'>,
): void {
  const dialog = DialogPlugin.confirm({
    header: t(
      `maintenance.calculation.demandList.dialogs.${action}Title`,
    ),
    body: t(
      `maintenance.calculation.demandList.dialogs.${action}Body`,
    ),
    confirmBtn: {
      content: t(
        `maintenance.calculation.demandList.actions.${action}`,
      ),
      theme: action === 'void'
        ? 'danger'
        : 'primary',
    },
    cancelBtn: t('common.cancel'),
    theme: 'warning',
    onConfirm: async () => {
      try {
        await runLifecycle(action)
      } finally {
        dialog.destroy()
      }
    },
    onClose: () => dialog.destroy(),
  })
}
```

The publish copy must explain immutability and derivation. The void copy must explain retained history.

- [ ] **Step 7: Add the page-owned confirmation-note dialog**

Add template after the item editor:

```vue
<div
  v-if="confirmationNoteOpen"
  class="demand-list-detail__dialog-backdrop"
>
  <section
    class="demand-list-detail__dialog"
    role="dialog"
    aria-modal="true"
    :aria-label="
      t(
        'maintenance.calculation.demandList.dialogs.confirmTitle',
      )
    "
  >
    <header>
      <div>
        <span>
          {{
            t(
              'maintenance.calculation.demandList.dialogs.confirmEyebrow',
            )
          }}
        </span>
        <h2>
          {{
            t(
              'maintenance.calculation.demandList.dialogs.confirmTitle',
            )
          }}
        </h2>
      </div>
    </header>

    <p>
      {{
        t(
          'maintenance.calculation.demandList.dialogs.confirmBody',
        )
      }}
    </p>

    <label>
      <span>
        {{
          t(
            'maintenance.calculation.demandList.dialogs.confirmationNote',
          )
        }}
      </span>
      <textarea
        v-model="confirmationNote"
        maxlength="1000"
      />
    </label>

    <footer>
      <button
        type="button"
        :disabled="mutating"
        @click="closeConfirmationNote"
      >
        {{ t('common.cancel') }}
      </button>
      <button
        type="button"
        :disabled="(
          mutating
          || !confirmationNote.trim()
        )"
        @click="submitConfirmationNote"
      >
        {{
          t(
            'maintenance.calculation.demandList.actions.confirm',
          )
        }}
      </button>
    </footer>
  </section>
</div>
```

Add:

```ts
function closeConfirmationNote(): void {
  if (mutating.value) return
  confirmationNoteOpen.value = false
  confirmationNote.value = ''
}

async function submitConfirmationNote(): Promise<void> {
  const note = confirmationNote.value.trim()

  if (!note || mutating.value) {
    return
  }

  try {
    await store.confirm(
      note,
      requestKey('confirm'),
    )
    confirmationNoteOpen.value = false
    confirmationNote.value = ''
    MessagePlugin.success(
      t(
        'maintenance.calculation.demandList.actions.confirmSuccess',
      ),
    )
  } catch {
    // Preserve the entered note on failure.
  }
}
```

The page forwards the note as a positional store argument. It does not construct an API `confirmation_note` field.

- [ ] **Step 8: Add complete English demand-list locale copy**

Inside `enUS`, after `comparison`, add:

```ts
demandList: {
  generation: {
    eyebrow: 'GOVERNED DEMAND OUTPUT',
    title: 'Create demand-list draft',
    description: 'Create an auditable DRAFT from the saved decisions in this completed comparison.',
    name: 'Demand-list name',
    notes: 'Description',
    create: 'Create DRAFT',
    creating: 'Creating…',
    unavailable: 'Generation requires a terminal group, a saved decision for every row, at least one successful candidate result per row, and demand-list edit permission.',
  },
  detail: {
    back: 'Back to comparison',
    loading: 'Loading demand list…',
    eyebrow: 'DEMAND-LIST LIFECYCLE',
    listId: 'Demand-list ID',
    versionNumber: 'Lineage version',
    optimisticVersion: 'Server version',
    lineage: 'Lineage',
    scenarioVersion: 'Scenario version',
    calculationGroup: 'Calculation group',
    currentPublished: 'Current published version',
    createdBy: 'Created by',
    createdAt: 'Created',
    updatedAt: 'Updated',
    lifecycle: 'Lifecycle',
    openDerivedFrom: 'Open source version #{id}',
    openSupersededBy: 'Open superseding version #{id}',
  },
  status: {
    DRAFT: 'Draft',
    PENDING_CONFIRMATION: 'Pending confirmation',
    CONFIRMED: 'Confirmed',
    PUBLISHED: 'Published',
    VOIDED: 'Voided',
  },
  items: {
    title: 'Demand items',
    description: 'Quantities remain exact decimal strings and published content remains immutable.',
    part: 'Spare part',
    unit: 'Unit',
    criticality: 'Criticality',
    model: 'Reliability model',
    mode: 'Execution mode',
    original: 'Original quantity',
    final: 'Final quantity',
    currentFinal: 'Current final quantity',
    newFinal: 'New final quantity',
    decision: 'Decision',
    risk: 'Risk',
    confirmed: 'Admin confirmed',
    actions: 'Actions',
    editTitle: 'Edit DRAFT item',
    reason: 'Adjustment reason',
    save: 'Save item',
    saving: 'Saving…',
    saved: 'Demand item saved',
  },
  actions: {
    edit: 'Edit items',
    submit: 'Submit',
    confirm: 'Confirm',
    publish: 'Publish',
    derive: 'Derive new DRAFT',
    void: 'Void',
    submitSuccess: 'Demand list submitted',
    confirmSuccess: 'Demand list confirmed',
    publishSuccess: 'Demand list published',
    deriveSuccess: 'Derived DRAFT created',
    voidSuccess: 'Demand list voided',
  },
  dialogs: {
    submitTitle: 'Submit demand list',
    submitBody: 'Submit this DRAFT for administrator confirmation? Item editing will stop after submission.',
    confirmEyebrow: 'ADMINISTRATOR CONFIRMATION',
    confirmTitle: 'Confirm demand list',
    confirmBody: 'Confirm the reviewed high-risk decisions and record a required confirmation note.',
    confirmationNote: 'Confirmation note',
    publishTitle: 'Publish demand list',
    publishBody: 'Publication makes this version immutable. Future changes require deriving a new DRAFT in the same lineage.',
    deriveTitle: 'Derive new DRAFT',
    deriveBody: 'Copy this published version into a new editable DRAFT while preserving the source version and lineage?',
    voidTitle: 'Void published version',
    voidBody: 'Voiding preserves history but removes this version from current published use when applicable.',
  },
  timeline: {
    title: 'Lifecycle audit',
    actor: 'Actor',
    roles: 'Roles',
    request: 'Request ID',
    idempotency: 'Idempotency key',
    details: 'Before and after summary',
    empty: 'No lifecycle events are available.',
    events: {
      CREATED: 'Created',
      ITEM_UPDATED: 'Item updated',
      SUBMITTED: 'Submitted',
      CONFIRMED: 'Confirmed',
      PUBLISHED: 'Published',
      DERIVED: 'Derived',
      VOIDED: 'Voided',
    },
  },
  errors: {
    invalidRoute: 'The demand-list link is invalid.',
  },
},
```

- [ ] **Step 9: Add complete Simplified Chinese copy**

Inside `zhCN`, add the same shape:

```ts
demandList: {
  generation: {
    eyebrow: '受控需求输出',
    title: '生成需求清单草稿',
    description: '根据当前计算比较中已保存的逐项决策，生成可审计的 DRAFT 需求清单。',
    name: '需求清单名称',
    notes: '说明',
    create: '生成 DRAFT',
    creating: '正在生成…',
    unavailable: '生成要求计算组已终止、每一行均已保存决策、每一行至少有一个成功候选结果，并且当前用户具有需求清单编辑权限。',
  },
  detail: {
    back: '返回结果比较',
    loading: '正在加载需求清单…',
    eyebrow: '需求清单生命周期',
    listId: '需求清单 ID',
    versionNumber: '谱系版本',
    optimisticVersion: '服务器版本',
    lineage: '版本谱系',
    scenarioVersion: '场景版本',
    calculationGroup: '计算组',
    currentPublished: '当前发布版本',
    createdBy: '创建人',
    createdAt: '创建时间',
    updatedAt: '更新时间',
    lifecycle: '生命周期',
    openDerivedFrom: '查看来源版本 #{id}',
    openSupersededBy: '查看替代版本 #{id}',
  },
  status: {
    DRAFT: '草稿',
    PENDING_CONFIRMATION: '待确认',
    CONFIRMED: '已确认',
    PUBLISHED: '已发布',
    VOIDED: '已作废',
  },
  items: {
    title: '需求条目',
    description: '数量始终保持精确小数字符串；已发布内容不可修改。',
    part: '器材',
    unit: '单位',
    criticality: '关键度',
    model: '可靠性模型',
    mode: '执行模式',
    original: '原始数量',
    final: '最终数量',
    currentFinal: '当前最终数量',
    newFinal: '新的最终数量',
    decision: '决策类型',
    risk: '风险',
    confirmed: '管理员已确认',
    actions: '操作',
    editTitle: '编辑 DRAFT 条目',
    reason: '调整理由',
    save: '保存条目',
    saving: '正在保存…',
    saved: '需求条目已保存',
  },
  actions: {
    edit: '编辑条目',
    submit: '提交',
    confirm: '确认',
    publish: '发布',
    derive: '派生新 DRAFT',
    void: '作废',
    submitSuccess: '需求清单已提交',
    confirmSuccess: '需求清单已确认',
    publishSuccess: '需求清单已发布',
    deriveSuccess: '已生成派生 DRAFT',
    voidSuccess: '需求清单已作废',
  },
  dialogs: {
    submitTitle: '提交需求清单',
    submitBody: '确认将该 DRAFT 提交管理员确认？提交后将停止条目编辑。',
    confirmEyebrow: '管理员确认',
    confirmTitle: '确认需求清单',
    confirmBody: '请确认已复核高风险决策，并填写必填的确认说明。',
    confirmationNote: '确认说明',
    publishTitle: '发布需求清单',
    publishBody: '发布后该版本不可修改；后续变更必须在同一谱系中派生新的 DRAFT。',
    deriveTitle: '派生新 DRAFT',
    deriveBody: '确认复制当前已发布版本，生成同一谱系下的新可编辑 DRAFT，并保留原版本？',
    voidTitle: '作废已发布版本',
    voidBody: '作废会保留完整历史；若该版本是当前发布版本，它将不再用于当前正式需求。',
  },
  timeline: {
    title: '生命周期审计',
    actor: '操作人',
    roles: '角色',
    request: '请求 ID',
    idempotency: '幂等键',
    details: '操作前后摘要',
    empty: '暂无生命周期事件。',
    events: {
      CREATED: '已创建',
      ITEM_UPDATED: '条目已更新',
      SUBMITTED: '已提交',
      CONFIRMED: '已确认',
      PUBLISHED: '已发布',
      DERIVED: '已派生',
      VOIDED: '已作废',
    },
  },
  errors: {
    invalidRoute: '需求清单链接无效。',
  },
},
```

- [ ] **Step 10: Add Korean and Russian core overrides while preserving shape**

Extend `koKR`:

```ts
demandList: {
  ...enUS.demandList,
  generation: {
    ...enUS.demandList.generation,
    title: '수요 목록 초안 생성',
    create: 'DRAFT 생성',
  },
  detail: {
    ...enUS.demandList.detail,
    back: '비교 결과로 돌아가기',
    lifecycle: '수명 주기',
  },
  status: {
    DRAFT: '초안',
    PENDING_CONFIRMATION: '확인 대기',
    CONFIRMED: '확인됨',
    PUBLISHED: '게시됨',
    VOIDED: '무효화됨',
  },
  actions: {
    ...enUS.demandList.actions,
    edit: '항목 편집',
    submit: '제출',
    confirm: '확인',
    publish: '게시',
    derive: '새 DRAFT 파생',
    void: '무효화',
  },
  dialogs: {
    ...enUS.demandList.dialogs,
    publishTitle: '수요 목록 게시',
    voidTitle: '게시 버전 무효화',
  },
},
```

Extend `ruRU`:

```ts
demandList: {
  ...enUS.demandList,
  generation: {
    ...enUS.demandList.generation,
    title: 'Создать черновик перечня потребности',
    create: 'Создать DRAFT',
  },
  detail: {
    ...enUS.demandList.detail,
    back: 'К сравнению результатов',
    lifecycle: 'Жизненный цикл',
  },
  status: {
    DRAFT: 'Черновик',
    PENDING_CONFIRMATION: 'Ожидает подтверждения',
    CONFIRMED: 'Подтверждён',
    PUBLISHED: 'Опубликован',
    VOIDED: 'Аннулирован',
  },
  actions: {
    ...enUS.demandList.actions,
    edit: 'Редактировать позиции',
    submit: 'Отправить',
    confirm: 'Подтвердить',
    publish: 'Опубликовать',
    derive: 'Создать новый DRAFT',
    void: 'Аннулировать',
  },
  dialogs: {
    ...enUS.demandList.dialogs,
    publishTitle: 'Опубликовать перечень',
    voidTitle: 'Аннулировать опубликованную версию',
  },
},
```

- [ ] **Step 11: Run all Task 6 focused contracts**

Run:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected:

```text
all focused tests pass
fail = 0
cancelled = 0
skipped = 0
todo = 0
```

- [ ] **Step 12: Run app type-check**

Run:

```powershell
npm run type-check
```

Expected: exit 0.

- [ ] **Step 13: Run app build**

Run:

```powershell
npm run build
```

Expected: exit 0. Existing chunk-size warnings are non-blocking; any TypeScript, Vue template, or Vite error is blocking.

- [ ] **Step 14: Verify exact eight-file feature scope**

Expected production/test paths:

```text
M  frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
M  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
M  frontend/src/views/maintenance/calculations/CalculationComparison.vue
M  frontend/src/router/maintenance.ts
M  frontend/src/i18n/locales/maintenance-calculation.ts
?? frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
?? frontend/src/views/maintenance/calculations/DemandListDetail.vue
?? frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

No additional path is allowed.

No stage, commit, network, or push.

---

### Task 7: Run the Final Task 6 Verification and Reach the Feature-Commit Boundary

**Files:**
- Verify: all eight Task 6 feature paths.
- Do not modify: documentation, backend, Go, Task 5 API/store/permission files, or unrelated frontend paths.

**Interfaces:**
- Consumes: completed Task 6 working tree and all prior evidence.
- Produces: final pre-commit evidence and an explicit feature-commit approval boundary.

- [ ] **Step 1: Verify branch, documentation baseline, and clean index**

Run:

```powershell
git branch --show-current
git log -1 --format="%H%n%P%n%s"
git diff --cached --name-only
git status --short
```

Expected:

```text
branch = feature/maintenance-frontend-plan05
HEAD = exact Task 0 documentation commit
documentation subject = docs: plan plan05 demand list lifecycle ui
index = empty
working paths = exact eight Task 6 feature files
```

- [ ] **Step 2: Run focused Task 6 tests**

Run:

```powershell
cd frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: all selected tests pass with no skip or todo.

- [ ] **Step 3: Run the complete frontend test suite**

Run:

```powershell
npm run test
```

Expected:

```text
test count > 398
pass = test count
fail = 0
cancelled = 0
skipped = 0
todo = 0
```

- [ ] **Step 4: Run type-check and production build**

Run:

```powershell
npm run type-check
npm run build
```

Expected: both exit 0.

- [ ] **Step 5: Run static contract scans**

Run checks that assert:

```text
DemandListLifecycleActions has no store/router/dialog/raw-role dependency
CalculationComparison uses canOfferDemandListGeneration
CalculationComparison routes with created.id
DemandListDetail uses store.load and store.dispose
DemandListDetail uses text + inputmode=decimal for quantity
DemandListDetail forwards note to store.confirm
DemandListDetail routes with derived.id
no quantity Number/parseFloat/parseInt conversion
no tenant selector
all four demandList locale key shapes match
```

The static scanner must distinguish allowed route-ID parsing from forbidden Decimal conversion. It must not reject the `Number(raw)` used by `positiveInteger`.

- [ ] **Step 6: Run exact scope and whitespace gates**

Run:

```powershell
cd ..
git diff --check
git diff --cached --check
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --name-only
```

Expected:

```text
tracked modifications = exactly five approved files
untracked additions = exactly three approved files
staged files = none
total feature paths = eight
```

Reject changes under:

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/i18n/locales/zh-CN.ts
frontend/src/i18n/locales/en-US.ts
frontend/src/i18n/locales/ko-KR.ts
frontend/src/i18n/locales/ru-RU.ts
extensions/maintenance-api/
internal/
```

- [ ] **Step 7: Capture complete pre-commit evidence**

Evidence must include:

```text
branch and HEAD
documentation commit parent/subject
focused test output
complete frontend test output
type-check output
build output
static-contract output
tracked/untracked/staged path lists
eight feature file SHA256 values
complete working-tree patch including untracked files
source snapshot of all eight feature files
evidence SHA256 manifest
```

Do not stage or commit while capturing evidence.

- [ ] **Step 8: Request explicit feature-commit approval**

Required approval phrase:

```text
批准提交 Plan 05-3C Task 6
```

Do not create the feature commit before this approval.

- [ ] **Step 9: After approval, stage exactly the eight feature paths**

Run:

```powershell
git add -- `
  frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts `
  frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue `
  frontend/src/views/maintenance/calculations/CalculationComparison.vue `
  frontend/src/views/maintenance/calculations/DemandListDetail.vue `
  frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  frontend/src/router/maintenance.ts `
  frontend/src/i18n/locales/maintenance-calculation.ts
```

Verify staged scope, empty unstaged diff, empty untracked set, and `git diff --cached --check`.

- [ ] **Step 10: Create the local feature commit**

Run:

```powershell
git commit -m "feat: add demand list lifecycle ui"
```

Expected:

```text
parent = Task 0 documentation commit
commit paths = exact eight feature files
modified/new = 5/3
worktree = clean
index = empty
remote tracking ref unchanged
push = not performed
```

- [ ] **Step 11: Keep push as a separate approval boundary**

Required push phrase:

```text
批准推送 Plan 05-3C Task 6 并更新 PR #4
```

A later push script must use strict fast-forward only, must not force-push, and must preserve PR #4 as an open draft unless the user explicitly changes that instruction.

---

## Task 6 Completion Evidence

Task 6 is complete only when:

- the approved design and plan are committed separately from feature code;
- the conservative generation helper is pure and capability-driven;
- calculation comparison creates through the Task 5 store and routes with the returned ID;
- the demand-list detail route is authenticated, initialized, hidden, and stable;
- invalid route IDs do not call the API;
- detail loading uses the stale-safe Task 5 store and disposes route-owned requests;
- DRAFT item editing uses exact strings and a required reason;
- all non-DRAFT item states are read-only;
- the lifecycle action component is presentation-only;
- submit, confirm, publish, derive, and void use explicit user interactions;
- confirmation forwards the exact note to the store;
- derive routes to the returned new DRAFT ID;
- lineage links and audit events are rendered from server fields;
- all four calculation locale objects expose the same demand-list key shape;
- focused tests pass;
- the complete frontend suite exceeds the 398-test baseline and is fully green;
- type-check and production build pass;
- the final feature diff is exactly five modified and three new files;
- no backend, Go, tenant selector, list page, menu entry, inventory, procurement, review, or report scope is introduced;
- the feature commit is created only after explicit approval;
- push remains a separate explicit approval and strict fast-forward operation.

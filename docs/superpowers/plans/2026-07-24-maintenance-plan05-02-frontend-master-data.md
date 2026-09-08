# Plan 05-2 Native Frontend Shell and Master Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the native WeKnora maintenance menu, route shell, typed API layer, tenant dashboard, and usable master-data pages for equipment, configurations, parts, spare parts, reliability, warehouses, inventory summaries, suppliers, substitutions, kit rules, lots and serials.

**Architecture:** Extend the existing `/platform` Vue Router tree and left menu rather than adding a second application shell. Build a typed maintenance API client on top of `frontend/src/utils/request.ts`, reuse Pinia only for cross-page state, use registry-driven generic master-data tables for repeated CRUD behavior, and reserve specialized detail components for configuration trees, spare-part relationships, lots and serials.

**Tech Stack:** Vue 3.5, TypeScript 6, Vite 7, Pinia 3, Vue Router 4.5, TDesign Vue Next 1.19, Axios through the existing request wrapper, Node `test` through `tsx --test`, Python 3.11, FastAPI, pytest, Ruff.

## Global Constraints

- Phase 05-1 security gate must be green before this plan starts.
- Use the existing WeKnora `Menu`, `/platform` layout, theme, user menu, command palette and auth store.
- Do not create a second permanent sidebar or iframe.
- The frontend calls `/api/maintenance/*`, which WeKnora proxies to Maintenance API `/api/v1/*`.
- All page data is current-tenant data from actor-aware API responses.
- `viewer` sees pages and exports but no write controls; `contributor` sees ordinary master-data actions; `admin` additionally sees high-risk controls introduced in later plans.
- Common list/editor behavior is registry-driven; configuration trees and spare-part detail tabs are explicit specialized components.
- Dashboard refreshes every 30 seconds, stops while the document is hidden or the route leaves `/platform/maintenance`, and never overwrites local edits.
- Import preview does not write data; execution revalidates server-side.
- Existing knowledge-base, agent, organization, settings and chat routes must remain unchanged.

---

## File Map

**Create:**

```text
frontend/src/api/maintenance/client.ts
frontend/src/api/maintenance/types.ts
frontend/src/api/maintenance/dashboard.ts
frontend/src/api/maintenance/master-data.ts
frontend/src/api/maintenance/imports.ts
frontend/src/api/maintenance/__tests__/client.test.ts
frontend/src/api/maintenance/__tests__/query.test.ts
frontend/src/stores/maintenance/permissions.ts
frontend/src/stores/maintenance/dashboard.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
frontend/src/views/maintenance/MaintenanceShell.vue
frontend/src/views/maintenance/dashboard/MaintenanceDashboard.vue
frontend/src/views/maintenance/master-data/MasterDataHome.vue
frontend/src/views/maintenance/master-data/MasterDataListPage.vue
frontend/src/views/maintenance/master-data/ConfigurationDetail.vue
frontend/src/views/maintenance/master-data/SparePartDetail.vue
frontend/src/components/maintenance/common/MaintenancePageHeader.vue
frontend/src/components/maintenance/common/MaintenanceMetricCard.vue
frontend/src/components/maintenance/common/MaintenanceStatusTag.vue
frontend/src/components/maintenance/common/MaintenanceSourceTag.vue
frontend/src/components/maintenance/common/MaintenanceRiskTag.vue
frontend/src/components/maintenance/common/MaintenanceEmptyState.vue
frontend/src/components/maintenance/common/MaintenanceErrorState.vue
frontend/src/components/maintenance/common/MaintenanceAuditTimeline.vue
frontend/src/components/maintenance/master-data/MasterDataTable.vue
frontend/src/components/maintenance/master-data/MasterDataEditorDrawer.vue
frontend/src/components/maintenance/master-data/MasterDataRegistry.ts
frontend/src/components/maintenance/master-data/ConfigurationTree.vue
frontend/src/components/maintenance/master-data/SparePartOverview.vue
frontend/src/components/maintenance/master-data/SparePartApplicability.vue
frontend/src/components/maintenance/master-data/SparePartInventory.vue
frontend/src/components/maintenance/master-data/SparePartSubstitutions.vue
frontend/src/components/maintenance/master-data/SparePartKitRules.vue
frontend/src/components/maintenance/master-data/SparePartReliability.vue
frontend/src/components/maintenance/master-data/SparePartEvidence.vue
frontend/src/components/maintenance/import/MasterDataImportDialog.vue
frontend/src/components/maintenance/import/ImportFieldMapping.vue
frontend/src/components/maintenance/import/ImportValidationTable.vue
frontend/src/components/maintenance/import/ImportTaskStatus.vue
frontend/src/composables/maintenance/usePageVisibilityPolling.ts
frontend/src/composables/maintenance/useServerTable.ts
frontend/src/composables/maintenance/__tests__/polling.test.ts
frontend/src/assets/img/maintenance.svg
frontend/src/types/maintenance-menu.d.ts
extensions/maintenance-api/app/api/v1/dashboard.py
extensions/maintenance-api/app/services/dashboard_service.py
extensions/maintenance-api/app/schemas/dashboard.py
extensions/maintenance-api/app/exporters/master_data_excel.py
extensions/maintenance-api/tests/api/test_dashboard_api.py
extensions/maintenance-api/tests/services/test_dashboard_service.py
extensions/maintenance-api/tests/exporters/test_master_data_excel.py
```

**Modify:**

```text
frontend/src/router/index.ts
frontend/src/stores/menu.ts
frontend/src/components/menu.vue
frontend/src/i18n/locales/zh-CN.json
frontend/src/i18n/locales/en-US.json
frontend/package.json
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/api/v1/master_data/*.py
extensions/maintenance-api/app/services/import_service.py
extensions/maintenance-api/app/schemas/import_data.py
extensions/maintenance-api/README.md
```

---

### Task 1: Create the Typed Maintenance API Client

**Files:**
- Create: `frontend/src/api/maintenance/types.ts`
- Create: `frontend/src/api/maintenance/client.ts`
- Test: `frontend/src/api/maintenance/__tests__/client.test.ts`
- Test: `frontend/src/api/maintenance/__tests__/query.test.ts`

**Interfaces:**
- Produces: `maintenanceGet`, `maintenancePost`, `maintenancePut`, `maintenancePatch`, `maintenanceDelete`, `buildQuery`, `MaintenanceResponse<T>`, `PageData<T>`.
- Consumed by: every later frontend task.

- [ ] **Step 1: Write failing client tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { buildQuery, unwrapMaintenanceResponse } from '../client'


test('buildQuery omits null values and preserves false', () => {
  assert.equal(
    buildQuery({ page: 2, keyword: null, include_inactive: false, sort_by: 'code' }),
    'page=2&include_inactive=false&sort_by=code',
  )
})

test('unwrap returns data and metadata together', () => {
  const result = unwrapMaintenanceResponse({
    success: true,
    data: { id: 7 },
    message: 'ok',
    meta: { request_id: 'r-1', tenant_id: 't-1', version: 3 },
  })
  assert.deepEqual(result, { data: { id: 7 }, meta: { request_id: 'r-1', tenant_id: 't-1', version: 3 } })
})

test('unwrap rejects malformed responses', () => {
  assert.throws(() => unwrapMaintenanceResponse({ data: {} } as never), /Invalid maintenance response/)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/api/maintenance/__tests__/client.test.ts src/api/maintenance/__tests__/query.test.ts
```

Expected: FAIL because the maintenance client does not exist.

- [ ] **Step 3: Implement the response and query contracts**

```ts
export interface ApiMeta {
  request_id: string
  tenant_id: string
  version?: number
}

export interface MaintenanceResponse<T> {
  success: true
  data: T
  message: string
  meta: ApiMeta
}

export interface PageData<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface MaintenanceResult<T> {
  data: T
  meta: ApiMeta
}
```

```ts
import { del, get, patch, post, put } from '@/utils/request'
import type { MaintenanceResponse, MaintenanceResult } from './types'

const PREFIX = '/api/maintenance'

export function buildQuery(values: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value))
  })
  return params.toString()
}

export function unwrapMaintenanceResponse<T>(response: MaintenanceResponse<T>): MaintenanceResult<T> {
  if (!response?.success || !response.meta?.request_id || !response.meta?.tenant_id) {
    throw new Error('Invalid maintenance response')
  }
  return { data: response.data, meta: response.meta }
}

export async function maintenanceGet<T>(path: string): Promise<MaintenanceResult<T>> {
  return unwrapMaintenanceResponse(await get<MaintenanceResponse<T>>(`${PREFIX}${path}`))
}

export async function maintenancePost<T>(path: string, body: unknown, config?: unknown): Promise<MaintenanceResult<T>> {
  return unwrapMaintenanceResponse(await post<MaintenanceResponse<T>>(`${PREFIX}${path}`, body as object, config))
}

export async function maintenancePut<T>(path: string, body: unknown): Promise<MaintenanceResult<T>> {
  return unwrapMaintenanceResponse(await put<MaintenanceResponse<T>>(`${PREFIX}${path}`, body as object))
}

export async function maintenancePatch<T>(path: string, body: unknown): Promise<MaintenanceResult<T>> {
  return unwrapMaintenanceResponse(await patch<MaintenanceResponse<T>>(`${PREFIX}${path}`, body as object))
}

export async function maintenanceDelete<T>(path: string, body?: unknown): Promise<MaintenanceResult<T>> {
  return unwrapMaintenanceResponse(await del<MaintenanceResponse<T>>(`${PREFIX}${path}`, body))
}
```

Add this exact helper to `frontend/src/utils/request.ts` before using the client:

```ts
export function patch<T = any>(url: string, data = {}, config?: any): Promise<T> {
  return instance.patch<T>(url, data, config) as unknown as Promise<T>
}
```

Add stable error normalization:

```ts
export interface MaintenanceClientError {
  status?: number
  code: string
  message: string
  details?: unknown
  request_id?: string
  retryable: boolean
}
```

- [ ] **Step 4: Run tests and type check**

```powershell
npm run test -- src/api/maintenance/__tests__/*.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance frontend/src/utils/request.ts
git commit -m "feat: add typed maintenance frontend client"
```

---

### Task 2: Add Maintenance Permission Store

**Files:**
- Create: `frontend/src/stores/maintenance/permissions.ts`
- Test: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`
- Modify: `frontend/src/stores/auth.ts` only when a typed role accessor is missing

**Interfaces:**
- Consumes: existing `useAuthStore().hasRole` and active tenant role.
- Produces: `useMaintenancePermissionsStore`, `canView`, `canMaintain`, `canAdminister`, `can(action)`.

- [ ] **Step 1: Write failing permission matrix tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { permissionsForRole } from '../permissions'


test('viewer is read only', () => {
  const p = permissionsForRole('viewer')
  assert.equal(p.view, true)
  assert.equal(p.editMasterData, false)
  assert.equal(p.runCalculation, false)
  assert.equal(p.adjustInventory, false)
})

test('contributor can maintain ordinary workflows', () => {
  const p = permissionsForRole('contributor')
  assert.equal(p.editMasterData, true)
  assert.equal(p.runCalculation, true)
  assert.equal(p.reserveInventory, true)
  assert.equal(p.adjustInventory, false)
})

test('owner and admin map to maintenance admin', () => {
  for (const role of ['owner', 'admin'] as const) {
    assert.equal(permissionsForRole(role).publishRules, true)
  }
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: FAIL because the permission map is missing.

- [ ] **Step 3: Implement explicit capabilities**

```ts
export type TenantRole = 'owner' | 'admin' | 'contributor' | 'viewer'

export interface MaintenancePermissions {
  view: boolean
  exportData: boolean
  editMasterData: boolean
  importMasterData: boolean
  runCalculation: boolean
  handleReview: boolean
  reserveInventory: boolean
  issueReturnInventory: boolean
  transferInventory: boolean
  adjustInventory: boolean
  confirmHighRisk: boolean
  publishRules: boolean
}

export function permissionsForRole(role: TenantRole): MaintenancePermissions {
  const admin = role === 'owner' || role === 'admin'
  const contributor = admin || role === 'contributor'
  return {
    view: true,
    exportData: true,
    editMasterData: contributor,
    importMasterData: contributor,
    runCalculation: contributor,
    handleReview: contributor,
    reserveInventory: contributor,
    issueReturnInventory: contributor,
    transferInventory: admin,
    adjustInventory: admin,
    confirmHighRisk: admin,
    publishRules: admin,
  }
}
```

Expose a computed Pinia store that derives the current tenant role from the existing auth store. Do not persist a second role in local storage.

- [ ] **Step 4: Run tests**

```powershell
npm run test -- src/stores/maintenance/__tests__/permissions.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/stores/maintenance/permissions.ts frontend/src/stores/maintenance/__tests__/permissions.test.ts frontend/src/stores/auth.ts
git commit -m "feat: add maintenance frontend permissions"
```

---

### Task 3: Register Native Routes and Nested Menu

**Files:**
- Create: `frontend/src/views/maintenance/MaintenanceShell.vue`
- Create: `frontend/src/assets/img/maintenance.svg`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/stores/menu.ts`
- Modify: `frontend/src/components/menu.vue`
- Modify: locale files
- Test: `frontend/src/stores/maintenance/__tests__/menu.test.ts`

**Interfaces:**
- Produces: `maintenanceRoutes`, `maintenanceMenuChildren`, route names used by all later plans.

- [ ] **Step 1: Write failing route/menu tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { maintenanceMenuChildren } from '@/stores/maintenance/menu-definition'
import { maintenanceRouteRecords } from '@/router/maintenance'


test('maintenance menu has exactly seven ordered entries', () => {
  assert.deepEqual(
    maintenanceMenuChildren.map(item => item.path),
    ['maintenance/dashboard', 'maintenance/master-data', 'maintenance/scenarios',
     'maintenance/calculations', 'maintenance/inventory-gap', 'maintenance/reviews',
     'maintenance/reports'],
  )
})

test('all maintenance routes require authentication and initialization', () => {
  assert.ok(maintenanceRouteRecords.every(route => route.meta?.requiresAuth && route.meta?.requiresInit))
})
```

Create `frontend/src/router/maintenance.ts` and `frontend/src/stores/maintenance/menu-definition.ts` to keep pure definitions testable.

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/stores/maintenance/__tests__/menu.test.ts
```

Expected: FAIL because route and menu definitions are absent.

- [ ] **Step 3: Implement route and menu definitions**

```ts
export const maintenanceRouteRecords: RouteRecordRaw[] = [
  {
    path: 'maintenance',
    component: () => import('@/views/maintenance/MaintenanceShell.vue'),
    redirect: '/platform/maintenance/dashboard',
    meta: { requiresInit: true, requiresAuth: true },
    children: [
      { path: 'dashboard', name: 'maintenanceDashboard', component: () => import('@/views/maintenance/dashboard/MaintenanceDashboard.vue') },
      { path: 'master-data', name: 'maintenanceMasterData', component: () => import('@/views/maintenance/master-data/MasterDataHome.vue') },
      { path: 'scenarios', name: 'maintenanceScenarios', component: () => import('@/views/maintenance/scenarios/ScenarioList.vue') },
      { path: 'calculations', name: 'maintenanceCalculations', component: () => import('@/views/maintenance/calculations/CalculationList.vue') },
      { path: 'inventory-gap', name: 'maintenanceInventoryGap', component: () => import('@/views/maintenance/inventory-gap/InventoryGapPage.vue') },
      { path: 'reviews', name: 'maintenanceReviews', component: () => import('@/views/maintenance/reviews/ReviewList.vue') },
      { path: 'reports', name: 'maintenanceReports', component: () => import('@/views/maintenance/reports/ReportCenter.vue') },
    ].map(route => ({ ...route, meta: { requiresInit: true, requiresAuth: true } })),
  },
]
```

For pages delivered in later plans, create small route-safe placeholders under their final paths containing only a title and “该功能将在对应实施阶段启用”; remove each placeholder in its owning phase. This is acceptable scaffolding because the route shell is the independently testable deliverable and the text is not a product claim.

Add menu item:

```ts
{
  title: '', titleKey: 'menu.maintenance', icon: 'maintenance', path: 'maintenance',
  childrenPath: 'maintenance', children: maintenanceMenuChildren,
}
```

In `menu.vue`, render nested maintenance children only while the current path begins with `/platform/maintenance`; clicking the parent routes to dashboard and expands the group. The existing global collapsed state controls icon-only mode.

- [ ] **Step 4: Run tests, type check and build**

```powershell
npm run test -- src/stores/maintenance/__tests__/menu.test.ts
npm run type-check
npm run build
```

Expected: PASS; existing routes remain present.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/router frontend/src/stores/menu.ts frontend/src/stores/maintenance/menu-definition.ts frontend/src/components/menu.vue frontend/src/views/maintenance frontend/src/assets/img/maintenance.svg frontend/src/i18n/locales
git commit -m "feat: add native maintenance navigation"
```

---

### Task 4: Build Common Maintenance UI Components

**Files:**
- Create: common components listed in the file map
- Create: `frontend/src/components/maintenance/common/status.ts`
- Test: `frontend/src/components/maintenance/common/__tests__/status.test.ts`

**Interfaces:**
- Produces: source/risk/status mappings and reusable page states.
- Consumed by: all later UI tasks.

- [ ] **Step 1: Write failing mapping tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { sourceLabel, riskTheme, lifecycleLabel } from '../status'


test('source labels preserve authority distinctions', () => {
  assert.equal(sourceLabel('USER_CONFIRMED', 'zh-CN'), '人工确认')
  assert.equal(sourceLabel('LLM_INFERRED', 'zh-CN'), '模型推断')
})

test('high risk uses danger theme', () => {
  assert.equal(riskTheme('HIGH'), 'danger')
})

test('unknown status remains visible instead of disappearing', () => {
  assert.equal(lifecycleLabel('CUSTOM_STATE', 'zh-CN'), 'CUSTOM_STATE')
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/common/__tests__/status.test.ts
```

Expected: FAIL because mappings do not exist.

- [ ] **Step 3: Implement exact mappings and components**

```ts
const SOURCE_LABELS = {
  USER_CONFIRMED: { 'zh-CN': '人工确认', 'en-US': 'User confirmed' },
  USER_PROVIDED: { 'zh-CN': '用户录入', 'en-US': 'User provided' },
  MASTER_DATA: { 'zh-CN': '主数据', 'en-US': 'Master data' },
  KNOWLEDGE_RETRIEVED: { 'zh-CN': '知识检索', 'en-US': 'Retrieved evidence' },
  SYSTEM_DEFAULT: { 'zh-CN': '系统默认', 'en-US': 'System default' },
  LLM_INFERRED: { 'zh-CN': '模型推断', 'en-US': 'Model inferred' },
} as const
```

Components requirements:

- `MaintenancePageHeader`: title, description, status/version badges, primary/secondary action slots.
- `MaintenanceMetricCard`: label, value, suffix, trend, loading skeleton, click action.
- `MaintenanceErrorState`: normalized error, request ID, retry event, no raw stack.
- `MaintenanceAuditTimeline`: actor, action, timestamp, before/after summary, pagination.
- `MaintenanceSourceTag`: tooltip includes evidence reference when supplied.
- `MaintenanceRiskTag`: LOW/MEDIUM/HIGH/BLOCKING themes.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/common/__tests__/status.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/maintenance/common
git commit -m "feat: add maintenance ui primitives"
```

---

### Task 5: Add Tenant-Scoped Dashboard Aggregation API

**Files:**
- Create: `extensions/maintenance-api/app/schemas/dashboard.py`
- Create: `extensions/maintenance-api/app/services/dashboard_service.py`
- Create: `extensions/maintenance-api/app/api/v1/dashboard.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Test: `extensions/maintenance-api/tests/services/test_dashboard_service.py`
- Test: `extensions/maintenance-api/tests/api/test_dashboard_api.py`

**Interfaces:**
- Produces: `GET /api/v1/dashboard/summary`, `DashboardSummary`.
- Consumed by: Task 6.

- [ ] **Step 1: Write failing dashboard tests**

```python
def test_dashboard_counts_only_actor_tenant(session, actor_viewer, tenant_one_data, tenant_two_data):
    summary = DashboardService().summary(session, actor_viewer)
    assert summary.active_equipment_count == tenant_one_data.equipment_count
    assert summary.active_spare_part_count == tenant_one_data.spare_part_count
    assert summary.running_calculation_count == tenant_one_data.running_calculations


def test_dashboard_api_returns_one_aggregate_response(client, viewer_headers):
    response = client.get("/api/v1/dashboard/summary", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["tenant_id"] == "t-1"
    assert set(body["data"]) >= {"metrics", "recent_tasks", "risk_items", "risk_distribution"}
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_dashboard_service.py tests/api/test_dashboard_api.py -v
```

Expected: FAIL because the dashboard aggregate does not exist.

- [ ] **Step 3: Implement one aggregate query service**

```python
class DashboardMetric(BaseModel):
    key: str
    value: int | Decimal
    trend: Decimal | None = None


class DashboardSummary(BaseModel):
    metrics: list[DashboardMetric]
    recent_tasks: list[RecentTask]
    risk_items: list[RiskItem]
    risk_distribution: dict[str, int]
    generated_at: datetime
```

Use bounded queries:

- counts with `SELECT count(*)` filtered by tenant and state;
- recent tasks limited to 10 across scenario/calculation/review/report types;
- risk items limited to 10;
- no loading of complete inventory or calculation result collections.

The endpoint requires viewer and returns `Cache-Control: no-store` because data is tenant-specific and operational.

- [ ] **Step 4: Run tests and performance query-count assertion**

```powershell
python -m pytest tests/services/test_dashboard_service.py tests/api/test_dashboard_api.py -v
```

Expected: PASS; test asserts the service performs at most 12 SQL statements for a populated dashboard.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/dashboard.py extensions/maintenance-api/app/services/dashboard_service.py extensions/maintenance-api/app/api/v1/dashboard.py extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/tests/services/test_dashboard_service.py extensions/maintenance-api/tests/api/test_dashboard_api.py
git commit -m "feat: add maintenance dashboard summary"
```

---

### Task 6: Build Dashboard Store, Polling and Page

**Files:**
- Create: `frontend/src/api/maintenance/dashboard.ts`
- Create: `frontend/src/stores/maintenance/dashboard.ts`
- Create: `frontend/src/composables/maintenance/usePageVisibilityPolling.ts`
- Create: `frontend/src/views/maintenance/dashboard/MaintenanceDashboard.vue`
- Test: `frontend/src/composables/maintenance/__tests__/polling.test.ts`
- Test: `frontend/src/stores/maintenance/__tests__/dashboard.test.ts`

**Interfaces:**
- Consumes: dashboard API from Task 5 and common components.
- Produces: dashboard page and `usePageVisibilityPolling`.

- [ ] **Step 1: Write failing polling tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { createPollingController } from '../usePageVisibilityPolling'


test('polling runs immediately and then every interval', async () => {
  const calls: number[] = []
  const timers = fakeTimers()
  const controller = createPollingController({ intervalMs: 30_000, run: async () => { calls.push(timers.now) }, timers })
  await controller.start()
  assert.deepEqual(calls, [0])
  await timers.advanceBy(30_000)
  assert.deepEqual(calls, [0, 30_000])
})

test('hidden state pauses and visible state refreshes immediately', async () => {
  const calls: number[] = []
  const controller = createPollingController({ intervalMs: 30_000, run: async () => { calls.push(Date.now()) } })
  await controller.start()
  controller.setVisible(false)
  controller.setVisible(true)
  assert.equal(calls.length, 2)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/composables/maintenance/__tests__/polling.test.ts src/stores/maintenance/__tests__/dashboard.test.ts
```

Expected: FAIL because polling and store do not exist.

- [ ] **Step 3: Implement store and page behavior**

```ts
export const useMaintenanceDashboardStore = defineStore('maintenanceDashboard', () => {
  const summary = ref<DashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref<MaintenanceClientError | null>(null)

  async function refresh(): Promise<void> {
    if (loading.value) return
    loading.value = true
    try {
      summary.value = (await getDashboardSummary()).data
      error.value = null
    } catch (value) {
      error.value = normalizeMaintenanceError(value)
    } finally {
      loading.value = false
    }
  }
  return { summary, loading, error, refresh }
})
```

`MaintenanceDashboard.vue` displays metrics, recent tasks, risk ranking, risk distribution and quick actions. The poller is active only when `route.path.startsWith('/platform/maintenance')` and `document.visibilityState === 'visible'`. It refreshes store data but never mutates forms in other stores.

- [ ] **Step 4: Run tests, type check and build**

```powershell
npm run test -- src/composables/maintenance/__tests__/polling.test.ts src/stores/maintenance/__tests__/dashboard.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/dashboard.ts frontend/src/stores/maintenance/dashboard.ts frontend/src/composables/maintenance/usePageVisibilityPolling.ts frontend/src/views/maintenance/dashboard frontend/src/composables/maintenance/__tests__ frontend/src/stores/maintenance/__tests__/dashboard.test.ts
git commit -m "feat: add live maintenance dashboard"
```

---

### Task 7: Build Registry-Driven Master Data Lists and Editors

**Files:**
- Create: `frontend/src/components/maintenance/master-data/MasterDataRegistry.ts`
- Create: `frontend/src/composables/maintenance/useServerTable.ts`
- Create: `frontend/src/components/maintenance/master-data/MasterDataTable.vue`
- Create: `frontend/src/components/maintenance/master-data/MasterDataEditorDrawer.vue`
- Create: `frontend/src/views/maintenance/master-data/MasterDataHome.vue`
- Create: `frontend/src/views/maintenance/master-data/MasterDataListPage.vue`
- Create: `frontend/src/api/maintenance/master-data.ts`
- Test: `frontend/src/components/maintenance/master-data/__tests__/registry.test.ts`
- Test: `frontend/src/composables/maintenance/__tests__/server-table.test.ts`

**Interfaces:**
- Produces: `MasterDataResourceDefinition`, `MASTER_DATA_RESOURCES`, generic list/editor page.
- Consumed by: Task 8 and Task 9.

- [ ] **Step 1: Write failing registry tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { MASTER_DATA_RESOURCES } from '../MasterDataRegistry'


test('standard resources expose endpoint, key and editable fields', () => {
  const spare = MASTER_DATA_RESOURCES.spareParts
  assert.equal(spare.endpoint, '/v1/master-data/spare-parts')
  assert.equal(spare.rowKey, 'id')
  assert.ok(spare.columns.some(column => column.key === 'code'))
  assert.ok(spare.form.some(field => field.key === 'criticality'))
})

test('viewer actions never include writes', () => {
  for (const resource of Object.values(MASTER_DATA_RESOURCES)) {
    assert.equal(resource.actions({ view: true, editMasterData: false }).some(action => action.kind !== 'view'), false)
  }
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/master-data/__tests__/registry.test.ts src/composables/maintenance/__tests__/server-table.test.ts
```

Expected: FAIL because registry and table state are missing.

- [ ] **Step 3: Implement explicit resource definitions**

```ts
export interface MasterDataResourceDefinition<T extends Record<string, unknown> = Record<string, unknown>> {
  key: string
  titleKey: string
  endpoint: string
  rowKey: keyof T
  columns: Array<{ key: keyof T; titleKey: string; width?: number; formatter?: string }>
  form: Array<{ key: keyof T; labelKey: string; control: 'text' | 'number' | 'select' | 'date' | 'switch'; required?: boolean; options?: unknown[] }>
  actions: (permissions: MaintenancePermissions) => Array<{ key: string; kind: 'view' | 'edit' | 'deactivate' }>
}
```

Define resources for:

```text
equipmentModels, configurations, parts, spareParts, reliabilityProfiles,
warehouses, inventorySummaries, suppliers, supplierOffers, failureModes,
maintenanceActivities, substitutions, kitRules, lots, serialItems
```

The generic page owns query, pagination, sorting, loading, errors and drawer state. It never embeds resource-specific business rules; those remain in backend schemas and specialized pages.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/master-data/__tests__/registry.test.ts src/composables/maintenance/__tests__/server-table.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/master-data.ts frontend/src/components/maintenance/master-data/MasterDataRegistry.ts frontend/src/components/maintenance/master-data/MasterDataTable.vue frontend/src/components/maintenance/master-data/MasterDataEditorDrawer.vue frontend/src/composables/maintenance/useServerTable.ts frontend/src/views/maintenance/master-data frontend/src/components/maintenance/master-data/__tests__ frontend/src/composables/maintenance/__tests__/server-table.test.ts
git commit -m "feat: add maintenance master data workspace"
```

---

### Task 8: Build Configuration Tree and Spare-Part Detail Views

**Files:**
- Create: specialized components and views listed in the file map
- Modify: `frontend/src/router/maintenance.ts`
- Test: `frontend/src/components/maintenance/master-data/__tests__/configuration-tree.test.ts`
- Test: `frontend/src/components/maintenance/master-data/__tests__/spare-part-tabs.test.ts`

**Interfaces:**
- Consumes: master-data API and permission store.
- Produces: configuration and spare-part detail routes.

- [ ] **Step 1: Write failing tree and tab model tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { buildConfigurationTree } from '../ConfigurationTree'
import { SPARE_PART_TABS } from '../SparePartOverview'


test('configuration tree preserves parent-child order', () => {
  const tree = buildConfigurationTree([
    { id: 2, parent_id: 1, sort_order: 2, name: 'Child B' },
    { id: 1, parent_id: null, sort_order: 1, name: 'Root' },
    { id: 3, parent_id: 1, sort_order: 1, name: 'Child A' },
  ])
  assert.deepEqual(tree[0].children.map(node => node.id), [3, 2])
})

test('spare part detail exposes approved information architecture', () => {
  assert.deepEqual(SPARE_PART_TABS.map(tab => tab.key), [
    'overview', 'applicability', 'inventory', 'lotsSerials', 'substitutions',
    'kitRules', 'reliability', 'supply', 'evidence', 'audit',
  ])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/master-data/__tests__/configuration-tree.test.ts src/components/maintenance/master-data/__tests__/spare-part-tabs.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement the specialized pages**

Add routes:

```ts
{ path: 'master-data/configurations/:configurationId', name: 'maintenanceConfigurationDetail', component: () => import('@/views/maintenance/master-data/ConfigurationDetail.vue') },
{ path: 'master-data/spare-parts/:sparePartId', name: 'maintenanceSparePartDetail', component: () => import('@/views/maintenance/master-data/SparePartDetail.vue') },
```

Configuration detail requirements:

- version status and effective dates;
- tree view with installation position, part, installed quantity and evidence;
- contributor can edit only draft versions;
- published version is read-only and offers “clone as draft”.

Spare-part detail requirements:

- overview, applicability, inventory, lots/serials, substitutions, kit rules, reliability, supply, evidence, audit;
- tab content lazy-loads and retains each tab’s load/error state;
- no tab requests cross-tenant IDs because all calls use actor-scoped backend endpoints.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/master-data/__tests__/configuration-tree.test.ts src/components/maintenance/master-data/__tests__/spare-part-tabs.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/maintenance/master-data frontend/src/views/maintenance/master-data/ConfigurationDetail.vue frontend/src/views/maintenance/master-data/SparePartDetail.vue frontend/src/router/maintenance.ts
git commit -m "feat: add maintenance master data details"
```

---

### Task 9: Complete Previewable Excel Import and Export

**Files:**
- Create: import UI components listed in the file map
- Create: `frontend/src/api/maintenance/imports.ts`
- Create: `extensions/maintenance-api/app/exporters/master_data_excel.py`
- Modify: import service/schema/router files
- Test: `extensions/maintenance-api/tests/exporters/test_master_data_excel.py`
- Test: `extensions/maintenance-api/tests/api/test_master_data_import_tasks.py`
- Test: `frontend/src/components/maintenance/import/__tests__/import-state.test.ts`

**Interfaces:**
- Produces: preview task, execute task, error workbook, filtered export.

- [ ] **Step 1: Write failing backend and frontend tests**

```python
def test_preview_never_mutates_database(client, contributor_headers, valid_workbook, session):
    before = count_master_rows(session)
    response = client.post("/api/v1/master-data/imports/preview", headers=contributor_headers, files={"file": valid_workbook})
    assert response.status_code == 200
    assert count_master_rows(session) == before
    assert response.json()["data"]["valid_rows"] > 0


def test_export_respects_filter_and_tenant(client, viewer_headers, seeded_two_tenants):
    response = client.get("/api/v1/master-data/spare-parts/export?criticality=CRITICAL", headers=viewer_headers)
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    assert all(row["tenant_id"] is None for row in rows_as_dicts(workbook["spare_parts"]))
    assert {row["criticality"] for row in rows_as_dicts(workbook["spare_parts"])} == {"CRITICAL"}
```

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { importReducer } from '../import-state'

test('execution is disabled before a successful preview', () => {
  const state = importReducer(undefined, { type: 'FILE_SELECTED', fileName: 'data.xlsx' })
  assert.equal(state.canExecute, false)
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/exporters/test_master_data_excel.py tests/api/test_master_data_import_tasks.py -v
cd ..\..\frontend
npm run test -- src/components/maintenance/import/__tests__/import-state.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement preview, execute and export contracts**

Preview response:

```json
{
  "task_id": "uuid",
  "template_version": "PLAN05-1",
  "sheets": [{"name":"spare_parts","valid_rows":10,"invalid_rows":2}],
  "errors": [{"sheet":"spare_parts","row":4,"column":"code","code":"DUPLICATE_CODE","message":"..."}],
  "expires_at": "2026-07-24T12:30:00Z"
}
```

Execute request:

```json
{"task_id":"uuid","mode":"UPSERT","accept_valid_rows_only":false}
```

Execution reloads the uploaded temporary file, verifies actor tenant and preview hash, revalidates all rows, writes in one transaction, and stores an audit event. An expired or other-tenant task returns 404.

The UI sequence is file → mapping → validation → confirmation → task progress → result. Viewer sees export only. Contributor sees import and export.

- [ ] **Step 4: Run tests and build**

```powershell
cd extensions\maintenance-api
python -m pytest tests/imports tests/exporters/test_master_data_excel.py tests/api/test_master_data_import_tasks.py -v
python -m ruff check app tests
cd ..\..\frontend
npm run test -- src/components/maintenance/import/__tests__/import-state.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/imports.ts frontend/src/components/maintenance/import extensions/maintenance-api/app/exporters/master_data_excel.py extensions/maintenance-api/app/services/import_service.py extensions/maintenance-api/app/schemas/import_data.py extensions/maintenance-api/app/api/v1/master_data extensions/maintenance-api/tests/exporters/test_master_data_excel.py extensions/maintenance-api/tests/api/test_master_data_import_tasks.py
git commit -m "feat: add previewable master data import export"
```

---

### Task 10: Verify Master Data Role, Tenant and UX Behavior

**Files:**
- Modify: `extensions/maintenance-api/README.md`
- Create: `frontend/src/views/maintenance/__tests__/master-data-navigation.test.ts`
- Test: all Phase 05-2 files

**Interfaces:**
- Produces: verified, documented Phase 05-2 release slice.

- [ ] **Step 1: Add navigation and role acceptance tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { visibleMasterDataActions } from '@/components/maintenance/master-data/actions'


test('viewer sees view and export only', () => {
  assert.deepEqual(visibleMasterDataActions('viewer'), ['view', 'export'])
})

test('contributor sees create edit deactivate import and export', () => {
  assert.deepEqual(visibleMasterDataActions('contributor'), ['view', 'create', 'edit', 'deactivate', 'import', 'export'])
})
```

- [ ] **Step 2: Run full phase tests before documentation**

```powershell
cd frontend
npm run test
npm run type-check
npm run build
cd ..\extensions\maintenance-api
python -m pytest tests/api/test_dashboard_api.py tests/services/test_dashboard_service.py tests/api/test_master_data_api.py tests/api/test_master_data_import_tasks.py tests/imports tests/exporters -v
```

Expected: PASS. Any failure is fixed before documentation is committed.

- [ ] **Step 3: Document exact user and developer workflows**

Document:

- route map and role behavior;
- 30-second dashboard refresh and visibility pause;
- generic registry extension instructions;
- configuration and spare-part detail tabs;
- import preview/execute/error workbook workflow;
- exact local commands for Go proxy, FastAPI and Vite;
- known non-goals: procurement, financial accounting, mobile offline scanning.

- [ ] **Step 4: Run final Phase 05-2 gate**

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\frontend
npm ci
npm run test
npm run type-check
npm run build
cd ..\extensions\maintenance-api
python -m pytest tests/api/test_dashboard_api.py tests/services/test_dashboard_service.py tests/api/test_master_data_api.py tests/api/test_master_data_import_tasks.py tests/imports tests/exporters -v
python -m ruff check app tests
```

Expected: all tests pass, frontend production build completes, and Ruff is clean.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/maintenance/__tests__/master-data-navigation.test.ts extensions/maintenance-api/README.md
git commit -m "docs: verify maintenance master data frontend"
```

## Phase Completion Evidence

Attach to review:

- screenshot of expanded and collapsed WeKnora maintenance menu;
- viewer and contributor master-data pages;
- dashboard loading, populated, empty and error states;
- configuration tree and spare-part detail tabs;
- import preview with row/column errors and a successful execution result;
- frontend test/type-check/build output;
- backend dashboard/import/export test output;
- confirmation that no direct Maintenance API URL or internal JWT secret exists in built frontend assets.

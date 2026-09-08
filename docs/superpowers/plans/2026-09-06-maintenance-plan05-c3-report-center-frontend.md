# Maintenance Plan 05 C3 — Report Center Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the maintenance Report Center placeholder with a typed, lifecycle-correct, C2D-safe report workflow UI.

**Architecture:** A single typed report API module consumes `/v1/reports` and produces public report data only. Pure action rules derive UI affordances from actor role, report job state, and latest version state; list, detail, mutation, and download components compose those rules without duplicating backend authority.

**Tech Stack:** Vue 3 Composition API, TypeScript, vue-router, vue-i18n, TDesign Vue Next, existing authenticated maintenance client, `tsx --test`, Vue TypeScript checking, Vite.

## Global Constraints

- Build on `feature/demand-calculation-engine` after C2D merge; implement on `codex/maintenance-plan05-5-c3` only.
- Consume `/api/maintenance/v1/reports`; do not add or alter backend report endpoints, schemas, C2D source policy, lifecycle behavior, or export filenames.
- Model job states exactly as `CREATED`, `GENERATING_SECTIONS`, `VALIDATING_NUMBERS`, `READY_FOR_REVIEW`, `PARTIALLY_COMPLETED`, `FAILED`, and `FINALIZED`; never use a `COMPLETED` assumption.
- Model version states exactly as `DRAFT`, `REVIEWED`, `FINAL`, and `SUPERSEDED`.
- Viewer may view/list/export; Contributor adds create/generate/validate/regenerate; Admin adds finalize. Backend authorization remains authoritative after every UI decision.
- Render only C2D public `source_versions`; never render raw source snapshot JSON, private metadata, absolute paths, credentials, tenant IDs, or database records.
- Implement only backend-supported list fields: `keyword`, `report_type`, `job_status`, `version_status`, `session_id`, `scenario_version_id`, `calculation_run_id`, `review_run_id`, `source_type`, `source_id`, `source_version`, `sort_by`, `sort_order`, `page`, `page_size`.
- Use authenticated download handling and the server-provided filename/content type for `MARKDOWN`, `JSON`, and `DOCX`; never construct an absolute filesystem path.
- Keep Chat Card navigation under `/platform/maintenance/`; do not add C4, source backfill, automatic supersede, or unrelated frontend refactors.

---

## File map

| File | Responsibility |
| --- | --- |
| `frontend/src/api/maintenance/reports.ts` | Typed report transport and wire-format types. |
| `frontend/src/components/maintenance/report/report-types.ts` | Public UI domain types, status labels, and safe guards. |
| `frontend/src/components/maintenance/report/report-actions.ts` | Pure role/lifecycle action derivation and error-message mapping. |
| `frontend/src/views/maintenance/reports/ReportCenter.vue` | List page composition, route query synchronization, and refresh. |
| `frontend/src/views/maintenance/reports/ReportDetail.vue` | Detail page composition and route-param loading. |
| `frontend/src/components/maintenance/report/*.vue` | Focused filter, list, provenance, timeline, findings, sections, lifecycle, and export presentation. |
| `frontend/src/router/maintenance.ts` | Report-detail route registration. |
| `frontend/src/i18n/locales/{zh-CN,en-US}.ts` | All user-visible C3 copy and error labels. |

## Task 1: Typed client, public report model, and pure action rules

**Files:**
- Create: `frontend/src/api/maintenance/reports.ts`
- Create: `frontend/src/components/maintenance/report/report-types.ts`
- Create: `frontend/src/components/maintenance/report/report-actions.ts`
- Create: `frontend/src/components/maintenance/report/__tests__/report-api-contract.test.ts`
- Create: `frontend/src/components/maintenance/report/__tests__/report-actions.test.ts`
- Modify: `frontend/src/api/maintenance/client.ts`

**Interfaces:**
- Consumes: `MaintenanceClient`, `MaintenanceResult`, `PageData`, and `buildQuery` from the existing maintenance client.
- Produces: `reportApi`, `ReportListQuery`, `ReportDetail`, `ReportJobStatus`, `ReportVersionSummary`, `ReportAction`, `getReportActions`, and `reportErrorMessageKey` for all later tasks.

- [ ] **Step 1: Write failing API-contract tests**

Create an injected fake client and assert URL, method, query encoding, body, and export metadata behavior:

```ts
const api = createReportApi(fakeClient)
await api.listReports({ page: 2, page_size: 20, source_type: 'SESSION' })
assert.equal(calls[0].path, '/v1/reports?page=2&page_size=20&source_type=SESSION')
await api.createReportJob({ title: 'Weekly', report_type: 'MANAGEMENT_DECISION', source_refs: [] })
assert.deepEqual(calls[1], { method: 'post', path: '/v1/reports/jobs', body: { title: 'Weekly', report_type: 'MANAGEMENT_DECISION', source_refs: [] } })
```

Also assert `getReportJob`, `getReport`, `listReportVersions`, `generateReport`, `validateReport`, `finalizeReport`, `regenerateReport`, and `exportReport` use encoded numeric IDs and exactly the `/v1/reports` endpoints.

- [ ] **Step 2: Run the contract test and verify failure**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-api-contract.test.ts`

Expected: FAIL because `reports.ts` and the report API types do not exist.

- [ ] **Step 3: Implement the typed transport boundary**

Define the literal unions and public structures, including a source type that contains only display-safe C2D fields:

```ts
export type ReportJobStatus = 'CREATED' | 'GENERATING_SECTIONS' | 'VALIDATING_NUMBERS' | 'READY_FOR_REVIEW' | 'PARTIALLY_COMPLETED' | 'FAILED' | 'FINALIZED'
export type ReportVersionStatus = 'DRAFT' | 'REVIEWED' | 'FINAL' | 'SUPERSEDED'
export type ReportExportFormat = 'MARKDOWN' | 'JSON' | 'DOCX'
export interface PublicSourceVersion { source_type: string; source_id: number | null; source_version: string | null; display_name?: string | null }
export interface ReportListQuery { page: number; page_size: number; keyword?: string; report_type?: string; job_status?: ReportJobStatus; version_status?: ReportVersionStatus; session_id?: number; scenario_version_id?: number; calculation_run_id?: number; review_run_id?: number; source_type?: string; source_id?: number; source_version?: string; sort_by?: 'created_at' | 'report_code' | 'title' | 'report_type' | 'job_status'; sort_order?: 'asc' | 'desc' }
```

`createReportApi` must accept a small injected client interface and use `buildQuery`. Add a metadata-aware authenticated `download` result to `client.ts` so reports can read `Blob`, `Content-Disposition`, and `Content-Type` from the existing request adapter without changing existing import callers. Parse only an attachment filename; reject path separators and fall back to a fixed browser-safe filename.

- [ ] **Step 4: Write failing action-rule tests**

Cover viewer/contributor/admin behavior, FINAL immutability, valid regenerate behavior, and known/unknown errors:

```ts
assert.deepEqual(getReportActions({ role: 'VIEWER', jobStatus: 'READY_FOR_REVIEW', versionStatus: 'REVIEWED' }), ['view', 'versions', 'export'])
assert.equal(getReportActions({ role: 'ADMIN', jobStatus: 'READY_FOR_REVIEW', versionStatus: 'REVIEWED' }).includes('finalize'), true)
assert.equal(getReportActions({ role: 'CONTRIBUTOR', jobStatus: 'FINALIZED', versionStatus: 'FINAL' }).includes('generate'), false)
assert.equal(reportErrorMessageKey('REPORT_SOURCE_CONFLICT'), 'maintenance.reports.errors.sourceConflict')
```

- [ ] **Step 5: Implement pure action and error helpers**

Implement a non-Vue function with this signature:

```ts
export function getReportActions(input: { role: 'VIEWER' | 'CONTRIBUTOR' | 'ADMIN'; jobStatus: ReportJobStatus; versionStatus: ReportVersionStatus | null; backendAllowsRegenerate?: boolean }): ReportAction[]
```

It must return the deterministic UI affordance list; it must not call the API or infer backend authorization. Map every known code in the design to an i18n key and return `maintenance.reports.errors.generic` for all unknown values.

- [ ] **Step 6: Run focused tests and commit**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-actions.test.ts`

Expected: PASS.

```powershell
git add frontend/src/api/maintenance/client.ts frontend/src/api/maintenance/reports.ts frontend/src/components/maintenance/report/report-types.ts frontend/src/components/maintenance/report/report-actions.ts frontend/src/components/maintenance/report/__tests__/report-api-contract.test.ts frontend/src/components/maintenance/report/__tests__/report-actions.test.ts
git commit -m "feat(maintenance): add typed report client and action rules"
```

## Task 2: Report list, supported filters, and list-state tests

**Files:**
- Create: `frontend/src/components/maintenance/report/ReportFilterBar.vue`
- Create: `frontend/src/components/maintenance/report/ReportListTable.vue`
- Create: `frontend/src/components/maintenance/report/__tests__/report-list-state.test.ts`
- Modify: `frontend/src/views/maintenance/reports/ReportCenter.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: `reportApi.listReports`, `ReportListQuery`, `ReportListItem`, and `getReportActions` from Task 1.
- Produces: a list route that emits a selected report ID and maintains a backend-valid query state.

- [ ] **Step 1: Write failing list-state tests**

Test a pure `normalizeReportListQuery` exported from `ReportCenter.vue` or a colocated state module. Assert page defaults, blank filter removal, source filters preservation, and rejection of unsupported keys:

```ts
assert.deepEqual(normalizeReportListQuery({ keyword: '', source_type: 'SESSION', page: 0, generator: 'fake' }), { page: 1, page_size: 20, source_type: 'SESSION', sort_by: 'created_at', sort_order: 'desc' })
```

Test that clicking a row uses `router.push({ name: 'maintenanceReportDetail', params: { reportId } })` and that only actions returned by `getReportActions` render.

- [ ] **Step 2: Run the list-state test and verify failure**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts`

Expected: FAIL because the placeholder page has no list query or table.

- [ ] **Step 3: Implement filters and table**

`ReportFilterBar` emits a `ReportListQuery` containing only the global-constraint fields. Use controlled local values and a clear action that restores:

```ts
const DEFAULT_QUERY: ReportListQuery = { page: 1, page_size: 20, sort_by: 'created_at', sort_order: 'desc' }
```

`ReportListTable` renders report code, title, type, job status, latest version number/status, progress, created/updated timestamps, and action affordances. It emits `open`, `generate`, `validate`, `finalize`, `regenerate`, and `export`; it does not mutate report data itself.

Replace the placeholder `ReportCenter.vue` with query-route synchronization, cancellation-safe loading state, empty/error states, pagination, and an explicit “create report” entry point supplied by Task 4. Do not add date or generator controls. Add Chinese and English copy for every new label, state, empty result, and retry action.

- [ ] **Step 4: Run focused test and commit**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts`

Expected: PASS.

```powershell
git add frontend/src/components/maintenance/report/ReportFilterBar.vue frontend/src/components/maintenance/report/ReportListTable.vue frontend/src/components/maintenance/report/__tests__/report-list-state.test.ts frontend/src/views/maintenance/reports/ReportCenter.vue frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts
git commit -m "feat(maintenance): add report center list and filters"
```

## Task 3: Detail, timeline, public provenance, findings, and sections

**Files:**
- Create: `frontend/src/views/maintenance/reports/ReportDetail.vue`
- Create: `frontend/src/components/maintenance/report/ReportVersionTimeline.vue`
- Create: `frontend/src/components/maintenance/report/ReportProvenancePanel.vue`
- Create: `frontend/src/components/maintenance/report/ReportValidationFindings.vue`
- Create: `frontend/src/components/maintenance/report/ReportSections.vue`
- Create: `frontend/src/components/maintenance/report/__tests__/report-detail-state.test.ts`
- Modify: `frontend/src/router/maintenance.ts`

**Interfaces:**
- Consumes: `reportApi.getReport`, `reportApi.listReportVersions`, `ReportDetail`, and public source types from Task 1.
- Produces: `maintenanceReportDetail` route and a read-only detail surface for Task 4/5 action components.

- [ ] **Step 1: Write failing detail-state tests**

Create a detail fixture containing public `source_versions` and deliberately add forbidden keys (`source_snapshot_json`, `tenant_id`, `database_record_json`, `token`). Assert the view-model selector returns only public provenance fields and never JSON-stringifies unknown report metadata:

```ts
assert.deepEqual(toProvenanceRows(detail), [{ type: 'SESSION', id: 7, version: 'v2', name: 'Scenario input' }])
assert.equal(renderedText.includes('source_snapshot_json'), false)
```

Also assert timeline rows include `parent_version_id`, template version, generation mode/time, and digest without presenting it as editable state.

- [ ] **Step 2: Run the detail-state test and verify failure**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-detail-state.test.ts`

Expected: FAIL because no detail components or route exist.

- [ ] **Step 3: Implement detail components and route**

Add the exact route:

```ts
{ path: 'reports/:reportId', name: 'maintenanceReportDetail', component: () => import('@/views/maintenance/reports/ReportDetail.vue'), meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true } }
```

`ReportDetail.vue` validates a positive numeric route param, loads detail and version timeline, and renders loading/error/not-found states. The provenance panel accepts `PublicSourceVersion[]` only, whitelists display fields, and displays an unavailable state for malformed data. The sections component renders title/content/tables/citations supplied by the public response only; it must not add a generic metadata JSON viewer. Findings render severity/code/message as safe text. The timeline displays parent lineage without offering lifecycle mutations.

- [ ] **Step 4: Run focused test and commit**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-detail-state.test.ts`

Expected: PASS.

```powershell
git add frontend/src/views/maintenance/reports/ReportDetail.vue frontend/src/components/maintenance/report/ReportVersionTimeline.vue frontend/src/components/maintenance/report/ReportProvenancePanel.vue frontend/src/components/maintenance/report/ReportValidationFindings.vue frontend/src/components/maintenance/report/ReportSections.vue frontend/src/components/maintenance/report/__tests__/report-detail-state.test.ts frontend/src/router/maintenance.ts
git commit -m "feat(maintenance): add report detail and provenance view"
```

## Task 4: Create, lifecycle, regenerate, and error interactions

**Files:**
- Create: `frontend/src/components/maintenance/report/ReportGenerationDialog.vue`
- Create: `frontend/src/components/maintenance/report/ReportLifecycleActions.vue`
- Create: `frontend/src/components/maintenance/report/ReportRegenerateDialog.vue`
- Create: `frontend/src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts`
- Modify: `frontend/src/views/maintenance/reports/ReportCenter.vue`
- Modify: `frontend/src/views/maintenance/reports/ReportDetail.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: Task 1 typed mutations/action rules and Task 2/3 refresh callbacks.
- Produces: role/lifecycle-safe commands that refresh server state and render normalized errors.

- [ ] **Step 1: Write failing lifecycle tests**

Use injected mutation functions to prove the action component calls only allowed mutations and refreshes after success:

```ts
await controller.run('validate')
assert.deepEqual(calls, ['validate:42', 'refresh'])
assert.equal(controller.messageFor({ code: 'REPORT_VALIDATION_REQUIRED', request_id: 'r-1' }), 'maintenance.reports.errors.validationRequired')
```

Assert a FINAL version does not expose generate/validate/finalize; regenerate text contains the immutable-source-copy explanation; an unknown error uses the generic key and shows only the returned request ID.

- [ ] **Step 2: Run lifecycle test and verify failure**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts`

Expected: FAIL because lifecycle components do not exist.

- [ ] **Step 3: Implement dialogs and action component**

`ReportGenerationDialog` requires `title`, `report_type`, and a C2D-policy-valid `source_refs` list before calling `createReportJob`; legacy session/scenario/calculation/review IDs remain optional compatibility fields, not primary controls. `ReportLifecycleActions` receives current server status and `ReportAction[]`, calls the matching typed method, disables duplicate submits, then emits `changed` for its parent to reload. `ReportRegenerateDialog` shows exactly this semantic message: a new version is created, its source snapshot is copied from the current report version, and no business source data is recalculated.

All caught errors pass through Task 1’s mapper. Do not optimistic-update job/version state; refresh from the API after a successful mutation or display the backend error.

- [ ] **Step 4: Run focused test and commit**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts`

Expected: PASS.

```powershell
git add frontend/src/components/maintenance/report/ReportGenerationDialog.vue frontend/src/components/maintenance/report/ReportLifecycleActions.vue frontend/src/components/maintenance/report/ReportRegenerateDialog.vue frontend/src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts frontend/src/views/maintenance/reports/ReportCenter.vue frontend/src/views/maintenance/reports/ReportDetail.vue frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts
git commit -m "feat(maintenance): add report lifecycle controls"
```

## Task 5: Authenticated export and safe browser download

**Files:**
- Create: `frontend/src/components/maintenance/report/ReportExportActions.vue`
- Create: `frontend/src/components/maintenance/report/__tests__/report-export.test.ts`
- Modify: `frontend/src/api/maintenance/reports.ts`
- Modify: `frontend/src/views/maintenance/reports/ReportCenter.vue`
- Modify: `frontend/src/views/maintenance/reports/ReportDetail.vue`

**Interfaces:**
- Consumes: Task 1 metadata-aware authenticated report export response and normalized client errors.
- Produces: an `exported` event after a browser download and safe export error feedback.

- [ ] **Step 1: Write failing export tests**

Stub `URL.createObjectURL`, `URL.revokeObjectURL`, and a click-capable anchor. Assert every supported format calls `reportApi.exportReport(reportId, format)` and uses the returned safe filename/content type:

```ts
await controller.download('DOCX')
assert.deepEqual(downloads, [{ filename: 'RPT-1-v2.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }])
assert.equal(downloads[0].filename.includes('/'), false)
```

Assert failed downloads never click an anchor and surface the known or generic error mapper.

- [ ] **Step 2: Run export test and verify failure**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-export.test.ts`

Expected: FAIL because no export component exists.

- [ ] **Step 3: Implement export component**

Render MARKDOWN, JSON, and DOCX choices. On success, wrap the blob in the response content type, create an object URL, set the server-provided sanitized attachment filename, click a temporary anchor, remove it, and revoke the URL in `finally`. Never expose a response path, never concatenate an absolute path, and do not guess a report filesystem location.

Wire the component into list-row and detail actions using the same report ID and the viewer-permitted action rule.

- [ ] **Step 4: Run focused test and commit**

Run: `cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-export.test.ts`

Expected: PASS.

```powershell
git add frontend/src/components/maintenance/report/ReportExportActions.vue frontend/src/components/maintenance/report/__tests__/report-export.test.ts frontend/src/api/maintenance/reports.ts frontend/src/views/maintenance/reports/ReportCenter.vue frontend/src/views/maintenance/reports/ReportDetail.vue
git commit -m "feat(maintenance): add report export downloads"
```

## Task 6: C3 integration, regression, type, and build closure

**Files:**
- Create: `docs/superpowers/sdd/c3-closure.md`
- Modify: any C3 file only when a failing required gate proves a C3 defect.

**Interfaces:**
- Consumes: all C3 tasks and the existing Chat Card test directory.
- Produces: reproducible C3 closure evidence; no new feature behavior.

- [ ] **Step 1: Run focused C3 and Chat Card regressions**

Run:

```powershell
cd frontend
npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-list-state.test.ts src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts src/components/maintenance/report/__tests__/report-export.test.ts
npm run test -- src/components/maintenance/chat/__tests__
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full frontend gates**

Run:

```powershell
cd frontend
npm run test
npm run type-check
npm run build
git diff --check
```

Expected: every command exits 0. Treat any type or build failure as a defect; do not merely document it.

- [ ] **Step 3: Verify manual acceptance checklist**

Record that the placeholder is removed; list/detail navigation remains under `/platform/maintenance/`; only supported filters appear; C2D public provenance is shown without raw snapshot; Viewer/Contributor/Admin affordances match Task 1; FINAL remains immutable in UI; all three exports use safe filenames; and Chat Cards retain their safe path behavior.

- [ ] **Step 4: Write closure evidence and commit**

Write `docs/superpowers/sdd/c3-closure.md` with base/head SHA, exact commands, pass counts, accepted warnings, output artifacts, manual acceptance observations, and confirmation that no backend/C4/source-policy/lifecycle changes were introduced.

```powershell
git add docs/superpowers/sdd/c3-closure.md
git commit -m "docs(maintenance): close c3 report center frontend"
```

## Plan self-review

- Source/API/action groundwork is isolated in Task 1 and consumed by every UI task.
- Tasks 2–5 have one independently testable user-facing boundary each.
- The plan includes all six roadmap tasks and no unsupported filter, raw snapshot, backend change, or unrelated phase.
- Every code task has a failing test, a focused pass command, exact files, interfaces, and a commit boundary.
- Task 6 closes the required C3, Chat Card, type, build, and whitespace gates.

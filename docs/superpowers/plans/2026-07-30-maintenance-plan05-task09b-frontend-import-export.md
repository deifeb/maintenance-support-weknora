# Plan 05-2 Task 9B Frontend Import and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the native WeKnora master-data Excel workflow from authenticated template/export download through upload, mapping, preview, confirmation, asynchronous execution, polling, error-workbook download, and result display.

**Architecture:** Extend the existing maintenance client with one normalized binary-download path and build a typed transfer API that exactly matches Task 9A. Keep workflow transitions and polling in pure TypeScript units, render them through focused Vue components, and integrate capabilities through `MasterDataRegistry` so every available resource inherits consistent role-aware import/export actions without exposing tenant identifiers.

**Tech Stack:** Vue 3.5, TypeScript 6, TDesign Vue Next, Pinia permission store, existing Axios request adapter, Node `tsx --test`, FastAPI Task 9A contracts.

## Global Constraints

- Every browser request uses the existing `/api/maintenance/*` client path; the frontend never knows the Maintenance API base URL or internal JWT secret.
- The frontend never sends or displays `tenant_id`; backend actor scope remains authoritative.
- Viewer may download the template and filtered exports but cannot upload, preview, execute, or download another actor's task artifacts.
- Contributor and admin may import and export according to the existing `editMasterData` capability.
- Import URLs are exactly `/v1/master-data/import/template`, `/v1/master-data/import/tasks`, `/v1/master-data/import/tasks/{task_id}/preview`, `/execute`, task status, and `/errors.xlsx`.
- Export URL is exactly `/v1/master-data/exports/{resource_key}` and inherits current keyword, inactive, and sort filters.
- Upload is `multipart/form-data`; preview sends `{ mapping }`; execute accepts both first-submit `202` and idempotent replay `200` through the same success envelope.
- Binary downloads use Blob responses and structured JSON requests continue to use the standard success/data/message/meta envelope.
- Execution is impossible before a successful preview with `can_execute === true` and an explicit user confirmation.
- Route or resource changes invalidate the old workflow; stale upload, preview, execute, or poll results cannot overwrite the new resource state.
- Polling stops for terminal tasks, pauses while the page is hidden or the dialog is inactive, and refreshes immediately when active visibility returns.
- Task 9B does not modify Task 9A backend contracts, RBAC, tenant scope, idempotency, versioning, audit, or import persistence.

---

### Task 1: Add Binary Maintenance Requests and the Typed Transfer API

**Files:**
- Modify: `frontend/src/api/maintenance/client.ts`
- Modify: `frontend/src/api/maintenance/__tests__/client.test.ts`
- Create: `frontend/src/api/maintenance/imports.ts`
- Create: `frontend/src/api/maintenance/__tests__/imports.test.ts`

**Interfaces:**
- Produces: `MaintenanceClient.download(path)`, `createMasterDataTransferApi(client)`, `masterDataTransferApi`.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Write failing client and transfer-contract tests**

Add adapter assertions that `client.download('/v1/master-data/import/template')` requests `/api/maintenance/v1/master-data/import/template` with `{ responseType: 'blob' }`, returns the Blob unchanged, and normalizes download errors. In `imports.test.ts`, inject a fake client and assert exact paths, `FormData`, preview body, empty execute body, status path, error-workbook path, and encoded export query.

- [ ] **Step 2: Run and verify RED**

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test src/api/maintenance/__tests__/client.test.ts src/api/maintenance/__tests__/imports.test.ts
```

Expected: FAIL because `download` and `imports.ts` do not exist.

- [ ] **Step 3: Implement binary handling and exact Task 9A types**

Add to `MaintenanceClient`:

```ts
download(path: string): Promise<Blob>
```

Implement it with the same lazy adapter and error normalizer as JSON methods:

```ts
async download(path: string): Promise<Blob> {
  try {
    const adapter = await loadRequestAdapter()
    return await adapter.get<Blob>(`${PREFIX}${path}`, { responseType: 'blob' })
  } catch (error) {
    throw normalizeMaintenanceError(error)
  }
}
```

Define in `imports.ts`:

```ts
export interface ImportIssue {
  sheet: string | null
  row: number | null
  field: string | null
  code: string
  message: string
}

export interface ImportSheetInspection {
  name: string
  source_headers: string[]
  suggested_mapping: Record<string, string>
  required_fields: string[]
}

export interface ImportSheetSummary {
  name: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
}

export interface ImportExecutionResult {
  imported: boolean
  created: Record<string, number>
  updated: Record<string, number>
  total_rows: number
}

export interface ImportTaskUploadResult {
  task_id: string
  status: string
  original_filename: string
  file_sha256: string
  template_version: string
  sheets: ImportSheetInspection[]
  expires_at: string
}

export interface ImportTaskView {
  task_id: string
  status: string
  original_filename: string
  file_sha256: string
  template_version: string
  sheets: ImportSheetSummary[]
  preview: Record<string, Array<Record<string, unknown>>>
  errors: ImportIssue[]
  warnings: ImportIssue[]
  can_execute: boolean
  created_at: string
  expires_at: string
  started_at: string | null
  finished_at: string | null
  result: ImportExecutionResult | null
  error_code: string | null
  error_message: string | null
}
```

The factory exposes `downloadTemplate`, `uploadTask(file)`, `previewTask(taskId, mapping)`, `executeTask(taskId)`, `getTask(taskId)`, `downloadErrors(taskId)`, and `exportResource(resourceKey, query)`. Upload appends the file under form key `file` and posts with multipart headers. All path segments use `encodeURIComponent`; export uses `buildQuery` and never accepts a tenant filter.

- [ ] **Step 4: Run focused tests and type-check**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/api/maintenance/__tests__/client.test.ts src/api/maintenance/__tests__/imports.test.ts
npm run type-check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/client.ts frontend/src/api/maintenance/__tests__/client.test.ts frontend/src/api/maintenance/imports.ts frontend/src/api/maintenance/__tests__/imports.test.ts
git commit -m "feat: add typed master data transfer client"
```

---

### Task 2: Implement the Import Reducer and Visibility-Aware Polling

**Files:**
- Create: `frontend/src/components/maintenance/import/import-state.ts`
- Create: `frontend/src/components/maintenance/import/useImportTaskPolling.ts`
- Create: `frontend/src/components/maintenance/import/__tests__/import-state.test.ts`
- Create: `frontend/src/components/maintenance/import/__tests__/import-polling.test.ts`

**Interfaces:**
- Produces: `createImportState(resourceKey)`, `importReducer(state, event)`, `canConfirmImport(state)`, `canExecuteImport(state)`, `createImportTaskPolling(options)`.
- Consumed by: Task 3.

- [ ] **Step 1: Write failing state-machine and polling tests**

Cover these behaviors separately:

```text
idle → selected → uploaded → previewed → confirmed → queued/running → completed
failed and expired terminal states
execute disabled before preview and before explicit confirmation
new file or resource invalidates the previous task and increments generation
stale generation/task updates are ignored
poll starts immediately, schedules only nonterminal tasks, pauses hidden/inactive,
resumes immediately, and stop cancels the timer
```

- [ ] **Step 2: Run and verify RED**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/components/maintenance/import/__tests__/import-state.test.ts src/components/maintenance/import/__tests__/import-polling.test.ts
```

Expected: FAIL because the state and polling modules do not exist.

- [ ] **Step 3: Implement a pure reducer and injected-timer poller**

Use these public types:

```ts
export type ImportPhase =
  | 'idle' | 'selected' | 'uploaded' | 'previewed' | 'confirmed'
  | 'queued' | 'running' | 'completed' | 'failed' | 'expired'

export interface ImportWorkflowState {
  resourceKey: string
  generation: number
  phase: ImportPhase
  fileName: string | null
  mapping: Record<string, Record<string, string>>
  task: ImportTaskUploadResult | ImportTaskView | null
  confirmed: boolean
  error: MaintenanceClientError | null
}
```

Events carry the generation captured before each async request. `TASK_UPDATED`, `REQUEST_FAILED`, and terminal events return the original state when their generation or task ID is stale. Backend statuses map `UPLOADED → uploaded`, `PREVIEW_VALID/PREVIEW_INVALID → previewed`, `QUEUED → queued`, `RUNNING → running`, `COMPLETED → completed`, `FAILED → failed`, and `EXPIRED → expired`. `canExecuteImport` requires phase `confirmed`, a task view with `can_execute`, and no error.

`createImportTaskPolling` receives injected `load`, `onTask`, `onError`, `setTimeout`, and `clearTimeout`. It never overlaps requests and never creates a timer after stop or a terminal response.

- [ ] **Step 4: Run focused tests**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/components/maintenance/import/__tests__/import-state.test.ts src/components/maintenance/import/__tests__/import-polling.test.ts
```

Expected: PASS with no timer leaks.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/maintenance/import/import-state.ts frontend/src/components/maintenance/import/useImportTaskPolling.ts frontend/src/components/maintenance/import/__tests__/import-state.test.ts frontend/src/components/maintenance/import/__tests__/import-polling.test.ts
git commit -m "feat: add recoverable import task state"
```

---

### Task 3: Build the Upload-to-Result Import Dialog

**Files:**
- Create: `frontend/src/components/maintenance/import/MasterDataImportDialog.vue`
- Create: `frontend/src/components/maintenance/import/ImportMappingStep.vue`
- Create: `frontend/src/components/maintenance/import/ImportPreviewStep.vue`
- Create: `frontend/src/components/maintenance/import/ImportTaskResult.vue`
- Create: `frontend/src/components/maintenance/import/import-workflow.ts`
- Create: `frontend/src/components/maintenance/import/__tests__/import-workflow.test.ts`
- Create: `frontend/src/components/maintenance/import/__tests__/import-dialog.test.ts`

**Interfaces:**
- Consumes: transfer API, reducer, polling, permission-safe parent props.
- Produces: `MasterDataImportDialog` with `open`, `resourceKey`, `canImport`; emits `close` and `completed`.

- [ ] **Step 1: Write failing workflow and component-contract tests**

Use a fake transfer API to prove upload uses the selected File, preview uses edited sheet mappings, execute is rejected until confirmation, task polling begins after execute, a new resource/file cancels the old poll, 404 task loss becomes expired, 409/422 remain actionable, and 503 remains retryable. Add source-contract assertions that the dialog exposes template/error-workbook downloads, mapping, preview summaries and row/field errors, confirmation, queued/running progress, completed counts, failed/expired recovery, and no tenant input.

- [ ] **Step 2: Run and verify RED**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/components/maintenance/import/__tests__/import-workflow.test.ts src/components/maintenance/import/__tests__/import-dialog.test.ts
```

Expected: FAIL because the workflow and Vue components do not exist.

- [ ] **Step 3: Implement the workflow controller and focused components**

`createImportWorkflow` owns the selected File, reducer state, request generation, and poller. Its commands are:

```ts
selectFile(file: File): void
upload(): Promise<void>
setMapping(sheet: string, source: string, target: string): void
preview(): Promise<void>
confirm(): void
execute(): Promise<void>
retryStatus(): Promise<void>
reset(resourceKey: string): void
dispose(): void
```

The dialog flow is file → mapping → preview → confirmation → progress/result. Preview shows sheet totals plus row, field, code, and message for errors/warnings. Invalid preview offers error workbook download and corrected re-upload. Completed result shows `total_rows`, created counts, and updated counts. Failed and expired states explain whether to retry status or start a new upload. The component registers `visibilitychange`, calls `poller.setVisible(document.visibilityState === 'visible')`, and removes listeners/disposes on unmount.

- [ ] **Step 4: Run focused tests, maintenance tests, type-check, and build**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/components/maintenance/import/__tests__/import-workflow.test.ts src/components/maintenance/import/__tests__/import-dialog.test.ts
$maintenanceTests = rg --files -uu src | Where-Object { $_ -match '^src[\\/](api|stores|components|composables|views)[\\/]maintenance[\\/].*(\.test\.ts|[\\/]__tests__[\\/].*\.ts)$' }
& '.\node_modules\.bin\tsx.cmd' --test $maintenanceTests
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/maintenance/import
git commit -m "feat: add master data import workflow"
```

---

### Task 4: Integrate Registry-Driven Import and Filtered Export Actions

**Files:**
- Modify: `frontend/src/components/maintenance/master-data/MasterDataRegistry.ts`
- Modify: `frontend/src/components/maintenance/master-data/__tests__/registry.test.ts`
- Modify: `frontend/src/views/maintenance/master-data/MasterDataListPage.vue`
- Create: `frontend/src/views/maintenance/__tests__/master-data-transfer-actions.test.ts`

**Interfaces:**
- Produces: `MasterDataTransferDefinition`, `visibleMasterDataTransferActions(resource, permissions)`, page-level import/export actions.
- Consumed by: Plan 05-2 Task 10 acceptance.

- [ ] **Step 1: Write failing registry, role, filter, and stale-route tests**

Assert that every currently available resource declares its backend export key; planned resources expose no transfer action; viewer gets `template` and `export`; contributor/admin additionally get `import`; export forwards current `keyword`, `include_inactive`, `sort_by`, and `sort_order` but no tenant value; changing `resource.key` closes/resets the dialog so an old task cannot update the page.

Use these exact export keys for the available registry entries:

```text
equipmentModels → equipment-models
configurations → configuration-versions
parts → parts
spareParts → spare-parts
reliabilityProfiles → reliability-profiles
warehouses → warehouses
inventorySummaries → inventories
suppliers → suppliers
supplierOffers → supplier-offers
```

- [ ] **Step 2: Run and verify RED**

```powershell
& '.\node_modules\.bin\tsx.cmd' --test src/components/maintenance/master-data/__tests__/registry.test.ts src/views/maintenance/__tests__/master-data-transfer-actions.test.ts
```

Expected: FAIL because transfer metadata and page actions do not exist.

- [ ] **Step 3: Add transfer metadata and page actions**

Extend available definitions with:

```ts
export interface MasterDataTransferDefinition {
  exportKey: string
  importable: boolean
}
```

The page header uses secondary actions for “下载模板” and “导出当前结果”, and primary actions for “导入 Excel” plus the existing create action. `visibleMasterDataTransferActions` is the single role/capability decision function used by tests and the page. Export calls `exportResource` with current server-table state and triggers a sanitized `.xlsx` download. Import opens `MasterDataImportDialog`; `completed` closes it and refreshes the table. A resource watcher disposes the old workflow before resetting table state.

- [ ] **Step 4: Run all Task 9B gates**

```powershell
cd frontend
npm run test
npm run type-check
npm run build
cd ..\extensions\maintenance-api
& '.\.venv\Scripts\python.exe' -m pytest tests/api/test_master_data_exports.py tests/api/test_master_data_import_tasks.py tests/exporters/test_import_error_excel.py tests/exporters/test_master_data_excel.py tests/imports -q
& '.\.venv\Scripts\python.exe' -m ruff check app tests
```

Expected: frontend suite, type-check, build, Task 9A regression, and Ruff all pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/maintenance/master-data/MasterDataRegistry.ts frontend/src/components/maintenance/master-data/__tests__/registry.test.ts frontend/src/views/maintenance/master-data/MasterDataListPage.vue frontend/src/views/maintenance/__tests__/master-data-transfer-actions.test.ts
git commit -m "feat: integrate master data import export actions"
```

## Task 9B Completion Evidence

- Typed client tests prove all paths stay under `/api/maintenance` and binary requests use Blob handling.
- Reducer and polling tests prove preview-before-execute, stale-result rejection, terminal stop, and visibility pause/resume.
- Workflow tests prove upload, mapping, preview, confirmation, execution, polling, error download, retry, failure, and expiry behavior.
- Role tests prove viewer export-only and contributor/admin import/export behavior.
- Full frontend test/type-check/build and Task 9A backend/Ruff regression output are attached to the final review.

# Plan 05-3C Task 5 Typed Demand List Client, Permissions, and Store Design

**Date:** 2026-08-01
**Status:** Proposed for approval
**Repository:** `https://github.com/deifeb/maintenance-support-weknora`
**Worktree:** `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`
**Branch:** `feature/maintenance-frontend-plan05`
**Baseline commit:** `1edf45cdd8b092148f544f41c36f094b1e14c91c`
**Pull request:** Draft PR #4
**Parent plan:** `docs/superpowers/plans/2026-07-31-maintenance-plan05-03c-demand-list-lifecycle.md`

## 1. Purpose

Task 5 adds the non-visual frontend foundation for the demand-list lifecycle already delivered by Tasks 1–4.

It provides:

1. a typed demand-list API client matching the nine Task 4 routes;
2. explicit capability flags in the maintenance permission matrix;
3. a pure lifecycle-action resolver that derives allowed UI actions from server status and capabilities;
4. a Pinia-compatible demand-list state module with stale-response isolation and one serialized mutation gate;
5. focused Node tests proving paths, bodies, headers, Decimal string preservation, permissions, lifecycle actions, store sequencing, and error behavior.

Task 5 does not build the demand-list detail page. It creates the stable interfaces that Task 6 will consume.

## 2. Current Baseline

Task 4 exposes these tenant-safe routes under `/api/maintenance/v1/demand`:

```text
POST /demand-lists
GET  /demand-lists
GET  /demand-lists/{demand_list_id}
PUT  /demand-lists/{demand_list_id}/items/{item_id}
POST /demand-lists/{demand_list_id}/submit
POST /demand-lists/{demand_list_id}/confirm
POST /demand-lists/{demand_list_id}/publish
POST /demand-lists/{demand_list_id}/derive
POST /demand-lists/{demand_list_id}/void
```

The frontend already has these reusable patterns:

- `frontend/src/api/maintenance/client.ts`
  - returns `MaintenanceResult<T>`;
  - normalizes structured backend errors;
  - supports POST request configuration for headers;
  - never exposes a tenant selector.
- `frontend/src/api/maintenance/calculation-groups.ts`
  - uses exact path builders;
  - passes `Idempotency-Key` through request configuration;
  - retains Decimal values as strings.
- `frontend/src/stores/maintenance/calculationGroup.ts`
  - separates read loading from mutation state;
  - ignores stale read responses through a request generation counter;
  - serializes mutations with a single gate;
  - normalizes server errors without parsing messages.
- `frontend/src/stores/maintenance/permission-matrix.ts`
  - maps tenant roles to capabilities;
  - applies a second fail-closed `hasRole()` hierarchy check;
  - treats owner and admin as maintenance administrators.

Task 5 follows those patterns instead of introducing a new client, error wrapper, role model, or state library.

## 3. Scope

### 3.1 Create

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

### 3.2 Modify

```text
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

### 3.3 Explicitly excluded

Task 5 does not modify:

```text
frontend/src/router/**
frontend/src/views/**
frontend/src/i18n/**
frontend/src/components/**/*.vue
extensions/maintenance-api/**
internal/**
```

It also does not add a demand-list menu entry, route, page, dialog, table, lifecycle button, notification, inventory reservation, procurement action, report action, or backend alias.

## 4. Approaches Considered

### 4.1 Recommended: two capability flags plus a pure resolver

Add:

```ts
editDemandList: boolean
publishDemandList: boolean
```

Interpret them as:

- `editDemandList`
  - edit DRAFT item quantities;
  - submit a DRAFT.
- `publishDemandList`
  - confirm a pending list;
  - publish a confirmed list;
  - derive a published list;
  - void a published list.

The resolver receives only:

```ts
status: DemandListStatus
permissions: MaintenancePermissions
```

It does not inspect tenant roles.

**Benefits**

- preserves the capability-based frontend architecture;
- matches the approved parent plan;
- keeps the permission matrix small;
- supports every current lifecycle transition;
- remains fail-closed when auth hierarchy checks downgrade a role;
- gives Task 6 one deterministic source of action visibility.

**Trade-off**

`publishDemandList` is an umbrella name for all administrator lifecycle actions, not only the publish button. This is acceptable because it represents authority over published-list lifecycle state rather than one HTTP method.

### 4.2 Alternative: one permission per lifecycle action

Possible flags:

```text
editDemandList
submitDemandList
confirmDemandList
publishDemandList
deriveDemandList
voidDemandList
```

This is more granular, but no current product requirement assigns these actions to different roles. It increases matrix size, test surface, and future configuration burden without changing authorization behavior.

This option is rejected under YAGNI.

### 4.3 Alternative: resolve actions from raw role names

The resolver could accept `viewer | contributor | admin | owner`.

This is rejected because:

- it duplicates `permission-matrix.ts`;
- it bypasses the `permissionsForAuth()` downgrade check;
- it couples components to raw role names;
- it makes future capability changes require component rewrites.

## 5. Typed API Contract

## 5.1 Decimal and enum types

Task 5 defines a local alias:

```ts
export type DecimalString = string
```

It does not move the existing alias from `calculation-groups.ts`, because doing so would create unrelated churn in a verified module.

Exact status union:

```ts
export type DemandListStatus =
  | 'DRAFT'
  | 'PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'VOIDED'
```

Exact lifecycle event union:

```ts
export type DemandListEventType =
  | 'CREATED'
  | 'ITEM_UPDATED'
  | 'SUBMITTED'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'DERIVED'
  | 'VOIDED'
```

Exact decision type union:

```ts
export type DemandListDecisionType =
  | 'SYSTEM_RECOMMENDATION'
  | 'ALTERNATIVE_CANDIDATE'
  | 'MANUAL_QUANTITY'
```

Exact execution-mode union follows the backend schema, not the narrower candidate-selection type:

```ts
export type DemandExecutionMode =
  | 'AUTO'
  | 'ANALYTICAL'
  | 'MONTE_CARLO'
  | 'COMPARE'
```

`ReliabilityModel` is imported from `model-recommendations.ts`, because that existing type already matches the backend reliability model enum.

## 5.2 Read models

`DemandListItem` mirrors every field in `DemandListItemRead`:

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
```

`DemandListEvent`, `DemandListSummary`, and `DemandList` mirror the backend models without renaming serialized fields.

`DemandList` extends `DemandListSummary` and includes lifecycle actor/time fields, `items`, and `events`.

No frontend model includes `tenant_id`; tenant identity remains exclusively in authenticated response metadata.

## 5.3 Request models

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

The client creates transition bodies internally:

```ts
{ expected_version: number }
```

Confirmation uses the exact backend field:

```ts
{
  expected_version: number
  confirmation_note: string
}
```

The obsolete field `note` is never accepted or sent.

## 5.4 API interface

```ts
export interface DemandListApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
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
```

Factory:

```ts
export function createDemandListApi(
  client: DemandListApiClient = defaultClient,
)
```

Exported singleton:

```ts
export const demandListApi = createDemandListApi()
```

Methods:

```ts
create(request, idempotencyKey)
list(query?)
get(demandListId)
updateItem(demandListId, itemId, request)
submit(demandListId, expectedVersion, idempotencyKey)
confirm(
  demandListId,
  expectedVersion,
  confirmationNote,
  idempotencyKey,
)
publish(demandListId, expectedVersion, idempotencyKey)
derive(demandListId, expectedVersion, idempotencyKey)
void(demandListId, expectedVersion, idempotencyKey)
```

Every identifier is encoded through:

```ts
encodeURIComponent(String(value))
```

Create and all five lifecycle methods send:

```ts
{
  headers: {
    'Idempotency-Key': idempotencyKey,
  },
}
```

No read, body, query, or header includes a tenant selector.

## 6. Permission Design

`MaintenancePermissions` gains:

```ts
editDemandList: boolean
publishDemandList: boolean
```

Exact matrix:

| Role/capability | editDemandList | publishDemandList |
|---|---:|---:|
| denied/unknown | false | false |
| viewer | false | false |
| contributor | true | false |
| admin | true | true |
| owner | true | true |

`permissionsForAuth()` applies both capability and hierarchy checks:

```ts
editDemandList:
  rolePermissions.editDemandList && canMaintain

publishDemandList:
  rolePermissions.publishDemandList && canAdminister
```

Therefore a recognized contributor whose `hasRole()` function grants only viewer authority receives read-only demand-list capabilities.

## 7. Pure Lifecycle Resolver

File:

```text
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
```

It contains no Vue imports and no network calls.

Types:

```ts
export type DemandListAction =
  | 'edit'
  | 'submit'
  | 'confirm'
  | 'publish'
  | 'derive'
  | 'void'
```

Resolver:

```ts
export function demandListActions(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): DemandListAction[]
```

Exact matrix:

| Status | Required capability | Actions |
|---|---|---|
| DRAFT | editDemandList | edit, submit |
| PENDING_CONFIRMATION | publishDemandList | confirm |
| CONFIRMED | publishDemandList | publish |
| PUBLISHED | publishDemandList | derive, void |
| VOIDED | none | none |

The returned array uses stable display order:

```text
edit
submit
confirm
publish
derive
void
```

A second helper stabilizes Task 6 item-editor logic:

```ts
export function canEditDemandListItem(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): boolean
```

It returns `true` only for `DRAFT` plus `editDemandList`.

Published, confirmed, pending, and voided lists remain read-only even for administrators.

## 8. Store Design

## 8.1 Public state

Factory:

```ts
export function createDemandListState(
  api: DemandListStoreApi = demandListApi,
)
```

Pinia store:

```ts
export const useDemandListStore = defineStore(
  'maintenanceDemandList',
  () => createDemandListState(),
)
```

State:

```ts
current: Ref<DemandList | null>
loading: Ref<boolean>
mutating: Ref<boolean>
error: Ref<MaintenanceClientError | null>
```

Internal state:

```ts
let requestGeneration = 0
```

Task 5 intentionally does not add list-page state. `demandListApi.list()` is typed and tested for future consumers, while the store remains focused on the Task 6 detail flow.

## 8.2 Read behavior

```ts
load(demandListId: number): Promise<DemandList>
```

Behavior:

1. increment `requestGeneration`;
2. set `loading = true`;
3. clear `error`;
4. call `api.get()`;
5. apply the response only when the captured generation is still current;
6. return the response data even when it is stale;
7. normalize errors only for the current generation;
8. clear loading only for the current generation.

This prevents a slow response for route A from replacing the state already loaded for route B.

## 8.3 Mutation gate

Every mutation uses one shared gate:

```ts
function beginMutation(): void
```

When `mutating` is already true, it throws:

```text
Demand list mutation is already in progress
```

This prevents overlapping item updates and lifecycle transitions from racing on the same optimistic aggregate version.

## 8.4 Current aggregate requirement

Methods that mutate an existing list call:

```ts
requireCurrent(): DemandList
```

When no list is loaded, it throws:

```text
Demand list is not loaded
```

The store, not the component, supplies the current aggregate version to every mutation. This prevents Task 6 from retaining a stale version number in local form state.

## 8.5 Public actions

```ts
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
```

The store method is named `voidList()` instead of `void()` because `void` is a TypeScript operator and the longer name is clearer at call sites. The API method may remain `void()` because it is an object method and directly mirrors the backend action.

## 8.6 Mutation application

A mutation captures:

```ts
const generation = requestGeneration
const targetId = current.value?.id
```

After the API returns, the server aggregate is applied only when:

```ts
generation === requestGeneration
```

For existing-list mutations, the captured target must also still represent the active route context.

`derive()` is allowed to return a new list ID. When the route generation is unchanged, the new DRAFT aggregate becomes `current`; Task 6 then navigates to its returned ID.

Every mutation returns the server aggregate even when route state has changed. The caller may complete its own navigation decision, but stale results cannot overwrite visible state.

## 8.7 Version propagation

The store always builds mutation requests from `current.version`.

Example:

```ts
api.submit(
  current.id,
  current.version,
  idempotencyKey,
)
```

After a successful response, `current` is replaced with the complete server aggregate. The store never increments versions locally and never patches only one field.

This preserves:

- backend state-machine authority;
- server-generated audit events;
- admin confirmation metadata;
- supersession/current flags;
- exact optimistic version.

## 8.8 Error handling

All API errors pass through:

```ts
normalizeMaintenanceError(value)
```

The store does not parse exception messages.

Structured backend fields remain accessible through:

```ts
error.code
error.details
error.request_id
error.retryable
```

On mutation failure:

- `current` remains the last successful aggregate;
- `error` receives the normalized server error;
- `mutating` is reset in `finally`;
- the original rejection is rethrown.

## 8.9 Disposal

```ts
dispose(): void
```

Behavior:

```ts
requestGeneration += 1
```

This invalidates all in-flight reads and mutations for a route being left.

Task 5 does not automatically clear `current`, because Task 6 may use the prior aggregate during transition rendering. A future page may explicitly replace it by calling `load()`.

## 9. Test Design

## 9.1 API client tests

File:

```text
frontend/src/api/maintenance/__tests__/demand-lists.test.ts
```

Required cases:

1. create path/body/idempotency header;
2. list query includes page, page size, status, and lineage ID;
3. get path encodes the list ID;
4. item update path and exact body;
5. submit body contains only `expected_version`;
6. confirm contains exact `confirmation_note`, never `note`;
7. publish/derive/void paths and headers;
8. no captured call contains `tenant`, `X-Tenant-ID`, or `tenant_id`;
9. very large Decimal strings survive JSON serialization unchanged;
10. response metadata remains outside the domain aggregate through `MaintenanceResult<T>`.

## 9.2 Permission tests

Extend the exact expected objects in:

```text
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

Required cases:

- viewer receives neither demand-list capability;
- contributor receives edit but not publish;
- admin and owner receive both;
- unknown roles fail closed;
- hierarchy downgrade of contributor to viewer removes edit capability;
- hierarchy downgrade of admin to contributor removes publish capability while retaining edit capability.

## 9.3 Resolver tests

File:

```text
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Required cases:

- DRAFT contributor/admin → `['edit', 'submit']`;
- DRAFT viewer → `[]`;
- PENDING_CONFIRMATION admin → `['confirm']`;
- PENDING_CONFIRMATION contributor/viewer → `[]`;
- CONFIRMED admin → `['publish']`;
- PUBLISHED admin → `['derive', 'void']`;
- PUBLISHED contributor/viewer → `[]`;
- VOIDED all roles → `[]`;
- item editing is true only for DRAFT plus `editDemandList`.

## 9.4 Store tests

File:

```text
frontend/src/stores/maintenance/__tests__/demand-list.test.ts
```

Required cases:

1. a slower first load cannot overwrite a newer route load;
2. `dispose()` invalidates an in-flight load;
3. all mutations are mutually exclusive;
4. mutation without a loaded aggregate is rejected before API invocation;
5. update item uses the current list ID and version;
6. submit uses the version returned by the previous update;
7. confirm sends exact note and current version;
8. publish replaces state with the server aggregate;
9. derive may replace current with a different list ID;
10. route change during mutation prevents stale state replacement;
11. mutation failure preserves the prior aggregate;
12. structured conflict details remain available in normalized store error;
13. `mutating` always resets after success or failure.

Tests use deferred promises and `MaintenanceResult<T>` fixtures. They do not mount Vue components or require a browser DOM.

## 10. TDD and Verification Boundaries

Implementation follows RED → GREEN → regression.

Focused RED/GREEN command:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\frontend

& '.\node_modules\.bin\tsx.cmd' --test `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Static gate:

```powershell
npm run type-check
```

Task 5 regression gate:

```powershell
npm run test
npm run type-check
npm run build
```

Repository gate:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
git diff --check
git status --short
```

The implementation must preserve all existing frontend tests. The previously recorded baseline was 377 passing frontend tests before Task 5; the final count is allowed to increase because Task 5 adds new tests.

## 11. Commit Boundaries

After explicit implementation approval and verified GREEN, Task 5 uses one focused feature commit:

```text
feat: add demand list lifecycle client
```

The commit contains only the eight approved files.

Documentation is committed separately before implementation:

```text
docs: plan plan05 demand list lifecycle client
```

No push occurs without separate explicit approval.

## 12. Acceptance Criteria

Task 5 is complete only when all conditions hold:

1. every Task 4 route has one typed client method;
2. all mutating POST requests send `Idempotency-Key`;
3. transition requests use the latest server aggregate version;
4. confirmation sends `confirmation_note`;
5. Decimal quantities remain strings;
6. no request contains a tenant selector;
7. viewer is read-only;
8. contributor can edit/submit but cannot administer lifecycle transitions;
9. admin/owner can edit and administer lifecycle transitions;
10. auth hierarchy reductions fail closed;
11. the lifecycle resolver uses capabilities, never raw role names;
12. item editing is allowed only for DRAFT;
13. one mutation gate covers update, submit, confirm, publish, derive, and void;
14. stale reads and stale mutations cannot overwrite a newer route;
15. structured errors are normalized without message parsing;
16. focused tests pass;
17. the full frontend test suite passes;
18. type-check passes;
19. production build passes;
20. only the approved eight files are changed;
21. the worktree is not staged, committed, or pushed until the corresponding explicit gate.

## 13. Deferred to Task 6

Task 5 deliberately defers:

1. `DemandListLifecycleActions.vue`;
2. `DemandListDetail.vue`;
3. calculation-comparison generation button;
4. route `maintenanceDemandListDetail`;
5. confirmation dialogs;
6. item editing form and validation messages;
7. timeline rendering;
8. current/superseded presentation;
9. locale strings;
10. navigation tests;
11. menu behavior;
12. browser/visual acceptance evidence.

## 14. Self-Review Result

- Placeholder scan: no unresolved placeholder remains.
- Scope check: one frontend foundation task with no page/UI implementation.
- Type check: request and response fields match the Task 4 backend schemas.
- Permission check: capability resolution remains fail-closed.
- Concurrency check: reads and mutations have explicit stale-response behavior.
- Task boundary check: all visual work remains in Task 6.

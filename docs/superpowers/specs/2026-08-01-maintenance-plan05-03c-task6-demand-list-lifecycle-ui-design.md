# Plan 05-3C Task 6 Demand List Lifecycle UI Design

**Date:** 2026-08-01
**Status:** Approved design, pending written-spec review
**Selected approach:** A — thin detail page plus isolated lifecycle action component
**Branch:** `feature/maintenance-frontend-plan05`
**Design baseline:** `d38e00f43d3b3f3245d7069f821be55d1fe86777`

## 1. Goal

Build the frontend UI that carries a completed calculation comparison into a governed demand-list workflow:

```text
calculation comparison
→ create demand-list DRAFT
→ open hidden demand-list detail route
→ edit DRAFT item quantities
→ submit
→ confirm
→ publish
→ derive or void
```

The UI must preserve the server-authoritative lifecycle, optimistic version boundary, immutable published history, exact Decimal strings, and explicit Contributor/Admin permissions already implemented by Plan 05-3C Tasks 1–5.

## 2. Scope

### 2.1 In scope

- Add a guarded demand-list generation entry to `CalculationComparison.vue`.
- Add the hidden route `calculations/demand-lists/:listId`.
- Add `DemandListDetail.vue`.
- Add `DemandListLifecycleActions.vue`.
- Extend the pure lifecycle helper with a conservative generation-eligibility function.
- Render demand-list summary, version/lineage facts, item table, audit timeline, and lifecycle state.
- Allow DRAFT item quantity edits with a required adjustment reason.
- Add explicit confirmation interactions for submit, confirm, publish, derive, and void.
- Route a successful derive operation to the newly returned DRAFT ID.
- Add route, lifecycle, generation, source-contract, locale-shape, type-check, full-test, and build verification.
- Add all demand-list UI locale keys through the existing centralized calculation locale module.

### 2.2 Out of scope

- Independent demand-list list/search page.
- Sidebar or maintenance-menu entry.
- Inventory reservation or allocation.
- Procurement or purchase-order creation.
- Review-engine execution.
- Report generation or export.
- Backend API, schema, service, route, or migration changes.
- New tenant-selection input, path, query, or header.
- Batch item editing.
- Client-side recreation of the backend lifecycle or validation service.
- Client-side numeric conversion of demand quantities.
- Automatic publication or confirmation without a user confirmation interaction.
- Plan 05-3 complete vertical acceptance; that belongs to Task 7.

## 3. Current architecture to preserve

Task 5 already provides:

```text
frontend/src/api/maintenance/demand-lists.ts
frontend/src/stores/maintenance/demandList.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
```

The Task 6 UI consumes these modules rather than duplicating their responsibilities.

Existing maintenance calculation pages use:

- hidden authenticated child routes;
- `MaintenancePageHeader`;
- shared loading, empty, and error states;
- Pinia stores with `storeToRefs`;
- route-driven loading;
- stale-response protection;
- `onBeforeUnmount(store.dispose)`;
- TDesign confirmation and message plugins.

Task 6 follows these conventions and does not introduce a second page architecture.

## 4. Selected approach

### 4.1 Decision

Use a thin page and an isolated action component:

```text
DemandListDetail.vue
  owns route parsing, store orchestration, edit state,
  dialogs, messages, navigation, and rendering

DemandListLifecycleActions.vue
  owns only action-button rendering
  from status + explicit permissions + busy state

demand-list-lifecycle.ts
  owns pure action and generation eligibility rules

useDemandListStore
  owns server state, loading, mutation serialization,
  stale response isolation, normalized errors, and versions
```

### 4.2 Rejected approaches

#### Smart lifecycle component

A component that imports the store, router, dialogs, and API directly would reduce page wiring but tightly couple presentation to navigation and state. It would also make the capability matrix harder to test independently.

#### Monolithic detail page

Putting all action rendering, lifecycle logic, item editing, dialogs, and store calls in one file would create an oversized page and encourage duplicate state checks.

## 5. File map

### 5.1 Create

```text
frontend/src/components/maintenance/calculation/DemandListLifecycleActions.vue
frontend/src/views/maintenance/calculations/DemandListDetail.vue
frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

### 5.2 Modify

```text
frontend/src/components/maintenance/calculation/demand-list-lifecycle.ts
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
frontend/src/views/maintenance/calculations/CalculationComparison.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/maintenance-calculation.ts
```

### 5.3 Explicitly unchanged

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

The parent Plan 05-3C document described the lifecycle test as a created file and the four top-level locale files as modified files. At the Task 6 baseline, the lifecycle test already exists and calculation locales are centralized in `maintenance-calculation.ts`. This design uses the actual repository structure.

## 6. Calculation comparison generation entry

### 6.1 Placement

Add a demand-list generation panel between the existing comparison summary and comparison table.

The panel contains:

```text
name                    required
description             optional
create action
eligibility explanation
normalized creation error
```

The existing item-decision table and decision drawer remain structurally unchanged.

### 6.2 Pure generation eligibility helper

Extend `demand-list-lifecycle.ts` with a pure helper:

```ts
export interface DemandListGenerationComparison {
  group_status: CalculationGroupStatus
  rows: ReadonlyArray<{
    decision: unknown | null
    candidates: Readonly<Record<
      string,
      { status: 'SUCCEEDED' | 'NO_RESULT' }
    >>
  }>
}

export function canOfferDemandListGeneration(
  comparison: DemandListGenerationComparison | null,
  permissions: MaintenancePermissions,
): boolean
```

The helper returns `true` only when:

1. `permissions.editDemandList` is true;
2. a comparison exists;
3. group status is terminal:
   - `COMPLETED`;
   - `PARTIALLY_COMPLETED`;
   - `FAILED`;
   - `CANCELLED`;
   - `INTERRUPTED`;
4. at least one row exists;
5. every row has a saved decision;
6. every row has at least one `SUCCEEDED` candidate cell.

It returns `false` for `PENDING` and `RUNNING`.

### 6.3 Authority boundary

This helper is a conservative presentation gate, not an authoritative business validator.

The comparison DTO does not currently expose a dedicated structural-error collection or backend generation-readiness summary. Therefore:

- the frontend must not infer that a group is definitely valid;
- the backend create endpoint remains authoritative;
- the page must display stable service errors such as incomplete decisions or structural conflicts;
- Task 6 must not modify the backend or comparison DTO to add readiness fields.

### 6.4 Creation request

Before calling the store:

- trim the name;
- reject an empty trimmed name locally;
- trim the description;
- send an empty description as `null`;
- generate a unique idempotency key;
- do not include tenant information.

Call:

```ts
await demandListStore.create(
  {
    calculation_group_id: groupId,
    name: trimmedName,
    description: trimmedDescription || null,
  },
  requestKey('create-demand-list'),
)
```

On success, navigate with the ID returned by the server aggregate:

```ts
router.push({
  name: 'maintenanceDemandListDetail',
  params: { listId: created.id },
})
```

Do not derive the target ID from the route, comparison, timestamp, or local sequence.

## 7. Hidden demand-list route

Add the following child route:

```text
path: calculations/demand-lists/:listId
name: maintenanceDemandListDetail
component: DemandListDetail.vue
```

Required metadata:

```ts
{
  requiresAuth: true,
  requiresInit: true,
  hideInMaintenanceMenu: true,
}
```

The route must not appear in the maintenance menu.

### 7.1 Route validation

`DemandListDetail.vue` parses `route.params.listId` as a positive integer.

Invalid input:

- does not call the store;
- clears the current store route through `dispose`;
- renders a stable invalid-link state;
- provides navigation to the calculation list.

Valid input:

- calls `store.load(listId)`;
- reloads when `listId` changes;
- invalidates previous requests on unmount.

## 8. Demand-list detail page

### 8.1 Header

Render:

- back action;
- demand-list name;
- description;
- status tag;
- lifecycle action component.

The normal back target is the source comparison:

```ts
router.push({
  name: 'maintenanceCalculationComparison',
  params: { groupId: current.calculation_group_id },
})
```

If no aggregate is available, back to `maintenanceCalculations`.

### 8.2 Aggregate facts

Render:

```text
demand-list ID
version_number
optimistic version
lineage_id
scenario_version_id
calculation_group_id
is_current
derived_from_id
superseded_by_id
created_by_user_id
created_at
updated_at
```

Link rules:

- `calculation_group_id` links to the comparison route;
- `derived_from_id` links to another demand-list detail route;
- `superseded_by_id` links to another demand-list detail route;
- `scenario_version_id` is displayed as an ID only because the aggregate does not contain the scenario template ID required by the existing scenario-version route.

### 8.3 Lifecycle strip

Render the fixed lifecycle order:

```text
DRAFT
PENDING_CONFIRMATION
CONFIRMED
PUBLISHED
VOIDED
```

Use the aggregate status to mark the current/reached state.

Do not invent actor, timestamp, or transition facts from status alone. Those facts come from `events`.

### 8.4 Item table

Columns:

```text
spare-part code
spare-part name
unit
criticality
reliability model
execution mode
original quantity
final quantity
decision type
decision risk
admin confirmation state
actions
```

Decimal values are rendered directly from strings.

Forbidden conversions:

```text
Number(...)
parseFloat(...)
parseInt(...)
unary plus
arithmetic formatting based on JS number
```

Text-only grouping or separators may be used only if implemented without numeric conversion and without changing the underlying value.

### 8.5 Audit timeline

Render lifecycle events in server order.

For each event show:

```text
event type
actor user ID
actor roles
occurred_at
request_id
idempotency key when present
before summary when present
after summary when present
```

Do not render raw full request or response snapshots by default. They may be placed in an expandable audit-details region if needed, but the default UI remains concise.

## 9. DRAFT item editing

### 9.1 Edit authorization

Use the existing pure helper:

```ts
canEditDemandListItem(
  current.status,
  permissionStore.permissions,
)
```

Only `DRAFT` plus `editDemandList` may edit.

Published, pending, confirmed, and voided lists remain read-only even for administrators.

### 9.2 Editor

The page owns one selected-item editor.

Fields:

```text
read-only spare-part identity
read-only original quantity
read-only current final quantity
new final quantity
adjustment reason
save
cancel
```

The quantity input uses:

```html
<input
  type="text"
  inputmode="decimal"
>
```

It does not use `type="number"`.

Local checks:

- trimmed quantity is non-empty;
- trimmed reason is non-empty.

The server remains authoritative for Decimal validity and quantity bounds.

### 9.3 Save behavior

Call:

```ts
await store.updateItem(
  item.id,
  trimmedQuantity,
  trimmedReason,
)
```

The page must not update the row optimistically.

After success:

- render the aggregate returned by the store;
- use the server-returned version;
- close the editor;
- show a success message.

After failure:

- preserve the current successful aggregate;
- preserve the user's editor values;
- display normalized error details;
- keep the editor open unless the route changed.

## 10. Lifecycle action component

### 10.1 Public contract

```ts
props:
  status: DemandListStatus
  permissions: MaintenancePermissions
  busy: boolean

emits:
  select: [action: DemandListAction]
```

The component calls:

```ts
demandListActions(status, permissions)
```

It does not infer roles.

### 10.2 Forbidden dependencies

`DemandListLifecycleActions.vue` must not import or call:

```text
useDemandListStore
useMaintenancePermissionsStore
useAuthStore
useRoute
useRouter
maintenance API modules
DialogPlugin
MessagePlugin
raw TenantRole values
```

It is a presentation component.

### 10.3 Button behavior

All buttons are disabled while `busy` is true.

Action order is the exact resolver order:

```text
DRAFT                edit, submit
PENDING_CONFIRMATION confirm
CONFIRMED            publish
PUBLISHED            derive, void
VOIDED               none
```

## 11. Lifecycle interactions owned by the page

### 11.1 Edit

Scroll to and focus the item table. No network call.

### 11.2 Submit

Show a confirmation dialog describing the transition to pending confirmation.

On confirm:

```ts
await store.submit(requestKey('submit'))
```

### 11.3 Confirm

Open an interaction containing a required confirmation note.

Rules:

- trim the note;
- do not submit an empty note;
- pass the exact note to the store;
- do not rename the field to `note` in the API layer.

Call:

```ts
await store.confirm(
  trimmedConfirmationNote,
  requestKey('confirm'),
)
```

### 11.4 Publish

Show a warning dialog that states:

- the list becomes published;
- item content becomes immutable;
- future changes require derivation.

Call:

```ts
await store.publish(requestKey('publish'))
```

### 11.5 Derive

Show a confirmation dialog.

Call:

```ts
const derived = await store.derive(requestKey('derive'))
```

Then route using `derived.id`.

The source published list remains readable in browser history.

### 11.6 Void

Show a danger confirmation dialog explaining that:

- history remains;
- the version is no longer current when applicable;
- the operation does not delete the list.

Call:

```ts
await store.voidList(requestKey('void'))
```

## 12. Error and concurrency behavior

The page relies on the Task 5 store guarantees:

```text
one shared mutation gate
server expected_version propagation
stale load isolation
stale mutation isolation
derive response may change ID
failure preserves the last successful aggregate
structured errors retain code/details/request_id
mutating resets in success and failure paths
```

The page must not:

- parse error messages;
- compare message substrings;
- locally increment versions;
- retry a mutation automatically with a new version;
- overwrite a newer route with an older result.

### 12.1 Conflict UX

On a structured conflict:

- keep the last successful aggregate visible;
- keep unsaved form values where safe;
- show code, details, and request ID through the shared error UI;
- offer an explicit reload;
- do not silently discard user input.

## 13. Internationalization

Add a `demandList` section to every locale object in:

```text
frontend/src/i18n/locales/maintenance-calculation.ts
```

Shape:

```ts
demandList: {
  generation: {},
  detail: {},
  status: {},
  items: {},
  actions: {},
  dialogs: {},
  timeline: {},
  errors: {},
}
```

Requirements:

- English and Simplified Chinese contain complete user-facing translations.
- Korean and Russian keep the existing `...enUS` inheritance pattern and override core headings, actions, statuses, and destructive confirmations.
- All four locale objects expose the same key shape.
- No Task 6 key is placed in the top-level `pages` menu object because no menu item is added.

## 14. Test strategy

### 14.1 Pure lifecycle tests

Extend:

```text
frontend/src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
```

Cover:

- exact action matrix;
- DRAFT item edit permission;
- published item editor always disabled;
- VOIDED returns no actions;
- running comparison cannot generate;
- missing decision cannot generate;
- row without a successful candidate cannot generate;
- viewer cannot generate;
- contributor can generate when all conservative conditions pass;
- admin can generate when all conservative conditions pass;
- helper does not require or inspect raw roles.

### 14.2 Navigation and source-contract tests

Create:

```text
frontend/src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

Cover:

- route name;
- route path;
- authentication metadata;
- initialization metadata;
- hidden-menu metadata;
- `CalculationComparison.vue` uses `useDemandListStore`;
- comparison creation routes with the returned aggregate ID;
- `DemandListDetail.vue` uses the demand-list store;
- detail page uses `DemandListLifecycleActions`;
- detail page uses `canEditDemandListItem`;
- derive routes with the returned aggregate ID;
- route invalidation calls `dispose`;
- quantity input uses text plus decimal input mode;
- source contains no raw-role checks;
- source contains no Decimal numeric conversion;
- locale shapes match.

### 14.3 Existing regressions

Re-run:

```text
demand-list API tests
demand-list store tests
permission tests
calculation comparison/navigation tests
scenario navigation tests
```

### 14.4 Final verification

Focused command:

```powershell
& '.\node_modules\.bin\tsx.cmd' --test `
  src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/stores/maintenance/__tests__/demand-list.test.ts `
  src/api/maintenance/__tests__/demand-lists.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Complete gates:

```powershell
npm run test
npm run type-check
npm run build
git diff --check
```

The Task 5 full frontend baseline is 398 tests. Task 6 acceptance requires:

```text
test count > 398
pass = test count
fail = 0
cancelled = 0
skipped = 0
todo = 0
type-check exit = 0
build exit = 0
```

## 15. Acceptance criteria

Task 6 is complete only when:

1. a permitted user can create a demand-list DRAFT from an eligible comparison;
2. the created aggregate ID drives navigation;
3. the detail route is authenticated, initialized, and hidden from the menu;
4. invalid list IDs do not call the API;
5. DRAFT item editing preserves Decimal strings and requires a reason;
6. non-DRAFT item editing is impossible;
7. lifecycle buttons come only from the pure capability resolver;
8. submit, confirm, publish, derive, and void require explicit interactions;
9. confirm passes the exact confirmation note;
10. derive navigates to the returned new ID;
11. published and voided versions remain readable;
12. audit and lineage facts come from server fields;
13. stale responses cannot overwrite a newer route;
14. structured error details remain visible;
15. no raw role names drive UI actions;
16. all four locale shapes match;
17. focused and complete frontend gates pass;
18. no backend, Go, menu, inventory, procurement, review, or report scope is added.

## 16. Implementation sequencing

After written-spec approval, create a separate implementation plan with TDD checkpoints:

```text
Task 0  plan documentation boundary
Task 1  RED lifecycle-generation and navigation contracts
Task 2  pure generation helper and route GREEN
Task 3  lifecycle action component GREEN
Task 4  comparison generation entry GREEN
Task 5  demand-list detail and item edit GREEN
Task 6  lifecycle dialogs, navigation, and locales GREEN
Task 7  full frontend verification and feature commit boundary
```

No production source work starts before that implementation plan is approved.

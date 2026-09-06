# Task 2 Report: Report list and supported filters

## RED

Command:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts
```

Result: failed as expected before implementation: `normalizeReportListQuery` was not exported from the placeholder `ReportCenter.vue`, and `ReportListTable.vue` did not exist.

## GREEN

Implemented `ReportFilterBar.vue`, `ReportListTable.vue`, and report-center route/query state. The normalizer applies page/sort defaults, removes blank values, preserves supported source constraints, and discards unsupported keys. The list is cancellation-safe, has loading/error/empty/pagination states, and uses the future `maintenanceReportDetail` route name without adding Task 3's route/detail files.

Focused test command:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts
```

Result: PASS — 2 tests passed.

Type check command:

```powershell
cd frontend; npm run type-check
```

Result: PASS.

Diff validation command:

```powershell
git diff --check
```

Result: PASS (no whitespace errors).

## Changes

- Added backend-supported report filter controls and clear/apply behavior.
- Added a list table with report/version/progress/timestamp fields and actions restricted through `getReportActions`.
- Added query-route synchronization at `/platform/maintenance/reports` and navigation to `maintenanceReportDetail`.
- Added English and Simplified Chinese report-list copy.

## Scope note

An existing unrelated modification to `.superpowers/sdd/progress.md` was preserved and not staged.

## Review repair

- Added the two missing backend job statuses and typed report-type/status allowlists.
- Query normalization now enforces backend page, page-size, string-length, enum, and sort constraints while preserving arbitrary nonblank `source_type` values.
- Replaced source-text evaluation with a direct pure-module test and SSR-rendered `ReportListTable` action test.
- Current requests clear old rows and pagination before loading, so stale data cannot remain visible during a query transition or error.

## DOM-test follow-up evidence

RED/GREEN history: the original report-list test failed before list/query implementation because the placeholder did not export list state and the table was absent. The later DOM-test attempt also exposed a TypeScript event-union error in `ReportListTable`; GREEN widens the emitted event type to cover the complete `ReportAction` union while runtime rendering remains restricted by `getReportActions`.

Dependencies: added Vue-3-compatible `@vue/test-utils` and `jsdom` as dev dependencies, with the frontend lockfile updated in commit `28425875c`.

Current mounted-test status: only the test utility/component loading is mounted; it does **not** yet mock router/report API deferred requests or exercise row navigation, query dispatch, loading, empty, error, pagination, and race behavior. Therefore those DOM scenarios are not claimed as covered by the current two focused tests.

Gate commands run after the follow-up:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-actions.test.ts
cd frontend; npm run type-check
git diff --check
```

Results: focused test 2/2 PASS; Task 1 report client/action regression 9/9 PASS; type-check PASS after the `ReportAction` event-union correction; diff check PASS.

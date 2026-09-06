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

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

## P1 remediation: executable SFC DOM interaction tests

The previous follow-up did not complete the P1 interaction coverage. This
remediation replaces the failed custom Vite transform/data-URL loader with
normal SFC imports compiled by `@vitejs/plugin-vue` in Vitest's jsdom
environment. No source-string replacement, `new Function`, SSR-only render,
or application-side test seam remains in the suite.

### RED evidence

Before changing the runtime, the inherited uncommitted test was executed:

```powershell
cd frontend
npm run test -- src/components/maintenance/report/__tests__/report-list-state.test.ts
```

Exit 1: 2 tests, 1 passed, 1 failed. The mounted center failed with
`TypeError [ERR_UNSUPPORTED_RESOLVE_REQUEST]`: the data-URL module could not
resolve `/node_modules/vue-router/dist/vue-router.mjs`. This reproduced the
reported loader defect before replacing it.

After writing the standard import-based test suite and new component script,
but before installing the missing test runner:

```powershell
npm run test:components -- src/components/maintenance/report/__tests__/report-list-state.test.ts
```

Exit 1: `'vitest' is not recognized as an internal or external command,
operable program or batch file.` This is runtime RED evidence, not a claim
that existing production behavior newly failed a behavioral assertion.

### Runtime and coverage

- Added only `vitest` (`^4.1.11`) to dev dependencies and its lockfile entries.
  Reused existing Vue 3.5.34, Vite 7.3.6, plugin-vue 6.0.6,
  Vue Test Utils 2.5.0, jsdom 26.1.0, and TypeScript 6.0.3.
- Added `vitest.config.ts` with plugin-vue, the normal `@` alias, jsdom,
  and an explicit include for this migrated suite. `npm run test:components`
  runs it; the existing `npm test` continues to serve node:test suites such
  as the Task 1 regression. The old `npm test` command is no longer the
  command for `report-list-state.test.ts`.
- Mounts actual `ReportCenter` through `RouterView`, its real filter/table
  children, and independent `ReportListTable` instances. Report API and auth
  use Vitest mocks; i18n returns stable keys. A per-test memory router plus
  a `router.push` spy isolates app routing. Its named detail target is a
  test-only stub, so Task 3 routes/detail were not implemented.
- URL-to-API checks assert exact normalized backend query values, defaults,
  trimmed filters, supported source constraints, and discarded unsupported
  keys; a pure normalizer case also checks invalid enums and limits.
- Clicking an actual row asserts the exact named `maintenanceReportDetail`
  push, numeric ID argument, resolved route params, and stub destination.
- Six role/immutability cases assert exact row buttons from real
  `getReportActions`, then click every rendered button and assert its event
  and report ID. They also verify workflow/export clicks do not bubble into
  row navigation. `versions` and `create` remain non-row entry points;
  unauthorized regeneration is absent. An integrated auth case checks admin
  permissions reach the table.
- Deferred requests exercise loading, successful empty results, old-row/page
  removal during reload, error-exclusive state, retry, and both pagination
  directions with preserved query filters and disabled boundary buttons.
- Deferred race cases resolve the new request before the old one, reject an
  old request after current success, and settle an old request while current
  loading remains pending. They assert current rows, pagination, loading and
  error state cannot be overwritten by the stale completion.
- Auto-unmount and restored spies isolate each case. Shared client error
  normalization remains real; no production module was edited.

### GREEN and gates

Installed with `npm install --ignore-scripts --no-audit --no-fund` (exit 0,
22 packages added). Fresh verification on Node 24.13.1 / npm 11.10.0:

```powershell
cd frontend
npm run test:components -- src/components/maintenance/report/__tests__/report-list-state.test.ts
npm run test -- src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-actions.test.ts
npm run type-check
cd ..
git diff --check
```

- Component suite: exit 0, **17/17 passed**, 1 test file passed; Vitest
  duration 1.27 s (163 ms tests), no test errors or warnings.
- Task 1 regression: exit 0, **9/9 passed**, no failures, cancellations,
  skipped tests or todos; duration 241.9742 ms.
- `npm run type-check`: exit 0, `vue-tsc --build` passed, including the new
  Vitest configuration through the existing Node tsconfig include.
- `git diff --check`: exit 0, no whitespace errors. Git printed its usual
  LF-to-CRLF conversion notices.

Installation emitted existing engine warnings for `abbrev@5.0.0` and
`nopt@10.0.1` under Node 24.13.1. `npm explain abbrev` traces both to the
already installed `@vue/test-utils@2.5.0 -> js-beautify@2.0.3` dependency
chain; neither package changed in this remediation. The new Vitest/Vite
combination supports this Node version and all requested gates passed.

Scope: only the component test, test script/dependency, Vitest configuration,
lockfile and this appended report changed. Existing Task 2 production fixes,
backend/C2D/shared client, and Task 3 remain untouched.
`.superpowers/sdd/progress.md` is preserved as found and is not staged or
committed.

### C3 final review P1 remediation

The report-center state branches are now mutually exclusive: loading, error,
empty, and the report table are rendered through one `v-if`/`v-else-if`/
`v-else` chain. Pagination is also suppressed while loading or after an API
error. The existing error-state test now asserts that both `ReportListTable`
and the native `<table>` are absent, while retry and successful rendering
remain covered by the same case.

Verification:

```powershell
cd frontend
npm run test:components -- src/components/maintenance/report/__tests__/report-list-state.test.ts
cd ..
git diff --check
```

- Component suite: exit 0, **17/17 passed**.
- `git diff --check`: exit 0 (only expected LF-to-CRLF conversion notices).

Scope remains limited to the Task 2 report view, its component test, and this
report; backend/shared client/Task 3 files were not changed.

### C3 final review allowlist and event-type follow-up

The report job status union and runtime normalizer allowlist now contain only
the C3-supported values: `CREATED`, `GENERATING_SECTIONS`,
`VALIDATING_NUMBERS`, `READY_FOR_REVIEW`, `PARTIALLY_COMPLETED`, `FAILED`,
and `FINALIZED`. `BUILDING_SKELETON` and `VALIDATING_CITATIONS` are rejected
by query normalization and are not sent to the list API. Report table runtime
buttons are unchanged, including the `view` button mapped to `open`, while
the component emit type is narrowed to `open`, `generate`, `validate`,
`finalize`, `regenerate`, and `export`; `view`, `versions`, and `create` are
not valid emitted event types.

Verification:

```powershell
cd frontend
npm run test:components -- src/components/maintenance/report/__tests__/report-list-state.test.ts
cd ..
git diff --check
```

- Component suite: exit 0, **18/18 passed**.
- `git diff --check`: exit 0 (only expected LF-to-CRLF conversion notices).

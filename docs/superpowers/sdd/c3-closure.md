# C3 report center frontend closure

## Revision evidence

- Base: `b96a281fbc6d1809a5bb1e0a0ab6bbe32d797330`
- Original C3 implementation head: `7c6f8e3e4f7b7529905d5f592979e47655f85327`
- Closure commit: `9349822c4107220e93a56710fa928266ec089ede`
- Branch: `codex/maintenance-plan05-5-c3`

The final commands below were run against the pre-commit working tree whose
committed representation is closure commit `9349822c4`; they did not run
against `7c6f8e3` alone. This evidence-correction follow-up commit is a child
of `9349822c4`, and does not claim that its own later HEAD was validated by
those earlier commands.

## Reproducible gates

Run from `frontend` unless noted otherwise.

| Command | Result |
| --- | --- |
| `npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-list-state.test.ts src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts src/components/maintenance/report/__tests__/report-export.test.ts` | exit 0; Node/tsx 16 passed and Vitest 26 passed (42 total) |
| `npm run test -- src/components/maintenance/chat/__tests__` | exit 0; Node/tsx 9 passed |
| `npm run test` | exit 0; Node/tsx 505 passed, Vitest 30 passed, 535 total; 0 failed, skipped, cancelled, or todo |
| `npm run type-check` | exit 0 (`vue-tsc --build`) |
| `npm run build` | exit 0; Vite transformed 6,635 modules and built in 1m42s |
| `git diff --check` | exit 0 |

`npm test` now invokes `scripts/run-tests.mjs`: it recursively expands the supplied files or directories, removes duplicate resolved paths, then runs ordinary `node:test` suites through `tsx --tsconfig tsconfig.app.json --test` and explicit Vitest suites through Vitest. This preserves the Node suite while loading Vue SFC tests with the Vue-aware runner. The focused commands in the task brief use this same reproducible entrypoint.

## Accepted warnings and artifacts

- The test run prints the existing TDesign whole-package notice while importing the shared download interceptor; all 15 affected client tests pass.
- The production build reports the existing Rollup chunk-size warning for chunks over 500 kB. It does not prevent output generation or produce an error.
- `git diff --check` prints Windows CRLF working-copy warnings only; it reports no whitespace errors.
- Build output is the ignored `frontend/dist/` artifact; no generated artifact is staged.

## Manual acceptance

- The former report placeholder is replaced by `ReportCenter` and `ReportDetail`; list/filter navigation is `/platform/maintenance/reports` and the named detail route remains under `/platform/maintenance/`.
- `ReportFilterBar` and `normalizeReportListQuery` expose and serialize only the typed supported report, job, version, source, paging, and sort filters; unsupported values are discarded.
- `ReportProvenancePanel` consumes the public C2D selector only. Its focused rendered-state test feeds raw snapshot/tenant/token fields and verifies none reach the DOM.
- `getReportActions` supplies Viewer read-only view/version/export affordances, permits Contributor workflows only at allowed server states, and gates finalize to Admin with reviewed, ready, resolved evidence.
- A `FINAL` version removes immutable lifecycle actions while retaining only the explicit allowed regeneration affordance.
- `ReportExportActions` offers exactly MARKDOWN, JSON, and DOCX. The controller uses the safe server filename parser and cleanup path verified by focused export tests.
- Chat Card normalization accepts only same-origin `/platform/maintenance/` paths and fails closed for unsafe navigation; all 9 Chat Card tests pass.

## Scope confirmation

This closure changes only the C3 test runner configuration, a C3-caused hidden-route regression expectation, and closure evidence. It introduces no backend, C4, source-policy, or lifecycle behavior changes. `.superpowers/sdd/progress.md` is an existing user change and is intentionally excluded.

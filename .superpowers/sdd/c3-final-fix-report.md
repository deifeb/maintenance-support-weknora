# C3 final fix wave

Date: 2026-09-08 (Asia/Shanghai). Branch: `codex/maintenance-plan05-5-c3`.
Reviewed head: `54a96e580194091f4d15e4434d45fb3f02e52e20`.
Base: `b96a281fbc6d1809a5bb1e0a0ab6bbe32d797330`.

This report covers one final frontend fix wave, resumed from its existing
uncommitted changes after interruption. It is separate from the old C2D-C
`final-fix-report.md`, which was not changed.

## Findings addressed

1. The test runner accepts both `.test.ts` and `.test.mjs`. Explicit files,
   directories and overlaps deduplicate; Node/Vitest classification and nonzero
   propagation remain intact. A deliberately failing fixture outside default
   discovery verifies failure propagation. The regression starts fresh subprocess
   harnesses without inheriting Node's internal NODE_TEST_CONTEXT.
2. Report mutations are locked by report ID in shared reactive state. The lock
   outlives component unmount, includes the active detail reader reload, and
   blocks Refresh, all lifecycle buttons and regenerate entry/confirmation.
   Mounted readers register/unregister with the report ID; mutation completion
   refreshes the current reader. The lifecycle controller captures the original
   report ID so a reused component cannot refresh another report.
3. Apply normalizes the full current query with edited controls, preserving
   untouched source_id/source_version, legacy IDs, sort and page_size. Unchanged
   filters retain page; changed filters reset page to 1. Clear resets defaults.
4. source_type is the eight-value AIReportSourceType union. The normalizer and
   select reject SESSION, FUTURE and unsupported values.
5. Public generated evidence is generated_at OR nonempty sections, preserving
   persisted legacy reports' validate/regenerate affordances and disabling
   generate for an already generated version.
6. Citations render source_name, document_version, page_number, chunk_reference
   and knowledge_node with citation_id fallback. No label/source_id assumption
   remains, and unknown/private fields are not rendered.
7. Generate/validate/finalize/regenerate return the ReportJobStatusRead envelope
   documented by the existing backend facade; client contract tests enforce it.
8. Detail, provenance, timeline, findings, sections, legacy-create labels and
   type/status/source labels use en-US/zh-CN translations. A template AST check
   guards hardcoded visible English and missing keys; actual mounted Detail tests
   exercise both locale dictionaries.

Backend contracts inspected read-only:
`app/schemas/report_center.py`, `app/schemas/ai_report.py`,
`app/models/enums.py`, `app/api/v1/reports.py`,
`app/services/report_center_service.py`, and
`app/services/ai_report_service.py`, under `extensions/maintenance-api`.
In particular, _is_version_generated checks timestamp then persisted sections;
the facade's four lifecycle methods all return ReportJobStatusRead; the public
citation allowlist includes the displayed document fields.

## RED evidence

All commands below ran from `frontend` before their corresponding production
fixes:

- `npm run test -- src/components/maintenance/report/__tests__/report-runner.test.ts src/components/maintenance/report/__tests__/report-list-state.test.ts`:
  exit 1. The runner rejected the explicit settingsStorage.test.mjs target.
  Three component assertions exposed FUTURE acceptance, lost source/sort/page
  constraints and the missing source enum selector. The initial subprocess
  failure check also exposed inherited NODE_TEST_CONTEXT in the test harness;
  this was corrected before relying on its result.
- `npm run test -- src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-runner.test.ts`:
  exit 1. Three Detail regressions failed: Refresh was not disabled during a
  deferred regeneration, legacy sections did not allow validate, and a
  backend-shaped citation displayed “#undefined” instead of its document name.
  A test-harness directory-count assertion was corrected to compare a directory
  with its overlapping explicit file, since src/stores contains other TS suites.
- `npm run test -- src/components/maintenance/report/__tests__/report-i18n.test.ts src/components/maintenance/report/__tests__/report-api-contract.test.ts`:
  exit 1; two tests failed on hardcoded provenance text and incorrect mutation
  response declarations.
- `npm run test -- src/components/maintenance/report/__tests__/report-lifecycle-ui.test.ts`:
  exit 1; 1 failed, 4 passed. Changing reportId while validation was unresolved
  refreshed the new ID rather than the mutated ID. Capturing the original ID
  fixed this regression.

During GREEN verification the i18n scanner initially used baseParse without
HTML void-element rules; switching to compiler-dom's HTML parser resolved that
test-harness issue. Production Vue compilation was unaffected.

## GREEN and final gates

The exact commands and totals are also recorded in
`docs/superpowers/sdd/c3-closure.md`.

| Gate | Command | Final result |
| --- | --- | --- |
| Exact planned focused C3 | `npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-list-state.test.ts src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts src/components/maintenance/report/__tests__/report-export.test.ts` | exit 0; 17 Node + 33 Vitest = 50 |
| All C3 + shared client | `npm run test -- src/components/maintenance/report/__tests__ src/api/maintenance/__tests__/client.test.ts` | exit 0; 35 Node + 38 Vitest = 73 |
| Chat Cards | `npm run test -- src/components/maintenance/chat/__tests__` | exit 0; 9 |
| Existing MJS suites | `$mjsSuites = @(rg --files src -g '*.test.mjs'); npm run test -- $mjsSuites` | exit 0; 22 files, 117 tests |
| Full frontend | `npm run test` | exit 0; 626 Node + 38 Vitest = 664; zero failures/skips/cancellations/todo |
| Types | `npm run type-check` | exit 0 |
| Build | `npm run build` | exit 0; 6,636 modules, 1m52s |
| Whitespace | `git diff --check` at worktree root | exit 0 |

The extended, full, type and build commands yielded running sessions; each was
polled to its final exit code. No completion result was inferred from an early
yield. The 117 MJS tests are included once in the 626 Node total. The earlier
535 total omitted these suites; adding those 117 and 12 new regressions produces
the corrected 664 total.


## Route-reuse ownership follow-up after 6ddf64f05

Final review reproduced a remaining fallback ownership error when no reader for
the original report remained registered. A deferred report 7 regeneration was
started, the memory router navigated directly to report 8 (same Detail component
UID), and report 8's regeneration dialog was opened. When report 7 completed,
the fallback load callback read the reactive current route ID and caused an
unrelated report 8 reload.

The new regression uses the compiled ReportDetail and production children.
After correcting the test's instance-identity assertion to use Vue's stable UID
instead of the test wrapper's changing proxy, the RED run was:

`npm run test -- src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-ui.test.ts`

Result: exit 1; 1 failed and 13 passed. getReport calls were [7, 8, 8] instead
of [7, 8]. This directly exercised unregistering reader 7 through route reuse.

The fix binds the Detail refresh callback to its owning report ID and mounted
instance, uses that callback for reader registration and both mutation controls,
and captures the regeneration callback at submission time. A stale callback
returns without reading another report. Shared lock cleanup still runs.

GREEN command:

`npm run test -- src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-ui.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts`

Result: exit 0; 4 Node + 14 Vitest = 18 passed. The new assertions prove reads
remain [7, 8] for detail and timeline, report 8 keeps its exact dialog DOM node
and enabled confirmation control, report 7's lock releases, and regeneration
was called exactly once with report 7. All final gates above were then rerun,
including full tests, type checking and production build. The additional test
raises the final total from 663 to 664 without changing the 626 Node count.

## Scope and handoff

All changes are C3 frontend contract alignment, regression coverage and closure
documentation. No backend/C4/source-policy/lifecycle service changes were made.
No merge or push was requested in this subtask. The named worktree and branch
remain available. `.superpowers/sdd/progress.md` is user-owned and excluded.
The pre-commit final working tree was validated; the task handoff reports the
commit that contains those code/tests and this evidence.

Accepted existing warnings: TDesign whole-package import notice, Rollup chunks
over 500 kB and Git LF/CRLF conversion warnings. Ignored frontend/dist output is
not staged. No known remaining reviewer finding or failing gate.

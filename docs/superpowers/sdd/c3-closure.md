# C3 report center frontend closure

## Revision evidence

- Base: `b96a281fbc6d1809a5bb1e0a0ab6bbe32d797330`
- Reviewed head before this final fix wave: `54a96e580194091f4d15e4434d45fb3f02e52e20`
- Initial final-fix commit before the route-reuse follow-up: `6ddf64f055b0c7b418beeece97d7255753617cf6`
- Branch: `codex/maintenance-plan05-5-c3`
- Verification date: 2026-09-08 (Asia/Shanghai).

The commands below ran against the final corrected working tree based on the
reviewed head, with code, regression tests and this closure committed together.
They are not evidence for the reviewed head alone. The commit containing this
closure records the verified code revision; its hash is reported in the task
handoff. Detailed RED/GREEN evidence is in
`.superpowers/sdd/c3-final-fix-report.md`.

## Reproducible gates

Run from `frontend` unless noted otherwise.

| Command | Result |
| --- | --- |
| `npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts src/components/maintenance/report/__tests__/report-api-contract.test.ts src/components/maintenance/report/__tests__/report-list-state.test.ts src/components/maintenance/report/__tests__/report-detail-state.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts src/components/maintenance/report/__tests__/report-export.test.ts` | exit 0; Node/tsx 17 + Vitest 33 = 50 passed |
| `npm run test -- src/components/maintenance/report/__tests__ src/api/maintenance/__tests__/client.test.ts` | exit 0; Node/tsx 35 + Vitest 38 = 73 passed |
| `npm run test -- src/components/maintenance/chat/__tests__` | exit 0; Node/tsx 9 passed |
| `$mjsSuites = @(rg --files src -g '*.test.mjs'); npm run test -- $mjsSuites` | exit 0; 22 pre-existing files, 117 passed |
| `npm run test` | exit 0; Node/tsx 626 + Vitest 38 = 664 passed; 0 failed, skipped, cancelled or todo |
| `npm run type-check` | exit 0 (`vue-tsc --build`) |
| `npm run build` | exit 0; 6,636 modules transformed, built in 1m52s |
| `git diff --check` (worktree root) | exit 0 |

The former 535-test total omitted all 22 pre-existing `.test.mjs` files and is
not a valid full-suite total. The corrected final 664 total includes those
117 tests exactly once plus 12 new regression tests. The separate 117-test
verification is a subset of the 626 Node tests, not an additional count.

The runner discovers both `.test.ts` and `.test.mjs`, recursively expands
explicit files/directories, deduplicates resolved paths, and preserves the
Node/tsx versus Vitest classification. Both test-runner failures and unmatched
targets return a nonzero exit code.

## Acceptance and scope

- The report center and detail route remain under `/platform/maintenance/`;
  the placeholder is replaced and authenticated role gates remain in use.
- Apply preserves untouched source ID/version, legacy source IDs, sorting and
  page size; page resets only when a normalized filter changes. Clear explicitly
  restores defaults. Source type is constrained to the backend eight-value enum.
- A report-level mutation lock survives child and detail-route unmounts and
  remains held through the active detail reload. Refresh, lifecycle controls and
  the regenerate entry are disabled while busy. Deferred-promise DOM tests prove
  one backend regeneration call and correct refresh ownership after ID changes.
  An owned refresh callback additionally guards route reuse after its old reader
  unregisters: report 7 completion cannot reload report 8 or unmount its dialog.
- Generated evidence uses the public timestamp or nonempty persisted sections,
  matching legacy backend behavior; FINAL immutability and role rules remain.
- Public citation fields render meaningful document evidence; raw/private fields
  never enter a generic metadata view. C2D provenance remains allowlisted.
- Lifecycle responses use `ReportJobStatusRead`; all C3 labels, state copy,
  buttons and enum labels have en-US/zh-CN translations with regression checks.
- Exports remain MARKDOWN/JSON/DOCX with authenticated downloads and safe server
  filenames. All 9 Chat Card tests pass.
- No backend, C4, source policy, lifecycle service, or export filename behavior
  changed. The existing user-owned `.superpowers/sdd/progress.md` change is
  excluded from this commit.

## Warnings and artifacts

The existing TDesign whole-package notice and Rollup chunk-size warning remain
non-fatal. Git reports Windows LF/CRLF conversion warnings but no whitespace
errors. Build output remains in ignored `frontend/dist/`; it is not committed.

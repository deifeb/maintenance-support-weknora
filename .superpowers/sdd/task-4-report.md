# Task 4 report — Create, lifecycle, regenerate, and error interactions

## RED

Added `frontend/src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts` before lifecycle implementation. It asserted:

- an allowed `validate` mutation calls `validate:42` and then `refresh`;
- ungranted actions never call a mutation;
- FINAL hides generate/validate/finalize and regeneration uses the required immutable-source-copy wording;
- known errors map to the prescribed key and unknown errors map to the generic key while exposing only `request_id`.

Command:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts
```

Actual RED output (before controller implementation):

```text
SyntaxError: The requested module '../report-actions.ts' does not provide an export named 'createReportLifecycleController'
✖ failing tests: 1
```

## GREEN and verification

Implemented the typed lifecycle controller and the three requested components. Creation requires title, report type, and one or more policy-shaped C2D source references; legacy IDs remain optional compatibility inputs. Mutations are gated, deduplicated while pending, normalized through the Task 1 mapper, and emit `changed` only after mutation success so parents reload server state. No UI state is optimistically changed. Regeneration displays the specified semantic explanation.

Commands and actual outputs:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts
```

```text
✔ lifecycle controller calls the allowed typed mutation then refreshes
✔ lifecycle controller rejects an action not granted by the server state
✔ final version hides immutable lifecycle controls and regeneration explains copied sources
✔ unknown errors use the generic key and expose only their request ID
pass 4; fail 0
```

```powershell
cd frontend; npm run test:components -- src/components/maintenance/report/__tests__/report-list-state.test.ts src/components/maintenance/report/__tests__/report-detail-state.test.ts
cd frontend; npm run type-check
```

```text
Test Files 2 passed (2)
Tests 21 passed (21)
vue-tsc --build (exit 0)
```

`git diff --check` completed with no whitespace errors.

## Scope and self-review

- Added only client components, integration in report Center/Detail, translations, tests, and a small typed controller extension to the Task 1 action module.
- Retained server authority: UI gates are affordances only, and every mutation is still sent to the existing typed endpoint.
- No endpoint/schema/C2D policy/lifecycle authority/export filename changes; no Task 5/C4/backfill/auto-supersede work.
- Dialogs do not render provenance payloads or private/raw backend error messages. Errors render translated normalized keys plus the returned request ID only.
- The existing detail test now mocks the new auth-store dependency, preserving its pre-existing test isolation.

## Review remediation RED/GREEN

### RED

Added the real Vue production-path suite and included it in `frontend/vitest.config.ts`:

```powershell
cd frontend; npm run test:components -- src/components/maintenance/report/__tests__/report-lifecycle-ui.test.ts
```

Actual initial RED result:

```text
Test Files 1 failed (1)
Tests 4 failed (4)
```

The failures proved the review findings through mounted components: a `DEMAND_CALCULATION` with `AI_SESSION` called create, lifecycle controls enabled before deferred parent refresh completed, and two regenerate clicks invoked the endpoint twice. The fourth test confirmed the old request-ID rendering expectation needed i18n interpolation rather than revealing a raw backend message.

### GREEN

Frontend creation policy now mirrors the existing backend `REPORT_SOURCE_POLICIES` in `extensions/maintenance-api/app/services/report_source_policy.py`: each strict report type has exact required/optional source types; `MANAGEMENT_DECISION` allows all supported types. The UI rejects missing required, disallowed, and duplicate source types before create, while the backend remains authoritative.

The action matrix now uses detail server truth: `generated_at`, job/version status, and unresolved findings. Generate requires an ungenerated non-final version; validate requires a generated non-final version; finalize requires admin + READY_FOR_REVIEW + REVIEWED + no unresolved findings; regenerate requires a generated version (including a FINAL parent). List payloads lack generation evidence, so they fail closed for lifecycle mutations. Detail no longer hardcodes a regenerate permission flag.

Each mutation dialog/action receives and awaits its parent `load` callback. Pending state spans the mutation and reload; regeneration mounts only when the computed granted action includes it and retains an internal allowed guard. Error surfaces render only mapped keys plus request IDs, never normalized raw messages.

Commands and actual results:

```powershell
cd frontend; npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts src/components/maintenance/report/__tests__/report-lifecycle-actions.test.ts
cd frontend; npm run test:components
cd frontend; npm run type-check
cd frontend; npm run build
git diff --check
```

```text
Node lifecycle/action suite: pass 8; fail 0
Vitest component suite: Test Files 3 passed (3); Tests 25 passed (25)
vue-tsc --build: exit 0
vite build: exit 0; frontend/dist/index.html generated
git diff --check: no whitespace errors
```

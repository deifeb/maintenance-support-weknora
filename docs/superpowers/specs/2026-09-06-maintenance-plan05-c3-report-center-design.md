# Maintenance Plan 05 C3 — Report Center Frontend Design

## Purpose

Replace the placeholder Report Center with a complete, tenant-safe frontend
for the stable C2D report contract. Deliver the full C3 scope as one PR, with
small independently reviewed implementation tasks. This design covers only the
frontend; it does not add, change, or emulate backend report semantics.

## Baseline and scope

- Baseline: `feature/demand-calculation-engine` at merge commit `b96a281f`.
- Working branch: `codex/maintenance-plan05-5-c3`.
- Existing list route: `/platform/maintenance/reports`.
- New detail route: `/platform/maintenance/reports/:reportId`.
- Existing C2D API contracts, source policy, lifecycle authority, source
  snapshots, and export filenames are authoritative.

In scope are the typed report client, list/filter view, detail/provenance
view, creation and lifecycle controls, export downloads, translations, and
frontend regression gates. Out of scope are backend endpoint changes,
date/generator filters unsupported by the API, raw snapshot rendering, source
backfill, automatic supersede, Chat Card feature work, and C4 or later work.

## Architecture

### API and types

`frontend/src/api/maintenance/reports.ts` will be the only transport boundary
for reports. It exposes typed calls for report listing, job/detail/version
reads, create, generate, validate, finalize, regenerate, and authenticated
exports. Request and response types live with report UI types, rather than
being duplicated across views.

The client carries C2D source fields (`source_type`, `source_id`,
`source_version`, and `source_refs`) and consumes only the backend's public
provenance projection. It must never reconstruct or request raw source
snapshots in the browser.

### Presentation and state

Report UI components are divided by responsibility:

- filter bar and list table own query input and pagination display;
- detail components own timeline, provenance, validation findings, and report
  sections;
- dialogs own create and regenerate input/confirmation;
- lifecycle and export components own mutations/download initiation;
- pure action helpers derive allowed UI affordances from role, job status,
  latest-version status, and the API's error contract.

Views compose these components and refresh server state after successful
mutations. No permission is inferred solely from a visible button: backend
errors remain authoritative and are rendered safely.

## Lifecycle and permissions

Current job states are `CREATED`, `GENERATING_SECTIONS`,
`VALIDATING_NUMBERS`, `READY_FOR_REVIEW`, `PARTIALLY_COMPLETED`, `FAILED`, and
`FINALIZED`. Version states are separately `DRAFT`, `REVIEWED`, `FINAL`, and
`SUPERSEDED`; C3 must not use the obsolete `COMPLETED` UI assumption.

The UI action matrix is:

| Role | Allowed UI actions |
| --- | --- |
| Viewer | view, list versions, export |
| Contributor | viewer actions plus create, generate, validate, regenerate |
| Admin | contributor actions plus finalize |

Finalized reports disable or hide generate, validate, and finalize.
Regeneration remains a distinct action only where the backend permits a
generated latest FINAL version as a parent. Its dialog explicitly says a new
child version is created from the existing version's source snapshot and does
not recalculate business source data.

## List and detail experience

The list supports exactly these backend query fields: `keyword`,
`report_type`, `job_status`, `version_status`, `session_id`,
`scenario_version_id`, `calculation_run_id`, `review_run_id`, `source_type`,
`source_id`, `source_version`, `sort_by`, `sort_order`, `page`, and
`page_size`. Unsupported date-range or generator filtering is absent rather
than stored as inert client state.

List rows show report code, title, type, job state, latest version number and
state, progress, creation/update times, and allowed actions. Detail presents
job and latest-version state, version timeline, parent ID, template version,
generation mode/time, input digest, public source versions, validation
findings, sections, and citations. Only public source versions are rendered;
raw source snapshot JSON and private/internal metadata never appear.

## Errors and downloads

Known backend errors map to translated guidance for
`REPORT_VERSION_ALREADY_GENERATED`, `REPORT_GENERATION_REQUIRED`,
`REPORT_FINAL_VERSION_IMMUTABLE`, `REPORT_REGENERATE_SOURCE_NOT_READY`,
`REPORT_VALIDATION_REQUIRED`, `REPORT_GENERATION_FAILED`,
`REPORT_SOURCE_REQUIRED`, `REPORT_SOURCE_CONFLICT`,
`REPORT_SOURCE_VERSION_CONFLICT`, and `INSUFFICIENT_MAINTENANCE_ROLE`.
Unknown failures use a safe generic message and include a request ID only when
the response provides one.

Export supports `MARKDOWN`, `JSON`, and `DOCX` through the authenticated
maintenance client. The browser download uses the server-supplied content type
and filename; it never builds or reveals an absolute filesystem path.

## Testing and acceptance

Each task receives focused component or API-contract tests. The C3 gate runs
the report action, API contract, list state, detail state, lifecycle, and
export tests; Chat Card regressions; all frontend tests; type checking; and
the production build.

Acceptance requires no placeholder Report Center, no lifecycle divergence,
the viewer/contributor/admin matrix above, C2D source filters and public
provenance visibility, all three export downloads, and safe existing Chat Card
rendering.

## Design decisions

1. Use a single full C3 PR, split into reviewable tasks, to avoid a temporary
   UI with a different lifecycle model from the backend.
2. Keep state/action derivation pure and unit-tested so role and lifecycle
   rules do not drift across list and detail views.
3. Prefer backend-supported filters over speculative frontend state.
4. Treat provenance as display-only public data and make the absence of raw
   snapshots an invariant, not a conditional UI choice.

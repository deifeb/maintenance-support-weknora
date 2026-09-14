# Plan 05 Task 9 Full-Stack Acceptance Design

## Goal

Provide deterministic browser acceptance evidence for the Plan 05 maintenance
workflow using one Playwright configuration that runs identically on a local
developer machine and in CI.

## Scope

Task 9 adds test infrastructure and end-to-end tests only. It does not change
maintenance business rules, report lifecycle semantics, tenant boundaries,
provider configuration, or the Chat Card architecture.

The tested browser path remains the deployed development shape:

```text
Playwright browser -> Vite -> WeKnora /api proxy -> Maintenance API
```

Tests must not bypass the proxy by calling the maintenance API directly from
the browser, and they must not replace authorization or tenant isolation with
browser mocks.

## Runtime Model

`npm run test:e2e` will own a disposable local test environment. The runner
starts the WeKnora service, the Maintenance API, and Vite with explicitly
allocated local ports and test-only configuration. Vite continues to proxy
`/api` through the existing development proxy contract.

The runner creates isolated, non-production test data before the browser
suite and removes it after the suite. A failure must still retain Playwright
trace and screenshot artifacts. Artifacts must never contain JWTs, provider
secrets, absolute local paths, or production records.

CI invokes the same npm command. CI may supply only port, temporary-directory,
and test-configuration values; it must not require persistent proxy settings
or live external AI providers.

## Actors and Data Isolation

The test environment exposes four deterministic actors:

| Actor | Tenant | Role |
| --- | --- | --- |
| `tenant-a-viewer` | tenant-a | Viewer |
| `tenant-a-contributor` | tenant-a | Contributor |
| `tenant-a-admin` | tenant-a | Admin |
| `tenant-b-admin` | tenant-b | Admin |

Authentication setup produces independent browser storage state for each
actor through the ordinary application flow. Tests use only seeded fixture
data and assert that tenant-b cannot enumerate or mutate tenant-a records.

## Test Boundaries

The suite is split by independently meaningful browser behavior:

1. Navigation: maintenance menu, collapsed navigation, and maintenance-only
   route ownership under `/platform/maintenance/`.
2. Permissions: viewer has no mutation controls, contributor can perform
   authorized report actions, and only admin can finalize.
3. Tenant isolation: tenant-b cannot list, open, or mutate tenant-a facts.
4. Scenario and calculation: structured scenario entry, autosave/version
   conflict presentation, calculation partial failure, and retry.
5. Inventory and allocation: demand-list immutability, review-derived list,
   FEFO reservation, allocation confirmation, and execution.
6. Reports and Chat Cards: Report Center list/detail/provenance/lifecycle,
   regenerate-to-child behavior, Markdown/JSON/DOCX download, all six known
   card renderers, safe unknown-card fallback, and maintenance-route
   navigation.

Each test seeds or reads only the smallest fixture required for its scenario.
Long cross-domain setup is centralized in the test environment, not duplicated
inside individual specs.

## Reliability and Failure Semantics

Playwright retains traces on failure and screenshots only on failure. The
suite runs serially where shared workflow state requires it; independent actor
and navigation cases remain isolated. Server startup, seed, readiness, and
cleanup failures are explicit test-environment failures and never downgrade to
mocked browser tests.

The expected UI assertions use stable accessible labels, roles, route paths,
and public response state. They do not rely on timing sleeps, internal IDs,
provider output wording, or implementation-only state.

## Acceptance Gates

Task 9 is ready for closure only when:

- local `npm run test:e2e` passes against the disposable stack;
- CI uses the same command and configuration contract;
- all four actors have isolated storage state;
- every required browser scenario has evidence;
- failure artifacts obey the redaction policy; and
- existing frontend unit tests, type checking, build, and backend integration
  gates remain green.

## Non-Goals

Task 9 does not introduce browser mocks for maintenance authorization, a
second frontend lifecycle state machine, real AI-provider dependencies,
production data access, persistent proxy changes, or release approval.

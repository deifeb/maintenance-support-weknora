# Plan 05 Task 9 E2E Runtime Design

## Goal

Provide a deterministic, local browser-acceptance runtime that exercises the
existing browser request path:

`Playwright -> Vite /api proxy -> WeKnora -> Maintenance API`.

The runtime uses real login and authorization behavior while keeping all data,
ports, logs, databases, and artifacts isolated to one test run.

## Runtime Topology

The launcher creates one E2E run directory below `E2E_ROOT_DIR`. It owns:

- a Maintenance API SQLite database and its export directory;
- a disposable Postgres container and a mounted Postgres data directory for
  WeKnora identities and sessions;
- service logs, a fixture manifest, and Playwright output; and
- three configured loopback ports for Vite, WeKnora, and Maintenance API.

The Postgres container receives a unique, launcher-generated name. It exposes
one launcher-selected loopback port and is started before WeKnora. Its password
and connection URL are process-local values and must never be written to the
manifest, browser storage state, logs, screenshots, or committed files.

The Maintenance API runs against its own disposable SQLite database. The
launcher generates one process-local signing secret, passes it to both backend
services, and does not print it.

## Lifecycle

1. Validate `E2E_ROOT_DIR` and all configured ports before side effects.
2. Create the per-run directory and start the Postgres container.
3. Wait for Postgres, initialize WeKnora's schema and seed four local users.
4. Apply the Maintenance API Alembic head and seed maintenance fixtures.
5. Start Maintenance API and wait for its health endpoint.
6. Start WeKnora with the temporary Postgres configuration and wait for its
   health endpoint.
7. Start Vite with `VITE_DEV_PROXY_TARGET` pointing only to WeKnora.
8. Run Playwright serially. Browser scenarios authenticate through
   `/auth/login`; they never inject internal authorization headers.
9. Stop Vite, WeKnora, Maintenance API, and Postgres in reverse order.
10. Delete the run directory and Postgres container on success. Retain only
    redacted service logs, traces, screenshots, and Playwright reports when a
    test fails.

Any start, readiness, seed, test, shutdown, or cleanup failure fails the E2E
command. The runtime does not substitute mocked browser traffic.

## Boundaries

`runtime.ts` owns validation, paths, process lifecycle, health checks,
sanitized diagnostics, and cleanup. It exposes no credentials to browser specs.
`e2e_seed.py` owns Maintenance API migration and fixture seeding. A separate
WeKnora seed step owns only the real login identities and memberships.
`auth.setup.ts` obtains session storage through the visible `/auth/login`
workflow. `fixtures.ts` exposes aliases and public routes only.

The launcher accepts only documented `E2E_` configuration. Docker is required
for `npm run test:e2e`; failure to find Docker or provision Postgres is a hard
failure with sanitized diagnostics.

## Verification

Unit tests cover launcher input validation and secret redaction before any
service process is introduced. Integration checks establish health and seeded
actor login before scenario specs run. Playwright runs serially with traces and
screenshots retained only on failure. The final local gate runs E2E, frontend
tests, type checks, builds, Maintenance API tests, Ruff, and whitespace checks.

## Scope

This changes test tooling, test-only seed code, browser specs, CI wiring, and
documentation only. It does not alter application business rules, production
configuration, report semantics, tenant isolation behavior, or the browser's
proxy path.

# Plan 05 Task 9 Full-Stack Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic Playwright acceptance gate that exercises the
maintenance UI through Vite, the WeKnora maintenance proxy, and the Maintenance
API with real seeded actor identities.

**Architecture:** A test-only launcher owns disposable data, service startup,
health checks, fixture seeding, and teardown. Playwright owns browser state and
scenario assertions only. Every browser request continues through `/api` and
the WeKnora proxy; neither browser routing nor maintenance authorization is
mocked.

**Tech Stack:** Playwright, Node.js ESM, Vite, Vue 3, Go, FastAPI, Python 3.11,
PowerShell, npm.

## Global Constraints

- Do not alter maintenance business rules, report lifecycle semantics, tenant
  isolation, provider configuration, or Chat Card contracts.
- Use only disposable local data and non-secret `E2E_` environment variables.
- Preserve the browser request path `Vite -> /api -> WeKnora proxy ->
  Maintenance API`; tests must not directly target `/api/v1`.
- Use the real `/auth/login` flow for four seeded actors and never commit
  passwords, JWTs, provider credentials, ports, or local absolute paths.
- Retain Playwright traces and screenshots only on failure. Redact sensitive
  request headers from all test logs and artifacts.
- The test suite fails when prerequisite services, health checks, seeding, or
  cleanup fail; it must not fall back to mocked browser flows.
- Run new browser specs serially until their seed ownership and isolation make
  parallel execution demonstrably safe.

---

### Task 1: Establish the disposable full-stack launcher and Playwright gate

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/scripts/run-maintenance-e2e.mjs`
- Create: `frontend/e2e/maintenance/runtime.ts`
- Create: `frontend/e2e/maintenance/runtime.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: `E2E_ROOT_DIR`, `E2E_FRONTEND_PORT`, `E2E_WEKNORA_PORT`,
  `E2E_MAINTENANCE_PORT`, and the existing `VITE_DEV_PROXY_TARGET` contract.
- Produces: `npm run test:e2e`, a running disposable stack, and a typed
  `MaintenanceE2ERuntime` with `baseURL`, `artifactsDir`, `start()`,
  `waitForHealthy()`, and `stop()`.

- [ ] **Step 1: Define the failing runtime contract**

Create `frontend/e2e/maintenance/runtime.test.ts` with tests that reject a
missing required `E2E_ROOT_DIR`, reject a port value outside `1024..65535`,
and verify that `sanitizeCommandEnvironment` removes every key containing
`TOKEN`, `SECRET`, `PASSWORD`, or `API_KEY` from diagnostic output.

- [ ] **Step 2: Run RED**

Run from `frontend`:

```powershell
npm run test -- e2e/maintenance/runtime.test.ts
```

Expected: failure because the runtime module does not exist.

- [ ] **Step 3: Implement the launcher boundary**

Implement `runtime.ts` so it:

1. resolves all paths relative to `E2E_ROOT_DIR` without printing them;
2. allocates the three explicit ports and passes the Vite proxy target as
   `http://127.0.0.1:<E2E_WEKNORA_PORT>`;
3. creates a unique temporary directory below the configured root for the
   SQLite database, export folders, service logs, and Playwright output;
4. starts the Maintenance API with a generated, process-local 32-byte signing
   secret and matching Go proxy settings;
5. starts WeKnora with its maintenance proxy enabled and Vite only after both
   backend health endpoints succeed; and
6. terminates child processes in reverse dependency order and removes the
   temporary directory in `finally` unless failure artifacts are required.

`run-maintenance-e2e.mjs` must create the runtime, run
`playwright test --config playwright.config.ts`, propagate its exit code, and
always invoke `stop()`.

Add `@playwright/test` as a development dependency and these scripts:

```json
"test:e2e": "node ./scripts/run-maintenance-e2e.mjs",
"test:e2e:headed": "node ./scripts/run-maintenance-e2e.mjs --headed"
```

Configure Playwright with `testDir: './e2e/maintenance'`, serial execution,
`trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, and an output
directory below the configured E2E temporary root.

- [ ] **Step 4: Run GREEN**

```powershell
npm run test -- e2e/maintenance/runtime.test.ts
npx playwright test --config playwright.config.ts --list
```

Expected: runtime tests pass and Playwright discovers no scenario failures.

- [ ] **Step 5: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/scripts/run-maintenance-e2e.mjs frontend/e2e/maintenance/runtime.ts frontend/e2e/maintenance/runtime.test.ts
git commit -m "test(maintenance): add full-stack e2e runtime"
```

### Task 2: Seed deterministic identities and authenticated browser states

**Files:**
- Create: `extensions/maintenance-api/scripts/e2e_seed.py`
- Create: `extensions/maintenance-api/scripts/test_e2e_seed.py`
- Create: `frontend/e2e/maintenance/auth.setup.ts`
- Create: `frontend/e2e/maintenance/fixtures.ts`
- Test: `frontend/e2e/maintenance/auth.setup.ts`

**Interfaces:**
- Consumes: the runtime's disposable database URL and generated test-only
  identity manifest.
- Produces: `viewer.json`, `contributor.json`, `admin.json`, and
  `foreign-admin.json` Playwright storage states, plus fixture IDs confined to
  tenant-a and tenant-b.

- [ ] **Step 1: Define seed-manifest failure cases**

Add a Python test beside the seed script that rejects manifests missing one of
`tenant-a-viewer`, `tenant-a-contributor`, `tenant-a-admin`, or
`tenant-b-admin`, and rejects a role other than `VIEWER`, `CONTRIBUTOR`, or
`ADMIN`.

- [ ] **Step 2: Run RED**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest scripts/test_e2e_seed.py -v
```

Expected: failure because the seed CLI and its validator are absent.

- [ ] **Step 3: Implement deterministic seeding and real login setup**

`e2e_seed.py` must accept only `--database-url` and `--manifest-path`, apply
the current Alembic head to the disposable database, create the two tenants,
four users, their exact memberships, and the minimal master/inventory/report
fixtures needed by the browser scenarios. It writes a manifest with opaque
fixture aliases rather than database URLs, passwords, or signed tokens.

`auth.setup.ts` must read the local ephemeral credentials from the launcher's
in-memory environment, use the application's `/auth/login` endpoint, confirm
navigation under `/platform/maintenance/`, and save a separate storage state
for each actor. `fixtures.ts` exposes only actor names, routes, and manifest
aliases to scenario specs.

- [ ] **Step 4: Run GREEN**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest scripts/test_e2e_seed.py -v
cd ../../frontend
npm run test:e2e -- --project=setup
```

Expected: all four storage-state files are generated without secret-bearing
contents and each actor reaches the maintenance shell.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/scripts/e2e_seed.py extensions/maintenance-api/scripts/test_e2e_seed.py frontend/e2e/maintenance/auth.setup.ts frontend/e2e/maintenance/fixtures.ts
git commit -m "test(maintenance): seed e2e maintenance actors"
```

### Task 3: Cover navigation, permissions, and tenant isolation

**Files:**
- Create: `frontend/e2e/maintenance/navigation.spec.ts`
- Create: `frontend/e2e/maintenance/permissions.spec.ts`
- Create: `frontend/e2e/maintenance/tenant-isolation.spec.ts`

**Interfaces:**
- Consumes: actor storage states and tenant-scoped fixture aliases.
- Produces: browser assertions for menu ownership, role visibility, typed
  report actions, and cross-tenant non-enumeration.

- [ ] **Step 1: Write the failing scenarios**

Add cases that verify:

1. the maintenance menu and collapsed navigation reach only
   `/platform/maintenance/` routes;
2. the viewer sees no mutation action, the contributor can generate and
   validate but cannot finalize, and the admin can finalize an eligible report;
3. tenant-b gets neither a tenant-a report list row nor a successful direct
   detail navigation; and
4. denied controls produce the existing safe forbidden/not-found state without
   leaking a tenant-a title or identifier.

- [ ] **Step 2: Run RED**

```powershell
cd frontend
npm run test:e2e -- navigation permissions tenant-isolation
```

Expected: scenario discovery fails until the specs exist.

- [ ] **Step 3: Implement stable browser assertions**

Use accessible roles, translated visible labels, and public route paths. Wait
for page-owned load states rather than fixed sleeps. Keep role setup in
`auth.setup.ts`; do not inject an Authorization header from a scenario.

- [ ] **Step 4: Run GREEN and commit**

```powershell
npm run test:e2e -- navigation permissions tenant-isolation
git add frontend/e2e/maintenance/navigation.spec.ts frontend/e2e/maintenance/permissions.spec.ts frontend/e2e/maintenance/tenant-isolation.spec.ts
git commit -m "test(maintenance): cover e2e navigation boundaries"
```

### Task 4: Cover scenario, calculation, inventory, review, and allocation workflows

**Files:**
- Create: `frontend/e2e/maintenance/scenario-calculation.spec.ts`
- Create: `frontend/e2e/maintenance/inventory-review-allocation.spec.ts`

**Interfaces:**
- Consumes: tenant-a contributor/admin storage states and seeded deterministic
  master-data aliases.
- Produces: browser-level evidence for state transitions already owned by the
  backend.

- [ ] **Step 1: Write the failing workflow cases**

Add scenarios that submit a structured scenario, expose an autosave/version
conflict without overwriting server state, observe partial calculation failure
and retry, publish a demand list, assert the published object is immutable,
derive a review list, reserve by FEFO, confirm an allocation, and execute it.

- [ ] **Step 2: Run RED**

```powershell
cd frontend
npm run test:e2e -- scenario-calculation inventory-review-allocation
```

Expected: scenario discovery fails until the specs exist.

- [ ] **Step 3: Implement public-state assertions**

Drive each browser action through its visible control and assert the existing
status badge, row state, and post-action detail view. Verify no fixture
creates a completed calculation, reservation, or allocation behind the
browser's back after the scenario begins.

- [ ] **Step 4: Run GREEN and commit**

```powershell
npm run test:e2e -- scenario-calculation inventory-review-allocation
git add frontend/e2e/maintenance/scenario-calculation.spec.ts frontend/e2e/maintenance/inventory-review-allocation.spec.ts
git commit -m "test(maintenance): cover e2e operational workflows"
```

### Task 5: Cover Report Center, downloads, and Chat Cards

**Files:**
- Create: `frontend/e2e/maintenance/reports-chat.spec.ts`

**Interfaces:**
- Consumes: seeded report lineage, role storage states, and the existing
  Report Center/Chat Card UI contracts.
- Produces: browser acceptance evidence for report lifecycle, provenance,
  safe downloads, regeneration, all known cards, and unknown-card fallback.

- [ ] **Step 1: Write the failing report and chat scenarios**

Add cases that browse report list/detail/version/provenance, create/generate/
validate/finalize under the correct role matrix, regenerate into a new child
version, and download Markdown, JSON, and DOCX through the authenticated
browser request path. Add one case for every supported Chat Card type and one
unknown-card case that preserves ordinary assistant text and stays within
`/platform/maintenance/` when a card navigates.

- [ ] **Step 2: Run RED**

```powershell
cd frontend
npm run test:e2e -- reports-chat
```

Expected: scenario discovery fails until the spec exists.

- [ ] **Step 3: Implement download and fallback assertions**

Use Playwright download events and assert only server-provided filename and
content type. Do not inspect a downloaded absolute path or embed file content
in a report. Assert the unknown-card fallback never exposes confirmation
tokens, provider configuration, or internal source snapshots.

- [ ] **Step 4: Run GREEN and commit**

```powershell
npm run test:e2e -- reports-chat
git add frontend/e2e/maintenance/reports-chat.spec.ts
git commit -m "test(maintenance): cover e2e reports and chat cards"
```

### Task 6: Close the local and CI acceptance gates

**Files:**
- Create: `.github/workflows/plan05-acceptance.yml`
- Modify: `frontend/package.json`
- Create: `docs/maintenance/plan05-task9-browser-acceptance.md`

**Interfaces:**
- Consumes: `npm run test:e2e`, retained failure artifacts, and existing
  frontend/backend verification commands.
- Produces: one CI-visible Task 9 gate and documented local reproduction
  instructions without credentials.

- [ ] **Step 1: Define the failing CI contract**

Add a workflow contract test or static assertion that requires the workflow to
run `npm ci`, `npx playwright install --with-deps chromium`, and
`npm run test:e2e`, while publishing only failure artifacts.

- [ ] **Step 2: Run RED**

```powershell
rg -n "npm run test:e2e" .github/workflows/plan05-acceptance.yml
```

Expected: no matching workflow exists before implementation.

- [ ] **Step 3: Implement CI and documentation**

Create the workflow with separate Go, Python, and Node setup; create only
ephemeral service state; run the same `npm run test:e2e` command used locally;
and upload `playwright-report` and `test-results` only when the job fails.

Document prerequisites, the one local command, expected generated artifacts,
redaction rules, and cleanup behavior. Do not claim a CI pass until an actual
run is available.

- [ ] **Step 4: Run final gates**

```powershell
cd frontend
npm run test:e2e
npm run test
npm run type-check
npm run build
cd ../extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check app tests
git -C ../.. diff --check
```

Expected: every local gate exits `0`; CI remains explicitly unclaimed until
GitHub reports a run.

- [ ] **Step 5: Commit**

```powershell
git add .github/workflows/plan05-acceptance.yml frontend/package.json frontend/package-lock.json docs/maintenance/plan05-task9-browser-acceptance.md
git commit -m "test(maintenance): close plan05 task9 browser gate"
```

## Self-Review

- Spec coverage: Tasks 1-2 create the real stack, actors, and storage states;
  Tasks 3-5 cover every required browser domain; Task 6 makes the same command
  reproducible locally and in CI.
- Placeholder scan: each task identifies exact files, commands, expected
  outcomes, and a commit boundary.
- Type consistency: the launcher is the only producer of runtime ports and
  temporary roots; `fixtures.ts` is the only scenario-facing producer of
  actor/state aliases; all scenarios consume those interfaces.

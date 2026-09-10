# Plan 05 Task 9 E2E Postgres Runtime Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Task 9 browser acceptance against a disposable Postgres-backed WeKnora instance and a separate disposable SQLite-backed Maintenance API.

**Architecture:** `frontend/e2e/maintenance/runtime.ts` owns one temporary run directory, a unique Docker Postgres container, and Vite, WeKnora, and Maintenance API child processes. A Go test-only seed command creates the real WeKnora users and memberships; the Python seed command creates Maintenance API fixtures. Browser tests receive aliases and storage states only.

**Tech Stack:** Node.js ESM, Vitest, Playwright, Docker, Postgres 17, Go, FastAPI, SQLite, Python 3.11.

## Global Constraints

- Browser traffic stays `Vite -> /api -> WeKnora -> Maintenance API`; no spec calls Maintenance API directly.
- Credentials, JWTs, signing secrets, database URLs, and temporary absolute paths remain process-local and are absent from manifests and diagnostics.
- Docker, health, migration, seeding, shutdown, and cleanup failures fail `npm run test:e2e`.
- The runner is serial and retains traces, screenshots, service logs, and reports only for a failing run.
- Business rules and production configuration are unchanged.

---

### Task 1: Define and test the launcher contract

**Files:**
- Create: `frontend/e2e/maintenance/runtime.ts`
- Create: `frontend/e2e/maintenance/runtime.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: `E2E_ROOT_DIR`, `E2E_FRONTEND_PORT`, `E2E_WEKNORA_PORT`, `E2E_MAINTENANCE_PORT`, optional `E2E_POSTGRES_IMAGE`.
- Produces: `readRuntimeConfig(env)`, `sanitizeCommandEnvironment(env)`, and `MaintenanceE2ERuntime`.

- [ ] **Step 1: Write the failing contract test**

```ts
import { expect, it } from 'vitest'
import { readRuntimeConfig, sanitizeCommandEnvironment } from './runtime'

it('requires a root directory', () => {
  expect(() => readRuntimeConfig({})).toThrow('E2E_ROOT_DIR is required')
})

it('rejects an invalid port', () => {
  expect(() => readRuntimeConfig({ E2E_ROOT_DIR: 'C:/e2e', E2E_FRONTEND_PORT: '70000' }))
    .toThrow('E2E_FRONTEND_PORT must be between 1024 and 65535')
})

it('redacts diagnostic environment values', () => {
  expect(sanitizeCommandEnvironment({ E2E_ROOT_DIR: 'C:/e2e', DB_PASSWORD: 'hidden' }))
    .toEqual({ E2E_ROOT_DIR: 'C:/e2e' })
})
```

- [ ] **Step 2: Verify RED**

Run: `npm run test -- e2e/maintenance/runtime.test.ts`

Expected: FAIL because `./runtime` does not exist.

- [ ] **Step 3: Implement the smallest public contract**

```ts
export function sanitizeCommandEnvironment(env: NodeJS.ProcessEnv): Record<string, string> {
  return Object.fromEntries(Object.entries(env).filter(([key, value]) => (
    value !== undefined && !/(TOKEN|SECRET|PASSWORD|API_KEY)/i.test(key)
  )))
}

export function readRuntimeConfig(env: NodeJS.ProcessEnv) {
  const rootDir = env.E2E_ROOT_DIR?.trim()
  if (!rootDir) throw new Error('E2E_ROOT_DIR is required')
  const port = (name: string, fallback: number) => {
    const value = Number(env[name] ?? fallback)
    if (!Number.isInteger(value) || value < 1024 || value > 65535) throw new Error(`${name} must be between 1024 and 65535`)
    return value
  }
  return { rootDir, frontendPort: port('E2E_FRONTEND_PORT', 5174), weknoraPort: port('E2E_WEKNORA_PORT', 8081), maintenancePort: port('E2E_MAINTENANCE_PORT', 8101), postgresImage: env.E2E_POSTGRES_IMAGE ?? 'postgres:17-alpine' }
}
```

Add `@playwright/test` and scripts `test:e2e` / `test:e2e:headed` which call `node ./scripts/run-maintenance-e2e.mjs`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `npm run test -- e2e/maintenance/runtime.test.ts`

Expected: PASS.

```powershell
git add frontend/package.json frontend/package-lock.json frontend/e2e/maintenance/runtime.ts frontend/e2e/maintenance/runtime.test.ts
git commit -m "test(maintenance): define e2e runtime contract"
```

### Task 2: Launch and clean up the two-database stack

**Files:**
- Modify: `frontend/e2e/maintenance/runtime.ts`
- Modify: `frontend/e2e/maintenance/runtime.test.ts`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/scripts/run-maintenance-e2e.mjs`

**Interfaces:**
- Consumes: Task 1 configuration and Docker CLI.
- Produces: `start()`, `waitForHealthy()`, `stop({ failed })`, `baseURL`, and `artifactsDir`.

- [ ] **Step 1: Write lifecycle tests**

```ts
it('creates a unique container name below the E2E root', async () => {
  const runtime = new MaintenanceE2ERuntime({ E2E_ROOT_DIR: root })
  await runtime.prepare()
  expect(runtime.containerName).toMatch(/^maintenance-e2e-/)
  expect(runtime.runDir.startsWith(root)).toBe(true)
})
```

- [ ] **Step 2: Verify RED**

Run: `npm run test -- e2e/maintenance/runtime.test.ts`

Expected: FAIL because `prepare` is absent.

- [ ] **Step 3: Implement ownership and process ordering**

`prepare()` creates `postgres-data`, `logs`, `artifacts`, and `maintenance.sqlite3` under a UUID run directory. `start()` uses:

```text
docker run --detach --rm --name <unique> --publish 127.0.0.1:<dynamic>:5432 --mount type=bind,src=<run>/postgres-data,dst=/var/lib/postgresql/data --env POSTGRES_DB=<memory> --env POSTGRES_USER=<memory> --env POSTGRES_PASSWORD=<memory> postgres:17-alpine
go run ./cmd/server
python -m uvicorn app.main:app --host 127.0.0.1 --port <maintenance-port>
npm run dev -- --port <frontend-port> --strictPort
```

Pass the dynamic Postgres settings only to WeKnora; pass the generated matching signing secret to WeKnora and Maintenance API; pass `VITE_DEV_PROXY_TARGET=http://127.0.0.1:<weknora-port>` only to Vite. Check the Postgres, WeKnora, and Maintenance health endpoints before Vite. `stop()` terminates Vite, WeKnora, Maintenance API, and Docker in reverse order, retaining redacted artifacts only after failure.

- [ ] **Step 4: Add serial Playwright configuration and runner**

```ts
export default defineConfig({ testDir: './e2e/maintenance', workers: 1, fullyParallel: false, trace: 'retain-on-failure', screenshot: 'only-on-failure', outputDir: process.env.E2E_PLAYWRIGHT_OUTPUT_DIR })
```

The runner must call `stop({ failed: exitCode !== 0 })` from `finally`.

- [ ] **Step 5: Verify and commit**

Run: `npm run test -- e2e/maintenance/runtime.test.ts`

Expected: PASS.

```powershell
git add frontend/e2e/maintenance/runtime.ts frontend/e2e/maintenance/runtime.test.ts frontend/playwright.config.ts frontend/scripts/run-maintenance-e2e.mjs
git commit -m "test(maintenance): launch disposable e2e stack"
```

### Task 3: Seed real identities and fixture aliases

**Files:**
- Create: `cmd/e2e-seed/main.go`
- Create: `cmd/e2e-seed/main_test.go`
- Create: `extensions/maintenance-api/scripts/e2e_seed.py`
- Create: `extensions/maintenance-api/scripts/test_e2e_seed.py`
- Create: `frontend/e2e/maintenance/auth.setup.ts`
- Create: `frontend/e2e/maintenance/fixtures.ts`

**Interfaces:**
- Consumes: private runtime database settings and run directory.
- Produces: tenant-a viewer/contributor/admin, tenant-b admin, opaque aliases, and four Playwright storage states.

- [ ] **Step 1: Write seed validation tests**

```go
func TestValidateActorsRejectsMissingAdmin(t *testing.T) {
  err := validateActors(map[string]Actor{"tenant-a-viewer": {Role: "VIEWER"}})
  require.ErrorContains(t, err, "tenant-a-admin")
}
```

```python
def test_manifest_rejects_missing_actor() -> None:
    with pytest.raises(ValueError, match="tenant-b-admin"):
        validate_manifest({"actors": {}})
```

- [ ] **Step 2: Verify RED**

Run: `go test ./cmd/e2e-seed -run TestValidateActors -count=1`

Expected: FAIL because the test-only seed command does not exist.

- [ ] **Step 3: Implement the private seeds**

The Go command accepts `--database-url` and `--manifest-path`, writes exactly two tenants and four memberships into runtime Postgres, and emits actor aliases only. The Python CLI accepts `--database-url` and `--manifest-path`, migrates Maintenance SQLite, and emits only fixture aliases. `auth.setup.ts` performs `/auth/login` through Vite and saves four storage files. `fixtures.ts` must not export passwords, JWTs, raw database URLs, or raw fixture identifiers.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
go test ./cmd/e2e-seed -count=1
& $py -m pytest scripts/test_e2e_seed.py -v
npm run test:e2e -- --project=setup
```

Expected: all setup states exist only under the disposable run directory.

```powershell
git add cmd/e2e-seed extensions/maintenance-api/scripts frontend/e2e/maintenance/auth.setup.ts frontend/e2e/maintenance/fixtures.ts
git commit -m "test(maintenance): seed e2e maintenance actors"
```

### Task 4: Consume the runtime in scenarios and CI

**Files:**
- Create: `frontend/e2e/maintenance/navigation.spec.ts`
- Create: `frontend/e2e/maintenance/permissions.spec.ts`
- Create: `frontend/e2e/maintenance/tenant-isolation.spec.ts`
- Create: `.github/workflows/plan05-acceptance.yml`
- Create: `docs/maintenance/plan05-task9-browser-acceptance.md`

**Interfaces:**
- Consumes: serial runtime, storage states, and opaque aliases.
- Produces: reproducible local and CI E2E gates.

- [ ] **Step 1: Write the failing proxy smoke test**

```ts
test('viewer reaches the maintenance shell through Vite and the proxy', async ({ page }) => {
  await page.goto('/platform/maintenance/')
  await expect(page.getByRole('main')).toBeVisible()
})
```

- [ ] **Step 2: Verify RED**

Run: `npm run test:e2e -- navigation`

Expected: FAIL until the scenario is configured with setup storage state.

- [ ] **Step 3: Add browser and CI wiring**

Use accessible locators and public maintenance routes only. The workflow runs `npm ci`, `npx playwright install --with-deps chromium`, and `npm run test:e2e`; upload only `playwright-report` and `test-results` when failing. The document states Docker as a prerequisite and `npm run test:e2e` as the local entry point.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
npm run test:e2e -- navigation permissions tenant-isolation
npm run test
npm run type-check
npm run build
& $py -m pytest -v
& $py -m ruff check app tests
git diff --check
```

Expected: all local commands pass; CI status remains unclaimed until GitHub runs the workflow.

```powershell
git add frontend/e2e/maintenance .github/workflows/plan05-acceptance.yml docs/maintenance/plan05-task9-browser-acceptance.md
git commit -m "test(maintenance): close task9 browser gate"
```

## Self-Review

- Tasks 1-2 implement the two-database runtime described in the approved design.
- Task 3 keeps identity and maintenance data seeding separate and secret-free.
- Task 4 makes browser scenarios and CI consume the identical runtime command.

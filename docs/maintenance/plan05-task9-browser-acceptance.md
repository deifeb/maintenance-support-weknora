# Plan 05 Task 9 Browser Acceptance

This gate runs the Maintenance browser scenarios against a disposable two-database stack:

- Docker provides an isolated PostgreSQL instance for WeKnora.
- Maintenance API uses a disposable SQLite file in the same run directory.
- Vite is the only browser origin. Requests continue through `Vite -> /api -> WeKnora -> Maintenance API`.
- The runner creates real users, tenant memberships, Maintenance fixtures, and Playwright storage states before scenarios start.

## Prerequisites

Install Node.js 24, Go, Python 3.11, and Docker with a running daemon. Chromium is installed by the setup command below. The runner owns its temporary data under `E2E_ROOT_DIR` and removes it after a successful run.

## Local run

From `frontend`:

```powershell
npm ci
python -m pip install -r ..\extensions\maintenance-api\requirements-dev.txt
npx playwright install --with-deps chromium
$env:E2E_ROOT_DIR = Join-Path $env:TEMP 'maintenance-e2e'
npm run test:e2e
```

Use `npm run test:e2e:headed` when an interactive browser is required. A failed run retains redacted service logs and Playwright artifacts below the disposable run directory; successful runs remove it.

The GitHub Actions gate is defined in `.github/workflows/plan05-acceptance.yml`. It installs the same dependencies, runs `npm run test:e2e`, and uploads only failure artifacts.

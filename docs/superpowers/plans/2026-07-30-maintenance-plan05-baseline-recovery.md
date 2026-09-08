# Plan 05-2 Baseline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the pre-Task-9B Go and frontend gates without changing Maintenance business contracts.

**Architecture:** Keep PostgreSQL parsing fully enabled in cgo builds and route all parser calls through local wrappers. In non-cgo builds, compile successfully and fail closed with an explicit parser-unavailable error. Keep the workspace-terminology check focused on user-facing locales and public documentation while excluding internal implementation plans that intentionally use tenant as a security boundary.

**Tech Stack:** Go 1.26, build constraints, `pg_query_go/v6`, Vue 3/TypeScript, Node `tsx --test`.

## Global Constraints

- Do not change Maintenance API routes, tenant scoping, RBAC, internal JWT, idempotency, versioning, or audit behavior.
- SQL validation must never accept or rewrite SQL when the PostgreSQL parser is unavailable.
- cgo builds must retain the existing `pg_query.Parse` and `pg_query.Deparse` behavior.
- User-facing Chinese copy uses “工作区”; internal implementation plans may use “租户” for the technical isolation boundary.
- Baseline recovery is committed separately from Task 9B.

---

### Task 1: Correct the Workspace-Terminology Gate

**Files:**
- Modify: `frontend/src/i18n/locales/workspaceTerminology.test.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `.env.example`
- Modify: `README_CN.md`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: locale objects and repository documentation roots.
- Produces: a scanner that checks public copy but excludes `docs/superpowers` implementation artifacts.

- [ ] **Step 1: Add a failing scanner-boundary test**

Add a test fixture assertion proving `collectDocumentationFiles(resolve(repositoryRoot, 'docs'))` does not return paths below `docs/superpowers`, while it still returns public files below `docs/api`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test src/i18n/locales/workspaceTerminology.test.ts
```

Expected: FAIL because `docs/superpowers` is still recursively scanned and the remaining public Chinese copy still contains “租户”.

- [ ] **Step 3: Implement the narrow scanner exclusion and copy corrections**

Define the excluded repository-relative directory as `docs/superpowers`. Skip it during recursion; do not add broad line-level exemptions. Change the remaining user-facing locale, environment help, README summary, and Compose comments to “工作区” phrasing while preserving technical identifiers such as `tenant_id`, `CanAccessAllTenants`, and environment variable names.

- [ ] **Step 4: Run focused and full frontend gates**

Run:

```powershell
cd frontend
& '.\node_modules\.bin\tsx.cmd' --test src/i18n/locales/workspaceTerminology.test.ts
npm run test
npm run type-check
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/i18n/locales/workspaceTerminology.test.ts frontend/src/i18n/locales/zh-CN.ts .env.example README_CN.md docker-compose.yml
git commit -m "fix: restore workspace terminology gate"
```

---

### Task 2: Make SQL Validation Compile and Fail Closed Without cgo

**Files:**
- Create: `internal/utils/pg_query_cgo.go`
- Create: `internal/utils/pg_query_nocgo.go`
- Create: `internal/utils/pg_query_nocgo_test.go`
- Modify: `internal/utils/inject.go`

**Interfaces:**
- Produces: `parsePostgresSQL(string) (*pg_query.ParseResult, error)` and `deparsePostgresSQL(*pg_query.ParseResult) (string, error)`.
- Consumed by: `ParseSQL`, `ValidateSQL`, SQL tenant/security injection, and SQL normalization in `internal/utils/inject.go`.

- [ ] **Step 1: Add a failing non-cgo contract test**

Create `internal/utils/pg_query_nocgo_test.go` with `//go:build !cgo`. Assert that `ParseSQL("SELECT 1")` returns `IsSelect == false` and a parse error containing `requires cgo`; assert that `ValidateSQL("SELECT 1", WithSelectOnly())` is invalid rather than accepting unparsed SQL.

- [ ] **Step 2: Run the package test and verify RED**

Run:

```powershell
$env:CGO_ENABLED = '0'
go test ./internal/utils
```

Expected: build failure at the existing direct `pg_query.Parse` and `pg_query.Deparse` references.

- [ ] **Step 3: Add build-specific wrappers and replace direct calls**

In `pg_query_cgo.go`, delegate to `pg_query.Parse` and `pg_query.Deparse`. In `pg_query_nocgo.go`, return an error containing `PostgreSQL parser requires cgo`; never return a fabricated parse tree or unchanged SQL. Replace the four direct parser calls in `inject.go` with these wrappers.

- [ ] **Step 4: Run no-cgo and affected Go gates**

Run:

```powershell
$env:CGO_ENABLED = '0'
go test ./internal/utils
go test ./internal/maintenanceproxy ./internal/router
```

Expected: all commands exit 0. A cgo execution check is conditional on a C compiler being installed; source review must confirm the cgo wrapper delegates unchanged.

- [ ] **Step 5: Commit**

```powershell
git add internal/utils/inject.go internal/utils/pg_query_cgo.go internal/utils/pg_query_nocgo.go internal/utils/pg_query_nocgo_test.go
git commit -m "fix: fail closed when postgres parser is unavailable"
```

---

### Task 3: Verify the Recovered Baseline

**Files:**
- No production files.

**Interfaces:**
- Produces: fresh evidence that Task 9B starts from a trusted baseline.

- [ ] **Step 1: Run Maintenance frontend tests**

Run the directed Maintenance test discovery command from the handover. Expected: 77 or more tests pass with zero failures.

- [ ] **Step 2: Run full frontend test, type-check, and build**

Expected: all commands exit 0.

- [ ] **Step 3: Run Task 9A backend regression and Ruff**

Use `extensions/maintenance-api/.venv/Scripts/python.exe`. Expected: 47 tests pass and Ruff is clean.

- [ ] **Step 4: Run Go affected packages and diff checks**

Run:

```powershell
$env:CGO_ENABLED = '0'
go test ./internal/maintenanceproxy ./internal/router
git diff --check
git status -sb
```

Expected: Go packages pass, diff check is clean, and the worktree contains only intentional Task 9B planning work after baseline commits.

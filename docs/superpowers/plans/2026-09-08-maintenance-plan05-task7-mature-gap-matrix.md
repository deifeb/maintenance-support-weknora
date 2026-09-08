# Plan 05 Task 7 Mature Software Gap Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a complete Plan 05 mature-software capability matrix and a deterministic PowerShell gate that rejects incomplete or invalid matrix content.

**Architecture:** Markdown is the single human-maintained assessment. A PowerShell validator checks one matrix path for coverage and table invariants. A separate PowerShell harness mutates copied fixtures and proves both rejection and the committed happy path.

**Tech Stack:** Markdown, PowerShell, Git.

## Global Constraints

- Change only Task 7 documentation, validator, and its fixtures/harness.
- Do not change product code, APIs, databases, permissions, Chat Cards, C3, or Task 8--10 scope.
- Table columns are exactly `功能域`, `成熟软件能力`, `本项目必要性`, `现有能力`, `Plan 05 实现`, `前端页面`, `后端接口`, `数据表`, `权限`, `验收案例`, `状态`, `延后原因`.
- Status values are exactly `adopted`, `adapted`, `partial`, and `deferred`.
- Required coverage contains the eight Maximo, four SAP, and three Oracle domains named in the approved roadmap.
- Procurement, accounting ledger, full WMS, and offline scanning are explicit deferred rows with reasons.

---

### Task 1: Matrix and validator

**Files:**
- Create: `docs/maintenance/plan05-mature-software-gap-matrix.md`
- Create: `scripts/test-plan05-gap-matrix.ps1`

**Interfaces:**
- Consumes: UTF-8 Markdown at `-MatrixPath`, defaulting to the committed matrix.
- Produces: exit `0` and `Plan 05 gap matrix validated: <count> domains.`; otherwise throws a named invariant error.

- [ ] **Step 1: Write the matrix**

Use the exact header in Global Constraints. Add complete rows for `item master`, `storeroom`, `balance`, `reservation`, `issue/return`, `transfer`, `stocktake`, `repairable asset`, `maintenance task material linkage`, `stock/non-stock distinction`, `availability check`, `high-priority reassignment`, `warehouse/location/lot/serial reservation`, `pick/issue`, and `return`. Every row fills every column. Use known Plan 05 references or `deferred` plus a concrete reason. Add the four explicit non-goals as deferred rows.

- [ ] **Step 2: Run RED**

Run `pwsh -NoProfile -File scripts/test-plan05-gap-matrix.ps1`.

Expected: failure because the validator is absent.

- [ ] **Step 3: Implement the validator**

Create this parameter surface:

```powershell
param([string]$MatrixPath = 'docs/maintenance/plan05-mature-software-gap-matrix.md')
$ErrorActionPreference = 'Stop'
$allowedStatuses = @('adopted', 'adapted', 'partial', 'deferred')
```

Read UTF-8 text; require every header and capability label; reject `TBD`, `TODO`, `待补充`, and `N/A`; parse table data rows; reject invalid statuses and deferred rows without a reason. Throw before success output.

- [ ] **Step 4: Run GREEN and commit**

Run `pwsh -NoProfile -File scripts/test-plan05-gap-matrix.ps1`; expect exit `0`.

```powershell
git add docs/maintenance/plan05-mature-software-gap-matrix.md scripts/test-plan05-gap-matrix.ps1
git commit -m "docs(maintenance): add plan05 gap matrix"
```

### Task 2: Regression harness and closure

**Files:**
- Create: `scripts/tests/test-plan05-gap-matrix.ps1`

**Interfaces:**
- Consumes: `scripts/test-plan05-gap-matrix.ps1 -MatrixPath <fixture>`.
- Produces: exit `0` only after all negative fixtures fail and the committed matrix passes.

- [ ] **Step 1: Write fixture assertions**

Copy the committed matrix to a unique temporary directory. In child PowerShell invocations, assert non-zero exits and matching diagnostics after: removing `item master`; replacing a valid status with `unsupported`; inserting `TODO`; and clearing a deferred reason. Also assert the untouched matrix exits `0`.

- [ ] **Step 2: Run RED**

Run `pwsh -NoProfile -File scripts/tests/test-plan05-gap-matrix.ps1`.

Expected: failure because the harness is absent.

- [ ] **Step 3: Implement isolated fixture execution**

Use `$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) "plan05-gap-matrix-$PID"`, clean it in `finally`, and invoke `& pwsh -NoProfile -File $validator -MatrixPath $fixturePath`. Check `$LASTEXITCODE` and diagnostic substrings so expected validator failures do not terminate the harness.

- [ ] **Step 4: Run closure gates**

Run:

```powershell
pwsh -NoProfile -File scripts/tests/test-plan05-gap-matrix.ps1
pwsh -NoProfile -File scripts/test-plan05-gap-matrix.ps1
git diff --check
```

Expected: all commands exit `0`; the harness reports five passing cases.

- [ ] **Step 5: Commit**

```powershell
git add scripts/tests/test-plan05-gap-matrix.ps1 docs/maintenance/plan05-mature-software-gap-matrix.md
git commit -m "test(maintenance): validate plan05 gap matrix"
```

Record commands, pass count, and scope confirmation in the Task 7 report. Close Task 7 only after independent review approves it.

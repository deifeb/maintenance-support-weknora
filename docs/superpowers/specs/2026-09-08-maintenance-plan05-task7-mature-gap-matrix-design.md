# Plan 05 Task 7 Mature Software Gap Matrix Design

## Goal

Create a reviewable maintenance-capability gap matrix and a deterministic
PowerShell validator. The work documents Plan 05 coverage; it does not add
product behavior, backend contracts, database changes, or browser flows.

## Scope

The matrix will be the human-maintained source of truth at
`docs/maintenance/plan05-mature-software-gap-matrix.md`. It will contain one
Markdown table with these columns:

`功能域`, `成熟软件能力`, `本项目必要性`, `现有能力`, `Plan 05 实现`, `前端页面`,
`后端接口`, `数据表`, `权限`, `验收案例`, `状态`, `延后原因`.

It will cover the required Maximo-inspired, SAP-inspired, and Oracle-inspired
domains from the roadmap. Each row will use one of four closed status values:
`adopted`, `adapted`, `partial`, or `deferred`. Deferred rows will state a
concrete reason; the explicitly excluded procurement, accounting, full-WMS,
and offline-scanning areas will be recorded as deferred rather than left blank.

## Validation

`scripts/test-plan05-gap-matrix.ps1` will read the matrix as UTF-8 text and
fail with a non-zero exit code when:

- a required domain is absent;
- a required table header is absent;
- a row has an unsupported status;
- a row contains unfilled markers (`TBD`, `TODO`, `待补充`, or `N/A`);
- a deferred row has no reason.

The script will print a concise success count when all required domains and
rows validate. It will not attempt to parse repository implementation files or
claim that the matrix proves runtime behavior.

## Evidence and Boundaries

The matrix will link each adopted/adapted/partial capability to existing Plan
05 pages, API families, tables, permissions, and acceptance evidence only when
those references are known. Unknown or intentionally postponed capability is
explicitly marked `deferred` with its reason. The validator protects document
completeness, while later Tasks 8--10 retain responsibility for integration,
browser, resilience, and performance acceptance.

## Verification

Task 7 closes only after the PowerShell validator succeeds on the committed
matrix and the diff is whitespace-clean. The implementation will add targeted
PowerShell regression cases for a missing domain, invalid status, unfilled
marker, and missing deferred reason.

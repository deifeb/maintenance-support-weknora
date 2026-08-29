\
# Plan 05-4 Final Closure Review

## 1. Decision

**PLAN 05-4 SUBSTANTIVE CLOSURE CANDIDATE: APPROVED, WITH ONE DEFERRED NON-BLOCKING MINOR; TASK 9J PENDING**

Plan 05-4A through 05-4D now form one reviewed inventory/review/allocation authority chain. The final Task 9 code review has no Critical or Important blocker, the current-head real PostgreSQL Gate is PASS, and the latest backend/frontend/software evidence is green. The one carried design residual is the previously documented Plan 05-4C M-1 composite finding/review database invariant; it remains a **DEFERRED MINOR**, not a production-closure blocker.

This document is created in Task 9I before Task 9J. It is therefore a final cross-stage decision record and recommendation, not a claim that the post-document Task 9J verification or commit authorization has already occurred.

## 2. Reviewed Baseline and Evidence Model

- Repository: `deifeb/maintenance-support-weknora`
- Current Task 9 branch: `codex/maintenance-plan05-4d-task9`
- Current integration base / frozen HEAD before Task 9H/I: `63f4a55f32b7c1d4f9f2a55eb7edc0c68f5e5a3c`
- Current Alembic head established by SQLite and real PostgreSQL Gates: `20260827_15`
- Approved design: `docs/superpowers/specs/2026-08-03-maintenance-plan05-04-inventory-review-allocation-design.md`
- 05-4A historical closure: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04a-closure-review.md`
- 05-4B historical backend Gate: `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-backend-gate.md`
- 05-4B historical frontend Gate: `docs/superpowers/reviews/2026-08-16-maintenance-plan05-04b-frontend-gate.md`
- 05-4C historical closure: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04c-closure-review.md`
- 05-4D closure candidate: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04d-closure-review.md`

Evidence is deliberately separated into **historical stage-Gate evidence** and **Task 9 fresh/frozen evidence**. Historical test counts below are not represented as Task 9 reruns.

## 3. Approved Spec Sections 1-18 Requirement Matrix

Status vocabulary:

- **APPROVED** — substantive requirement is implemented and supported by the listed stage + integration/migration evidence.
- **DEFERRED MINOR** — requirement is substantively met, but a non-blocking structural residual is explicitly carried.
- **BLOCKED** — closure blocker remains. There are no BLOCKED rows in this candidate.

| Spec § | Stage | Authoritative production/service boundary | Focused test evidence | Integration evidence | Migration evidence | Status |
|---|---|---|---|---|---|---|
| 1. 背景 | 05-4A/B/C/D | Legacy aggregate inventory is replaced by ledger authority; formal review and allocation build on that authority rather than parallel sources of truth. | A/B/C/D focused Gates green; Task 9 D focused `158 passed`. | A authoritative-fact integration; B inventory workflows; C formal review; D cross-domain chain. | Actual chain through `20260827_15`. | APPROVED |
| 2. 目标 | 05-4A/B/C/D | Ledger facts -> governed inventory operations -> formal Demand Review -> simulated/published allocation rules -> reservation-backed execution. | Stage-specific service/API/RBAC suites; Task 9 full backend `1559 passed`. | Task 9 cross-domain test connects review, publish, plan, reservation, transaction, ledger. | A `08-10`, B `11`, C `12`, D `13-15`. | APPROVED |
| 3. 非目标 | 05-4A/B/C/D | No procurement execution, budget/cost engine, auto-preemption, report center, chat execution, or Plan 05-5 authority introduced. | Scope/static tests and final repo scope checks. | Task 9 integration exercises only approved domains. | No extra migration outside approved lineage. | APPROVED |
| 4. 方案比较 | 05-4A/B/C/D | Chosen architecture keeps inventory facts ledger-backed, formal review independent of AI, simulation side-effect free, execute delegated to reservation authority. | Deterministic scoring, state-machine, authority-boundary tests. | Cross-domain Task 9 contracts validate the chosen layered architecture. | Migrations preserve stage ownership rather than introducing parallel aggregate state. | APPROVED |
| 5. 总体架构与阶段依赖 | 05-4A/B/C/D | Later stages call earlier authorities: C reads current demand/inventory facts; D execution calls B reservation service; no stage bypasses ledger writes. | A/B/C/D service + repository regressions; D focused `158 passed`. | Task 9 authority/lineage test and partial-execute test. | Sequential chain `08 -> ... -> 15`. | APPROVED |
| 6. 05-4A：库存账本基础 | 05-4A | `InventoryTransactionService`, authoritative balances/lots/serialized facts, append-only `InventoryLedgerEntry`; legacy runtime aggregate absent. | Historical A focused `143 passed`; migration `26 passed`; Ruff PASS. | Historical A authoritative integration `3 passed`. Task 9 legacy scan confirms zero runtime legacy references. | `20260803_08`, target receipts `09`, execution principal `10`. | APPROVED |
| 7. 05-4B：库存操作、FEFO、预留与盘点 | 05-4B | FEFO/reservation/issue-return/release, transfer, stocktake, operation preview/execute/reverse; inventory writes remain transaction/ledger-backed. | Historical B backend focused `373 passed`; API/RBAC `127 passed`; real-PG focused inventory evidence recorded by B Gate. | Historical B four workflows `4 passed`; D execution reuses `InventoryReservationService`. | `20260803_11`, verified on SQLite and real PostgreSQL. | APPROVED |
| 8. 05-4C：权威需求审查 | 05-4C | `DemandReviewService` owns formal review independent of AI; current PUBLISHED source is immutable; derive creates a new same-lineage DRAFT. | Historical C focused `356 passed`, security `122 passed`, full backend `1406 passed`. | Historical C authoritative review integration `1 passed`; Task 9 cross-domain test re-verifies AI counts unchanged, source immutability, derive/publish lineage, actor/request audit. | `20260803_12`. | DEFERRED MINOR — M-1 composite DB invariant remains carried |
| 9. 05-4D：规则、模拟与保障方案 | 05-4D | `AllocationRuleService`, `AllocationSimulationService`/executor, `AllocationPlanService`; execute delegates to B reservation service. | Task 9 D focused `158 passed`; full backend `1559 passed`; Ruff PASS. | Final Task 9 integration set `4 passed`: simulation identity/side-effect, partial conflict/idempotency/ledger trace, source supersede fail-closed, cross-domain authority chain. | `20260803_13`, gap-line stabilization `14`, publish receipt/idempotency `15`. | APPROVED |
| 10. 服务边界 | 05-4A/B/C/D | Repository/service ownership is explicit; API/worker/frontend cannot directly become inventory/review/allocation write authority. | Repository/service boundary tests across all stages; Task 9 review removed direct-bypass false positives. | Task 9 uses real service interfaces and follows reservation transaction/ledger trace. | No migration introduces competing write authority. | APPROVED |
| 11. API 合同 | 05-4A/B/C/D | Stable REST APIs for inventory, review, rules/simulations/plans; structured read/write schemas and idempotent command headers. | B API/OpenAPI `127 passed`; C API/security historical Gate; D allocation API/security included in `158 passed`. | Frontend broad `575 passed` exercises typed inventory/review/allocation contracts. | API persistence fields backed by stage migrations through 15. | APPROVED |
| 12. RBAC | 05-4A/B/C/D | Viewer read; contributor ordinary workflow writes; ADMIN for high-risk inventory/final review governance and rule publish/retire. | Historical B/C RBAC/security plus D `tests/security/test_allocation_routes_actor_context.py` and `test_api_rbac.py`. | Task 9 cross-domain test verifies contributor/admin/other-tenant authority and audit actors. | Actor/audit persistence present in stage schemas. | APPROVED |
| 13. 幂等、并发和审计 | 05-4A/B/C/D | Tenant-scoped idempotency, optimistic versions/locks, request hashes/snapshots, actor roles/request IDs; execute replay must not duplicate physical effects. | State-machine/concurrency tests across B/C/D; D focused `158 passed`. | Task 9 same-key execute replay + exact reservation/transaction/ledger trace; real PG publish/execute/balance competition. | Revision 15 adds durable publish receipt/idempotency; real PG verifies its unique index. | APPROVED |
| 14. 稳定错误合同 | 05-4B/C/D | Structured conflict/not-current/version/idempotency errors with tenant-neutral boundaries and recovery metadata. | B API closure, C conflict/concurrency suites, D plan execution/API suites. | Task 9 asserts structured per-line conflict evidence and source-supersede fail-closed semantics. | Error semantics rely on state/version persistence in 11-15; no ad-hoc schema bypass. | APPROVED |
| 15. 前端信息架构 | 05-4B/C/D | One Inventory Gap workspace preserves five inventory tabs; formal Review Detail and allocation rule/plan routes are authenticated/hidden as designed. | Historical B frontend `491 passed`; C frontend `526 passed`; Task 9 fresh frontend `575 passed`. | Source-identity and route-identity fail-closed stabilizations plus hidden-route broad Gate. | No frontend-specific migration; UI consumes server-backed identities from 11-15. | APPROVED |
| 16. 测试策略 | 05-4A/B/C/D | RED/GREEN focused suites, full backend/frontend, migration round-trips, cross-domain integration, and real PostgreSQL concurrency/migration validation. | Latest D: integration `4`, focused `158`, full backend `1559`; frontend `575`; Ruff/type-check/build PASS. | A/B/C historical integrations plus D final cross-domain contracts. | SQLite round-trip + real PG `11 -> 15 -> 11 -> 15`, head 15. | APPROVED |
| 17. 文档与实施计划拆分 | 05-4A/B/C/D | Stage plans/reviews remain separate; Task 9H/I records D closure and cross-stage final decision without rewriting production plans. | Scope/freezes verify only approved review docs are added in H/I. | Closure evidence index links stage and Task 9 artifacts. | Documents record actual migration chain rather than obsolete planned head numbers. | APPROVED |
| 18. 批准边界 | 05-4A/B/C/D | Commit/push/PR/Ready/merge/cleanup/next-plan are separate mutations; Task 9H/I stops before Task 9J. | Repeated pre/post freeze evidence shows staged empty and no unauthorized mutations. | Task 9 recovery scripts stopped fail-closed on harness defects. | Migration Gates used disposable DBs and restored/removed test resources. | APPROVED |

## 4. Four-Stage Gate Summary

### 05-4A — Inventory Ledger Foundation (historical stage closure)

Historical closure decision: APPROVED.

Recorded evidence:

- authoritative-fact integration: `3 passed, 1 warning in 23.82s`;
- complete 05-4A focused suite: `143 passed, 1 warning in 190.11s`;
- migration/lineage suite: `26 passed, 1 warning in 159.25s`;
- historical full backend: `878 passed, 8 deselected, 2 warnings in 406.07s`;
- Ruff PASS;
- historical head: `20260803_10`;
- legacy runtime inventory references: zero at closure.

The A review originally carried live-PostgreSQL execution as an environment boundary. That historical limitation is superseded for Plan 05-4 production closure by later real PostgreSQL Gates in 05-4B and Task 9F.

### 05-4B — Inventory Operations + Frontend (historical backend/frontend Gates)

Backend historical evidence:

- focused inventory backend: `373 passed, 1 warning in 75.37s`;
- API/RBAC/OpenAPI closure: `127 passed, 1 warning`;
- four integration workflows: `4 passed, 1 warning`;
- full backend: `1227 passed, 8 deselected, 2 warnings`;
- SQLite head/round-trip at `20260803_11`: PASS;
- Ruff PASS.

05-4B real PostgreSQL Gate subsequently verified PostgreSQL 17.11 / psycopg 3.3.4, real migration round-trip at revision 11, concurrency/idempotency/tenant locking contracts, and the approved focused backend set with exact SQLite-only exclusions.

Frontend historical evidence:

- focused inventory frontend: `82/82`;
- full frontend: `491/491`;
- type-check PASS;
- production build PASS;
- >500 kB Vite chunk warning recorded as non-blocking.

### 05-4C — Authoritative Demand Review (historical stage closure)

Historical closure decision: APPROVED FOR CLOSURE with M-1 deferred Minor.

Recorded evidence:

- authoritative review integration: `1 passed, 1 warning in 6.97s`;
- focused backend: `356 passed, 1 warning`;
- security: `122 passed, 1 warning`;
- full backend: `1406 passed, 8 deselected, 2 warnings`;
- frontend focused: `54 passed`;
- frontend full: `526 passed`;
- frontend type-check/build PASS;
- Ruff PASS;
- historical head: `20260803_12`.

M-1 remains intentionally unclosed and is evaluated under residuals below.

### 05-4D — Allocation Assurance (Task 9 current closure evidence)

Task 9 fresh/frozen evidence after final test stabilization:

- Task 9 integration: `4 passed, 1 warning in 7.54s`;
- 05-4D focused backend: `158 passed, 1 warning in 34.54s`;
- full backend: `1559 passed, 8 deselected, 2 warnings in 455.12s`;
- backend Ruff: PASS;
- frontend full: `575/575`;
- frontend app type-check: PASS;
- frontend config type-check: PASS;
- Vite production build: PASS (`39.79s`), warning retained;
- SQLite Alembic single head/round-trip: `20260827_15`, PASS;
- runtime legacy inventory scan: `234` Python files, `0` matches;
- final code review: `0 Critical / 0 Important / 0 blocking Minor`;
- real PostgreSQL Task 9F: PASS at current head, with migration and concurrency evidence described below.

The frontend broad Gate was not repeated after later backend-only Task 9 integration-test edits because frontend content was unchanged; Task 9J is required to rerun frontend fresh after these documents are added.

## 5. Actual Migration Chain

The current Plan 05-4 chain is:

```text
... -> 20260803_08  inventory ledger foundation
    -> 20260803_09  atomic inventory target receipts
    -> 20260803_10  import execution principal
    -> 20260803_11  inventory operations and stocktake persistence
    -> 20260803_12  authoritative demand review persistence
    -> 20260803_13  allocation assurance persistence
    -> 20260825_14  allow gap-only allocation plan lines
    -> 20260827_15  allocation rule publish receipt/idempotency (head)
```

Both disposable SQLite and real PostgreSQL Gates establish `20260827_15` as the unique current head. The Plan 05-4D final revisions are not compressed back to the original roadmap placeholder; revisions 14 and 15 are part of the actual approved lineage.

## 6. Cross-Domain Invariant Closure

| Invariant | Decision | Evidence |
|---|---|---|
| Transaction/ledger is the inventory write authority | CLOSED | 05-4A/B services + Task 9 success-line trace from reservation to RESERVE transaction to ledger. |
| Legacy aggregate runtime removal | CLOSED | Task 9 read-only scan: 234 `app/**/*.py`, zero `WarehouseInventory|warehouse_inventories` matches. |
| Reservation / transfer / stocktake state machines | CLOSED | Historical 05-4B focused/API/integration Gates plus current full backend regression. |
| Formal Demand Review is separate from AI authority | CLOSED | 05-4C closure + Task 9 cross-domain test proves AI review row counts unchanged. |
| PUBLISHED source remains immutable and derived versioning is authoritative | CLOSED | 05-4C integration + Task 9 derive/publish lineage and execute-time superseded-source rejection. |
| Allocation simulation has no inventory side effects | CLOSED | Exact frozen source/rule/inventory identity and canonical fingerprint; before/after inventory facts unchanged. |
| Allocation execute delegates to reservation authority | CLOSED | Real `AllocationPlanService.execute` -> `InventoryReservationService`; exact reservation/transaction/ledger link verified; no direct balance write in Task 9. |
| Tenant isolation, RBAC, idempotency, version, audit | CLOSED | Actor user/roles/request IDs, tenant-chain assertion, structured conflict versions, same-key replay, PG tenant-scoped publish keys. |
| Full frontend/backend software Gate | CLOSED AS PRE-DOC EVIDENCE | Latest backend 1559; frontend 575 + type-check/build; Task 9J will rerun after docs. |
| Real PostgreSQL deployment Gate | CLOSED | PostgreSQL 17.11, psycopg 3.3.4, real `11 -> 15 -> 11 -> 15`, 7/7 Task 9F contracts, cleanup PASS. |

## 7. Real PostgreSQL Production-Closure Gate

The historical 05-4A PostgreSQL availability residual is no longer a Plan 05-4 blocker.

Task 9F used a disposable real PostgreSQL 17.11 database and verified:

- current single head `20260827_15`;
- real migration `20260803_11 -> 20260827_15 -> 20260803_11 -> 20260827_15`;
- revision-14 nullable expected-balance-version/pair constraint semantics;
- revision-15 durable publish receipt columns and tenant-scoped unique idempotency index;
- concurrent same-key rule publish replay;
- tenant-scoped publish idempotency keys;
- same-key plan execution reserving once;
- two plans competing for one balance with one reservation winner;
- zero final Gate business rows and successful disposable DB/harness cleanup.

Task 9F's seven tests passed in `11.16s`. The PostgreSQL Gate was executed before later test-only integration-test review stabilizations; no production or migration file changed afterward. It therefore remains the frozen current-head PostgreSQL migration/concurrency evidence. Task 9J must verify that status remains applicable before commit authorization.

## 8. Task 9 Review Findings and Approved Scope Amendment

### Review findings

Task 9 review initially found false-positive gaps in the new integration tests rather than production defects. All were remediated within the test-only boundary:

- Scenario A now uses real rule simulation/publish, production plan generation, `edit_line`, and legitimate inventory-authority drift;
- mandatory source-supersede-after-confirm Scenario B is present;
- actor roles/request-ID provenance is asserted across the chain;
- transaction response evidence is asserted structurally;
- success allocation line is traced exactly through reservation, transaction, and ledger;
- simulation candidate/baseline/source/frozen-inventory identity is exact;
- tenant consistency is explicitly asserted for persisted cross-domain entities.

Final read-only Task 9 code review: **0 Critical / 0 Important / 0 blocking Minor**. No production defect was found.

### Final manifest amendment

The original Task 9 plan's literal four-file final scope is superseded by two separately approved broad-Gate test-only stabilizations:

- `tests/models/test_tenant_models.py`: `+6/-0` allocation table registry expectations;
- `frontend/.../master-data-navigation.test.ts`: `+2/-0` hidden allocation route expectations.

Together with the two Task 9 integration tests and these two Closure Review documents, the correct final Task 9 manifest after Task 9I is **six files**. Task 9J and any later commit preflight must freeze those six files, not silently discard the approved stabilizations or claim an obsolete four-file manifest.

## 9. Known Residuals

### Plan 05-4C M-1 — DEFERRED MINOR

M-1 remains unchanged and non-blocking. The database does not express, with one composite foreign-key/unique invariant, that a Demand Review finding identity necessarily belongs to the same review identity supplied alongside it. Repository/service validation remains the authoritative enforcement layer. Plan 05-4D did not change that schema relationship and Task 9 found no new cross-tenant or cross-review disclosure. A separate schema-hardening decision is required if M-1 is to be closed later.

### Non-blocking warnings

The final evidence is not warning-free:

1. Starlette deprecation warning for the current `httpx` / `starlette.testclient` integration.
2. Deliberate JWT wrong-algorithm test emits `InsecureKeyLengthWarning` because its SHA384 HMAC test key is shorter than the RFC recommendation.
3. Vite reports minified chunks larger than 500 kB; build still exits successfully.

### Task 9 review findings

No Task 9 Critical/Important review residual remains. The integration-test findings listed above are closed.

### PostgreSQL status

Current-head real PostgreSQL Gate: PASS. PostgreSQL is no longer a production-deployment blocker for Plan 05-4.

## 10. Explicit Non-Started / Out-of-Scope Work

Plan 05-4 closure does **not** start or authorize:

- procurement execution or purchase ordering;
- reporting/report-center implementation;
- chat cards, chat-driven write workflows, or chat execution authority;
- Plan 05-5;
- browser E2E automation beyond the existing frontend contract/unit/type-check/build evidence;
- automatic preemption or budget/cost optimization;
- commit, push, PR creation/update, Ready transition, merge, branch/worktree cleanup, or deletion.

## 11. Final Recommendation and Task 9J Boundary

**Substantive recommendation:** approve Plan 05-4 production closure at Alembic head `20260827_15`, carrying only 05-4C M-1 as a deferred non-blocking Minor, **subject to Task 9J final verification after both closure documents exist**.

Task 9J has not run at the time this document is created. Before any commit authorization, Task 9J must freshly verify the final six-file reality-amended manifest, integration/focused/full backend, Ruff, Alembic head/current, legacy zero-scan, full frontend/type-check/build, real PostgreSQL status, `git diff --check`, staged-empty state, no production/dependency/build-artifact changes, and the accuracy of both Closure Review documents.

If Task 9J is green, the next action is to report the frozen six-file hashes and request separate approval for the local closure commit. No push, PR, merge, cleanup, or Plan 05-5 action is implied.

## 12. Evidence Index

Historical stage records:

- `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04a-closure-review.md`
- `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-backend-gate.md`
- `docs/superpowers/reviews/2026-08-16-maintenance-plan05-04b-frontend-gate.md`
- `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04c-closure-review.md`

Task 9 current evidence:

- `maintenance-plan05-4d-task9-tenant-invariant-recovery-result.txt`
- `maintenance-plan05-4d-task9-legacy-scan-recovery-v2-result.txt`
- `maintenance-plan05-4d-task9g-frontend-stabilization-result.txt`
- `maintenance-plan05-4d-task9-alembic-gate-result.txt`
- `maintenance-plan05-4d-task9-real-postgresql-gate-result.txt`
- `maintenance-plan05-4d-task9-code-review-bundle.txt` and subsequent code-review stabilization/recovery results
- `maintenance-plan05-4d-task8-source-identity-stabilization-verify-only-result.txt`
- `maintenance-plan05-4d-task8-plan-detail-route-identity-stabilization-result.txt`
- `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04d-closure-review.md`

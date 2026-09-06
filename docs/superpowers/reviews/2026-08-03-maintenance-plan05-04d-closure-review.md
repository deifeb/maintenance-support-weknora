\
# Plan 05-4D Allocation Assurance Closure Review

## 1. Decision / Closure Status

**SUBSTANTIVE REVIEW: APPROVED FOR TASK 9J FINAL VERIFICATION**

The final read-only Task 9 code review found **0 Critical, 0 Important, and 0 blocking Minor** findings in the approved Plan 05-4D closure scope. No production defect or scope leakage remains open from Task 9 review.

This document is intentionally written **before Task 9J**. It records the frozen implementation, migration, PostgreSQL, backend, frontend, legacy-runtime, and code-review evidence that qualifies Plan 05-4D as a closure candidate. It does **not** claim that Task 9J has run, does not authorize a commit, and does not start Plan 05-5.

Closure recommendation: proceed to Task 9J. If Task 9J reproduces the required final verification on the exact six-file reality-amended manifest described below, close Plan 05-4D at Alembic head `20260827_15`.

## 2. Reviewed Repository / Base / Task 9 Range

- Repository: `deifeb/maintenance-support-weknora`
- Task 9 branch: `codex/maintenance-plan05-4d-task9`
- Authoritative integration base: `feature/maintenance-frontend-plan05`
- Frozen base / HEAD / tracking SHA: `63f4a55f32b7c1d4f9f2a55eb7edc0c68f5e5a3c`
- Base-to-task topology at the final pre-document freeze: ahead `0`, behind `0`
- Task 9 execution plan artifact: `2026-08-28-maintenance-plan05-04d-task9-final-integration-closure.md`
- Task 9 execution plan SHA256: `cd7690c71d2ddebdaa9c656ed2d782b8b3e0a14d0481c11511384304d231d83b`
- Authoritative design: `docs/superpowers/specs/2026-08-03-maintenance-plan05-04-inventory-review-allocation-design.md`
- 05-4D implementation plan: `docs/superpowers/plans/2026-08-03-maintenance-plan05-04d-allocation-assurance.md`

Task 9 began from the already merged 05-4D implementation and frontend work. Task 9 production scope remained verification/closure only. All Task 9 repository changes are tests or review documentation; no production or migration file is modified by Task 9.

## 3. Exact Task 9 Code/Test Scope and Approved Manifest Amendment

The original Task 9 execution plan described an intended four-file final scope: two new integration tests plus two closure reviews. That literal file count became stale after two separately approved broad-Gate test-only stabilizations. The approved reality is therefore:

### Frozen code/test scope before this documentation

1. `extensions/maintenance-api/tests/integration/test_allocation_assurance_workflow.py`
   - untracked Task 9 integration contract
   - frozen SHA256: `c81d3b1dce7236f17827865616b3b187d09d8dbdadce61bbdb77535c02081807`
2. `extensions/maintenance-api/tests/integration/test_plan05_04_cross_domain_invariants.py`
   - untracked Task 9 cross-domain contract
   - frozen SHA256: `c9bce3f4536281cbd75f5fae3ab8c2cd9494c6339fef5efc03a232465bde5dd6`
3. `extensions/maintenance-api/tests/models/test_tenant_models.py`
   - approved backend broad-Gate stabilization
   - exact diff: `6 additions / 0 deletions`
   - reason: the production model registry already contained the six allocation tables, while the test-only `TENANT_TABLES` expectation had not been extended to them
4. `frontend/src/views/maintenance/__tests__/master-data-navigation.test.ts`
   - approved frontend broad-Gate stabilization
   - exact diff: `2 additions / 0 deletions`
   - additions: `maintenanceAllocationRules`, `maintenanceAllocationPlanDetail`
   - reason: the router correctly contained both hidden authenticated 05-4D routes, while the older test-only hidden-route whitelist did not

### Closure documentation added by Task 9H / Task 9I

5. `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04d-closure-review.md`
6. `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04-final-closure-review.md`

After these two documents are created, the correct final working manifest is **six files**. The two added broad-Gate files are approved test-only stabilizations, not scope leakage. No router, menu, production service, model, migration, dependency, or build artifact was added by those stabilizations.

Task 9J must use this six-file reality-amended manifest rather than the obsolete literal four-file count from the earlier execution plan.

## 4. Current Migration Lineage Through `20260827_15`

The actual current chain is:

```text
... -> 20260803_08 inventory ledger foundation
    -> 20260803_09 atomic inventory target receipts
    -> 20260803_10 import execution principal
    -> 20260803_11 inventory operations and stocktake persistence
    -> 20260803_12 authoritative demand review persistence
    -> 20260803_13 allocation assurance persistence
    -> 20260825_14 allow gap-only allocation plan lines
    -> 20260827_15 allocation rule publish receipt/idempotency (head)
```

`20260803_13` is an intermediate 05-4D revision, not the current head.

Task 9E executed an isolated SQLite single-head and round-trip Gate. It verified:

- exactly one head: `20260827_15 (head)`;
- the `20260803_12 -> 20260803_13 -> 20260825_14 -> 20260827_15` chain;
- downgrade and re-upgrade behavior in a disposable database;
- `allocation_plan_lines.expected_balance_version` is nullable at head with `ck_allocation_plan_line_balance_version_pair` semantics from revision 14;
- revision 15 exposes `publish_idempotency_key`, `publish_request_hash`, and `publish_response_snapshot_json` plus the tenant-scoped publish-idempotency unique index;
- migration files were unchanged by the Gate.

The same 12-through-15 head semantics were also exercised on real PostgreSQL as described below.

## 5. Rule Lifecycle Findings

**Finding: APPROVED.**

The 05-4D rule authority remains `AllocationRuleService` and the persisted rule-version repository/model. The reviewed lifecycle is:

```text
DRAFT -> SIMULATED -> PUBLISHED -> RETIRED
```

Key closure findings:

- draft creation and revision preserve lineage/version semantics; revising a simulated/published historical rule creates a new DRAFT instead of mutating history;
- scoring uses exact Decimal weights and deterministic ordering/tie-break behavior;
- publication is gated by a fresh successful simulation for the exact candidate rule/source/inventory facts;
- publish and retire remain ADMIN-only operations;
- publication is protected by strict tenant-scoped idempotency evidence persisted on the rule version;
- revision 15 persists publish idempotency key, request hash, and response snapshot, with a tenant-scoped unique index;
- real PostgreSQL concurrency verified same-key publish replay and tenant-scoped key independence.

Task 9 Scenario A now uses the real authority path: `create_draft -> simulation submit/executor -> admin publish -> plan create`. The earlier review finding that the focused integration setup could bypass candidate publication was removed.

## 6. Simulation Findings

**Finding: APPROVED.**

The final Task 9 contracts verify the real persistent simulation lifecycle rather than faking the business state machine:

- submit persists a simulation tied to exact candidate rule, baseline rule, and source DemandList identities;
- the real `AllocationSimulationExecutor` advances the persisted simulation to terminal `COMPLETED` state;
- the frozen input snapshot contains the inventory facts used for scoring;
- `inventory_fingerprint` equals the canonical hash of that frozen inventory snapshot;
- candidate, baseline, and source identities are asserted exactly;
- deterministic scoring/result behavior is inherited from the production scoring/service tests and exercised through the executor;
- simulation creates no inventory reservation, transaction, ledger, or balance mutation;
- before/after inventory business facts remain identical.

The final code review specifically required exact source/rule/fingerprint identity assertions so a simulation that merely reached `COMPLETED` could not create a false-positive closure result. That review item is closed.

## 7. Allocation Plan Lifecycle Findings

**Finding: APPROVED.**

The reviewed plan authority is `AllocationPlanService`; inventory mutation authority remains the 05-4B reservation/transaction/ledger stack. The production lifecycle remains:

```text
DRAFT -> PREVIEWED -> CONFIRMED -> EXECUTING
      -> COMPLETED | PARTIALLY_COMPLETED | FAILED
DRAFT / PREVIEWED / CONFIRMED -> VOIDED
```

Task 9 and the frozen 05-4D focused suite jointly cover:

- create from eligible source and matching PUBLISHED rule;
- production-generated plan lines rather than hand-constructed integration lines;
- `edit_line(...)` with a non-empty reason and optimistic line version;
- preview and confirm transitions;
- execute-time source, rule, plan version, and inventory-balance version revalidation;
- void and regenerate behavior through the existing focused service/API tests;
- source supersession after confirm: execute fails closed before inventory mutation or reservation creation;
- retired/superseded rule protection through the focused plan-execution regression;
- per-line partial execution: one line may reserve while another returns a structured concurrency conflict;
- conflict evidence includes expected/actual version, retryability, and suggested recovery without automatic preemption;
- execute idempotency: same-key replay returns the same terminal execution result without duplicate reservation/transaction/ledger effects;
- successful line result carries the exact `reservation_id` and is traced to one `InventoryReservation`, one reservation line, the exact child `RESERVE` `InventoryTransaction`, allocation audit context, and its `InventoryLedgerEntry`;
- the conflict line creates no allocation-owned reservation or preemption.

A legitimate inventory authority (`InventoryTransactionService`) is used to create the competing version drift in the focused integration scenario. Direct balance-version mutation and manual replacement of production plan-generation logic were removed during review stabilization.

## 8. Frontend 05-4D Evidence

**Finding: APPROVED for the frozen frontend content; Task 9J will rerun it after documentation.**

05-4D frontend delivery preserves the existing Inventory Gap information architecture while adding allocation-assurance entry points:

- the five existing Inventory Gap tabs remain present;
- allocation rule and allocation plan workspaces are Store/API-backed and keep backend authority for lifecycle transitions and conflict validation;
- `maintenanceAllocationRules` and `maintenanceAllocationPlanDetail` are authenticated hidden routes rather than new top-level Maintenance menu entries;
- the source-identity fail-closed stabilization prevents a stale plan/source relationship from being presented as current authority;
- the route-identity fail-closed stabilization prevents `AllocationPlanDetail` from exposing stale Store state for a different route identity;
- the frontend uses structured server conflict evidence and exact decimal strings rather than inventing inventory authority in the browser.

Task 9 broad frontend evidence on the current frontend content:

- focused hidden-route regression: `10 passed, 0 failed`;
- full frontend: `575 passed, 0 failed`;
- frontend app type-check: PASS;
- frontend config type-check: PASS;
- Vite 7.3.6 production build: PASS, `6575` modules transformed, built in `39.79s`;
- build output was isolated to a temporary repository mirror and did not create Task 9 worktree build artifacts.

The frontend broad Gate preceded later backend-only Task 9 integration-test review stabilizations. No frontend file changed after the approved two-line hidden-route test stabilization, so that frontend evidence remained the frozen frontend Gate for Task 9H/I. Task 9J must nevertheless rerun the full frontend Gate fresh after both closure documents exist.

## 9. Fresh 05-4D Focused / Backend Evidence

The latest Task 9 run after all integration-test review stabilizations produced:

- two-file Ruff preflight: PASS;
- Task 9 integration contracts: `4 passed, 1 warning in 7.54s`;
- 05-4D focused backend Gate: `158 passed, 1 warning in 34.54s`;
- full maintenance-api backend: `1559 passed, 8 deselected, 2 warnings in 455.12s`;
- full backend Ruff (`app tests`): PASS.

The final test-only tenant-chain repair was included in these results. It removed a `DemandListRead` DTO from the ORM tenant-ID assertion set, tied the DTO to its persisted row with `published_row.id == derived.id`, and retained the explicit persisted tenant-chain invariant. No production behavior was changed.

The final legacy runtime scan was then completed separately and read-only because `rg` was not available on PATH. The equivalent PowerShell/.NET scan recursively examined all `app/**/*.py` files:

- Python files scanned: `234`;
- pattern: `WarehouseInventory|warehouse_inventories`;
- matches: `0`.

This closes the runtime legacy aggregate reference requirement without modifying the repository.

## 10. Real PostgreSQL 05-4D / Current-Head Evidence

**Finding: APPROVED. Production PostgreSQL deployment Gate blocker is closed for Plan 05-4.**

Task 9F ran against a disposable real PostgreSQL database with:

- PostgreSQL server: `17.11` (`server_version_num=170011`);
- encoding: UTF8;
- SQLAlchemy dialect: `postgresql`;
- driver: `psycopg 3.3.4`;
- disposable database: `maintenance_plan05_4d_task9_pg_gate`;
- SQLite fallback: none.

Real PostgreSQL migration evidence:

```text
empty -> 20260803_11
20260803_11 -> 20260827_15
20260827_15 -> 20260803_11
20260803_11 -> 20260827_15
```

At `20260827_15`, the Gate verified the nullable expected-balance-version semantics, the balance/version pair constraint, publish receipt columns, and the tenant-scoped publish-idempotency unique index.

The PostgreSQL test harness collected seven contracts and passed all seven in `11.16s`:

- three then-current Task 9 integration contracts;
- concurrent same-key rule publish replay;
- tenant-scoped rule publish idempotency key behavior;
- concurrent same-key plan execute replay reserving once;
- two plans competing for the same balance with one reservation winner.

The disposable database ended at `20260827_15`, had zero Gate business rows after pytest cleanup, and was dropped successfully. The temporary harness was removed and repository files were unchanged.

Temporal note: the real PostgreSQL Gate was frozen before later **test-only** review stabilizations expanded/strengthened the Task 9 integration contracts to their final four-test form. No production or migration file changed after Task 9F. Therefore Task 9F remains the PostgreSQL migration/concurrency evidence, while the final four integration contracts are evidenced by the latest backend run above. Task 9J must re-check the final PostgreSQL Gate status against the unchanged current head.

## 11. Code Review Findings, Warnings, and Residual Risks

### Task 9 review findings

All blocking Task 9 review findings are closed:

| Review item | Final disposition |
|---|---|
| Scenario A bypassed production plan-line/edit authority | CLOSED: real two-item generation + `edit_line` + published candidate + legitimate inventory authority drift |
| Mandatory source-superseded-after-confirm Scenario B absent | CLOSED: execute-time source drift now fails before inventory mutation/reservation |
| Actor roles/request-ID provenance incomplete | CLOSED: review/rule/plan/reservation/transaction/event evidence asserts user/roles/request IDs |
| Transaction snapshot checked by weak string membership | CLOSED: structured allocation plan/line/audit-context identities are asserted |
| Success line not fully traced reservation -> transaction -> ledger | CLOSED: exact reservation, transaction, audit context, and ledger chain asserted |
| Simulation identity/fingerprint assertions too weak | CLOSED: exact candidate/baseline/source and canonical frozen inventory hash asserted |
| Tenant chain not explicit | CLOSED: persisted cross-domain entities assert one tenant; other-tenant actor is explicitly distinct |

Final read-only Task 9 code review: **0 Critical / 0 Important / 0 blocking Minor**.

### Non-blocking warnings / residuals

The closure evidence is not warning-free:

1. Starlette deprecation warning for the current `httpx` / `starlette.testclient` integration.
2. `InsecureKeyLengthWarning` in the deliberate wrong-algorithm JWT integration case because its SHA384 test HMAC key is shorter than the RFC recommendation.
3. Vite warning that some minified chunks exceed 500 kB and may benefit from code splitting/manual chunking.
4. Plan 05-4C deferred Minor M-1 remains visible: the database schema does not enforce finding-to-review membership with one composite foreign-key/unique invariant. Repository/service validation remains authoritative. 05-4D did not broaden schema scope to remediate it.

The current-head real PostgreSQL deployment Gate is PASS, so live PostgreSQL availability/locking is no longer a Plan 05-4 closure blocker.

PowerShell evidence-transport failures encountered during Task 9 (variable shadowing, unavailable `rg`, and scalar `.Count` under StrictMode) were harness defects. Each stopped fail-closed, left the repository within its approved scope, and was replaced by a read-only or bounded recovery. They are not production defects.

## 12. Explicit Scope Exclusions

This Closure Review does not approve or start:

- procurement execution or purchase-order placement;
- cost/budget optimization;
- automatic inventory preemption;
- reporting/report-center delivery;
- chat cards or chat-driven allocation execution;
- browser E2E automation beyond the frozen frontend unit/contract/type-check/build Gates;
- a new SSE transport for simulations;
- a new inventory write authority outside the existing 05-4B transaction/reservation/ledger services;
- Plan 05-5;
- commit, push, PR creation/update, merge, branch/worktree deletion, or cleanup.

## 13. Exact Recommendation

**Recommendation: proceed to Task 9J final verification on the six-file reality-amended Task 9 manifest.**

Substantively, Plan 05-4D rule, simulation, plan, frontend, migration, cross-domain, and real PostgreSQL contracts have no remaining Critical/Important blocker. The current authoritative Alembic head is `20260827_15`.

Do not commit yet. Task 9J must freshly re-run/re-check the required backend, frontend, Alembic/current, legacy scan, PostgreSQL status, diff/scope, and document-evidence assertions after both closure reviews exist. Commit, push, PR, merge, cleanup, and Plan 05-5 remain separate approvals.

## Evidence Index

Primary Task 9 evidence used by this review:

- `maintenance-plan05-4d-task9-tenant-invariant-recovery-result.txt` — final four integration tests, 05-4D focused Gate, full backend, Ruff, final Slice 1/2 hashes.
- `maintenance-plan05-4d-task9-legacy-scan-recovery-v2-result.txt` — 234-file runtime legacy inventory zero-scan and final four-file freeze.
- `maintenance-plan05-4d-task9g-frontend-stabilization-result.txt` — approved +2 hidden-route test stabilization, 575/575 frontend, two type-checks, Vite build.
- `maintenance-plan05-4d-task9-alembic-gate-result.txt` — SQLite single-head and round-trip through `20260827_15`.
- `maintenance-plan05-4d-task9-real-postgresql-gate-result.txt` — PostgreSQL 17.11 migration/current-head/concurrency Gate and cleanup.
- `maintenance-plan05-4d-task9-code-review-bundle.txt` plus subsequent stabilization/recovery results — code-review finding evidence and bounded remediation history.
- `maintenance-plan05-4d-task8-source-identity-stabilization-verify-only-result.txt` — source-identity fail-closed frontend evidence.
- `maintenance-plan05-4d-task8-plan-detail-route-identity-stabilization-result.txt` — route-identity fail-closed frontend evidence.

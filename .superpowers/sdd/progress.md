# Plan 05 Subagent-Driven Development Progress

## Recovery baseline

- Repository: `deifeb/maintenance-support-weknora`
- Branch: `feature/maintenance-frontend-plan05`
- Verified starting commit: `c36dca464ba9c1c0de59c35a0a9bfb2e3477053b`
- Execution mode: task-isolated TDD with specification and code-quality review gates
- Delivery mode: reviewable ZIP and patch packages for local PowerShell application

## Durable task ledger

- Unit 0: complete — approved design, roadmap, plans 05-1 through 05-5, revised execution plan, and this ledger preserved; documentation-only review clean.
- Unit 1: complete — canonical configuration contract implemented with RED/GREEN evidence, focused harness tests passing, specification review clean; full repository Go test awaits the user's Go 1.26 toolchain.
- Unit 2: complete — HS256 actor tokens implemented with exact 180-second expiry, normalized tenant roles, unique jti values, RED/GREEN tests, package verification, race detection, and security review clean.
- Unit 3: complete — authenticated HTTP and SSE reverse proxy implemented with strict path and method gates, trusted JWT exchange, request and response header isolation, safe redirect rewriting, stable error envelopes, streaming cancellation coverage, package verification, and race detection clean.
- Unit 4: complete — strict web-user actor mapping, disabled-aware fail-closed proxy construction, authenticated route registration, bare-path 404 handling, server and desktop entrypoint integration, cross-layer identity and CORS security coverage, focused package verification, and race detection clean.
- Unit 5: pending — FastAPI internal JWT verification.
- Unit 6: pending — RBAC, stable error envelopes, and response metadata.
- Unit 7A: pending — tenant/version model foundation for existing business tables.
- Unit 7B: pending — reversible tenant migration.
- Unit 8A: pending — tenant-safe master-data repositories and services.
- Unit 8B: pending — tenant-safe demand, AI, and worker flows.
- Unit 9A: pending — idempotency persistence and service.
- Unit 9B: pending — database optimistic locking and audit events.
- Unit 10: pending — business API permissions and metadata.
- Unit 11: pending — Docker, operations documentation, and complete security gate.

## Recovery rule

Resume from the first unit marked `pending`. Never infer completion from conversation text alone; completion requires a persisted patch or commit plus its review report.

<!-- PLAN05-01-SECURITY-FOUNDATION:START -->
## Plan 05-1 - Maintenance Security Foundation

**Status:** COMPLETE
**Completion date:** 2026-07-27
**Branch:** `feature/maintenance-frontend-plan05`
**PR base:** `feature/demand-calculation-engine`
**Base ref at ledger reconstruction:** `origin/feature/demand-calculation-engine` = `baf71615504606331ad4634fb6507843b6df5452`
**Merge base:** `baf71615504606331ad4634fb6507843b6df5452`
**Completion HEAD before ledger commit:** `77c3aeaafa93280d605cdf4a2c0ef1744aa88e17`
**Final gate:** `PLAN05_01_SECURITY_CLOSURE_TASK7_V5=READY_FOR_REVIEW`

### Units 5-11

- [x] **Unit 5:** internal JWT verification complete.
- [x] **Unit 6:** RBAC, errors, and response metadata complete.
- [x] **Unit 7A/7B:** tenant/version models and reversible migration complete.
- [x] **Unit 8A/8B:** tenant-safe repositories, services, routes, and workers complete.
- [x] **Unit 9A/9B:** idempotency, optimistic locking, and audit complete.
- [x] **Unit 10:** 127 business endpoints protected with role and metadata contracts.
- [x] **Unit 11:** Docker, operations documentation, and complete Phase 05-1 gate complete.

### Feature-branch completion commits

| Commit | Subject |
|---|---|
| `c36dca464ba9c1c0de59c35a0a9bfb2e3477053b` | feat: add maintenance integration configuration |
| `4e8c738e260ec49ffb68204ecef8770dac781797` | docs: preserve approved maintenance plan 05 |
| `06baad4b434ef7e94cec342d3d7d12284a52434a` | fix: align maintenance proxy configuration contract |
| `bbd161c8109e927c73911dc13074aa0c157fdadf` | feat: sign maintenance actor tokens |
| `4125b860adef68f55f83248c99db930335f69750` | feat: proxy maintenance http and sse traffic |
| `5577c03a0c520fad525f20ccac2a7e14bd541dbf` | docs: record approved maintenance unit 4 design |
| `d803044aa50a67621ea71b7c67c2d05726455433` | docs: add maintenance unit 4 implementation plan |
| `61d48869e22b3b64f997acc175b6d5cf33c9d9f4` | docs: record maintenance unit 4 planning gate |
| `33f10a1f00ab97ed70ec19598da2bff93d78f119` | docs: review maintenance unit 4 implementation plan |
| `08bddd5b9c7ac68e09ec56510aa4b5093280df86` | test: define maintenance actor role mapping |
| `9bf9950a0c4196fa3e3e77fd770f721543a5cf20` | feat: add minimal maintenance web actor resolver |
| `acc5c42d844eb7d0edd78a37aaaa8e951db23e0b` | test: cover maintenance actor identity boundaries |
| `ef12d55a80c66d3ba4b0864c3b24808047170fdf` | test: fix empty maintenance actor assertions |
| `ab3b9e770991bb0e3d3b5105094de52667c94116` | test: define maintenance proxy provider contract |
| `d4731269ea6212e5fb9dc06bb0d1c6d525dc9f17` | feat: add minimal maintenance proxy provider |
| `47a45e97f0c7ef739cf4a36291e3ba83839f2140` | test: cover maintenance proxy provider failures |
| `22ca12e1cf4f15367f24400fb4920812a01898f8` | test: require maintenance proxy provider registration |
| `6d4ea453aab4aef28950611b3a0cf6b945ffc5e9` | feat: provide configured maintenance proxy |
| `11d76cffa7ce879b5adab725eb0d2e77cc5f7a62` | test: define maintenance route registration contract |
| `d21bb000e3cdd87bed46df2a1effe6143e9bf485` | feat: add minimal maintenance route registration |
| `96cf0c3f69aff13c0bed9462798a7e5df3c325fa` | test: support maintenance proxy close notifications |
| `6c7003d6a65e0d4688fc725ec89e7d3877e712a8` | test: cover maintenance route method authority |
| `03442e2aacd1e2fd2d4e3c19635da2d79e499b35` | test: define maintenance router integration contract |
| `a486fb6115424f965f7fd1a4105393fb96e43f67` | feat: integrate maintenance proxy routes |
| `a72290683a3347316c733647a017ab9556759861` | test: define application handler maintenance path contract |
| `15d8b17a5f13baa47904c524a8dc2e39d2baf91a` | feat: add application http handler |
| `bdf39641cdf75cf68f66ffa09b814696eacf986b` | test: define application handler entrypoint contract |
| `d852aacba8a4f29fec9bc7dba6c453aa21d75589` | feat: serve application through maintenance handler |
| `6fdef1e0554e24a523b33637199738af4094f419` | test: cover maintenance proxy security integration |
| `807d6571574c55066f36c5d35d53c4078e4af014` | test: use cross-origin maintenance preflight |
| `b0ce7cec6545328261b35fb44f720cb8cd57aaa2` | docs: mark maintenance unit 4 complete |
| `d1ed73abc9e863dd6969ea23773f812005d686a4` | docs: add maintenance unit 5 design |
| `21b6a92f913661593f80ebee412b6f36ed9d1931` | docs: clarify maintenance JWT time boundaries |
| `8d5a16c0af7038153e81b1406af991f5bbfa8018` | docs: add maintenance unit 5 implementation plan |
| `047a84fdc263f024fa0a502ef098862189b677ba` | docs: correct maintenance unit 5 task boundaries |
| `eb0bbd11a1dc14a3d9a59e650f250a94b5b4273a` | docs: review maintenance unit 5 implementation plan |
| `5f1d1acde0466187221938dcf4dec3ebff88495a` | build: add PyJWT for internal identity |
| `be2e24be14e48bf18e88b6fda606910c1b75fb40` | test: define internal jwt settings contract |
| `bd7ded70884da99ae4e95293117c14a068b02ab5` | feat: validate internal maintenance identity settings |
| `cc0fee8042d800cc58ae8647fff85c53ca7b63a2` | test: bootstrap internal identity settings |
| `e60699d8335d847c132ad69bbfdbc605a3650c21` | docs: document internal identity settings |
| `bd3883ca683e474e7e7068b53a1544852733e8ef` | style: organize internal jwt test imports |
| `70ea5f29075db88115b12eef88c146bbc26f3511` | test: define maintenance actor contract |
| `a316ec9eab3c2093eaaf8d3a35f1b81a8c274d5a` | feat: define maintenance actor types |
| `3e7352295c1c363797ae4b9c2480546ed3aa2496` | feat: export maintenance actor types |
| `24c2bb1bff3b5a6c1e6fab52b4d3ef686fce6cc6` | test: define minimal internal token verifier contract |
| `7217617e8461548040c8f6b55b218223918a5ce3` | feat: implement internal jwt verifier |
| `646edeea692deaa45a434cf76531ab487e96e841` | feat: add internal jwt request authentication |
| `6e756bae51b468ac4d810c877d8f5f7016f9bab5` | feat: enforce maintenance roles and response metadata |
| `8ed98181e7d547dd03b252c0ba0060a82e1bbd52` | feat: add tenant security schema foundation |
| `a82da85e9f0ff389d06b3055e602fb970f9b0f05` | fix: enforce tenant scope in maintenance persistence |
| `d8a9aa59d9b122954050aca198c8c6ddcb5e3502` | fix: enforce tenant scope in demand workflows |
| `f88f0ecb82bc1c19f3f8a80a0a2d93c06261c9f7` | feat: enforce tenant-safe ai orchestration boundaries |
| `3c9c26be372375bdc6e3502ed53b57f555ff049d` | feat: preserve actor context across ai routes and workers |
| `733b3025365e8b1ab12f7abad9b386ef0ecdd5f0` | test: verify tenant-safe ai review routes |
| `a7ff333a6c8b3855c4197b1c889e37dc6a767c44` | fix: enforce tenant-safe ai report routes |
| `cd9a46ea83e39be8f22c55db50e9a5e5a0806eb6` | fix: migrate crud callers to tenant-aware contracts |
| `199778f93447e00184416faee5302f69b1ab4574` | test: complete tenant-aware API fixtures |
| `70c6f460981b8d841569881c4ed86006057b39ab` | fix: propagate actor context through demand routes |
| `b4a0943a77bb6acd2413531c8423108ea84153af` | docs: plan maintenance security closure |
| `73ba2b0162ddf0f3b92d62632e6ee5200f2b43b5` | fix: protect demand scenario and comparison routes |
| `c3c711503d67b5711412a2984b50c5c530b27de6` | fix: enforce calculation and repair route roles |
| `11a741cd2ac0a35061a521fb367200d9378b7162` | fix: complete maintenance api rbac metadata |
| `37117c8af199a8e81febfe829a28cfdd3f1ed13d` | test: verify maintenance proxy identity boundary |
| `f847d7d44f17bfc606971863cb5aecd2a2007278` | docs: configure maintenance security deployment |
| `ee3546f70268c382779bd27d92511fbc585259dd` | docs: plan Task 7 full-suite recovery |
| `77c3aeaafa93280d605cdf4a2c0ef1744aa88e17` | fix: restore tenant-aware ai integration suite |

The closure sequence from `70c6f460981b8d841569881c4ed86006057b39ab`
through `77c3aeaafa93280d605cdf4a2c0ef1744aa88e17` is a continuous
first-parent chain. The final ledger commit is intentionally recorded after
the gate and is not part of the table above.

### Final Phase 05-1 gate

- Go security packages: PASS.
- Alembic disposable-database round trip:
  `upgrade head -> downgrade base -> upgrade head`: PASS.
- Ephemeral Alembic internal JWT secret restored: PASS.
- Focused Python security scope: **110 passed**, 2 non-blocking warnings.
- Complete Python scope: **366 passed**, 2 non-blocking warnings.
- Route RBAC/metadata inventory:
  **127 PASS = 61 master-data + 40 demand + 26 AI**.
- Raw business-route `get_actor` dependencies: **0**.
- Business success responses without actor metadata: **0**.
- Tenant isolation, tenant-aware seed contract, and admin confirmation
  boundary: PASS.
- WeKnora proxy identity boundary and shared signing-secret contract: PASS.
- Production security settings and internal-only Docker Compose service: PASS.
- Ruff, compileall, Git diff checks, clean worktree, and empty index: PASS.

### Final gate artifact hashes

| Artifact | SHA-256 |
|---|---|
| `maintenance-plan05-01-security-closure-task7-v5-gates.log` | `cf98849c7770bd09199d80dd56350dfdeebafd16dbf366718f7ed549d0d94ddd` |
| `maintenance-plan05-01-security-closure-task7-v5-status.txt` | `608e4201a557a666e2634933ba0abeabb0ca549369750c9d9af69a64bf6c5e01` |
| `maintenance-plan05-01-security-closure-task7-v5-review.diff` | `93783ec1162666bc63ede17f72709811a40579ca3fdae74e15405cc4fc8c426a` |
| `maintenance-plan05-01-security-closure-task7-v5-files.txt` | `3673ad7b2abcea5eefa93b2e3ff9a880e2710e065a6324932c19bc664c5033f2` |

### Plan 05-2 entry gate

Plan 05-2 remains blocked until this ledger change is reviewed, committed as
`docs: complete maintenance security foundation`, pushed to
`origin/feature/maintenance-frontend-plan05`, and represented by a PR targeting
`feature/demand-calculation-engine`.

The first Plan 05-2 implementation commit remains:

```text
feat: add typed maintenance frontend client
```

No menu, dashboard, or master-data page work begins before the typed client
passes its frontend tests and type checking.
<!-- PLAN05-01-SECURITY-FOUNDATION:END -->

## Plan 05-2 continuation and closure (2026-07-30)

- Baseline Task 1: complete (commits `fb32b03..30fc216`, spec compliant, task quality approved; minor path-segment boundary note deferred to final review).
- Baseline Task 2: complete (commits `30fc216..febccfb`, spec compliant, task quality approved; the affected Go gate reaches the separate gojieba no-CGO boundary).
- Baseline Jieba Task 1: complete (commits `4b2dde5..b29d27a`, spec compliant, task quality approved; minor fallback edge-case coverage note deferred to final review).
- Task 9B Task 1: complete (commit `3bde177`; typed binary transfer client; focused 11/11 and type-check pass; independent review approved).
- Task 9B Task 2: complete (commits `4de02c7..6b63bcf`; reducer and visibility-aware polling; focused 10/10 and type-check pass; two race conditions fixed and rereview approved).
- Task 9B Task 3: complete (commits `52ae74f..92074db`, plus Task 2 gate fix `1e3316e`; focused 5/5, maintenance 96/96, type-check and build pass).
- Task 9B Task 4: complete (commits `2e67192`, `cf936a9`, and `45d8814`, with Task 3 serialization fix `c55f3bc`; frontend 327/327, type-check, build, backend 47, and Ruff pass).
- Plan 05-2 Task 10: complete (commits `42d4d9e`, `39326e0`, and `cc1c158`; acceptance 9/9, frontend 336/336, backend 50, Ruff, no-CGO Go, and bundle scans pass).
- Plan 05-2 implementation and automated acceptance are complete.
- Runtime screenshots and human UX acceptance remain an explicit manual acceptance item. They do not reopen implementation unless the review identifies a concrete defect.

## Plan 05-3 delivery status (2026-07-31)

### Plan 05-3A: scenario draft wizard — complete

Plan document:

- `docs/superpowers/plans/2026-07-31-maintenance-plan05-03a-scenario-draft-wizard.md`

Implementation range:

- `ce9c8348..5af3ee7c`

Delivered boundaries:

- versioned scenario draft persistence;
- manual and AI-assisted draft creation;
- deterministic validation;
- autosave with conflict handling;
- atomic materialization into executable scenarios;
- administrator-only publication;
- multilingual six-step scenario wizard;
- complete scenario-draft workflow verification.

Completion commit:

- `5af3ee7c feat: complete scenario draft workflow`

### Plan 05-3B: calculation orchestration — complete

Plan document:

- `docs/superpowers/plans/2026-07-31-maintenance-plan05-03b-calculation-orchestration.md`

Implementation and verification range:

- `92a36d1f..42986b36`

Delivered boundaries:

- calculation-group persistence;
- deterministic candidate recommendations;
- independent candidate calculation creation;
- resumable calculation-group execution;
- child-identity-safe event streaming;
- retry, cancellation, and recovery behavior;
- typed resumable frontend client;
- multi-candidate comparison workflow;
- union comparison item decisions;
- end-to-end scenario and calculation integration coverage.

Final verification commit:

- `42986b36 test: verify calculation group workflow`

Recorded Plan 05-3B gate evidence:

- focused backend gate: **38 passed**;
- frontend gate: **377 passed**;
- Vue type checking: PASS;
- production frontend build: PASS;
- Ruff: PASS;
- Alembic `upgrade -> downgrade one revision -> upgrade`: PASS;
- maintenance proxy and router Go tests: PASS;
- Git diff and repository checks: PASS.

## Closure revalidation (2026-07-31)

The Plan 05-3B closure gate was rerun locally against the closure baseline before starting Plan 05-3C.

Fresh verification results:

- focused backend gate: **38 passed**, with one non-blocking Starlette/httpx deprecation warning;
- Ruff over `app` and `tests`: PASS;
- disposable SQLite migration cycle: empty database -> `20260731_06` -> downgrade to `20260729_05` -> restore to `20260731_06`: PASS;
- full frontend test gate: PASS;
- Vue and TypeScript type checking: PASS;
- production frontend build: PASS;
- maintenance proxy and router Go tests with `CGO_ENABLED=0`: PASS;
- Git diff validation: PASS.

The frontend build reports a non-blocking warning for minified chunks larger than 500 kB. This is retained as a future code-splitting and bundle-optimization item and does not block the current functional acceptance.

The only repository modification after revalidation is this progress ledger. Runtime screenshots and human UX acceptance remain the separate manual acceptance item recorded above.

## Implementation closure baseline and pull-request boundary

Branch:

- `feature/maintenance-frontend-plan05`

Implementation baseline verified by this closure:

- `42986b3630de00a6418960d29b6fad1c76bf5705`
- `test: verify calculation group workflow`

Pull request:

- repository: `https://github.com/deifeb/maintenance-support-weknora`
- pull request: `#4`
- title: `feat: deliver Maintenance Plan 05 scenario and calculation workflows`
- base: `feature/demand-calculation-engine`
- head: `feature/maintenance-frontend-plan05`
- state at closure review: open draft

The branch has completed:

- Plan 05-1;
- Plan 05-2;
- Plan 05-3A;
- Plan 05-3B.

Plan 05-3 as a whole is not complete because Plan 05-3C remains outstanding.

## Next implementation boundary

Approved next plan:

- `docs/superpowers/plans/2026-07-31-maintenance-plan05-03c-demand-list-lifecycle.md`

Plan 05-3C implementation is in progress.

At the verified implementation baseline there are no demand-list model, repository, service, route, migration, typed client, store, or detail-view implementation files.

The exact next task is:

- Plan 05-3C Task 2
- Generate a Complete Demand List Draft

Task 1 implementation commit:

- `3bb66f54 feat: add versioned demand list persistence`

Do not reimplement:

- internal JWT and maintenance identity boundaries;
- frontend master data;
- scenario draft persistence and services;
- the six-step scenario wizard;
- calculation-group persistence;
- resumable calculation orchestration;
- candidate comparison and item decisions.

Do not begin Plan 05-4 or Plan 05-5 before all seven Plan 05-3C tasks and the complete Plan 05-3 vertical gate are finished.
## Plan 05-3C Task 1 closure (2026-07-31)

Plan document:

- `docs/superpowers/plans/2026-07-31-maintenance-plan05-03c-task1-demand-list-persistence.md`

Formal implementation commit:

- `3bb66f54 feat: add versioned demand list persistence`

Delivered boundaries:

- versioned `DemandList`, `DemandListItem`, and `DemandListEvent` persistence;
- exact demand-list lifecycle and event enums;
- tenant-scoped demand-list and item repositories;
- lineage-version uniqueness;
- one current published version per tenant and lineage;
- tenant-scoped lifecycle-event idempotency;
- exact `Numeric(20, 6)` quantity storage;
- decimal-string JSON serialization;
- reversible Alembic revision `20260731_07`.

Fresh Task 1 verification evidence:

- focused migration and repository tests: **8 passed**;
- Ruff over all Task 1 files: PASS;
- `git diff --check`: PASS;
- worktree cleanliness and branch synchronization: PASS;
- local and remote branch difference after synchronization: `0 0`.

The non-blocking Starlette/httpx deprecation warning remains unchanged from the previous baseline.

Task 1 was developed on a temporary branch and squash-merged through PR #6. The temporary local branch was removed after the formal merge commit was synchronized.

Next implementation boundary:

- Plan 05-3C Task 2;
- Generate a Complete Demand List Draft;
- add authoritative draft-generation preconditions and immutable source snapshots;
- do not begin lifecycle transitions, publication, derivation, API routes, or frontend work in Task 2.

## Plan 05-4A Inventory Ledger Foundation (2026-08-03)

- Status: **COMPLETE — TASK 7 FINAL GATE AND INDEPENDENT CLOSURE REVIEW PASSED**
- Branch: `codex/maintenance-plan05-4`
- Plan: `docs/superpowers/plans/2026-08-03-maintenance-plan05-04a-inventory-ledger-foundation.md`
- Implementation base: `228d96dc74609b692efa1c3ff122f78ad5256a68`
- Committed Task 1–6 head: `d53fe56dc6ba6e33527d3903c06beedf91aac810`
- Task 1: complete — inventory models and reversible ledger migration.
- Task 2: complete — tenant-scoped repository and aggregate query contract.
- Task 3: complete — OPENING/ADJUST transaction core, idempotency, fixed-order locking, and append-only ledger.
- Task 4: complete — ledger-backed compatibility API and canonical DEFAULT identity.
- Task 5: complete — dashboard, demand, AI, deletion guards, and legacy relationship cleanup.
- Task 6: complete — ledger-backed import, export, seed compatibility, target receipts, bounded exact exports, and durable execution-principal recovery.
- Task 7: complete — authoritative-fact integration contract, corrected 05-4A Gate, independent closure review, and test Settings-cache isolation.
- Task 7 integration: **3 passed**, 1 warning in 23.82s.
- Complete Plan 05-4A focused Gate: **143 passed**, 1 warning in 190.11s.
- Migration lineage Gate: **26 passed**, 1 warning in 159.25s.
- Full backend: **878 passed, 8 deselected**, 2 warnings in 406.07s.
- Ruff: PASS.
- Alembic: single head `20260803_10`.
- `git diff --check`: PASS.
- Runtime legacy reference scan for `WarehouseInventory|warehouse_inventories`: no matches.
- Independent closure review: **APPROVED** with no remaining Critical, Important, or Minor blocking findings.
- Closure review: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04a-closure-review.md`.
- Live PostgreSQL migration execution, unique-conflict timing, and `SELECT ... FOR UPDATE` scheduling were not executed; `psql` was unavailable and only the Docker CLI was detected.
- Plan 05-4A is complete. Plan 05-4B is not started or authorized.
- Before Plan 05-4B begins, migration allocations must be corrected to `20260803_11`, `20260803_12`, and `20260803_13` for 05-4B/05-4C/05-4D respectively.
- Proposed Task 7 commit: `test(maintenance): close plan05-4a inventory ledger`.

## Plan 05 C2D-A Source Model (2026-09-04)

- Status: **IMPLEMENTATION COMPLETE — AWAITING USER INTEGRATION DECISION**
- Branch: `codex/maintenance-plan05-5-c2d-a`
- Base: `83f3248b181a083d34962846fffc05a801548970`
- Design: `docs/superpowers/specs/2026-09-04-maintenance-plan05-c2d-a-source-model-design.md`
- Plan: `docs/superpowers/plans/2026-09-04-maintenance-plan05-c2d-a-source-model.md`
- Task 1: complete — commits `415d4cce3..b87c2d723`; specification and task-quality review approved. Final whole-branch review must retain the non-escalated note that the migration test does not independently assert both secondary indexes.
- Task 2: complete — commit `aeb396f24`; specification and task-quality review approved.
- Task 3: complete — commit `6f8864ff4`; specification and task-quality review approved.
- Final hardening: commits `7235ea51a` and `b74e0e60e`; final whole-branch review approved with no Critical or Important findings.
- Migration-chain compatibility: commit `95b3c9270`; focused independent review approved.
- Fresh verification: report source/service/migration regressions 48 passed; report API 18 passed; regenerate API 5 passed; exports 4 passed; lifecycle API 11 passed; complete migration directory 54 passed; `ruff check app tests` passed; Alembic head is `20260904_17`; `git diff --check` passed.

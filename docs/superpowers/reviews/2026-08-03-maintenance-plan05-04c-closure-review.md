# Plan 05-4C Authoritative Demand Review Closure Review

## Decision

APPROVED FOR CLOSURE

No Critical or Important blocking findings remain in the approved Plan 05-4C scope. The previously identified M-1 remains a deferred, non-blocking Minor and is carried forward explicitly below.

## Reviewed Range

- Repository: `deifeb/maintenance-support-weknora`
- Branch: `codex/maintenance-plan05-4c-task8`
- Implementation base / current HEAD: `5847319a3e8be11fe477c1ff8d844f0210484727`
- Alembic head verified by the final Gate: `20260803_12 (head)`
- Final Task 8 code/test working scope before this documentation:
  - `extensions/maintenance-api/app/services/demand_review_service.py`
  - `extensions/maintenance-api/tests/integration/test_authoritative_review_workflow.py`
  - `frontend/src/views/maintenance/__tests__/master-data-navigation.test.ts`
- Closure document added after the frozen GREEN evidence:
  - `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04c-closure-review.md`
- Staged area at the frozen final Gate: empty
- Commit, push, PR, merge, and Plan 05-4D: not started

The final full integration Gate was executed on one frozen three-file code/test scope. The Closure Review is documentation added only after that Gate; it is not counted as implementation code that was exercised by the frozen GREEN run.

## Approved Scope

Plan 05-4C establishes the authoritative demand-review domain for the current published demand list:

- server-authoritative review runs from `PUBLISHED AND is_current=true` demand-list identity and version;
- immutable review source snapshots, deterministic findings, input hashes, and append-only audit evidence;
- independent formal review records that do not reuse `AIReviewRun` or AI findings as authoritative state;
- contributor/admin decision authority, including governed acceptance and `EDIT_ACCEPTED` quantity changes;
- blocking-finding state transition to `READY_TO_DERIVE`;
- atomic derivation of a new same-lineage DRAFT while preserving the published source;
- idempotency keys, request hashes, actor identity, roles, and request IDs on commands and decisions;
- formal Review List / hidden Review Detail frontend workflow and permission gates;
- migration lineage through `20260803_12`.

Plan 05-4C does not implement allocation plans, assurance rules, Plan 05-4D behavior, or a new inventory write authority.

## Requirement-by-Requirement Findings

| Requirement | Finding |
|---|---|
| Published/current source gate | APPROVED. Task 8 runs from the server-side current published DemandList identity/version and the integration contract verifies `PUBLISHED` and `is_current=true` in the authoritative snapshot. |
| Formal vs AI authority | APPROVED. Formal review state remains separate from `AIReviewRun` / `AIReviewFinding`; the Task 8 integration contract verifies those AI table counts are unchanged. |
| Snapshot and deterministic authority | APPROVED after the Task 8 wiring fix. The authoritative source snapshot and input hash are persisted before finding append/locking can refresh the review row. |
| Finding decisions and RBAC | APPROVED. Contributor ordinary rejection, admin governed acceptance, admin `EDIT_ACCEPTED`, role/request evidence, and formal frontend permission gates are covered by focused and full-suite evidence. |
| Batch atomicity / concurrency | APPROVED by the frozen focused Gate, including decision, replay, and competing-session coverage. |
| Source immutability | APPROVED. The integration contract reloads the source after derive and compares a business-semantic immutable projection of source and item authority fields. |
| Derivation semantics | APPROVED. Derive creates a DRAFT in the same lineage, records `derived_from_id`, advances the lineage version, preserves rejected quantity, and applies edited accepted quantity. |
| Derivation rollback / conflict protection | APPROVED by the focused derivation and concurrency suites included in the final Gate. |
| Idempotency and audit envelope | APPROVED. Command events carry the expected idempotency keys and 64-character request hashes; actor user, roles, and request IDs are verified. Decision records also preserve request hashes and actor evidence. |
| Frontend routing/menu contract | APPROVED. Review Detail remains authenticated, initialized, and hidden from the Maintenance menu; the stale navigation regression whitelist was synchronized without changing router or menu production code. |
| Full backend / frontend Gate | APPROVED. Backend focused/security/full, Ruff, Alembic, frontend focused/full/type-check/build, and `git diff --check` all pass on the same final three-file scope. |
| Scope discipline | APPROVED. Production behavior changed only by the targeted review snapshot/hash flush; the remaining Task 8 stabilizations are test-only. |
| M-1 composite database invariant | DEFERRED MINOR. Database foreign keys still do not enforce finding-to-review membership with one composite invariant. Repository/service validation remains authoritative; Task 8 intentionally does not broaden schema scope to address it. |

## Authoritative Integration Contract Evidence

`extensions/maintenance-api/tests/integration/test_authoritative_review_workflow.py` provides the Task 8 end-to-end contract.

The workflow exercised by the frozen test is:

1. create a current `PUBLISHED` source demand list with two items and authoritative risk-evidence snapshots;
2. run a formal review as a contributor;
3. verify the stored review points to the source ID/version and contains the published/current source snapshot;
4. produce two HIGH blocking `INVENTORY_GAP` findings with no current inventory;
5. let the contributor reject one ordinary inventory-gap finding;
6. let an admin `EDIT_ACCEPTED` the second inventory-gap finding to `7.500000`;
7. let the admin accept a governed finding that requires admin acceptance;
8. resolve the remaining blocking findings and reach `READY_TO_DERIVE` with zero pending blockers;
9. derive a new DRAFT as admin;
10. verify the new list has `derived_from_id=source.id`, the same lineage, and `version_number = source.version_number + 1`;
11. verify the rejected item's quantity remains unchanged and the edited item's quantity becomes `7.500000`;
12. expire/reload ORM state and verify the published source remains business-semantically unchanged;
13. verify command-event idempotency keys, request hashes, actor users, roles, and request IDs;
14. verify decision request hashes and actor evidence;
15. verify `AIReviewRun` and `AIReviewFinding` counts are unchanged.

Fresh final rerun result:

- `1 passed, 1 warning in 6.97s`

This contract is the final Task 8 integration evidence; its SHA256 at the frozen Gate is:

```text
0372695bafe4f9a39d9a933919e90b30a84680c235f68c3d39af291e20e702ef
```

## Production Wiring Defect Found and Fixed

Task 8 RED exposed a real production defect in `DemandReviewService.run()`.

### Observed failure

The runner generated legitimate formal findings and advanced the review to `OPEN`, but the read model returned:

```text
input_hash = 0000000000000000000000000000000000000000000000000000000000000000
source_snapshot = {}
```

The integration test failed when reading the expected published source snapshot.

### Root cause

The maintenance API session is configured with `autoflush=False`.

`DemandReviewService.run()` initially persists placeholder review values, then computes the authoritative snapshot and assigns:

```python
review.rule_set_version = snapshot.rule_set_version
review.input_hash = snapshot.input_hash
review.source_snapshot_json = snapshot.model_dump(mode="json")
```

Before those assignments were flushed, finding persistence called repository locking/read logic using `populate_existing=True`. With autoflush disabled, that refresh could reload the placeholder database values into the existing ORM review instance and overwrite the unflushed authoritative hash/snapshot.

Finding rows and later review counts/status could still persist, which explains the mixed state observed by the RED probe.

### Minimal production fix

The approved fix is exactly one production line after authoritative snapshot/hash assignment and before the first finding append:

```python
session.flush()
```

No global Session `autoflush` setting changed. Repository locking and `populate_existing` behavior were not weakened or removed. No unrelated production refactor was introduced.

Frozen production file SHA256:

```text
de99f3b851f5c400feace25ab9ec41dbc8b07fe93e0414d9e8e6cbb5cce083fc
```

Frozen production diff:

```text
1 addition, 0 deletions
+                    session.flush()
```

## Test-Only Stabilization During Task 8

### 1. Authoritative derivation risk-evidence fixture

After the production snapshot/hash fix, the integration probe advanced into derive and correctly failed with `DEMAND_LIST_SOURCE_INVALID` / `risk_snapshot_incomplete`.

The Task 8 source fixture had created a published DemandList without the decision/interval risk snapshots required by the existing derivation contract. The fixture was completed with consistent:

- `decision_snapshot_json.source_child_id`;
- `interval_snapshot_json.system_source_child_id`;
- `interval_snapshot_json.selected_child_id`;
- candidate evidence and recommended quantities.

No production risk-evidence validation was relaxed.

### 2. Source-immutability comparison helper

After the fixture was corrected, derive succeeded but the source-immutability assertion detected an aware-vs-naive datetime representation difference after SQLite ORM reload.

The assertion itself was retained. The helper was changed from a full ORM-column deepcopy to the same business-semantic projection used by existing derivation tests. It compares:

- source `status`, `is_current`, `version`, `version_number`, `superseded_by_id`, and `superseded_at`;
- item `final_quantity`, decision metadata, decision/interval/parameter/warning/inventory snapshots, and item version.

`created_at` / `updated_at` representation fields are intentionally excluded from that projection. This removes a SQLite datetime round-trip false failure without weakening the source-immutability business invariant.

## Task 7 Navigation Regression Contract Stabilization

The first full frontend rerun found one stale regression-test expectation:

```text
526 tests
525 passed
1 failed
```

`maintenanceReviewDetail` was correctly present in the router with `hideInMaintenanceMenu=true`, and the dedicated Task 7 review-navigation tests already required that hidden authenticated route contract. The older `master-data-navigation.test.ts` maintained a hand-written hidden-route whitelist that had not been updated when Task 7 introduced Review Detail.

The stabilization changed only that test whitelist:

```text
1 addition, 0 deletions
+      'maintenanceReviewDetail',
```

No router, menu, permission, or other frontend production file changed.

Frozen navigation test SHA256:

```text
4c3016c97951bd5e9747c5a3f1eb2279c813494cd853331fd869c73d7d8eceeb
```

## Full Gate Results

The final full integration GREEN rerun was executed after all three code/test files were frozen.

Fresh local toolchain:

- Python: `3.11.9`
- npm: `11.10.0`

Final Gate evidence:

- Task 8 authoritative integration probe: `1 passed, 1 warning in 6.97s`
- Expanded Plan 05-4C backend focused regression: `356 passed, 1 warning in 90.85s`
- Backend security suite: `122 passed, 1 warning in 16.73s`
- Ruff: `All checks passed!`
- Alembic: exactly one head, `20260803_12 (head)`
- Maintenance API full pytest: `1406 passed, 8 deselected, 2 warnings in 436.12s`
- Frontend Plan 05-4C focused tests: `54 passed, 0 failed`
- Frontend full test: `526 passed, 0 failed`
- Frontend type-check: PASS
- Frontend production build: PASS (`built in 51.23s`)
- `git diff --check`: PASS
- Final HEAD movement: none
- Final staged area: empty
- Final code/test scope: exactly three files
- Temporary frontend build output: removed
- Temporary `node_modules` junction: removed

Final three-file SHA256 set:

```text
extensions/maintenance-api/app/services/demand_review_service.py
de99f3b851f5c400feace25ab9ec41dbc8b07fe93e0414d9e8e6cbb5cce083fc

extensions/maintenance-api/tests/integration/test_authoritative_review_workflow.py
0372695bafe4f9a39d9a933919e90b30a84680c235f68c3d39af291e20e702ef

frontend/src/views/maintenance/__tests__/master-data-navigation.test.ts
4c3016c97951bd5e9747c5a3f1eb2279c813494cd853331fd869c73d7d8eceeb
```

## Non-Blocking Warnings

The final Gate is not warning-free. The following warnings remain non-blocking:

1. Starlette deprecation warning for the current `httpx` / `starlette.testclient` integration.
2. `InsecureKeyLengthWarning` in the deliberate wrong-algorithm JWT integration case because its SHA384 HMAC test key is shorter than the RFC recommendation.
3. Vite build warning that some minified chunks exceed 500 kB and may benefit from code splitting or manual chunking.

None of these warnings produced a failing Gate. They are not represented here as fixed or absent.

## Deferred Minor M-1

M-1 remains deferred and unchanged.

The database schema does not enforce, through one composite foreign-key/unique invariant, that a finding identity necessarily belongs to the same review identity supplied alongside it. Repository and service validation remain the authoritative enforcement layer for that relationship.

Task 8 deliberately did not:

- add a new composite schema constraint solely to close M-1;
- alter global transaction/session behavior;
- weaken repository locking;
- broaden the implementation into schema remediation outside the approved Task 8 wiring scope.

The security, repository, decision, derivation, replay, and concurrency Gates are green, but they do not convert this structural schema observation into a closed finding. M-1 should remain visible for a separately planned schema-hardening decision.

## Scope Exclusions

This Closure Review does not approve or start:

- Plan 05-4D allocation / assurance implementation;
- reservation or inventory-write behavior beyond the already merged 05-4B capabilities;
- reuse of AI review records as formal review authority;
- global SQLAlchemy Session autoflush changes;
- repository lock / `populate_existing` removal;
- unrelated frontend router/menu changes;
- dependency installation or toolchain changes;
- commit, push, PR creation, merge, branch deletion, or worktree cleanup.

## Closure Recommendation

Approve Plan 05-4C Task 8 and close Plan 05-4C at Alembic head `20260803_12`, subject to the separately gated review and commit steps.

The implementation/integration Gate is frozen PASS on the three-file code/test scope described above. This Closure Review is the fourth candidate file and must be reviewed without modifying the frozen implementation evidence.

The plan's proposed commit subject remains:

```text
test(maintenance): close plan05-4c demand review
```

Staging, commit, push, PR creation, merge, and Plan 05-4D remain separate approval boundaries.

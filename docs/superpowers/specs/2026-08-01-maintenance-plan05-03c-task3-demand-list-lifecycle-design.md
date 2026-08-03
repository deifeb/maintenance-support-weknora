# Plan 05-3C Task 3 Demand List Lifecycle Design

**Date:** 2026-08-01  
**Status:** Approved design  
**Branch:** `feature/maintenance-frontend-plan05`  
**Baseline:** `f6df18fee1a4c3ef9ff9f261498cfe702fc3de12` (`feat: generate demand list drafts`)

## 1. Purpose

Task 3 adds the demand-list lifecycle on top of the versioned persistence and DRAFT-generation work delivered by Tasks 1 and 2.

The service must enforce the exact lifecycle:

```text
DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED
```

It must also support deriving a new DRAFT from a PUBLISHED version while preserving the original version and lineage history.

The implementation is service-focused. It establishes the domain contract consumed later by the API, frontend, inventory, allocation, audit, and reporting modules without implementing those downstream integrations in this task.

## 2. Approved Scope

Only these files may change:

```text
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
```

Task 3 produces these service methods:

```python
submit(...)
confirm(...)
publish(...)
derive(...)
void(...)
```

Task 3 does not change:

```text
extensions/maintenance-api/app/models/demand_list.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/repositories/demand_list_repository.py
extensions/maintenance-api/alembic/**
extensions/maintenance-api/app/api/**
frontend/**
```

It also does not implement inventory reservation, procurement, allocation, review engines, notification delivery, report generation, or an outbox.

The known equal-`created_at` cross-page ordering issue remains a repository-layer follow-up and is outside this task.

## 3. Design Choice

The approved approach is a shared command shell with action-specific business logic.

Shared lifecycle infrastructure handles:

- role checks;
- idempotency-key normalization;
- canonical request hashing;
- sequential replay;
- optimistic-version validation;
- status validation;
- append-only event creation;
- response-snapshot storage;
- concurrent unique-conflict recovery;
- commit and rollback.

Action-specific methods retain their own rules:

- `submit`: validate list contents and record risk counts;
- `confirm`: confirm all high-risk items and require a note;
- `publish`: lock the lineage and supersede the previous current version;
- `derive`: copy the published aggregate into a new DRAFT version;
- `void`: preserve history while removing current-publication eligibility.

A single universal transition function is intentionally avoided because publication and derivation have materially different data and locking behavior.

## 4. Schema Contract

Add two request models.

```python
class DemandListTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class DemandListConfirmRequest(DemandListTransitionRequest):
    confirmation_note: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator("confirmation_note", mode="before")
    @classmethod
    def strip_confirmation_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value
```

The confirmation note is trimmed before validation and hashing. Whitespace-only and overlong values are rejected.

No API-specific header or envelope schema is added in this task.

## 5. Roles and Transition Matrix

| Action | Required source | Result | Minimum role |
|---|---|---|---|
| `submit` | `DRAFT` | same row becomes `PENDING_CONFIRMATION` | Contributor |
| `confirm` | `PENDING_CONFIRMATION` | same row becomes `CONFIRMED` | Admin |
| `publish` | `CONFIRMED` | same row becomes current `PUBLISHED` | Admin |
| `derive` | `PUBLISHED` | new row in same lineage becomes `DRAFT` | Admin |
| `void` | `PUBLISHED` | same row becomes `VOIDED` | Admin |

Viewer cannot perform lifecycle mutations.

Contributor can submit but cannot confirm, publish, derive, or void.

Admin can perform all lifecycle actions.

Service-layer checks are mandatory even when the future API layer also enforces RBAC.

Any unsupported source/action pair returns `DEMAND_LIST_INVALID_TRANSITION`.

Example details:

```json
{
  "action": "publish",
  "expected_status": "CONFIRMED",
  "actual_status": "DRAFT",
  "conflict_object": "demand_list",
  "retryable": false
}
```

## 6. Shared Lifecycle Command Shell

The existing create idempotency implementation remains valid. Task 3 generalizes its internals without changing create behavior.

Recommended internal primitives:

```text
_require_admin
_normalize_idempotency_key
_lifecycle_request_hash
_require_version
_require_status
_idempotent_read_model
_append_lifecycle_event
_store_response_snapshot
_recover_lifecycle_receipt
```

The generalized replay helper accepts the expected event type.

It must verify:

1. the receipt event type matches the invoked action;
2. the request hash matches;
3. the response snapshot exists;
4. the response snapshot validates as `DemandListRead`;
5. the returned model is deeply copied.

Receipt mismatch behavior:

- wrong hash: `IDEMPOTENCY_KEY_REUSED`;
- wrong event type: `IDEMPOTENT_RESPONSE_UNAVAILABLE`;
- missing or malformed response: `IDEMPOTENT_RESPONSE_UNAVAILABLE`.

The existing `create_from_group()` contract continues to allow only `CREATED` receipts.

## 7. Canonical Request Hashes

Each action hashes a normalized payload.

```text
submit:
{
  action,
  demand_list_id,
  expected_version
}

confirm:
{
  action,
  demand_list_id,
  expected_version,
  confirmation_note
}

publish:
{
  action,
  demand_list_id,
  expected_version
}

derive:
{
  action,
  demand_list_id,
  expected_version
}

void:
{
  action,
  demand_list_id,
  expected_version
}
```

The hash excludes:

```text
tenant_id
actor user ID
actor role
request ID
Idempotency-Key
timestamps
```

Tenant isolation is enforced by tenant-scoped receipt lookup. Request IDs and actors are audit metadata, not business-payload identity.

Hashing continues to use `snapshot_service.canonical_hash()`.

## 8. Submit Semantics

`submit()` executes in this order:

1. require Contributor or Admin;
2. normalize and validate the idempotency key;
3. calculate the request hash;
4. replay an existing valid `SUBMITTED` receipt;
5. lock the tenant-scoped demand list;
6. require the expected version;
7. require status `DRAFT`;
8. load all tenant-scoped items;
9. reject an empty list;
10. count total, high-risk, admin-confirmation-required, and unconfirmed items;
11. set submission actor, request, and time;
12. set status `PENDING_CONFIRMATION`;
13. increment the aggregate version once;
14. append `SUBMITTED`;
15. store the complete typed response snapshot;
16. commit once.

An empty list returns `DEMAND_LIST_EMPTY`.

The event after-summary includes:

```text
lineage_id
version_number
status
is_current
item_count
high_risk_item_count
requires_admin_confirmation_count
unconfirmed_item_count
version
```

## 9. Confirm Semantics

`confirm()` requires Admin and a nonblank confirmation note.

It:

1. replays a valid `CONFIRMED` receipt if present;
2. locks the list;
3. validates the expected version;
4. requires `PENDING_CONFIRMATION`;
5. loads all items;
6. sets `confirmed_by_admin=True` on every item where `requires_admin_confirmation=True`;
7. increments only those item versions that change;
8. sets confirmation actor, request, and time on the aggregate;
9. changes status to `CONFIRMED`;
10. increments the aggregate version once;
11. appends `CONFIRMED`;
12. stores the response snapshot and commits once.

Low-risk items are not modified merely because confirmation occurs.

An admin confirmation is still required when no item needs admin confirmation, so the approval itself remains auditable.

The event records:

```text
confirmation_note
confirmed_item_ids
confirmed_item_count
lineage_id
version_number
status
version
```

`confirmed_item_ids` are sorted.

## 10. Publish Semantics

`publish()` requires Admin.

It:

1. replays a valid `PUBLISHED` receipt if present;
2. locks the target demand list;
3. validates the expected version;
4. requires `CONFIRMED`;
5. loads and revalidates items;
6. rejects an empty list;
7. rejects any item where `requires_admin_confirmation=True` and `confirmed_by_admin=False`;
8. locks the current published row for the same tenant and lineage;
9. if another current version exists, marks it non-current and records supersession;
10. marks the target row `PUBLISHED` and current;
11. records publication actor, request, and time;
12. increments the target version once;
13. increments the superseded aggregate version once when another row changes;
14. appends `PUBLISHED`;
15. stores the complete response snapshot;
16. commits once.

Unconfirmed items return `DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED` with sorted item IDs.

The old published row remains `PUBLISHED` but receives:

```text
is_current = False
superseded_by_id = new_published_id
superseded_at = now
version += 1
```

The new row receives:

```text
status = PUBLISHED
is_current = True
published_by_user_id
published_by_request_id
published_at
version += 1
```

The database partial unique index remains the final invariant for one current published version per tenant and lineage.

## 11. Derive Semantics

`derive()` requires Admin and accepts only `PUBLISHED`.

It creates a new row using `repository.create_version()` with:

```text
same lineage_id
derived_from_id = source.id
same scenario_version_id
same calculation_group_id
same name
same description
status = DRAFT
is_current = False
new creator actor/request
```

All source items are copied.

Copied item fields include all identity, source, decision, risk, quantity, and versioned snapshot values needed by the current model.

Every JSON field is deep-copied:

```text
source_snapshot_json
decision_snapshot_json
interval_snapshot_json
parameter_snapshot_json
warning_snapshot_json
inventory_snapshot_json
```

The new aggregate and new items start at version 1.

The source published row remains unchanged and current until a later publication supersedes it.

`DERIVED` is appended to the new DRAFT and records:

```text
derived_from_id
lineage_id
source_version_number
new_version_number
copied_item_count
status
version
```

The idempotent response is the new DRAFT aggregate.

## 12. Void Semantics

`void()` requires Admin and accepts only `PUBLISHED`.

It:

- changes status to `VOIDED`;
- clears `is_current` when necessary;
- records void actor, request, and time;
- increments the aggregate version once;
- appends `VOIDED`;
- preserves all items and historical events;
- commits once.

Voiding never restores an older superseded version as current.

A lineage may therefore temporarily have no current published version.

## 13. Published Immutability

`update_item()` remains allowed only for `DRAFT`.

When status is `PUBLISHED`, it returns:

```text
PUBLISHED_DEMAND_LIST_IMMUTABLE
```

Other non-DRAFT states continue to return:

```text
DEMAND_LIST_NOT_EDITABLE
```

No lifecycle action mutates immutable source snapshots except `derive()`, which copies them into a new aggregate.

## 14. Transaction and Concurrency Model

All lifecycle mutations use one database transaction and one commit.

The common order is:

```text
validate role and input
→ normalize key
→ compute request hash
→ tenant-scoped receipt lookup
→ replay if valid
→ acquire row locks
→ revalidate version and state
→ apply mutation
→ append event
→ materialize DemandListRead
→ store complete response snapshot
→ commit once
```

Any exception rolls back.

### 14.1 Optimistic version conflicts

When two commands start with the same expected version, the row lock serializes them. The second command must re-read the current row and return `DEMAND_LIST_VERSION_CONFLICT` when the version changed.

### 14.2 Same-key races

If concurrent first use of one idempotency key triggers an event unique constraint:

```text
IntegrityError
→ rollback
→ tenant-scoped receipt reread
→ matching event/hash: replay winner
→ different hash: IDEMPOTENCY_KEY_REUSED
→ no receipt: re-raise original IntegrityError
```

Rollback must occur before the receipt reread.

### 14.3 Publication races

Publishing locks both the target row and current published row for the lineage.

Concurrent valid publications may serialize as two legal successive publications. After each transaction, only one row may be current.

### 14.4 Derivation races

The existing repository calculates `max(version_number) + 1`.

Under the approved three-file boundary:

- the same idempotency key recovers the winning derived version;
- different keys may race on the lineage/version unique constraint;
- when no matching receipt exists, the original `IntegrityError` is re-raised.

Automatic retry with a new version number requires a repository or lineage-lock change and is a follow-up, not hidden inside Task 3.

## 15. Error Contract

| Condition | Code |
|---|---|
| missing idempotency key | `IDEMPOTENCY_KEY_REQUIRED` |
| invalid idempotency key | `INVALID_IDEMPOTENCY_KEY` |
| same key, different request | `IDEMPOTENCY_KEY_REUSED` |
| invalid receipt type or response | `IDEMPOTENT_RESPONSE_UNAVAILABLE` |
| missing or cross-tenant aggregate | `RESOURCE_NOT_FOUND` |
| invalid expected version | `DEMAND_LIST_VERSION_INVALID` |
| stale expected version | `DEMAND_LIST_VERSION_CONFLICT` |
| invalid status/action | `DEMAND_LIST_INVALID_TRANSITION` |
| no items | `DEMAND_LIST_EMPTY` |
| unconfirmed required items | `DEMAND_LIST_ADMIN_CONFIRMATION_REQUIRED` |
| blank confirmation note | `DEMAND_LIST_CONFIRMATION_NOTE_REQUIRED` |
| invalid confirmation note | `DEMAND_LIST_CONFIRMATION_NOTE_INVALID` |
| published item update | `PUBLISHED_DEMAND_LIST_IMMUTABLE` |
| other non-DRAFT item update | `DEMAND_LIST_NOT_EDITABLE` |
| insufficient role | `INSUFFICIENT_MAINTENANCE_ROLE` |

List-valued error details are sorted for deterministic tests and clients.

## 16. Cross-Module Domain Contract

The lifecycle is part of a larger vertical slice and must remain linked to upstream and downstream modules.

### 16.1 Upstream calculation lineage

The provenance chain remains:

```text
DemandScenarioVersion
→ CalculationGroup
→ CalculationGroupChild / Calculation / Run / Result
→ CalculationItemDecision
→ DemandList / DemandListItem
```

Task 3 never recomputes demand or reloads mutable upstream results to redefine an existing aggregate.

Submission, confirmation, publication, derivation, and voiding operate on the immutable snapshots created in Task 2.

A derived version copies the published snapshots rather than regenerating from the calculation group.

### 16.2 Identity, tenant, and RBAC

`ActorContext` is the only source of:

```text
tenant_id
user_id
role
request_id
```

The service passes `actor.tenant_id` into every repository operation.

Request bodies, paths, and headers may not select a tenant.

Future API RBAC is an additional boundary, not a substitute for service checks.

### 16.3 Audit

`DemandListEvent` is the stable audit contract.

Lifecycle consumers should read events rather than infer actions from timestamps.

Every event retains:

```text
event type
actor
roles
request ID
idempotency key
request hash
before summary
after summary
response snapshot
occurred time
```

Summaries expose stable identifiers and lifecycle meaning needed by audit, timeline, and reporting code.

### 16.4 API

Task 4 will map the service methods directly:

```text
POST /demand-lists/{id}/submit
POST /demand-lists/{id}/confirm
POST /demand-lists/{id}/publish
POST /demand-lists/{id}/derive
POST /demand-lists/{id}/void
```

Every route passes `expected_version` and `Idempotency-Key`; confirmation also passes `confirmation_note`.

The API does not reconstruct business state.

### 16.5 Frontend

Future frontend actions are derived only from server status and explicit permissions:

```text
DRAFT                → edit, submit
PENDING_CONFIRMATION → confirm
CONFIRMED            → publish
PUBLISHED            → derive, void
VOIDED               → no write action
```

On version, transition, or idempotency conflict, the client reloads the aggregate.

### 16.6 Inventory, allocation, procurement, and reports

Eligibility contract:

| State | Current operational demand basis | Reporting meaning |
|---|---:|---|
| `DRAFT` | No | Draft only |
| `PENDING_CONFIRMATION` | No | Pending approval |
| `CONFIRMED` | No | Approved but not effective |
| `PUBLISHED && is_current` | Yes | Current official version |
| `PUBLISHED && !is_current` | Historical only | Historical report |
| `VOIDED` | No | Audit history only |

Task 3 does not invoke external modules in the transaction.

Future asynchronous integration requires an explicit outbox design. `DemandListEvent` is an audit record and local domain history; it is not claimed to be an at-least-once message transport.

## 17. Test Strategy

Every new behavior starts RED.

### 17.1 Schema tests

- required models are exported;
- expected version must be at least 1;
- confirmation note is trimmed;
- blank note is rejected;
- overlong note is rejected;
- extra fields are rejected.

### 17.2 Transition and role tests

- Contributor can submit;
- Viewer cannot submit;
- Contributor cannot perform admin actions;
- Admin can perform every action;
- all invalid source/action pairs return the stable transition error;
- cross-tenant access returns NotFound;
- version conflicts contain exact deterministic details.

### 17.3 Submit and confirm tests

- empty list cannot submit;
- submission metadata and risk counts are correct;
- aggregate version increments once;
- confirmation requires a note;
- all required items are confirmed in one command;
- low-risk items are not changed;
- only changed item versions increment;
- confirmed IDs are sorted;
- failures roll back aggregate, item, and event changes.

### 17.4 Publish tests

- unconfirmed required items cannot publish;
- publication metadata is correct;
- target becomes current;
- published items are immutable;
- a newer publication atomically supersedes the old current version;
- old row remains published and historical;
- only one current version exists;
- publication failure rolls back both rows and the event.

### 17.5 Derive tests

- only published rows can derive;
- lineage and source linkage are correct;
- version number advances;
- new aggregate is DRAFT and non-current;
- source remains current;
- all scalar item fields are copied;
- nested JSON is deeply isolated;
- aggregate and item versions restart at 1;
- event and replay response are correct.

### 17.6 Void tests

- only published rows can void;
- current is cleared;
- non-current published history can be voided;
- nothing is deleted;
- older superseded versions are not restored;
- metadata and event are correct.

### 17.7 Idempotency and race tests

For every lifecycle action:

- same key and hash replays exactly;
- same key and different hash conflicts;
- wrong receipt event type is unavailable;
- missing response is unavailable;
- malformed response is unavailable;
- replay nested JSON is isolated;
- same-hash unique conflict replays the winner;
- different-hash unique conflict is controlled;
- rollback precedes receipt reread;
- no winning receipt re-raises the original integrity error.

### 17.8 Complete service lifecycle

One service-level test covers:

```text
create DRAFT
→ update a high-risk item
→ submit
→ confirm
→ publish v1
→ derive v2 DRAFT
→ submit v2
→ confirm v2
→ publish v2
→ void v2
```

It verifies:

- exact status sequence;
- exact event sequence;
- actor and request metadata;
- aggregate and item versions;
- high-risk confirmation;
- snapshot isolation;
- lineage version numbers;
- supersession;
- one-current invariant;
- no current version after void;
- tenant scope throughout.

## 18. Verification Gates

Focused gate:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  -v
```

Approved-domain gate:

```powershell
& .\.venv\Scripts\python.exe -m pytest `
  tests/services/test_demand_list_service.py `
  tests/services/test_demand_decision_policy.py `
  tests/services/test_calculation_group_service.py `
  tests/repositories/test_demand_list_repository.py `
  tests/repositories/test_demand_domain_tenant_scope.py `
  tests/migrations/test_demand_list_migration.py `
  tests/security/test_api_rbac.py `
  -v
```

Final gate:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe -m compileall -q app tests
& .\.venv\Scripts\python.exe -m ruff check app tests
git -c core.safecrlf=false diff --check
```

## 19. Commit Boundary

The planned implementation commit is:

```text
feat: enforce demand list lifecycle
```

It contains only:

```text
extensions/maintenance-api/app/services/demand_list_service.py
extensions/maintenance-api/app/schemas/demand_list.py
extensions/maintenance-api/tests/services/test_demand_list_service.py
```

The design document itself is committed separately before implementation.

## 20. Explicit Follow-Ups

These are not Task 3 implementation work:

1. repository SQL tie-break for equal `created_at` pagination;
2. distinct-key concurrent derive retry or lineage advisory locking;
3. lifecycle API routes and route-level RBAC;
4. typed frontend client, store, actions, and detail view;
5. inventory, allocation, procurement, and report consumers;
6. reliable external event delivery through an outbox.

They must not be silently added to the Task 3 feature commit.

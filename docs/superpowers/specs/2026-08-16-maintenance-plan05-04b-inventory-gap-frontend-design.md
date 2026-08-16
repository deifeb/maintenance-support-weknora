# Plan 05-4B Frontend Inventory Gap Design

**Document status:** APPROVED — architecture previously approved; this consistency-revised artifact requires explicit SHA re-approval before docs commit
**Design date:** 2026-08-16
**Target branch:** `codex/maintenance-plan05-4b`
**Frozen backend head:** `952d7ceb13f214a079bb1871191ef27cfcc8db22`
**Target integration base:** `feature/maintenance-frontend-plan05`
**Intended repository path:** `docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-gap-frontend-design.md`

---

## 1. Purpose

This design activates the existing Maintenance **Inventory Gap** frontend placeholder as the operational frontend for the already-verified Plan 05-4B inventory backend.

The frontend must make the completed inventory contracts usable without weakening the backend authority model:

- inventory balances remain authoritative server state;
- all quantity mutations remain backend commands;
- FEFO remains server-side authoritative behavior;
- reservations, transfers, stocktakes, and high-risk operations continue to use backend state machines;
- `Idempotency-Key`, optimistic versions, confirmation tokens, tenant isolation, RBAC, and stable backend error contracts remain authoritative;
- Task 10.5 list filtering, counting, sorting, and pagination remain server-side;
- the frontend must not reconstruct private preview state or invent data the backend does not expose.

This design covers the frontend work that was originally planned as Plan 05-4B Tasks 11–13, updated to match the **actual backend contract at `952d7ceb...`**, including the pushed Inventory Lot Concurrency Read Contract Amendment, rather than assumptions from the older implementation plan.

This document does **not** authorize implementation.

---

## 2. Verified current frontend facts

### 2.1 Inventory Gap is already routed and already appears in the Maintenance menu

The route already exists at:

`/platform/maintenance/inventory-gap`

with route name:

`maintenanceInventoryGap`

and points to:

`frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`

The Maintenance menu already contains the Inventory Gap entry. The design therefore does not add a second top-level Inventory navigation item.

### 2.2 The current Inventory Gap page is only a placeholder

`InventoryGapPage.vue` currently renders only a title and generic placeholder text. It has no inventory API, store, list, detail, command, or workflow behavior.

### 2.3 No inventory frontend API or store exists

There is currently no:

- `frontend/src/api/maintenance/inventory.ts`
- `frontend/src/stores/maintenance/inventory.ts`
- `frontend/src/components/maintenance/inventory/`

The existing Maintenance frontend already provides patterns that should be reused:

- `api/maintenance/client.ts`
- `buildQuery(...)`
- `MaintenanceResult<T>`
- `PageData<T>`
- normalized `MaintenanceClientError`
- Pinia composition stores
- request-generation protection against stale responses
- common Maintenance page/error/empty/status components.

### 2.4 The permission matrix already contains inventory capabilities

Existing permissions already include:

- `reserveInventory`
- `issueReturnInventory`
- `transferInventory`
- `adjustInventory`
- `confirmHighRisk`

The frontend should extend this matrix only where the current backend exposes a materially distinct user capability. It must not create a parallel role system.

### 2.5 Existing hidden Maintenance routes use `hideInMaintenanceMenu`

The current router convention for detail pages is:

```ts
meta: {
  ...maintenanceRouteMeta,
  hideInMaintenanceMenu: true,
}
```

The older Plan 05-4B text referred to `meta.hidden=true`. That is no longer the repository convention and must not be introduced.

---

## 3. Frozen backend contract

The frontend is designed against the current backend at:

`952d7ceb13f214a079bb1871191ef27cfcc8db22`

The backend has already passed local and real PostgreSQL gates. This frontend phase treats it as frozen unless implementation uncovers a genuine blocker that cannot be solved without changing the public contract. If such a blocker is found, frontend implementation must stop and return to a separate backend DESIGN gate.

The frozen public contract includes the approved Inventory Lot Concurrency Read Contract Amendment:

- design: `docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment-design.md`;
- implementation plan: `docs/superpowers/plans/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment.md`;
- documentation commit: `b3d58c7dbe604ae09dd14fb56dc5c89415aee136`;
- feature/backend baseline commit: `952d7ceb13f214a079bb1871191ef27cfcc8db22`.

That amendment is additive read state only. It does not reopen FEFO, write semantics, migrations, parent list filtering/counting/sorting/pagination, or introduce a lot-detail endpoint.

### 3.1 Query/read surface

All list endpoints return the existing success envelope containing `PageData`.

#### Balances

`GET /api/maintenance/v1/inventory/balances`

Filters:

- `warehouse_id`
- `spare_part_id`
- `location_id`
- `lot_id`
- `serial_item_id`

Sort fields:

- `id`
- `warehouse_id`
- `spare_part_id`
- `location_id`
- `lot_id`
- `on_hand_quantity`
- `reserved_quantity`
- `available_quantity`

Detail:

`GET /api/maintenance/v1/inventory/balances/{id}`

#### Transactions

`GET /api/maintenance/v1/inventory/transactions`

Filters:

- `operation_type`
- `status`
- `reference_type`
- `reference_id`

Sort fields:

- `id`
- `operation_type`
- `status`
- `completed_at`

Transaction list statuses:

- `PREVIEWED`
- `COMPLETED`
- `PARTIALLY_COMPLETED`
- `FAILED`
- `EXPIRED`
- `REVERSED`

Detail:

`GET /api/maintenance/v1/inventory/transactions/{id}`

#### Reservations

`GET /api/maintenance/v1/inventory/reservations`

Filters:

- `status`
- `owner_type`
- `owner_id`

Sort fields:

- `id`
- `status`
- `expires_at`

Reservation statuses:

- `ACTIVE`
- `PARTIALLY_ISSUED`
- `FULFILLED`
- `RELEASED`
- `CANCELLED`
- `EXPIRED`

Detail:

`GET /api/maintenance/v1/inventory/reservations/{id}`

#### Transfers

`GET /api/maintenance/v1/inventory/transfers`

Filters:

- `status`
- `source_warehouse_id`
- `source_location_id`
- `target_warehouse_id`
- `target_location_id`
- `reference_type`
- `reference_id`

Sort fields:

- `id`
- `status`
- `dispatched_at`
- `completed_at`

Transfer statuses:

- `DRAFT`
- `DISPATCHED`
- `PARTIALLY_RECEIVED`
- `COMPLETED`
- `CANCELLED`

Detail:

`GET /api/maintenance/v1/inventory/transfers/{id}`

#### Stocktakes

`GET /api/maintenance/v1/inventory/stocktakes`

Filters:

- `status`
- `warehouse_id`
- `location_id`

Sort fields:

- `id`
- `status`
- `snapshot_at`
- `confirmed_at`

Stocktake statuses:

- `DRAFT`
- `COUNTING`
- `REVIEWING`
- `CONFIRMED`
- `CONFLICTED`
- `CANCELLED`

Detail:

`GET /api/maintenance/v1/inventory/stocktakes/{id}`

### 3.2 Common list semantics

Every frontend list must use the backend contract directly:

- `page >= 1`
- `page_size` between 1 and 100
- default `page=1`
- default `page_size=20`
- `sort_order` is exactly `asc | desc`
- backend default sort is `id ASC`
- filtering happens before count
- sorting happens before pagination
- backend applies stable ID tie-breaking
- backend applies NULLS LAST for nullable supported sort fields
- duplicate known scalar query parameters are invalid
- tenant cannot be supplied by frontend query/body.

The frontend must therefore **not fetch a page and then perform authoritative in-memory filter/sort on that page**.

### 3.3 Public balance fields

The public balance read model exposes:

- IDs for warehouse, location, spare part, lot, serial item;
- on-hand quantity;
- reserved quantity;
- damaged quantity;
- quarantined quantity;
- in-transit quantity;
- computed available quantity;
- balance `version`;
- nullable lot concurrency state:
  - `lot_version: int | null`;
  - `lot_is_frozen: bool | null`.

The lot-concurrency fields are **read-side concurrency/affordance evidence**, not new list dimensions. They do not add balance filters or sort keys.

Frontend semantics are frozen:

```text
lot_id == null
  -> lot_version == null
  -> lot_is_frozen == null
  -> Freeze/Unfreeze unavailable

lot_id != null AND (lot_version == null OR lot_is_frozen == null)
  -> fail closed
  -> Freeze/Unfreeze unavailable

lot_version is a positive integer AND lot_is_frozen == false
  -> Freeze only

lot_version is a positive integer AND lot_is_frozen == true
  -> Unfreeze only
```

The frontend must never guess/default `lot_version`, infer it from transaction/audit JSON, or turn nullable state into an executable default.

It does **not** expose:

- lot expiry date;
- inventory risk level;
- reorder risk;
- demand gap.

Those values must not appear as authoritative Inventory Gap table columns in this phase.

### 3.4 Reservation commands

Contributor-authorized commands are:

- create/reserve;
- issue;
- release;
- return;
- cancel.

Reservation creation supports:

- owner type/id;
- spare part;
- warehouse;
- requested quantity;
- `allow_partial`;
- expected balance versions;
- `as_of`;
- optional location/lot/serial constraints;
- optional expiration;
- optional FEFO override reason.

Reservation reads expose the resulting allocation lines, including:

- balance/lot/serial;
- requested/reserved/issued/released quantities;
- FEFO rank;
- FEFO override reason;
- line and aggregate versions.

### 3.5 High-risk operations

Admin-authorized high-risk operation flow is:

1. preview;
2. execute using the returned transaction/version/token.

Supported direct operation previews are:

- `ADJUST`
- `FREEZE`
- `UNFREEZE`

Reverse has its own preview/execute endpoints.

For `FREEZE` / `UNFREEZE`, preview is executable only when the currently loaded authoritative balance supplies all of:

- `balance_id`;
- positive `balance.version` as `expected_balance_version`;
- non-null `lot_id`;
- positive `lot_version` as `expected_lot_version`;
- non-null `lot_is_frozen`;
- reason.

`lot_is_frozen == false` permits `FREEZE` only. `lot_is_frozen == true` permits `UNFREEZE` only. Nullable lot concurrency state fails closed.

The public preview response exposes only:

- transaction ID;
- operation type;
- `PREVIEWED` status;
- transaction version;
- confirmation token;
- confirmation expiry.

It does **not** expose a public authoritative `before/after/warnings/risks` preview payload.

After successful FREEZE/UNFREEZE execute, the frontend must re-read authoritative balance detail and refresh the balance list before rendering the next lot-state action. It must not optimistic-toggle `lot_is_frozen` or locally increment either balance or lot version.

### 3.6 Transfers

Admin-authorized transfer lifecycle is:

1. create transfer;
2. dispatch preview;
3. dispatch execute;
4. receive preview;
5. receive execute;
6. cancel when backend state allows.

Partial receiving is supported through explicit receive lines/quantities.

### 3.7 Stocktakes

Contributor-authorized lifecycle:

- create;
- start;
- record line count;
- review;
- rebase conflicted lines;
- cancel.

Admin-authorized lifecycle:

- confirmation preview;
- confirmation execute.

Stocktake lines expose:

- system quantity;
- counted quantity;
- variance;
- snapshot balance version;
- line version;
- resolution;
- conflict details;
- confirmed transaction ID.

---

## 4. Design alternatives

### Approach A — Strict frozen-contract operational console — **recommended**

Build the complete Inventory frontend using only the current public backend contract.

Implications:

- five server-driven list views;
- full detail and mutation workflows;
- no frontend-authored inventory authority;
- no fake risk/expiry fields;
- no client FEFO algorithm;
- preview dialog shows public preview metadata and user command context, not private server internals;
- FEFO evidence is displayed after reservation allocation from returned reservation lines.

**Advantages**

- preserves the already-verified backend Gate;
- no new migration or API surface;
- keeps Plan 05-4B moving forward;
- lowest contract drift risk;
- testable against current OpenAPI/runtime behavior.

**Trade-off**

The UI cannot provide several richer concepts assumed by the older plan, because the current backend does not expose them.

### Approach B — Reopen backend first for richer frontend semantics

Before frontend implementation, add backend APIs/fields for:

- authoritative pre-reservation FEFO recommendations;
- lot expiry in balance rows;
- inventory risk/demand-gap values;
- richer public high-risk preview data.

**Advantages**

- richer operator experience;
- closer to the original Task 12 prose.

**Disadvantages**

- reopens a backend already closed through Task 10.5 and real PostgreSQL verification;
- requires a new backend design, plan, RED/GREEN, regression, PostgreSQL Gate, commit, push, and PR update;
- materially expands schedule and regression surface.

This is not recommended unless the missing UX becomes a hard business requirement.

### Approach C — Read-only or balance-only frontend

Activate only the balance table/details now and defer mutations/workflows.

**Advantages**

- minimal implementation risk.

**Disadvantages**

- fails the Plan 05-4B frontend goal;
- leaves reservations, transfers, stocktakes, and high-risk operations inaccessible through the intended frontend;
- creates another partial frontend stage without a strong technical reason.

This approach is rejected.

---

## 5. Recommended information architecture

The existing route remains:

`/platform/maintenance/inventory-gap`

The page becomes a single operational workspace with five domain tabs:

1. **Balances** — default;
2. **Reservations**;
3. **Transfers**;
4. **Stocktakes**;
5. **Transactions**.

The tabs share the Maintenance visual system but keep independent query state.

This avoids adding five new menu entries while making each backend list first-class.

### 5.1 Balances tab

Purpose: current authoritative inventory position and primary entry point for inventory actions.

Columns:

- warehouse ID;
- location ID;
- spare-part ID;
- lot ID;
- lot version / frozen state when the backend exposes non-null authoritative values;
- serial item indicator/IDs;
- on hand;
- reserved;
- damaged;
- quarantined;
- in transit;
- available;
- version;
- actions.

Not included:

- expiry;
- risk;
- reorder recommendation;
- demand gap.

Supported server filters:

- warehouse;
- spare part;
- location;
- lot;
- serial item.

Supported server sort maps exactly to the backend allowlist.

A row opens the hidden balance detail route.

### 5.2 Reservations tab

Columns should emphasize:

- reservation ID;
- owner;
- status;
- requested;
- reserved;
- issued;
- released;
- unfilled;
- expires at;
- version.

Filters:

- status;
- owner type;
- owner ID.

Actions are status- and permission-gated, but backend state remains authoritative.

### 5.3 Transfers tab

Columns:

- transfer ID;
- status;
- source warehouse/location;
- target warehouse/location;
- reference;
- dispatched time;
- completed time;
- version.

Filters and sorts map exactly to backend capabilities.

### 5.4 Stocktakes tab

Columns:

- stocktake ID;
- warehouse/location;
- status;
- snapshot time;
- confirmed time;
- version.

### 5.5 Transactions tab

This is the immutable operational audit list.

Columns:

- transaction ID;
- operation type;
- status;
- reason;
- actor;
- request ID;
- completed time;
- version.

The detail page renders ledger entries and their quantity/state evidence. It never exposes or assumes private confirmation-token storage.

---

## 6. Hidden detail routes

Add five child routes beneath the existing Maintenance shell:

- balance detail;
- transaction detail;
- reservation detail;
- transfer detail;
- stocktake detail.

They must use the existing repository convention:

```ts
meta: {
  ...maintenanceRouteMeta,
  hideInMaintenanceMenu: true,
}
```

Suggested paths:

- `inventory-gap/balances/:balanceId`
- `inventory-gap/transactions/:transactionId`
- `inventory-gap/reservations/:reservationId`
- `inventory-gap/transfers/:transferId`
- `inventory-gap/stocktakes/:stocktakeId`

Direct URL access is supported subject to normal auth and backend tenant scope.

No detail route is added to `maintenanceMenuChildren`.

---

## 7. Typed API design

Create:

`frontend/src/api/maintenance/inventory.ts`

Inventory domain types live in this module. Shared Maintenance envelopes remain in `api/maintenance/types.ts`.

### 7.1 Exact domain types

Use string-literal unions matching backend English enums exactly.

Examples:

- operation types;
- transaction statuses;
- reservation statuses;
- transfer statuses;
- stocktake statuses;
- stocktake line resolutions/actions;
- list sort fields.

UI labels may be translated, but logic compares canonical English enum values only.

### 7.2 Decimal quantities

All inventory quantities cross the frontend boundary as exact decimal strings.

The frontend must not use JavaScript floating-point arithmetic to generate authoritative quantities.

Rules:

- API models expose a `DecimalString` alias;
- input controls maintain string values;
- client validation may verify syntax, positivity, non-negativity, and at most four decimals;
- arithmetic or inventory-state authority is never moved into JavaScript `number`.

### 7.3 List query types

Define a distinct query type per domain.

Each query type contains only backend-accepted fields.

No inventory API type contains `tenant_id`.

`buildQuery` is used so each known scalar parameter is emitted once.

### 7.4 Write methods

Typed API methods cover the entire frozen write surface:

Reservations:

- reserve/create;
- issue;
- release;
- return;
- cancel.

Operations:

- preview adjust/freeze/unfreeze;
- execute;
- reverse preview;
- reverse execute.

Transfers:

- create;
- dispatch preview/execute;
- receive preview/execute;
- cancel.

Stocktakes:

- create;
- start;
- update count;
- review;
- confirm preview/execute;
- rebase;
- cancel.

Every write method requires an explicit idempotency key argument and sends it only in `Idempotency-Key`.

The API module never creates idempotency keys itself. Key lifecycle belongs to the Store.

---

## 8. Store architecture

Create:

`frontend/src/stores/maintenance/inventory.ts`

Use one Inventory Pinia store for orchestration, but do not use one global list state.

### 8.1 Five independent server-list slices

Maintain separate state for:

- balances;
- transactions;
- reservations;
- transfers;
- stocktakes.

Each slice owns:

- query;
- items;
- `page`;
- `page_size`;
- `total`;
- `pages`;
- loading;
- error;
- request generation;
- active abort controller.

A request in one domain must not make another domain appear loading.

### 8.2 Query semantics

Changing a filter resets that domain to page 1.

Changing sort or page issues a fresh backend request.

The Store does not perform authoritative list filtering or sorting after receipt.

The Store may preserve inactive-tab state in memory for operator convenience.

URL query synchronization is intentionally out of scope for this phase because current Maintenance list pages use Store-local query state and no explicit deep-link requirement exists.

### 8.3 Detail state

Maintain independent detail loading/error state.

A stale detail response must not overwrite a newer entity load. Use the existing repository generation-counter pattern and AbortController where supported.

After a successful mutation:

1. replace or refresh the affected aggregate detail from server response;
2. refresh affected list state;
3. refresh impacted balance data where the workflow changes inventory;
4. never optimistic-write balance quantities locally.

---

## 9. Idempotency lifecycle

Idempotency behavior is a frontend correctness boundary, not merely a header helper.

### 9.1 Logical command identity

A new logical command receives a UUID generated in memory using `crypto.randomUUID()`.

The same key is reused while retrying the **same logical request payload** after an uncertain result.

The key is not written to localStorage/sessionStorage.

### 9.2 Uncertain failure

Network failures, timeouts, and backend failures whose normalized contract is retryable retain the same idempotency key.

The UI shows an uncertain state and offers retry without silently generating another key.

### 9.3 Definite result

On definite success, the logical command closes and its key is retired.

On a definite validation/state/version conflict where the user must change input or reload state, the existing command remains visible long enough to preserve error/form evidence; submitting changed payload becomes a new logical command with a new key.

For FREEZE/UNFREEZE balance/lot version or state conflicts, the old preview is retired, authoritative balance state is reloaded, and any retry starts as a **new preview logical command with a new idempotency key**. A stale preview is never replayed against newly loaded versions.

### 9.4 Preview and execute are separate logical writes

Preview and execute are different HTTP requests and must not share one idempotency key.

Preview state stores:

- preview transaction ID;
- transaction version;
- confirmation token;
- confirmation expiry.

Execute receives a new logical-command key while consuming the preview metadata.

---

## 10. Permission design

Backend authorization remains authoritative. Frontend permissions control affordances only.

### 10.1 Existing permissions retained

Keep:

- `reserveInventory`
- `issueReturnInventory`
- `transferInventory`
- `adjustInventory`
- `confirmHighRisk`

### 10.2 Add explicit permissions where the UI needs distinct capability labels

Add:

- `freezeInventory`
- `reverseInventory`
- `createStocktake`
- `confirmStocktake`

`manageInventoryPolicies` is **not** added by this design because the frozen Inventory API does not expose a policy-management workflow in this phase.

### 10.3 Role mapping

Viewer:

- all list/detail reads;
- no write affordances.

Contributor:

- reserve/create reservation;
- issue;
- release;
- return;
- cancel reservation;
- create/start/count/review/rebase/cancel stocktake.

Admin/owner:

- all contributor actions;
- transfer create/dispatch/receive/cancel;
- adjust;
- freeze;
- unfreeze;
- reverse;
- stocktake confirmation.

High-risk execute controls require both the relevant domain permission and `confirmHighRisk`.

Examples:

- adjust execute: `adjustInventory && confirmHighRisk`;
- freeze/unfreeze execute: `freezeInventory && confirmHighRisk`;
- reverse execute: `reverseInventory && confirmHighRisk`;
- transfer dispatch/receive execute: `transferInventory && confirmHighRisk`;
- stocktake confirm execute: `confirmStocktake && confirmHighRisk`.

---

## 11. Reservation and FEFO UX

The backend does not expose an authoritative pre-reservation FEFO recommendation endpoint.

Therefore the frontend must **not** implement its own FEFO sorter and must not display a fabricated “server recommendation” before reservation.

### 11.1 Reservation form

User supplies:

- owner type/id;
- part;
- warehouse;
- requested quantity;
- `allow_partial`;
- `as_of`;
- optional expiry;
- optional location/lot/serial constraints.

The frontend obtains fresh balance IDs/versions from current server data and sends `expected_balance_versions`.

### 11.2 Manual allocation constraints

If the user constrains lot or serial selection in a way that intentionally narrows server FEFO choice, the form requires a non-empty FEFO override reason before submission.

This is a client-side usability rule; backend validation/state remains authoritative.

### 11.3 FEFO evidence after success

After reservation succeeds, render the server-returned reservation lines as **FEFO allocation evidence**:

- balance;
- lot/serial;
- quantity;
- FEFO rank;
- override reason.

Recommended component name:

`FEFOAllocationEvidence.vue`

This replaces the old misleading concept of a pre-command `FEFOSelectionPanel`.

---

## 12. High-risk preview and confirmation UX

The frontend must respect the public preview boundary.

### 12.1 Before preview

The dialog can show:

- the user-entered operation;
- selected balance/transaction;
- current visible balance version;
- for FREEZE/UNFREEZE, current authoritative `lot_id`, `lot_version`, and `lot_is_frozen`;
- proposed exact decimal deltas where applicable;
- reason.

For FREEZE/UNFREEZE, null lot-concurrency fields disable preview construction. `false -> Freeze` and `true -> Unfreeze`; the user is not offered the opposite command.

This is labeled **command summary**, not authoritative resulting state.

### 12.2 After preview

Display the server-issued:

- preview transaction ID;
- operation type;
- transaction version;
- confirmation expiration.

Do not claim the server returned public before/after quantities or risk analysis when it did not.

If proposed values are displayed, label them as user input/proposed change.

### 12.3 Execute

Execute uses only the Store-held:

- transaction ID;
- transaction version;
- confirmation token.

The execute button is disabled when the client clock says the confirmation has expired, but backend expiry validation remains final.

On expiry/version/state conflict:

- preserve the original form/context;
- discard unusable confirmation metadata;
- for balance/lot state conflicts, reload authoritative balance state;
- require a fresh preview with a new logical-command idempotency key;
- never carry stale `expected_balance_version` or `expected_lot_version` into the new preview.

---

## 13. Reservation detail workflow

The reservation detail page is the command center for an existing reservation.

Display:

- owner;
- status;
- aggregate quantities;
- expiration;
- allow-partial flag;
- version;
- line errors;
- allocation lines and FEFO ranks.

Allowed actions are derived from:

1. frontend permission;
2. current canonical status.

But no frontend status check substitutes for backend validation.

After issue/release/return/cancel:

- use returned aggregate;
- refresh detail/list;
- refresh affected balances.

Conflict UI exposes normalized public details such as expected/actual version, affected lines, and suggested action when present.

---

## 14. Transfer workflow

Transfer detail drives the two-stage lifecycle.

### 14.1 Create

Admin selects:

- source warehouse/location;
- target warehouse/location;
- exact quantity lines;
- source balances/versions;
- reason;
- optional reference.

### 14.2 Dispatch

For `DRAFT`:

1. preview dispatch;
2. show public preview metadata;
3. execute using returned token/version;
4. reload transfer and balances.

### 14.3 Receive

For `DISPATCHED` or `PARTIALLY_RECEIVED`:

1. enter positive receive quantities by transfer line;
2. preview receive;
3. execute;
4. reload aggregate;
5. support repeated partial receipt until backend reaches completed state.

No frontend calculation can exceed backend remaining quantity authority.

### 14.4 Cancel

Show only when status/permission make it meaningful. Backend remains final authority.

---

## 15. Stocktake workflow

### 15.1 Contributor workflow

Contributor can:

- create warehouse/location stocktake;
- start;
- count lines;
- review;
- rebase conflicted lines;
- cancel.

Line edits use both:

- stocktake expected version;
- line expected version.

### 15.2 Confirmation

Admin/owner:

1. preview confirm;
2. show preview metadata;
3. execute with token/version.

### 15.3 Partial conflicts

After confirmation:

- reload server detail;
- `ADJUSTED`/resolved lines are disabled;
- conflicted lines remain visible with public `conflict_details`;
- rebase only targets unresolved conflict lines;
- supported rebase actions are exactly:
  - `RECOUNT`
  - `BASELINE_ACCEPT`.

The UI must never resubmit already-adjusted lines as if they were unresolved.

---

## 16. Transaction detail and audit evidence

Transaction detail is the primary read-only audit evidence for completed operations.

Display:

- operation type;
- terminal/current status;
- reason;
- actor;
- request ID;
- transaction version;
- completion time;
- ledger entries.

Each ledger entry can display:

- target balance/part/location/lot/serial;
- exact deltas;
- before balance version;
- resulting balance version;
- public state-before/state-after JSON when present.

This is post-operation evidence. It is not used to reconstruct or reveal private preview storage.

---

## 17. Error handling

Use existing `MaintenanceClientError` normalization and common Maintenance error components.

### 17.1 Validation errors

For 422:

- map field-level details where the public error structure permits;
- keep invalid form values visible;
- do not parse exception messages to infer domain codes.

### 17.2 Conflict errors

For 409/domain conflict:

- preserve user input;
- show normalized code;
- render expected/actual version when present;
- render affected lines when present;
- show `suggested_action` when present;
- expose request ID for support.

A conflict that requires changed payload is a definite result; corrected resubmission starts a new logical command.

### 17.3 Auth

401/403 are not transformed into retryable inventory commands.

The application’s existing auth handling remains in force.

### 17.4 Not found / tenant isolation

404 is displayed as unavailable/not found without attempting to infer cross-tenant existence.

### 17.5 Retryable/uncertain errors

Network/timeout/429/appropriate 5xx use normalized retryability.

For writes, retry preserves the same logical idempotency key.

For reads, retry simply issues a fresh request generation.

---

## 18. Internationalization

Add a modular inventory locale resource following the existing modular Maintenance localization pattern, for example:

`frontend/src/i18n/locales/maintenance-inventory.ts`

It should contain frontend labels for:

- tabs;
- fields;
- actions;
- statuses;
- validation;
- conflict guidance;
- preview confirmation wording;
- FEFO allocation evidence.

Canonical backend enum values remain the source for logic. Translation text is display-only.

---

## 19. Component architecture

Create a focused inventory component directory:

`frontend/src/components/maintenance/inventory/`

Recommended components:

- `InventoryBalanceTable.vue`
- `InventoryListToolbar.vue`
- `ReservationDialog.vue`
- `FEFOAllocationEvidence.vue`
- `InventoryOperationPreviewDialog.vue`
- `TransferWorkflow.vue`
- `StocktakeWorkflow.vue`

Reuse existing common components:

- `MaintenancePageHeader`
- `MaintenanceEmptyState`
- `MaintenanceErrorState`
- `MaintenanceStatusTag`
- `MaintenanceAuditTimeline` where semantically appropriate.

Components must communicate through typed props/emits and Store methods. They do not import the HTTP client directly.

---

## 20. Detail view file map

Create:

- `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryReservationDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransferDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue`

Modify:

- `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`

The main page owns tab-level orchestration. Detail views own one aggregate and related actions.

---

## 21. Test design

The implementation plan must preserve RED → GREEN gates and separate Task-level approval.

### 21.1 Typed API tests

Cover:

- exact endpoint paths;
- exact supported filters;
- exact sort values;
- page/page-size serialization;
- omitted empty optional query values;
- no `tenant_id`;
- list `PageData`;
- detail response shape;
- exact decimal-string handling;
- Idempotency-Key on every write;
- preview and execute use independent keys;
- stable normalized errors;
- confirmation metadata.

### 21.2 Store tests

Cover:

- independent list slices;
- stale response generation;
- AbortController behavior where available;
- one domain loading does not block unrelated domain state;
- server sort/filter/page forwarding;
- no in-memory authoritative resort/refilter;
- uncertain write retains key;
- success closes key;
- corrected request after definite conflict receives new key;
- preview and execute are separate logical commands;
- confirmation expiry behavior;
- conflict preserves form/context;
- post-mutation refresh behavior.

### 21.3 Permission/router tests

Cover:

- viewer/contributor/admin/owner matrix;
- all new inventory-specific permission flags;
- detail routes;
- `hideInMaintenanceMenu`;
- menu contains only the existing Inventory Gap top-level entry;
- direct detail navigation.

### 21.4 UI workflow tests

Cover:

- viewer read-only behavior;
- balance server querying;
- contributor reservation lifecycle;
- FEFO evidence after reservation without client FEFO authority;
- admin adjust/freeze/unfreeze/reverse;
- metadata-only preview semantics;
- two-stage transfer including partial receive;
- stocktake create/count/review;
- partial confirmation conflicts;
- rebase only unresolved lines;
- status-driven controls using canonical English enums;
- error/request-ID presentation.

### 21.5 Frontend Gate

After Task-level GREEN:

1. focused Inventory tests;
2. complete frontend test suite;
3. TypeScript typecheck;
4. production build;
5. exact frontend/backend contract audit;
6. `git diff --check`;
7. changed-file scope review.

A mock passing is not sufficient if it diverges from the current backend fields or endpoint paths.

---

## 22. Explicit reconciliation with the older Plan 05-4B frontend plan

The older plan remains useful for intent, but the following points are superseded by current repository/backend facts.

### 22.1 Hidden route metadata

**Old text:** `meta.hidden=true`
**Current design:** `hideInMaintenanceMenu: true`

Reason: this is the existing Maintenance router convention.

### 22.2 FEFO selection

**Old text:** pre-command FEFO recommendation/selection panel.
**Current design:** no client-authoritative FEFO recommendation; display returned server allocation and FEFO ranks after reservation.

Reason: no public FEFO recommendation endpoint exists in the frozen backend.

### 22.3 Inventory Gap expiry/risk columns

**Old text:** balance table includes expiry and risk.
**Current design:** omit both as authoritative balance columns.

Reason: current `InventoryBalanceRead` exposes neither field.

### 22.4 Rich preview dialog

**Old text:** preview shows backend before/after/warnings/risks.
**Current design:** show command context plus public preview transaction/version/token expiry metadata.

Reason: current public `InventoryOperationPreviewRead` does not expose rich preview internals, and Task 9 intentionally keeps private preview storage out of public schemas.

### 22.5 Inventory policy management

**Old text:** add `manageInventoryPolicies`.
**Current design:** deferred.

Reason: no policy-management workflow is part of the frozen Inventory API surface being activated by this frontend phase.

These are contract-alignment corrections, not product downgrades hidden in implementation.

---

## 23. Scope boundaries

### In scope

- Inventory typed API;
- Inventory Pinia store;
- Task 10.5 server-side list query integration;
- Inventory list/detail navigation;
- inventory permission affordances;
- reservations;
- issue/release/return/cancel;
- high-risk operation preview/execute;
- reverse;
- transfers;
- stocktakes;
- in-memory idempotency command lifecycle;
- conflict/retry UX;
- FEFO allocation evidence;
- i18n;
- focused/full frontend verification.

### Out of scope

- any backend production change;
- any Alembic migration;
- new backend endpoints;
- client-side authoritative FEFO calculation;
- fake expiry/risk/demand-gap data;
- client-side authoritative preview before/after state;
- inventory policy management;
- localStorage persistence of command keys/tokens;
- Plan 05-4C or 05-4D;
- PR merge.

If implementation proves one of these is necessary to make an in-scope workflow correct, stop and return to a separate design gate.

---

## 24. File boundary for the future implementation plan

Expected frontend production files are constrained to these areas:

### Create

- `frontend/src/api/maintenance/inventory.ts`
- `frontend/src/stores/maintenance/inventory.ts`
- `frontend/src/components/maintenance/inventory/**`
- five Inventory detail views
- inventory-focused tests
- modular inventory locale resource if the locale registry supports it cleanly.

### Modify

- `frontend/src/router/maintenance.ts`
- `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- `frontend/src/stores/maintenance/permission-matrix.ts`
- permission tests;
- the minimal i18n registry/locale integration files required to register inventory labels.

`frontend/src/stores/maintenance/permissions.ts` should only change if an actual exported helper or computed contract requires it; its current generic permission lookup already derives from the matrix.

`frontend/src/api/maintenance/types.ts` should remain unchanged unless the implementation plan identifies a genuinely cross-module envelope type. Inventory domain types stay in `inventory.ts`.

Any need to modify backend production files is a STOP condition.

---

## 25. Definition of frontend design success

The eventual frontend implementation is successful when:

1. Inventory Gap is no longer a placeholder.
2. All five inventory read domains use the frozen server-side list contract.
3. Viewer can inspect all authorized list/detail information without write controls.
4. Contributor can complete all backend-authorized reservation and stocktake contributor workflows.
5. Admin/owner can complete transfer and high-risk workflows using preview/execute correctly.
6. No frontend code mutates balances optimistically or calculates authoritative FEFO/state transitions.
7. Write retries preserve idempotency exactly across uncertain outcomes.
8. Confirmation tokens/versions are handled as ephemeral server authority.
9. Conflict UI preserves user context and presents public recovery metadata.
10. Frontend does not display unavailable expiry/risk/rich-preview data as if authoritative.
11. Focused tests, full frontend tests, typecheck, production build, and exact contract audit pass.
12. Backend remains unchanged during this frontend phase.
13. FREEZE/UNFREEZE fail closed on nullable lot concurrency state, use authoritative `lot_version`, and re-read server state after execute instead of optimistic toggling.
14. Frontend Gate closes separately before final Plan 05-4B integration/closure work.

---

## 26. Approval boundary

This DESIGN architecture has already been approved and has authorized only detailed implementation planning. This consistency revision updates status/baseline/lot-concurrency documentation; its new artifact SHA must be explicitly re-approved before docs commit.

It does **not** authorize:

- RED tests;
- frontend production changes;
- backend changes;
- commit;
- push;
- PR update;
- PR ready-for-review;
- merge;
- Plan 05-4C.

After this design is explicitly approved, the next step is a separate detailed implementation plan for the Frontend Inventory Gap, with Task-level RED/GREEN/commit gates preserved.

# Plan 05-4B Frontend Inventory Gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已冻结并通过真实 PostgreSQL Gate 的 Plan 05-4B Inventory backend 上，交付可操作的 Inventory Gap 前端：五类服务端列表、详情读取、reservation/FEFO evidence、普通发退料、高风险 preview/execute、两阶段 transfer、stocktake、权限、幂等生命周期和 Frontend Gate。

**Architecture:** 前端严格消费 backend `952d7ceb13f214a079bb1871191ef27cfcc8db22` 的公开合同，不重算库存权威、不实现客户端 FEFO、不伪造 expiry/risk/rich preview。`frontend/src/api/maintenance/inventory.ts` 负责 typed transport 与冻结合同类型，单一 Pinia Inventory store 负责五个独立 server-list slice、详情状态、logical-command 幂等生命周期与 mutation 后的权威刷新；Vue 页面/组件只调用 Store。FREEZE/UNFREEZE 仅从 `InventoryBalanceRead.lot_version` / `lot_is_frozen` 构造可执行状态，不做 optimistic toggle；所有列表均保持 server-side `filter -> count -> sort -> page`，写命令只通过冻结 API 执行。

**Tech Stack:** Vue 3.5.34、Pinia 3.0.4、TypeScript ~6.0.3、Vue Router 4.5.0、vue-i18n 11.4.2、TDesign Vue Next 1.19.2、Axios 1.16、Node `node:test` + `tsx --test`、vue-tsc 3.2.8、Vite 7.3.5。

**Revision:** reconciled after Inventory Lot Concurrency Read Contract Amendment.

**Supersedes plan artifact SHA256:** `36cb4941fb0855edb1d98dc37fe7cdc41bb63990df11177e4a46bd1d1a75caa1`.
**Supersedes reconciled artifact SHA256:** `d8a7c59c2afc7fd6f76c4a112a2997915c0c9c7eb594145baa8c8af6a252e3e8`.

**Intended repository path:** `docs/superpowers/plans/2026-08-16-maintenance-plan05-04b-inventory-gap-frontend.md`.

**Consistency revision:** the approved frontend DESIGN was updated only to mark its approved status, move its frozen backend baseline to `952d7ceb13f214a079bb1871191ef27cfcc8db22`, document the already-approved `lot_version` / `lot_is_frozen` amendment semantics, and remove trailing whitespace that blocked `git diff --check`. Architecture and execution task boundaries are unchanged.

**Execution status:** APPROVED — consistency-revised after the docs-only commit blocker; the new artifact SHA still requires explicit re-approval before docs materialization/commit. The previous lot-version blocker remains resolved by the pushed Inventory Lot Concurrency Read Contract Amendment at backend HEAD `952d7ceb13f214a079bb1871191ef27cfcc8db22`. This revised artifact has a new SHA and requires explicit re-approval before docs materialization/commit. It still does **not** authorize RED or production changes.

## Resolved Contract Reconciliation

The earlier implementation plan correctly stopped because FREEZE/UNFREEZE required a public current lot version but the then-frozen balance read exposed only `lot_id`. That blocker is now closed by the approved and pushed amendment.

Authoritative amendment artifacts:

- design: `docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment-design.md`
- design SHA256: `d1cb92f29fea4a200882746927a9af9f53de9c3e671f46fed2696c9abdd4786a`
- implementation plan: `docs/superpowers/plans/2026-08-16-maintenance-plan05-04b-inventory-lot-concurrency-read-contract-amendment.md`
- implementation plan SHA256: `657e6e41b8e3dabe8edd1235699ce7fbfeeacdb0a973e057f1bdd30e72e7242d`
- documentation commit: `b3d58c7dbe604ae09dd14fb56dc5c89415aee136`
- feature commit / backend contract baseline: `952d7ceb13f214a079bb1871191ef27cfcc8db22`

The exact additive public balance fields are:

```ts
lot_version: number | null
lot_is_frozen: boolean | null
```

Frontend contract semantics are frozen as follows:

```text
lot_id == null
  -> lot_version == null
  -> lot_is_frozen == null
  -> Freeze/Unfreeze unavailable

lot_id != null AND lot_version == null
  -> fail closed
  -> Freeze/Unfreeze unavailable

lot_id != null AND lot_is_frozen == null
  -> fail closed
  -> Freeze/Unfreeze unavailable

lot_version is positive integer AND lot_is_frozen == false
  -> only Freeze is offered
  -> preview payload uses expected_lot_version = balance.lot_version

lot_version is positive integer AND lot_is_frozen == true
  -> only Unfreeze is offered
  -> preview payload uses expected_lot_version = balance.lot_version
```

The frontend must never:

- guess or default `expected_lot_version`;
- derive lot version from transaction audit JSON or any private/non-public source;
- let the user manually choose FREEZE when `lot_is_frozen=true` or UNFREEZE when `lot_is_frozen=false`;
- optimistic-toggle `lot_is_frozen`;
- reuse a preview after a version/state conflict;
- add lot-version filters/sorts or invent a lot detail endpoint.

After successful FREEZE/UNFREEZE execute, the frontend must refresh authoritative balance state before rendering the next Freeze/Unfreeze affordance. If the refresh returns `lot_version=null` or `lot_is_frozen=null`, the control remains disabled/fail-closed.

This reconciliation does not reopen backend write semantics, FEFO, Alembic, or the approved frontend information architecture.

### Planning-time source revalidation at backend HEAD `952d7ceb...`

The plan was rechecked against the exact current repository state before this revision:

```text
frontend/package.json
  blob 900692ca70dc50b2bdfeea99989bfbc6c330ca66
  test       = tsx --test
  type-check = vue-tsc --build
  build      = vite build

frontend/src/router/maintenance.ts
  blob bd845acbc12dd880b943bb3b8907e8e6a8245248
  inventory-gap top-level route exists
  hidden detail convention = hideInMaintenanceMenu: true

frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue
  blob 4ed51241c8b3a1f6e12173b80584a3d8f12e5c4f
  placeholder-only

frontend/src/api/maintenance/inventory.ts
  absent

frontend/src/stores/maintenance/inventory.ts
  absent

frontend/src/stores/maintenance/permission-matrix.ts
  blob bbe3ea06fa79395057001d45a47c387b431688a6
  no freezeInventory/reverseInventory/createStocktake/confirmStocktake yet

frontend/src/stores/maintenance/permissions.ts
  blob 782c141b2f1a94fee2a51b7ace7e959016324c69
  generic can(action: MaintenanceAction) remains sufficient

frontend/src/api/maintenance/client.ts
  blob ec6cf6c440f0da19b6ab280e26d6fc8233ea5702
  maintenancePost supports config
  maintenancePatch still does not expose config

frontend/src/utils/request.ts
  blob ad04bf4c6eccf12848862749276eb8502d08814b
  low-level patch(url, data, config?) supports config

extensions/maintenance-api/app/schemas/inventory_ledger.py
  blob b9efbb052a51759240436ea5f5bc0e263b9de8fb
  InventoryBalanceRead includes lot_version / lot_is_frozen

extensions/maintenance-api/app/api/v1/inventory/operations.py
  blob bf5450115dc78f6f08e95622d6df1cbbdf0c9895
  FREEZE/UNFREEZE preview accepts lot_id + expected_lot_version

extensions/maintenance-api/app/schemas/inventory_operation.py
  blob 3d92ec56ae91c6ed8d6d65f3e8003146ceece146
  public preview remains metadata-only

extensions/maintenance-api/app/api/v1/inventory/queries.py
  blob 154159d7968cfe79d2af67e071e43ed42dd97eff
  five list/detail read surfaces and Task 10.5 filter/sort matrices unchanged

extensions/maintenance-api/app/schemas/common.py
  blob 31a9d617725999fd62242416f011098d21cfb7e4
  PageData = items/page/page_size/total/pages

extensions/maintenance-api/app/api/v1/inventory/reservations.py
  blob 37f60141271849345d86eec938cc500de8ca8a70
  five contributor reservation writes unchanged

extensions/maintenance-api/app/schemas/inventory_reservation.py
  blob bbbd406b3d1e23f8ddddff026bf705e4b9bfff88
  reservation commands/read fields revalidated

extensions/maintenance-api/app/api/v1/inventory/transfers.py
  blob 77730bf0535d373820464901b1af0a0d71f1bef9
  six admin transfer writes unchanged

extensions/maintenance-api/app/schemas/inventory_transfer.py
  blob b349ce81d86a67273614606b812ae213e7a2ea11
  transfer command/read fields revalidated

extensions/maintenance-api/app/api/v1/inventory/stocktakes.py
  blob 7df2310591f72bc8c531f5e806a80c72547ef823
  eight stocktake writes unchanged; count remains PATCH

extensions/maintenance-api/app/schemas/inventory_stocktake.py
  blob cd4de7562a25113d56fb161c4d1b9cf0d388a5f5
  stocktake read/count fields revalidated
```

These blob SHAs are planning evidence, not an execution shortcut. Task 0 must still re-read the execution worktree and stop on drift.

## Global Constraints

- 权威设计：`docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-gap-frontend-design.md`。
- 权威设计 SHA256：`a7b36bb08ded5b8bd6a28aab758c2c50855f5dacd3fe3897aa16ae4acbfccd4b`。
- 执行分支固定：`codex/maintenance-plan05-4b`。
- backend/public contract 唯一基线：`952d7ceb13f214a079bb1871191ef27cfcc8db22`。开始 RED 时 HEAD 必须是该 commit，或只包含随后单独批准的 frontend design/plan docs-only commit；任何其他 production/test commit 都必须 STOP 并重新核对。
- lot concurrency amendment design SHA256：`d1cb92f29fea4a200882746927a9af9f53de9c3e671f46fed2696c9abdd4786a`；其 contract delta 与已批准 frontend DESIGN 共同构成本计划的输入。
- `InventoryBalanceRead` 必须按 public JSON 合同包含 `lot_version: number | null` 与 `lot_is_frozen: boolean | null`；这两个字段只用于并发前置条件与 Freeze/Unfreeze affordance，不加入 balance list filters/sorts。
- FREEZE/UNFREEZE fail closed：`lot_id`、`lot_version`、`lot_is_frozen` 任一不可用时不构造 preview command；`false -> FREEZE`，`true -> UNFREEZE`。
- FREEZE/UNFREEZE preview payload 的 `expected_lot_version` 必须直接取当前 authoritative `balance.lot_version`；禁止 hard-code、fallback、audit-derived 或 private-source version。
- FREEZE/UNFREEZE execute 成功后必须重新读取 authoritative balance（至少当前 detail，并刷新 balance list）；不得直接把本地 `lot_is_frozen` 取反。
- 当前 PR #8 保持 Draft；本计划不得自动 update PR、ready、merge。
- backend production、backend tests、Alembic、数据库 schema 一律不修改；任何 backend 变更需求都是 STOP 条件。
- Alembic head 保持 `20260803_11`；本计划不创建 migration。
- 不实现 Plan 05-4C / 05-4D。
- 所有 inventory list 必须使用 Task 10.5 server contract；禁止取当前页后再做权威内存过滤/排序。
- list query 只发送 backend 已知 scalar 参数；不得发送 `tenant_id`。
- `page >= 1`；`1 <= page_size <= 100`；默认 `page=1,page_size=20`；`sort_order` 仅 `asc|desc`。
- inventory 数量在 frontend 类型、表单、payload 中保持精确十进制字符串；禁止以 JavaScript `number` 作为权威数量算术载体。
- 不在前端实现 FEFO 排序算法；FEFO 排序与选择仍由 backend 决定。
- reservation 创建前为了满足 `expected_balance_versions`，前端可以按相同 server filters、`page_size=100`、`sort_by=id`、`sort_order=asc` 逐页收集 balance ID/version；这只是版本快照收集，不是 FEFO 决策。
- 不把 lot expiry、inventory risk、demand gap 当作 `InventoryBalanceRead` 的权威字段展示。
- 不把 user command summary 冒充 server rich preview；公开 preview 只依赖 transaction ID、operation type、transaction version、confirmation token、expiration。
- 当前 `InventoryOperationPreviewRead` 精确 public 字段仍为 `transaction_id`、`operation_type`、`status=PREVIEWED`、`transaction_version`、nullable `confirmation_token`、`confirmation_expires_at`；不增加 `before/after/warnings/risks`。
- `confirmation_token == null` 时 preview 视为不可执行；前端不得生成 token。
- 不增加 `manageInventoryPolicies`。
- confirmation token 和 idempotency key 只保存在内存；不得写 localStorage/sessionStorage。
- preview 与 execute 是不同 logical write，必须使用不同 `Idempotency-Key`。
- 同一 logical write 遭遇 uncertain/retryable failure 时复用原 key；payload 改变后必须生成新 key。
- 当前共享 `maintenanceGet()` 不支持 request config/AbortSignal；本计划以独立 generation counter 作为必需 stale-response protection，不重构共享 Maintenance client。
- stocktake line update 是 PATCH 且要求 `Idempotency-Key`；由于共享 `maintenancePatch()` 无 config 参数，只允许在 `inventory.ts` 内建立窄的 PATCH adapter，直接复用 `@/utils/request.patch` + `unwrapMaintenanceResponse()` + `normalizeMaintenanceError()`；不得修改 `frontend/src/api/maintenance/client.ts` 或 `frontend/src/utils/request.ts`。
- frontend 当前测试 runner 是 `tsx --test` / `node:test`，不是 Vitest；不得新增 Vitest 或 `@vue/test-utils` 依赖。
- 在 backend HEAD `952d7ceb...` 上已重新核对：`frontend/package.json` scripts 仍为 `test=tsx --test`、`type-check=vue-tsc --build`、`build=vite build`；`InventoryGapPage.vue` 仍是 placeholder，Inventory API/store 尚不存在，hidden route convention 仍为 `hideInMaintenanceMenu: true`。
- 现有 `permission-matrix.ts` 仍仅包含 `reserveInventory`、`issueReturnInventory`、`transferInventory`、`adjustInventory`、`confirmHighRisk` 等旧 keys；本计划仍只新增已批准设计规定的 `freezeInventory`、`reverseInventory`、`createStocktake`、`confirmStocktake`。
- Vue 行为测试沿用现有 repository 模式：domain/workflow 逻辑下沉为可直接 `node:test` 的纯 TS helper；SFC/route wiring 用 `readFileSync` + route records 检查；type-check/build 是 SFC 编译 Gate。
- 使用现有 `MaintenancePageHeader`、`MaintenanceEmptyState`、`MaintenanceErrorState`、`MaintenanceStatusTag` 等组件；不做无关 UI framework 重构。
- `frontend/src/stores/maintenance/permissions.ts` 当前 generic `can(action)` 已基于 `MaintenanceAction`；除非 RED 证明必须，否则不得修改。
- `frontend/src/api/maintenance/types.ts` 不放 inventory domain types；除非出现真正跨模块 envelope 类型，否则不得修改。
- 每个 Task 的 RED 与 GREEN 是独立批准边界。批准 RED 不等于批准 GREEN。
- 每个 commit、push、PR update/ready、merge 都必须分别明确批准。
- 不得 reset/rebase/stash/clean 工作树来“修复”失败；失败时先诊断现状，再提交恢复方案。
- 每个 Gate 必须使用新鲜命令输出；不得用历史“已通过”替代。
- 如果实现需要超出本计划冻结的 frontend production scope，先 STOP 并说明原因，不得自行扩大范围。

---

## Approved Design → Plan Coverage Map

- Design §§5–6 information architecture/hidden routes → Task 12A。
- Design §7 typed API → Task 11A。
- Design §8 independent list/detail store → Task 11B。
- Design §9 idempotency lifecycle → Task 11C。
- Design §10 permissions → Task 11D。
- Design §§11,13 reservation/FEFO evidence → Task 12B。
- Design §§12,14 high-risk + transfer → Task 12C。
- Design §15 stocktake → Task 12D。
- Design §16 transaction audit detail → Task 12A。
- Design §17 error handling → Task 11A + 11C + all workflow Tasks。
- Design §18 i18n → Task 12A。
- Design §§19–20 component/detail architecture → Task 12A–12D。
- Design §21 test design → each Task RED/GREEN + Task 13。
- Design §§22–24 old-plan reconciliation/scope → Global Constraints + Task 0/Task 13 scope audit。
- Design §25 success definition → Task 13 final checklist。
- Lot concurrency amendment read fields → Task 0 + Task 11A + Task 11B。
- Lot concurrency fail-closed/action mapping → Task 12C。
- Lot concurrency success refresh/conflict re-preview → Task 11C + Task 12C。
- Lot concurrency final contract audit → Task 13。

---

## File Map

### Task 11 production

Create:

- `frontend/src/api/maintenance/inventory.ts` — exact Inventory domain types, list/detail API, all write methods, Idempotency-Key transport, narrow PATCH adapter。
- `frontend/src/stores/maintenance/inventory.ts` — five independent list slices, five detail states, stale-generation protection, candidate version collection, logical command/idempotency state。
- `frontend/src/api/maintenance/__tests__/inventory.test.ts`
- `frontend/src/stores/maintenance/__tests__/inventory.test.ts`

Modify:

- `frontend/src/stores/maintenance/permission-matrix.ts`
- `frontend/src/stores/maintenance/__tests__/permissions.test.ts`

Do not modify in Task 11:

- `frontend/src/router/maintenance.ts`
- any Inventory Vue SFC
- `frontend/src/api/maintenance/client.ts`
- `frontend/src/utils/request.ts`
- backend files.

### Task 12 production

Create:

- `frontend/src/i18n/locales/maintenance-inventory.ts`
- `frontend/src/i18n/locales/maintenance-inventory.test.ts`
- `frontend/src/components/maintenance/inventory/inventory-workflow.ts`
- `frontend/src/components/maintenance/inventory/InventoryListToolbar.vue`
- `frontend/src/components/maintenance/inventory/InventoryBalanceTable.vue`
- `frontend/src/components/maintenance/inventory/ReservationDialog.vue`
- `frontend/src/components/maintenance/inventory/FEFOAllocationEvidence.vue`
- `frontend/src/components/maintenance/inventory/InventoryOperationPreviewDialog.vue`
- `frontend/src/components/maintenance/inventory/TransferWorkflow.vue`
- `frontend/src/components/maintenance/inventory/StocktakeWorkflow.vue`
- `frontend/src/components/maintenance/inventory/__tests__/inventory-gap.test.ts`
- `frontend/src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts`
- `frontend/src/components/maintenance/inventory/__tests__/inventory-operations.test.ts`
- `frontend/src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts`
- `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryReservationDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransferDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue`
- `frontend/src/views/maintenance/__tests__/inventory-navigation.test.ts`

Modify:

- `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- `frontend/src/router/maintenance.ts`
- `frontend/src/i18n/locales/en-US.ts`
- `frontend/src/i18n/locales/zh-CN.ts`
- `frontend/src/i18n/locales/ko-KR.ts`
- `frontend/src/i18n/locales/ru-RU.ts`

### Task 13 evidence

Create only after fresh Gate output:

- `docs/superpowers/reviews/2026-08-16-maintenance-plan05-04b-frontend-gate.md`

No implementation code is added in Task 13 unless Gate discovers a defect; any defect fix returns to the owning Task RED/GREEN scope.

---

## Pre-Implementation Documentation Gate

The lot-concurrency blocker is resolved and this plan is now the reconciled execution blueprint candidate. The frontend DESIGN remains the architectural baseline; the pushed lot-concurrency amendment supplies the exact backend contract delta. No frontend RED may begin until:

1. this reconciled implementation plan is explicitly approved;
2. the approved frontend DESIGN and this reconciled plan are placed at their intended repository paths under a **separately approved docs-only commit**;
3. that docs commit is verified to descend from backend contract baseline `952d7ceb13f214a079bb1871191ef27cfcc8db22`;
4. Task 0 preflight passes with no contract drift.

Intended plan path:

`docs/superpowers/plans/2026-08-16-maintenance-plan05-04b-inventory-gap-frontend.md`

Suggested docs-only commit message:

```text
docs(maintenance): add inventory gap frontend design and plan
```

Plan approval does not authorize the docs commit, Task 11A RED, or any production change.

---

## Task 0: Execution Preflight and Contract Freeze

**Files:** none.

**Interfaces:**
- Consumes: approved design SHA and approved implementation plan SHA。
- Produces: verified execution baseline for Task 11A RED。
- Writes: none。

- [ ] **Step 1: Verify branch, HEAD, clean worktree, staged-empty**

Run from:

`E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-plan05-4b`

```powershell
$repoRoot = "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-plan05-4b"
$git = "C:\Program Files\Git\cmd\git.exe"

& $git -C $repoRoot branch --show-current
& $git -C $repoRoot rev-parse HEAD
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --cached --name-only
```

Expected:

- branch exactly `codex/maintenance-plan05-4b`;
- HEAD is the separately approved docs commit whose first parent chain contains `952d7ceb13f214a079bb1871191ef27cfcc8db22`, or `952d7ceb...` itself if docs have not yet been committed;
- working tree clean;
- staged empty.

Any unrelated change → STOP.

- [ ] **Step 2: Verify backend frozen head is an ancestor**

```powershell
& $git -C $repoRoot merge-base --is-ancestor `
  952d7ceb13f214a079bb1871191ef27cfcc8db22 `
  HEAD

if ($LASTEXITCODE -ne 0) {
    throw "Frozen backend contract baseline 952d7ceb... is not an ancestor."
}
```

Expected: exit code 0.

- [ ] **Step 3: Verify design SHA**

```powershell
$design = Join-Path $repoRoot `
  "docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-inventory-gap-frontend-design.md"

$designHash = (
    Get-FileHash -LiteralPath $design -Algorithm SHA256
).Hash.ToLowerInvariant()

if ($designHash -ne "a7b36bb08ded5b8bd6a28aab758c2c50855f5dacd3fe3897aa16ae4acbfccd4b") {
    throw "Frontend Inventory Gap design hash mismatch: $designHash"
}
```

Expected: exact SHA match.

- [ ] **Step 4: Verify actual frontend scripts before using commands**

```powershell
Get-Content -LiteralPath (Join-Path $repoRoot "frontend/package.json") |
  Select-String '"test"|"type-check"|"build"'
```

Expected actual scripts:

```text
"test": "tsx --test"
"type-check": "vue-tsc --build"
"build": "vite build"
```

Do not use the obsolete `typecheck` script name and do not assume Vitest.

- [ ] **Step 5: Verify frontend baseline has no Inventory API/store/component implementation**

```powershell
$expectedAbsent = @(
  "frontend/src/api/maintenance/inventory.ts",
  "frontend/src/stores/maintenance/inventory.ts",
  "frontend/src/components/maintenance/inventory"
)

foreach ($path in $expectedAbsent) {
    $full = Join-Path $repoRoot $path
    if (Test-Path -LiteralPath $full) {
        throw "Unexpected pre-existing Inventory frontend implementation: $path"
    }
}
```

Expected: all absent.

- [ ] **Step 6: Verify current placeholder and existing menu/route entry**

```powershell
Get-Content -LiteralPath (
  Join-Path $repoRoot `
    "frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue"
)

& $git -C $repoRoot grep -n "maintenanceInventoryGap" -- `
  frontend/src/router/maintenance.ts `
  frontend/src/stores/maintenance/menu-definition.ts
```

Expected:

- page still placeholder-only;
- existing top-level Inventory Gap route/menu entry exists.

- [ ] **Step 7: Verify the reconciled lot concurrency read contract at the frozen backend baseline**

Inspect the exact backend files at the execution HEAD:

```powershell
$schema = Join-Path $repoRoot `
  "extensions/maintenance-api/app/schemas/inventory_ledger.py"
$operations = Join-Path $repoRoot `
  "extensions/maintenance-api/app/api/v1/inventory/operations.py"
$previewSchema = Join-Path $repoRoot `
  "extensions/maintenance-api/app/schemas/inventory_operation.py"

Get-Content -LiteralPath $schema |
  Select-String "lot_version|lot_is_frozen"

Get-Content -LiteralPath $operations |
  Select-String "expected_lot_version|operation_type"

Get-Content -LiteralPath $previewSchema |
  Select-String `
    "transaction_id|transaction_version|confirmation_token|confirmation_expires_at"
```

Expected public contract:

```text
InventoryBalanceRead:
  lot_version: int | None = Field(default=None, gt=0)
  lot_is_frozen: bool | None = None

OperationPreviewCommand:
  operation_type: ADJUST | FREEZE | UNFREEZE
  lot_id: positive int | None
  expected_lot_version: positive int | None

InventoryOperationPreviewRead:
  transaction_id
  operation_type
  status=PREVIEWED
  transaction_version
  confirmation_token nullable
  confirmation_expires_at
```

No lot endpoint/filter/sort is required or allowed by this plan.

- [ ] **Step 8: Verify frontend starting facts are still unchanged at `952d7ceb...`**

Confirm:

```text
frontend/src/api/maintenance/inventory.ts       ABSENT
frontend/src/stores/maintenance/inventory.ts   ABSENT
InventoryGapPage.vue                           placeholder-only
maintenance hidden route convention            hideInMaintenanceMenu=true
permission matrix                              no freezeInventory/reverseInventory/createStocktake/confirmStocktake yet
```

Any unexpected pre-existing Inventory frontend implementation or contract drift → STOP and reconcile again.

- [ ] **Step 9: STOP for Task 11A RED approval**

No implementation file has changed. Task 11A RED may be requested only after this reconciled plan is approved and its docs-only commit is separately approved and verified.

---

# Task 11 — Typed API, Store and Permission Foundation

Task 11 is decomposed into 11A–11D so each correctness boundary can be reviewed independently. No subtask proceeds from RED to GREEN without explicit approval.

## Task 11A: Typed Inventory API Contract

**Files:**

- Create: `frontend/src/api/maintenance/inventory.ts`
- Create: `frontend/src/api/maintenance/__tests__/inventory.test.ts`

**Interfaces:**

Produces canonical frontend types:

```ts
export type DecimalString = string

export type InventoryOperationType =
  | 'OPENING'
  | 'ADJUST'
  | 'RESERVE'
  | 'UNRESERVE'
  | 'ISSUE'
  | 'RETURN'
  | 'TRANSFER_DISPATCH'
  | 'TRANSFER_RECEIVE'
  | 'FREEZE'
  | 'UNFREEZE'
  | 'REVERSE'
  | 'STOCKTAKE_CONFIRM'

export type InventoryTransactionStatus =
  | 'PREVIEWED'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'EXPIRED'
  | 'REVERSED'

export type InventoryReservationStatus =
  | 'ACTIVE'
  | 'PARTIALLY_ISSUED'
  | 'FULFILLED'
  | 'RELEASED'
  | 'CANCELLED'
  | 'EXPIRED'

export type InventoryTransferStatus =
  | 'DRAFT'
  | 'DISPATCHED'
  | 'PARTIALLY_RECEIVED'
  | 'COMPLETED'
  | 'CANCELLED'

export type InventoryStocktakeStatus =
  | 'DRAFT'
  | 'COUNTING'
  | 'REVIEWING'
  | 'CONFIRMED'
  | 'CONFLICTED'
  | 'CANCELLED'

export type InventorySortOrder = 'asc' | 'desc'
```

Produces public read interfaces mirroring backend:

```ts
export interface InventoryBalanceRead {
  id: number
  warehouse_id: number
  location_id: number
  spare_part_id: number
  lot_id: number | null
  serial_item_id: number | null
  serial_item_ids: number[]
  on_hand_quantity: DecimalString
  reserved_quantity: DecimalString
  damaged_quantity: DecimalString
  quarantined_quantity: DecimalString
  in_transit_quantity: DecimalString
  available_quantity: DecimalString
  version: number
  lot_version: number | null
  lot_is_frozen: boolean | null
}

export interface InventoryLedgerEntryRead {
  id: number
  balance_id: number
  spare_part_id: number
  warehouse_id: number
  location_id: number
  lot_id: number | null
  serial_item_id: number | null
  on_hand_delta: DecimalString
  reserved_delta: DecimalString
  damaged_delta: DecimalString
  quarantined_delta: DecimalString
  in_transit_delta: DecimalString
  state_before_json: Record<string, unknown>
  state_after_json: Record<string, unknown>
  before_balance_version: number
  resulting_balance_version: number
  created_at: string
}

export interface InventoryTransactionRead {
  id: number
  tenant_id: string
  operation_type: InventoryOperationType
  status: InventoryTransactionStatus
  idempotency_key: string
  request_hash: string
  reason: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  completed_at: string | null
  entries: InventoryLedgerEntryRead[]
}
```

Reservation interfaces:

```ts
export interface InventoryReservationLineRead {
  id: number
  reservation_id: number
  spare_part_id: number
  balance_id: number
  lot_id: number | null
  serial_item_id: number | null
  requested_quantity: DecimalString
  reserved_quantity: DecimalString
  issued_quantity: DecimalString
  released_quantity: DecimalString
  expected_balance_version: number
  fefo_rank: number
  fefo_override_reason: string | null
  version: number
}

export interface InventoryReservationRead {
  id: number
  tenant_id: string
  owner_type: string
  owner_id: string
  status: InventoryReservationStatus
  expires_at: string | null
  allow_partial: boolean
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  requested_quantity: DecimalString
  reserved_quantity: DecimalString
  issued_quantity: DecimalString
  released_quantity: DecimalString
  unfilled_quantity: DecimalString
  line_errors: string[]
  lines: InventoryReservationLineRead[]
}
```

Transfer/stocktake/preview types mirror backend field names exactly; no UI-translated enum values are used in these types.

For direct high-risk preview, the frontend uses a stricter discriminated union than the permissive backend model so FREEZE/UNFREEZE cannot be constructed without the concurrency preconditions:

```ts
export interface InventoryQuantityDeltaRequest {
  on_hand: DecimalString
  reserved: DecimalString
  damaged: DecimalString
  quarantined: DecimalString
  in_transit: DecimalString
}

export interface InventoryAdjustPreviewRequest {
  operation_type: 'ADJUST'
  balance_id: number
  expected_balance_version: number
  reason: string
  deltas: InventoryQuantityDeltaRequest
  lot_id?: never
  expected_lot_version?: never
}

export interface InventoryLotStatePreviewRequest {
  operation_type: 'FREEZE' | 'UNFREEZE'
  balance_id: number
  expected_balance_version: number
  reason: string
  deltas: null
  lot_id: number
  expected_lot_version: number
}

export type InventoryOperationPreviewRequest =
  | InventoryAdjustPreviewRequest
  | InventoryLotStatePreviewRequest

export interface InventoryOperationPreviewRead {
  transaction_id: number
  operation_type: InventoryOperationType
  status: 'PREVIEWED'
  transaction_version: number
  confirmation_token: string | null
  confirmation_expires_at: string
}
```

This union intentionally forbids `lot_id` / `expected_lot_version` on ADJUST and requires both on FREEZE/UNFREEZE. It does not widen the backend API; it makes the frontend fail closed before transport.

Produces query types:

```ts
export interface InventoryBalanceListQuery {
  page?: number
  page_size?: number
  warehouse_id?: number
  spare_part_id?: number
  location_id?: number
  lot_id?: number
  serial_item_id?: number
  sort_by?:
    | 'id'
    | 'warehouse_id'
    | 'spare_part_id'
    | 'location_id'
    | 'lot_id'
    | 'on_hand_quantity'
    | 'reserved_quantity'
    | 'available_quantity'
  sort_order?: InventorySortOrder
}

export interface InventoryTransactionListQuery {
  page?: number
  page_size?: number
  operation_type?: InventoryOperationType
  status?: InventoryTransactionStatus
  reference_type?: string
  reference_id?: string
  sort_by?: 'id' | 'operation_type' | 'status' | 'completed_at'
  sort_order?: InventorySortOrder
}

export interface InventoryReservationListQuery {
  page?: number
  page_size?: number
  status?: InventoryReservationStatus
  owner_type?: string
  owner_id?: string
  sort_by?: 'id' | 'status' | 'expires_at'
  sort_order?: InventorySortOrder
}

export interface InventoryTransferListQuery {
  page?: number
  page_size?: number
  status?: InventoryTransferStatus
  source_warehouse_id?: number
  source_location_id?: number
  target_warehouse_id?: number
  target_location_id?: number
  reference_type?: string
  reference_id?: string
  sort_by?: 'id' | 'status' | 'dispatched_at' | 'completed_at'
  sort_order?: InventorySortOrder
}

export interface InventoryStocktakeListQuery {
  page?: number
  page_size?: number
  status?: InventoryStocktakeStatus
  warehouse_id?: number
  location_id?: number
  sort_by?: 'id' | 'status' | 'snapshot_at' | 'confirmed_at'
  sort_order?: InventorySortOrder
}
```

Produces exact shared page/transport/request contracts:

```ts
export interface InventoryPage<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface InventoryApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
  patch<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
}

export interface InventoryReserveRequest {
  owner_type: string
  owner_id: string
  spare_part_id: number
  warehouse_id: number
  requested_quantity: DecimalString
  allow_partial: boolean
  expected_balance_versions: Record<number, number>
  as_of: string
  location_id?: number | null
  lot_id?: number | null
  serial_item_id?: number | null
  expires_at?: string | null
  fefo_override_reason?: string | null
}

export interface InventoryReservationQuantityLineRequest {
  reservation_line_id: number
  quantity: DecimalString
}

export interface InventoryReservationReturnLineRequest
  extends InventoryReservationQuantityLineRequest {
  issue_transaction_id: number
}

export interface InventoryReservationIssueRequest {
  expected_version: number
  lines: InventoryReservationQuantityLineRequest[]
}

export interface InventoryReservationReleaseRequest {
  expected_version: number
  lines: InventoryReservationQuantityLineRequest[]
}

export interface InventoryReservationReturnRequest {
  expected_version: number
  lines: InventoryReservationReturnLineRequest[]
}

export interface InventoryExpectedVersionRequest {
  expected_version: number
}

export interface InventoryOperationExecuteRequest {
  expected_transaction_version: number
  confirmation_token: string
}

export interface InventoryReversePreviewRequest {
  expected_transaction_version: number
  reason: string
}

export interface InventoryTransferCreateLineRequest {
  spare_part_id: number
  source_balance_id: number
  lot_id?: number | null
  serial_item_id?: number | null
  quantity: DecimalString
  expected_source_version: number
}

export interface InventoryTransferCreateRequest {
  source_warehouse_id: number
  source_location_id: number
  target_warehouse_id: number
  target_location_id: number
  reference_type?: string | null
  reference_id?: string | null
  reason: string
  lines: InventoryTransferCreateLineRequest[]
}

export interface InventoryTransferExecuteRequest {
  transaction_id: number
  expected_transaction_version: number
  confirmation_token: string
}

export interface InventoryTransferReceiveLineRequest {
  transfer_line_id: number
  quantity: DecimalString
}

export interface InventoryTransferReceivePreviewRequest {
  expected_version: number
  lines: InventoryTransferReceiveLineRequest[]
}

export interface InventoryTransferLineRead {
  id: number
  transfer_id: number
  spare_part_id: number
  source_balance_id: number
  target_balance_id: number
  lot_id: number | null
  serial_item_id: number | null
  requested_quantity: DecimalString
  dispatched_quantity: DecimalString
  received_quantity: DecimalString
  expected_source_version: number
  expected_target_version: number
  version: number
}

export interface InventoryTransferRead {
  id: number
  tenant_id: string
  status: InventoryTransferStatus
  source_warehouse_id: number
  source_location_id: number
  target_warehouse_id: number
  target_location_id: number
  reference_type: string | null
  reference_id: string | null
  reason: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  dispatched_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  lines: InventoryTransferLineRead[]
}

export interface InventoryStocktakeLineRead {
  id: number
  stocktake_id: number
  balance_id: number
  spare_part_id: number
  lot_id: number | null
  serial_item_id: number | null
  system_quantity: DecimalString
  counted_quantity: DecimalString | null
  variance_quantity: DecimalString | null
  snapshot_balance_version: number
  confirmed_transaction_id: number | null
  resolution: string
  conflict_details: Record<string, unknown> | null
  version: number
}

export interface InventoryStocktakeRead {
  id: number
  tenant_id: string
  warehouse_id: number
  location_id: number
  status: InventoryStocktakeStatus
  snapshot_at: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  confirmed_at: string | null
  cancelled_at: string | null
  lines: InventoryStocktakeLineRead[]
}

export interface InventoryStocktakeCreateRequest {
  warehouse_id: number
  location_id: number
}

export interface InventoryStocktakeCountRequest {
  expected_version: number
  expected_line_version: number
  counted_quantity: DecimalString
}

export interface InventoryStocktakeConfirmExecuteRequest {
  transaction_id: number
  expected_transaction_version: number
  confirmation_token: string
}

export type InventoryStocktakeRebaseAction =
  | 'RECOUNT'
  | 'BASELINE_ACCEPT'

export interface InventoryStocktakeRebaseLineRequest {
  line_id: number
  action: InventoryStocktakeRebaseAction
}

export interface InventoryStocktakeRebaseRequest {
  expected_version: number
  lines: InventoryStocktakeRebaseLineRequest[]
}
```

Exact typed API interface:

```ts
export interface InventoryApi {
  listBalances(
    query?: InventoryBalanceListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>
  getBalance(
    id: number,
  ): Promise<MaintenanceResult<InventoryBalanceRead>>

  listTransactions(
    query?: InventoryTransactionListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryTransactionRead>>>
  getTransaction(
    id: number,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>

  listReservations(
    query?: InventoryReservationListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryReservationRead>>>
  getReservation(
    id: number,
  ): Promise<MaintenanceResult<InventoryReservationRead>>

  listTransfers(
    query?: InventoryTransferListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryTransferRead>>>
  getTransfer(
    id: number,
  ): Promise<MaintenanceResult<InventoryTransferRead>>

  listStocktakes(
    query?: InventoryStocktakeListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryStocktakeRead>>>
  getStocktake(
    id: number,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>

  createReservation(
    request: InventoryReserveRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  issueReservation(
    id: number,
    request: InventoryReservationIssueRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  releaseReservation(
    id: number,
    request: InventoryReservationReleaseRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  returnReservation(
    id: number,
    request: InventoryReservationReturnRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  cancelReservation(
    id: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>

  previewOperation(
    request: InventoryOperationPreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeOperation(
    transactionId: number,
    request: InventoryOperationExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>
  previewReverse(
    transactionId: number,
    request: InventoryReversePreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeReverse(
    transactionId: number,
    request: InventoryOperationExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>

  createTransfer(
    request: InventoryTransferCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  previewTransferDispatch(
    transferId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeTransferDispatch(
    transferId: number,
    request: InventoryTransferExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  previewTransferReceive(
    transferId: number,
    request: InventoryTransferReceivePreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeTransferReceive(
    transferId: number,
    request: InventoryTransferExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  cancelTransfer(
    transferId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>

  createStocktake(
    request: InventoryStocktakeCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  startStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  updateStocktakeLine(
    stocktakeId: number,
    lineId: number,
    request: InventoryStocktakeCountRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  reviewStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  previewStocktakeConfirm(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeStocktakeConfirm(
    stocktakeId: number,
    request: InventoryStocktakeConfirmExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  rebaseStocktake(
    stocktakeId: number,
    request: InventoryStocktakeRebaseRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  cancelStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
}
```

Produces exact API factory:

```ts
export function createInventoryApi(
  client: InventoryApiClient = defaultInventoryClient,
): InventoryApi
```

with these methods:

```ts
listBalances
getBalance
listTransactions
getTransaction
listReservations
getReservation
listTransfers
getTransfer
listStocktakes
getStocktake

createReservation
issueReservation
releaseReservation
returnReservation
cancelReservation

previewOperation
executeOperation
previewReverse
executeReverse

createTransfer
previewTransferDispatch
executeTransferDispatch
previewTransferReceive
executeTransferReceive
cancelTransfer

createStocktake
startStocktake
updateStocktakeLine
reviewStocktake
previewStocktakeConfirm
executeStocktakeConfirm
rebaseStocktake
cancelStocktake
```

Exact endpoint/method matrix — no path may be inferred during implementation:

| API method | HTTP | Path | Response data |
|---|---|---|---|
| `listBalances` | GET | `/v1/inventory/balances` | `InventoryPage<InventoryBalanceRead>` |
| `getBalance` | GET | `/v1/inventory/balances/{id}` | `InventoryBalanceRead` |
| `listTransactions` | GET | `/v1/inventory/transactions` | `InventoryPage<InventoryTransactionRead>` |
| `getTransaction` | GET | `/v1/inventory/transactions/{id}` | `InventoryTransactionRead` |
| `listReservations` | GET | `/v1/inventory/reservations` | `InventoryPage<InventoryReservationRead>` |
| `getReservation` | GET | `/v1/inventory/reservations/{id}` | `InventoryReservationRead` |
| `listTransfers` | GET | `/v1/inventory/transfers` | `InventoryPage<InventoryTransferRead>` |
| `getTransfer` | GET | `/v1/inventory/transfers/{id}` | `InventoryTransferRead` |
| `listStocktakes` | GET | `/v1/inventory/stocktakes` | `InventoryPage<InventoryStocktakeRead>` |
| `getStocktake` | GET | `/v1/inventory/stocktakes/{id}` | `InventoryStocktakeRead` |
| `createReservation` | POST | `/v1/inventory/reservations` | `InventoryReservationRead` |
| `issueReservation` | POST | `/v1/inventory/reservations/{id}/issue` | `InventoryReservationRead` |
| `releaseReservation` | POST | `/v1/inventory/reservations/{id}/release` | `InventoryReservationRead` |
| `returnReservation` | POST | `/v1/inventory/reservations/{id}/return` | `InventoryReservationRead` |
| `cancelReservation` | POST | `/v1/inventory/reservations/{id}/cancel` | `InventoryReservationRead` |
| `previewOperation` | POST | `/v1/inventory/operations/preview` | `InventoryOperationPreviewRead` |
| `executeOperation` | POST | `/v1/inventory/operations/{transactionId}/execute` | `InventoryTransactionRead` |
| `previewReverse` | POST | `/v1/inventory/operations/{transactionId}/reverse/preview` | `InventoryOperationPreviewRead` |
| `executeReverse` | POST | `/v1/inventory/operations/{transactionId}/reverse/execute` | `InventoryTransactionRead` |
| `createTransfer` | POST | `/v1/inventory/transfers` | `InventoryTransferRead` |
| `previewTransferDispatch` | POST | `/v1/inventory/transfers/{id}/dispatch/preview` | `InventoryOperationPreviewRead` |
| `executeTransferDispatch` | POST | `/v1/inventory/transfers/{id}/dispatch/execute` | `InventoryTransferRead` |
| `previewTransferReceive` | POST | `/v1/inventory/transfers/{id}/receive/preview` | `InventoryOperationPreviewRead` |
| `executeTransferReceive` | POST | `/v1/inventory/transfers/{id}/receive/execute` | `InventoryTransferRead` |
| `cancelTransfer` | POST | `/v1/inventory/transfers/{id}/cancel` | `InventoryTransferRead` |
| `createStocktake` | POST | `/v1/inventory/stocktakes` | `InventoryStocktakeRead` |
| `startStocktake` | POST | `/v1/inventory/stocktakes/{id}/start` | `InventoryStocktakeRead` |
| `updateStocktakeLine` | PATCH | `/v1/inventory/stocktakes/{id}/lines/{lineId}` | `InventoryStocktakeRead` |
| `reviewStocktake` | POST | `/v1/inventory/stocktakes/{id}/review` | `InventoryStocktakeRead` |
| `previewStocktakeConfirm` | POST | `/v1/inventory/stocktakes/{id}/confirm/preview` | `InventoryOperationPreviewRead` |
| `executeStocktakeConfirm` | POST | `/v1/inventory/stocktakes/{id}/confirm/execute` | `InventoryStocktakeRead` |
| `rebaseStocktake` | POST | `/v1/inventory/stocktakes/{id}/rebase` | `InventoryStocktakeRead` |
| `cancelStocktake` | POST | `/v1/inventory/stocktakes/{id}/cancel` | `InventoryStocktakeRead` |

The last 23 rows are writes and each requires a non-empty `Idempotency-Key`. No write uses PUT or DELETE in this phase.

### Task 11A RED

- [ ] **Step 1: Create API test with exact five-list serialization**

The RED test must include assertions equivalent to:

```ts
test('inventory lists serialize only frozen server query fields', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.listBalances({
    page: 2,
    page_size: 100,
    warehouse_id: 7,
    spare_part_id: 41,
    sort_by: 'available_quantity',
    sort_order: 'desc',
  })

  assert.equal(
    calls[0]?.path,
    (
      '/v1/inventory/balances'
      + '?page=2'
      + '&page_size=100'
      + '&warehouse_id=7'
      + '&spare_part_id=41'
      + '&sort_by=available_quantity'
      + '&sort_order=desc'
    ),
  )

  assert.equal(
    JSON.stringify(calls).includes('tenant_id'),
    false,
  )
})
```

Add separate exact-query cases for transactions, reservations, transfers, and stocktakes.

- [ ] **Step 2: Add RED tests for all read detail paths**

Assertions:

```ts
assert.equal(
  pathFor(await api.getBalance(11)),
  '/v1/inventory/balances/11',
)
assert.equal(
  pathFor(await api.getTransaction(12)),
  '/v1/inventory/transactions/12',
)
assert.equal(
  pathFor(await api.getReservation(13)),
  '/v1/inventory/reservations/13',
)
assert.equal(
  pathFor(await api.getTransfer(14)),
  '/v1/inventory/transfers/14',
)
assert.equal(
  pathFor(await api.getStocktake(15)),
  '/v1/inventory/stocktakes/15',
)
```

- [ ] **Step 3: Add RED contract fixture for additive lot concurrency read fields**

The API test fixture must compile as `InventoryBalanceRead` with both matching and fail-closed states:

```ts
const thawedBalance: InventoryBalanceRead = {
  ...balanceFixture,
  id: 11,
  lot_id: 71,
  version: 5,
  lot_version: 9,
  lot_is_frozen: false,
}

const frozenBalance: InventoryBalanceRead = {
  ...balanceFixture,
  id: 12,
  lot_id: 72,
  version: 6,
  lot_version: 10,
  lot_is_frozen: true,
}

const unavailableLotState: InventoryBalanceRead = {
  ...balanceFixture,
  id: 13,
  lot_id: 73,
  version: 7,
  lot_version: null,
  lot_is_frozen: null,
}
```

Assert `getBalance()` and `listBalances()` preserve the values unchanged. The API layer must not synthesize defaults such as `lot_version=1` or `lot_is_frozen=false`.

Also assert the balance list query contract remains unchanged: `lot_version` and `lot_is_frozen` are response-only fields and are not accepted as query or sort keys.

- [ ] **Step 4: Add RED type/runtime tests for fail-closed high-risk preview request construction**

The typed API contract must require a positive `expected_lot_version` for `FREEZE` / `UNFREEZE` at the frontend boundary:

```ts
const freezeRequest: InventoryOperationPreviewRequest = {
  operation_type: 'FREEZE',
  balance_id: 11,
  expected_balance_version: 5,
  reason: 'quality hold',
  deltas: null,
  lot_id: 71,
  expected_lot_version: 9,
}

await api.previewOperation(freezeRequest, 'freeze-preview-key')
```

The test suite must include compile-time assertions (`@ts-expect-error`) proving these are invalid:

```ts
// missing expected_lot_version
{
  operation_type: 'FREEZE',
  balance_id: 11,
  expected_balance_version: 5,
  reason: 'quality hold',
  deltas: null,
  lot_id: 71,
}

// null expected_lot_version
{
  operation_type: 'UNFREEZE',
  balance_id: 12,
  expected_balance_version: 6,
  reason: 'release hold',
  deltas: null,
  lot_id: 72,
  expected_lot_version: null,
}
```

ADJUST remains independent of lot concurrency fields. Do not loosen the union to make the tests compile.

- [ ] **Step 5: Add RED tests proving every write sends explicit Idempotency-Key**

Use a fake client that captures `config.headers`.

Representative assertions:

```ts
await api.createReservation(reserveRequest, 'reserve-key')
await api.previewOperation(operationRequest, 'preview-key')
await api.executeOperation(31, executeRequest, 'execute-key')
await api.createTransfer(transferRequest, 'transfer-key')
await api.updateStocktakeLine(
  21,
  22,
  countRequest,
  'count-key',
)

assert.deepEqual(
  calls.find((call) => call.path === '/v1/inventory/reservations')?.headers,
  { 'Idempotency-Key': 'reserve-key' },
)

assert.deepEqual(
  calls.find((call) =>
    call.path === '/v1/inventory/stocktakes/21/lines/22'
  )?.headers,
  { 'Idempotency-Key': 'count-key' },
)
```

The test must cover all write methods, not only representatives.

- [ ] **Step 6: Add RED test for PATCH transport specifically**

The fake client interface includes:

```ts
patch<T>(
  path: string,
  body: unknown,
  config?: unknown,
): Promise<MaintenanceResult<T>>
```

Assert `updateStocktakeLine()` uses method `PATCH`, not POST.

- [ ] **Step 7: Add RED test for exact decimal-string preservation**

```ts
test('inventory quantities remain exact decimal strings', async () => {
  const request: InventoryReserveRequest = {
    owner_type: 'WORK_ORDER',
    owner_id: 'WO-001',
    spare_part_id: 41,
    warehouse_id: 7,
    requested_quantity: '9007199254740993.1250',
    allow_partial: false,
    expected_balance_versions: { 91: 4 },
    as_of: '2026-08-16',
  }

  const serialized = JSON.stringify(request)
  assert.match(serialized, /9007199254740993\.1250/)
})
```

- [ ] **Step 8: Run Task 11A RED and verify valid failure**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts
```

Expected RED:

- missing `../inventory.ts`, missing exported types/methods, or exact path/header assertion failures;
- no TypeScript syntax failure in test itself;
- no unrelated package/test infrastructure failure.

- [ ] **Step 9: STOP and request Task 11A GREEN approval**

No production file beyond the single new test is allowed in RED.

### Task 11A GREEN

- [ ] **Step 10: Implement `inventory.ts` canonical types and query builders**

Use `buildQuery()` from existing Maintenance client.

Pattern:

```ts
function listPath(
  base: string,
  values: Record<string, string | number | undefined>,
): string {
  const query = buildQuery(values)
  return query ? `${base}?${query}` : base
}
```

Do not include `tenant_id`.

- [ ] **Step 11: Implement normal GET/POST default transport by reusing Maintenance client**

```ts
const defaultInventoryClient: InventoryApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  patch: inventoryPatch,
}
```

- [ ] **Step 12: Implement narrow PATCH adapter without changing shared client**

Inside `inventory.ts` only:

```ts
import { patch as requestPatch } from '@/utils/request'
import {
  normalizeMaintenanceError,
  unwrapMaintenanceResponse,
} from './client'
import type {
  MaintenanceResponse,
  MaintenanceResult,
} from './types'

async function inventoryPatch<T>(
  path: string,
  body: unknown,
  config?: unknown,
): Promise<MaintenanceResult<T>> {
  try {
    const response = await requestPatch<
      MaintenanceResponse<T>
    >(
      `/api/maintenance${path}`,
      body,
      config,
    )
    return unwrapMaintenanceResponse(response)
  } catch (error) {
    throw normalizeMaintenanceError(error)
  }
}
```

No direct transport exception is permitted for any other method unless the same header limitation is demonstrated.

- [ ] **Step 13: Implement exact write paths**

Examples:

```ts
createReservation(request, idempotencyKey) {
  return client.post<InventoryReservationRead>(
    '/v1/inventory/reservations',
    request,
    idempotencyConfig(idempotencyKey),
  )
}

issueReservation(id, request, idempotencyKey) {
  return client.post<InventoryReservationRead>(
    `/v1/inventory/reservations/${identifier(id)}/issue`,
    request,
    idempotencyConfig(idempotencyKey),
  )
}

updateStocktakeLine(
  stocktakeId,
  lineId,
  request,
  idempotencyKey,
) {
  return client.patch<InventoryStocktakeRead>(
    (
      `/v1/inventory/stocktakes/${identifier(stocktakeId)}`
      + `/lines/${identifier(lineId)}`
    ),
    request,
    idempotencyConfig(idempotencyKey),
  )
}
```

Implement all methods listed in Interfaces.

- [ ] **Step 14: Run Task 11A focused GREEN**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts
```

Expected: all Task 11A tests PASS.

- [ ] **Step 15: Run type-check**

```powershell
pnpm --dir frontend run type-check
```

Expected: PASS.

- [ ] **Step 16: Scope check**

```powershell
git diff --check
git status --short
git diff --name-only
```

Expected Task 11A scope only:

```text
frontend/src/api/maintenance/inventory.ts
frontend/src/api/maintenance/__tests__/inventory.test.ts
```

- [ ] **Step 17: STOP for Task 11A review**

Do not commit yet. Task 11 commit occurs only after 11A–11D integrated Gate and separate commit approval.

---

## Task 11B: Five Independent List Slices and Detail Read State

**Files:**

- Create: `frontend/src/stores/maintenance/inventory.ts`
- Create: `frontend/src/stores/maintenance/__tests__/inventory.test.ts`

**Interfaces:**

Produces store state:

```ts
export interface InventoryListSlice<T, Q> {
  items: T[]
  query: Q
  page: number
  pageSize: number
  total: number
  pages: number
  loading: boolean
  error: MaintenanceClientError | null
}

export interface InventoryDetailState<T> {
  item: T | null
  loading: boolean
  error: MaintenanceClientError | null
}
```

Store exports:

```ts
export const useInventoryStore = defineStore(
  'maintenanceInventory',
  () => createInventoryState(),
)
```

Produces read methods:

```ts
fetchBalances
fetchTransactions
fetchReservations
fetchTransfers
fetchStocktakes

fetchBalanceDetail
fetchTransactionDetail
fetchReservationDetail
fetchTransferDetail
fetchStocktakeDetail

collectReservationBalanceVersions
```

### Task 11B RED

- [ ] **Step 1: Write RED test for independent list state**

Create a fake API with controlled promises.

Test:

```ts
test('inventory list slices load independently', async () => {
  const api = controlledInventoryApi()
  const state = createInventoryState(api)

  const balances = state.fetchBalances()
  assert.equal(state.balances.loading, true)
  assert.equal(state.transfers.loading, false)

  api.resolveBalances(pageData([balance(1)]))
  await balances

  assert.equal(state.balances.loading, false)
  assert.deepEqual(state.balances.items.map((item) => item.id), [1])
})
```

- [ ] **Step 2: Write RED test for stale list response generation**

```ts
test('older balance response cannot overwrite newer query state', async () => {
  const api = controlledInventoryApi()
  const state = createInventoryState(api)

  state.balances.query = {
    warehouse_id: 1,
    sort_by: 'id',
    sort_order: 'asc',
  }
  const oldRequest = state.fetchBalances()

  state.balances.query = {
    warehouse_id: 2,
    sort_by: 'id',
    sort_order: 'asc',
  }
  const newRequest = state.fetchBalances()

  api.resolveBalanceCall(1, pageData([balance(200)]))
  await newRequest
  api.resolveBalanceCall(0, pageData([balance(100)]))
  await oldRequest

  assert.deepEqual(
    state.balances.items.map((item) => item.id),
    [200],
  )
})
```

- [ ] **Step 3: Write RED test proving query is forwarded to server without in-memory filtering**

Use fake API capture:

```ts
await state.fetchBalances({
  warehouse_id: 7,
  spare_part_id: 41,
  page: 3,
  page_size: 20,
  sort_by: 'available_quantity',
  sort_order: 'desc',
})

assert.deepEqual(api.balanceQueries[0], {
  warehouse_id: 7,
  spare_part_id: 41,
  page: 3,
  page_size: 20,
  sort_by: 'available_quantity',
  sort_order: 'desc',
})
```

No test or production helper named `sortBalancesLocally` / `filterBalancesLocally` is allowed.

- [ ] **Step 4: Write RED test for independent detail generations**

Resolve older `fetchReservationDetail(1)` after newer `fetchReservationDetail(2)` and assert detail remains ID 2.

Repeat at least one detail test for balance and one aggregate detail; implementation uses separate generation counters per detail domain.

- [ ] **Step 5: Write RED test proving balance detail/list state preserves lot concurrency fields exactly**

Given API responses:

```ts
balance({
  id: 11,
  lot_id: 71,
  version: 5,
  lot_version: 9,
  lot_is_frozen: false,
})
```

assert both `balances.items[0]` and `balanceDetail.item` retain:

```ts
lot_version === 9
lot_is_frozen === false
```

Repeat with:

```ts
lot_version: null
lot_is_frozen: null
```

and assert the Store leaves both values `null`. Store read methods must not normalize null to an executable default.


- [ ] **Step 6: Write RED test for complete reservation candidate version collection**

Because backend FEFO may select any matching candidate, `expected_balance_versions` must cover every matching balance page.

```ts
test('collects reservation balance versions across all server pages', async () => {
  const api = pagedBalanceApi([
    pageData(
      Array.from({ length: 100 }, (_, index) =>
        balance(index + 1, index + 10)
      ),
      { page: 1, pages: 2, total: 101 },
    ),
    pageData(
      [balance(101, 777)],
      { page: 2, pages: 2, total: 101 },
    ),
  ])
  const state = createInventoryState(api)

  const versions = await state.collectReservationBalanceVersions({
    warehouse_id: 7,
    spare_part_id: 41,
    location_id: 3,
  })

  assert.equal(Object.keys(versions).length, 101)
  assert.equal(versions[1], 10)
  assert.equal(versions[101], 777)
  assert.deepEqual(api.balanceQueries, [
    {
      page: 1,
      page_size: 100,
      warehouse_id: 7,
      spare_part_id: 41,
      location_id: 3,
      sort_by: 'id',
      sort_order: 'asc',
    },
    {
      page: 2,
      page_size: 100,
      warehouse_id: 7,
      spare_part_id: 41,
      location_id: 3,
      sort_by: 'id',
      sort_order: 'asc',
    },
  ])
})
```

- [ ] **Step 7: Run Task 11B RED**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: valid missing-store/interface failures.

- [ ] **Step 8: STOP for Task 11B GREEN approval**

### Task 11B GREEN

- [ ] **Step 9: Implement state factory with injected API**

```ts
export function createInventoryState(
  api: InventoryApi = inventoryApi,
) {
  // reactive slices, detail states, generation counters
}
```

Keep testability independent of Pinia installation.

- [ ] **Step 10: Implement five list slices with separate generation counters**

Each method:

1. increments only its domain generation;
2. sets only its domain loading/error;
3. sends frozen query;
4. copies `items/page/page_size/total/pages` from server;
5. ignores stale resolution;
6. normalizes error using existing helper;
7. clears loading only for current generation.

- [ ] **Step 11: Implement five detail loaders with independent generations**

No stale response may overwrite a newer entity.

- [ ] **Step 12: Implement `collectReservationBalanceVersions()`**

Signature:

```ts
async function collectReservationBalanceVersions(
  filters: Pick<
    InventoryBalanceListQuery,
    | 'warehouse_id'
    | 'spare_part_id'
    | 'location_id'
    | 'lot_id'
    | 'serial_item_id'
  >,
): Promise<Record<number, number>>
```

Algorithm:

```ts
const versions: Record<number, number> = {}
let page = 1
let pages = 1

do {
  const response = await api.listBalances({
    ...filters,
    page,
    page_size: 100,
    sort_by: 'id',
    sort_order: 'asc',
  })

  for (const item of response.data.items) {
    versions[item.id] = item.version
  }

  pages = response.data.pages
  page += 1
} while (page <= pages)

return versions
```

This method must not infer FEFO ranks.

- [ ] **Step 13: Run Task 11B GREEN**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: PASS.

- [ ] **Step 14: Run Task 11A + 11B regression and type-check**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts

pnpm --dir frontend run type-check
```

Expected: PASS.

- [ ] **Step 15: Scope check and STOP**

Only Task 11A/11B files plus earlier approved uncommitted Task 11 changes may be modified.

---

## Task 11C: Logical Command and Idempotency Lifecycle

**Files:**

- Modify: `frontend/src/stores/maintenance/inventory.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/inventory.test.ts`

**Interfaces:**

Add:

```ts
export type InventoryCommandKind =
  | 'reservation.create'
  | 'reservation.issue'
  | 'reservation.release'
  | 'reservation.return'
  | 'reservation.cancel'
  | 'operation.preview'
  | 'operation.execute'
  | 'operation.reverse.preview'
  | 'operation.reverse.execute'
  | 'transfer.create'
  | 'transfer.dispatch.preview'
  | 'transfer.dispatch.execute'
  | 'transfer.receive.preview'
  | 'transfer.receive.execute'
  | 'transfer.cancel'
  | 'stocktake.create'
  | 'stocktake.start'
  | 'stocktake.count'
  | 'stocktake.review'
  | 'stocktake.confirm.preview'
  | 'stocktake.confirm.execute'
  | 'stocktake.rebase'
  | 'stocktake.cancel'

export type InventoryCommandState =
  | { phase: 'idle' }
  | {
      phase: 'submitting'
      kind: InventoryCommandKind
      logicalId: string
      idempotencyKey: string
      identity: string
    }
  | {
      phase: 'previewed'
      kind:
        | 'operation.preview'
        | 'operation.reverse.preview'
        | 'transfer.dispatch.preview'
        | 'transfer.receive.preview'
        | 'stocktake.confirm.preview'
      scope: number
      transactionId: number
      transactionVersion: number
      confirmationToken: string
      confirmationExpiresAt: string
    }
  | {
      phase: 'succeeded'
      kind: InventoryCommandKind
      transactionId?: number
    }
  | {
      phase: 'conflicted'
      kind: InventoryCommandKind
      error: MaintenanceClientError
      identity: string
    }
  | {
      phase: 'uncertain'
      kind: InventoryCommandKind
      logicalId: string
      idempotencyKey: string
      identity: string
      error: MaintenanceClientError
    }
```

For `phase: 'previewed'`, `scope` is the authoritative aggregate identifier captured when the preview was created:

```text
operation.preview          -> balance_id
operation.reverse.preview  -> source transaction_id
transfer.dispatch.preview  -> transfer_id
transfer.receive.preview   -> transfer_id
stocktake.confirm.preview  -> stocktake_id
```

The scope is not supplied again by execute callers; it is retained only so the Store can refresh the authoritative aggregate/balance after execution or conflict.

Store adds public command methods corresponding to typed API methods and:

```ts
resetLogicalCommand(): void
```

### Task 11C RED

- [ ] **Step 1: Write RED test for uncertain failure key reuse**

Inject deterministic UUID factory into state:

```ts
const keys = ['uuid-1', 'uuid-2', 'uuid-3']
const state = createInventoryState(
  api,
  () => keys.shift() ?? 'unexpected',
)
```

Test:

```ts
api.createReservation
  .mockRejectedValueOnce({
    code: 'MAINTENANCE_CLIENT_ERROR',
    message: 'network',
    retryable: true,
  })
  .mockResolvedValueOnce(reservationResult)

await assert.rejects(
  state.createReservation(command),
)

assert.equal(state.commandState.phase, 'uncertain')
const firstKey = state.commandState.idempotencyKey

await state.createReservation(command)

assert.equal(api.createReservation.calls[1]?.[1], firstKey)
```

- [ ] **Step 2: Write RED test that changed payload gets a new key**

After uncertain failure, change requested quantity from `5.0000` to `6.0000`; second call must use `uuid-2`, not `uuid-1`.

- [ ] **Step 3: Write RED test for definite conflict**

For normalized conflict:

```ts
{
  status: 409,
  code: 'RESERVATION_STATE_CONFLICT',
  message: 'conflict',
  retryable: false,
  details: {
    expected_version: 3,
    actual_version: 4,
    suggested_action: 'reload_reservation',
  },
}
```

Assert:

- phase becomes `conflicted`;
- original identity is retained for form/context;
- resubmitting corrected payload gets new UUID.

- [ ] **Step 4: Write RED test proving preview and execute use different keys**

```ts
await state.previewOperation(previewCommand)
const previewKey = api.previewOperation.calls[0]?.[1]

await state.executeOperation()
const executeKey = api.executeOperation.calls[0]?.[2]

assert.notEqual(previewKey, executeKey)
```

Execute must read transaction ID/version/token from stored `previewed` state, not from caller-supplied arbitrary token fields.

- [ ] **Step 5: Write RED test for expired preview handling**

Inject clock:

```ts
const now = () => new Date('2026-08-16T12:00:00Z')
```

Given `confirmation_expires_at = '2026-08-16T11:59:59Z'`, `canExecutePreview` must be false and execute method must reject locally without consuming a new server write key.

Backend remains final expiry authority for non-expired client clock state.

- [ ] **Step 6: Write RED test that FREEZE/UNFREEZE execute refreshes authoritative balance instead of optimistic toggling**

For an operation preview scoped to balance `11`, fake a successful execute and controlled refreshes.

Assert call order contains:

```text
executeOperation(...)
fetchTransactionDetail(executedTransactionId)
fetchTransactions(...)
fetchBalances(...)
fetchBalanceDetail(11)
```

The test must assert no Store assignment directly changes:

```ts
balance.lot_is_frozen
balance.lot_version
balance.version
```

The post-execute Freeze/Unfreeze affordance is derived only from the refreshed balance response.

- [ ] **Step 7: Write RED test that lot/balance version conflict retires preview and requires reload + new preview**

Given a normalized non-retryable conflict such as:

```ts
{
  status: 409,
  code: 'INVENTORY_OPERATION_STATE_CONFLICT',
  retryable: false,
  details: {
    conflict_object: 'inventory_lot',
    expected_version: 9,
    actual_version: 10,
    suggested_action: 'reload inventory state and preview again',
  },
}
```

assert:

- the old `previewed` token/version are no longer executable;
- command state becomes `conflicted`;
- `fetchBalanceDetail(scope)` is required before another preview;
- the next preview uses a new idempotency key and whatever `lot_version` the fresh balance returns;
- no automatic retry uses the stale preview payload.


- [ ] **Step 8: Write RED tests for reservation/transfer/stocktake write method mapping**

At minimum assert:

- create/issue/release/return/cancel call matching API functions;
- transfer preview stores preview metadata;
- stocktake count calls PATCH API method through typed API;
- successful mutation replaces detail aggregate when response type is aggregate and triggers relevant list/balance refresh contract.

- [ ] **Step 9: Run Task 11C RED**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: new command-state tests fail for missing behavior only.

- [ ] **Step 10: STOP for Task 11C GREEN approval**

### Task 11C GREEN

- [ ] **Step 11: Add UUID and clock injection**

```ts
export function createInventoryState(
  api: InventoryApi = inventoryApi,
  createUuid: () => string = () => crypto.randomUUID(),
  now: () => Date = () => new Date(),
) {
}
```

- [ ] **Step 12: Implement stable command identity**

Use a deterministic identity builder that serializes only canonical request object + command kind + route aggregate ID.

```ts
function commandIdentity(
  kind: InventoryCommandKind,
  scope: number | string | null,
  payload: unknown,
): string {
  return JSON.stringify([kind, scope, payload])
}
```

Do not include generated UUID or token in the identity of the preview request.

For FREEZE/UNFREEZE, the canonical payload includes `expected_balance_version`, `lot_id`, and `expected_lot_version`; therefore an authoritative reload that changes either version necessarily changes the command identity and forces a new preview idempotency key.

- [ ] **Step 13: Implement key lifecycle**

Rules:

```text
idle/new identity       -> new UUID
submitting same identity -> reject double-submit
uncertain same identity -> reuse same UUID
uncertain changed input -> new UUID
definite conflict        -> corrected/new submit uses new UUID
success                  -> old UUID retired
preview success          -> preview metadata retained, preview UUID retired
execute                  -> new UUID
```

- [ ] **Step 14: Implement preview metadata state**

Normalize backend field names to Store field names only at Store boundary:

```ts
commandState.value = {
  phase: 'previewed',
  kind,
  scope,
  transactionId: response.data.transaction_id,
  transactionVersion: response.data.transaction_version,
  confirmationToken: response.data.confirmation_token,
  confirmationExpiresAt:
    response.data.confirmation_expires_at,
}
```

If backend returns a null token, treat preview as non-executable and surface a definite error; never fabricate token.

- [ ] **Step 15: Implement write refresh rules**

Reservation mutation success:

- replace `reservationDetail.item`;
- refresh reservation list;
- refresh balances.

Transfer mutation success:

- replace `transferDetail.item`;
- refresh transfer list;
- refresh balances after dispatch/receive.

Stocktake mutation success:

- replace `stocktakeDetail.item`;
- refresh stocktake list;
- refresh balances after confirm execute.

High-risk operation success:

- fetch transaction detail;
- refresh transaction list;
- refresh balances;
- for direct `operation.preview`, refresh `balanceDetail` using stored preview `scope` (the originating balance ID);
- only derive the next FREEZE/UNFREEZE control from the refreshed `lot_version` / `lot_is_frozen`.

Do not optimistic-edit quantities, balance versions, lot versions, or lot frozen state. On direct-operation conflict, retire the stale preview metadata and require authoritative balance reload + a new preview.

- [ ] **Step 16: Run Task 11C GREEN + Task 11 regression**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts

pnpm --dir frontend run type-check
```

Expected: PASS.

- [ ] **Step 17: Scope check and STOP**

No Vue/UI/router files may be modified yet.

---

## Task 11D: Permission Matrix Completion

**Files:**

- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`

**Interfaces:**

Add to `MaintenancePermissions`:

```ts
freezeInventory: boolean
reverseInventory: boolean
createStocktake: boolean
confirmStocktake: boolean
```

Role contract:

```text
viewer:
  all four false

contributor:
  createStocktake true
  freezeInventory false
  reverseInventory false
  confirmStocktake false

admin/owner:
  all four true
```

Existing:

- `reserveInventory`, `issueReturnInventory` remain contributor+;
- `transferInventory`, `adjustInventory`, `confirmHighRisk` remain admin+.

`permissions.ts` remains unchanged unless RED proves generic typing is insufficient.

### Task 11D RED

- [ ] **Step 1: Update permission fixtures first**

Every complete `MaintenancePermissions` test fixture must include the four new keys.

- [ ] **Step 2: Add RED role tests**

```ts
test('viewer inventory operations remain read only', () => {
  const value = permissionsForRole('viewer')
  assert.equal(value.createStocktake, false)
  assert.equal(value.freezeInventory, false)
  assert.equal(value.reverseInventory, false)
  assert.equal(value.confirmStocktake, false)
})

test('contributor can create stocktake but not confirm high risk', () => {
  const value = permissionsForRole('contributor')
  assert.equal(value.createStocktake, true)
  assert.equal(value.confirmStocktake, false)
  assert.equal(value.freezeInventory, false)
  assert.equal(value.reverseInventory, false)
})

test('admin and owner receive complete inventory admin capabilities', () => {
  for (const role of ['admin', 'owner'] as const) {
    const value = permissionsForRole(role)
    assert.equal(value.freezeInventory, true)
    assert.equal(value.reverseInventory, true)
    assert.equal(value.createStocktake, true)
    assert.equal(value.confirmStocktake, true)
    assert.equal(value.confirmHighRisk, true)
  }
})
```

- [ ] **Step 3: Run Task 11D RED**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: type/property/assertion failure due missing new permission keys.

- [ ] **Step 4: STOP for Task 11D GREEN approval**

### Task 11D GREEN

- [ ] **Step 5: Modify permission matrix only**

Add new keys to:

- interface;
- denied;
- viewer inheritance;
- contributor;
- admin.

No special-case role code beyond existing hierarchy.

- [ ] **Step 6: Run focused permissions GREEN**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/permissions.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run Task 11 integrated Gate**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts

pnpm --dir frontend run type-check

git diff --check
git status --short
git diff --name-only
```

Expected modified/created Task 11 scope exactly:

```text
frontend/src/api/maintenance/inventory.ts
frontend/src/api/maintenance/__tests__/inventory.test.ts
frontend/src/stores/maintenance/inventory.ts
frontend/src/stores/maintenance/__tests__/inventory.test.ts
frontend/src/stores/maintenance/permission-matrix.ts
frontend/src/stores/maintenance/__tests__/permissions.test.ts
```

plus approved docs files if they were committed earlier; no router/SFC/backend/shared-client change.

- [ ] **Step 8: STOP and request Task 11 feature commit approval**

Suggested commit message:

```text
feat(maintenance): add inventory frontend state
```

Commit approval is separate. No push/PR update after commit.

---

# Task 12 — Activate Inventory Gap Workflows

Task 12 starts only after Task 11 commit is separately approved and verified.

## Task 12A: Five-Tab Workspace, Hidden Routes, i18n, Read-Only Detail Views

**Files:**

- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryReservationDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryTransferDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue`
- Create: `frontend/src/views/maintenance/__tests__/inventory-navigation.test.ts`
- Create: `frontend/src/components/maintenance/inventory/inventory-workflow.ts`
- Create: `frontend/src/components/maintenance/inventory/InventoryListToolbar.vue`
- Create: `frontend/src/components/maintenance/inventory/InventoryBalanceTable.vue`
- Create: `frontend/src/components/maintenance/inventory/__tests__/inventory-gap.test.ts`
- Create: `frontend/src/i18n/locales/maintenance-inventory.ts`
- Create: `frontend/src/i18n/locales/maintenance-inventory.test.ts`
- Modify: four top-level locale files.

**Interfaces:**

Five tabs:

```ts
export type InventoryWorkspaceTab =
  | 'balances'
  | 'reservations'
  | 'transfers'
  | 'stocktakes'
  | 'transactions'

export const INVENTORY_WORKSPACE_TABS = [
  'balances',
  'reservations',
  'transfers',
  'stocktakes',
  'transactions',
] as const
```

Five hidden routes:

```text
maintenanceInventoryBalanceDetail
maintenanceInventoryTransactionDetail
maintenanceInventoryReservationDetail
maintenanceInventoryTransferDetail
maintenanceInventoryStocktakeDetail
```

Paths:

```text
inventory-gap/balances/:balanceId
inventory-gap/transactions/:transactionId
inventory-gap/reservations/:reservationId
inventory-gap/transfers/:transferId
inventory-gap/stocktakes/:stocktakeId
```

All detail route meta:

```ts
{
  ...maintenanceRouteMeta,
  hideInMaintenanceMenu: true,
}
```

### Task 12A RED

- [ ] **Step 1: Write route RED**

`inventory-navigation.test.ts` imports route records and asserts all five paths/names/auth/init/hidden metadata.

Also assert `maintenanceMenuChildren` contains exactly the existing single Inventory Gap top-level entry and none of the five detail names.

- [ ] **Step 2: Write workspace RED**

`inventory-gap.test.ts` reads `InventoryGapPage.vue` and helper source.

Required assertions:

```ts
assert.deepEqual(
  INVENTORY_WORKSPACE_TABS,
  [
    'balances',
    'reservations',
    'transfers',
    'stocktakes',
    'transactions',
  ],
)

assert.match(pageSource, /fetchBalances/)
assert.match(pageSource, /fetchReservations/)
assert.match(pageSource, /fetchTransfers/)
assert.match(pageSource, /fetchStocktakes/)
assert.match(pageSource, /fetchTransactions/)
```

Assert no authoritative unsupported columns:

```ts
assert.doesNotMatch(
  balanceTableSource,
  /\bexpiry\b|\brisk\b|\bdemand gap\b/i,
)
```

`expires_at` remains allowed in reservation views; this assertion is scoped only to balance table source.

- [ ] **Step 3: Write read-only detail wiring RED**

Read each detail SFC and assert it calls only Inventory Store detail methods and does not import:

```text
@/api/maintenance/inventory
@/utils/request
```

Transaction detail source must reference public ledger entries and state-before/state-after evidence.

Balance detail source must reference `lot_version` and `lot_is_frozen` as read-only public evidence and must not contain a local fallback assignment such as `?? 1` or `?? false`.

- [ ] **Step 4: Write i18n locale parity RED**

`maintenance-inventory.ts` exports:

```ts
export const maintenanceInventoryLocales = {
  'en-US': enUS,
  'zh-CN': zhCN,
  'ko-KR': koKR,
  'ru-RU': ruRU,
} as const
```

Test recursive key parity:

```ts
assert.deepEqual(
  deepKeys(maintenanceInventoryLocales['en-US']),
  deepKeys(maintenanceInventoryLocales['zh-CN']),
)
assert.deepEqual(
  deepKeys(maintenanceInventoryLocales['en-US']),
  deepKeys(maintenanceInventoryLocales['ko-KR']),
)
assert.deepEqual(
  deepKeys(maintenanceInventoryLocales['en-US']),
  deepKeys(maintenanceInventoryLocales['ru-RU']),
)
```

- [ ] **Step 5: Run Task 12A RED**

```powershell
pnpm --dir frontend test -- `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts
```

Expected: missing files/routes/module/wiring only.

- [ ] **Step 6: STOP for Task 12A GREEN approval**

### Task 12A GREEN

- [ ] **Step 7: Add modular inventory locale**

Use the same pattern as `maintenance-calculation.ts`.

Each top-level locale file adds:

```ts
import {
  maintenanceInventoryLocales,
} from './maintenance-inventory'
```

and under `maintenance`:

```ts
inventory: maintenanceInventoryLocales['en-US']
```

with matching language key in each locale file.

- [ ] **Step 8: Implement five-tab InventoryGapPage**

Rules:

- default tab balances;
- tab change triggers that slice fetch only when required/explicitly refreshed;
- active slice toolbar renders exact filters and sort options for that domain;
- pagination uses `InventoryPage.pages`;
- no local authoritative filtering/sorting;
- viewer sees no write buttons.

- [ ] **Step 9: Implement shared list toolbar**

Typed props/emits:

```ts
defineProps<{
  loading: boolean
  sortBy: string
  sortOrder: 'asc' | 'desc'
}>()

defineEmits<{
  refresh: []
  sortChange: [
    value: {
      sortBy: string
      sortOrder: 'asc' | 'desc'
    },
  ]
}>()
```

Domain-specific filters remain in page/domain sections so toolbar does not become a generic untyped filter bag.

- [ ] **Step 10: Implement InventoryBalanceTable**

Render only public fields:

- warehouse/location/part IDs;
- lot/serial IDs;
- on-hand;
- reserved;
- damaged;
- quarantined;
- in-transit;
- available;
- version;
- action/open-detail.

Quantities render strings unchanged except cosmetic formatting that does not convert to `number`.

- [ ] **Step 11: Implement five read-only detail views**

Each:

- parse positive numeric route ID;
- calls Store detail loader;
- uses Maintenance header/error/empty/status components;
- displays backend version;
- has back navigation;
- no workflow action yet except read-only navigation.

`InventoryBalanceDetail.vue` additionally renders the public lot concurrency evidence without turning it into an action yet:

```text
lot_id
lot_version
lot_is_frozen
```

When either concurrency field is null, render an unavailable/unknown state rather than coercing it to version `1` or `false`. Task 12C later owns the write affordance.

Transaction detail additionally renders ledger deltas and public before/after JSON.

- [ ] **Step 12: Add five hidden routes after the files exist**

Do not use `meta.hidden`.

- [ ] **Step 13: Run Task 12A GREEN**

```powershell
pnpm --dir frontend test -- `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts

pnpm --dir frontend run type-check
pnpm --dir frontend build
```

Expected:

- focused tests PASS;
- type-check PASS;
- build PASS; existing chunk-size warning may be recorded but is not itself failure.

- [ ] **Step 14: Scope check and STOP**

No reservation/high-risk/transfer/stocktake workflow component implementation yet beyond read-only details.

---

## Task 12B: Reservation Lifecycle and FEFO Allocation Evidence

**Files:**

- Create: `frontend/src/components/maintenance/inventory/ReservationDialog.vue`
- Create: `frontend/src/components/maintenance/inventory/FEFOAllocationEvidence.vue`
- Create: `frontend/src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts`
- Modify: `frontend/src/components/maintenance/inventory/inventory-workflow.ts`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryReservationDetail.vue`
- Modify: inventory locale module as needed.

**Interfaces:**

Pure helper:

```ts
export type ReservationUiAction =
  | 'issue'
  | 'release'
  | 'return'
  | 'cancel'

export function reservationActions(
  status: InventoryReservationStatus,
  permissions: MaintenancePermissions,
): ReservationUiAction[]
```

Expected:

```text
viewer -> []
contributor/admin:
  ACTIVE -> issue, release, cancel
  PARTIALLY_ISSUED -> issue, release, return, cancel
  FULFILLED -> return
  RELEASED/CANCELLED/EXPIRED -> []
```

Backend remains final state authority; this table only controls affordances.

### Task 12B RED

- [ ] **Step 1: Write pure action RED**

Test exact status/capability combinations.

- [ ] **Step 2: Write RED for no client FEFO implementation**

Read source files and assert:

```ts
assert.doesNotMatch(
  reservationSource,
  /sort\(.*expiry|expiry.*sort|selectFefo|rankFefo/i,
)
```

and assert dialog calls Store `collectReservationBalanceVersions`.

- [ ] **Step 3: Write RED for expected version collection before reserve**

The Store test from Task 11B already proves all-page collection. UI source test proves it is used immediately before `createReservation`.

- [ ] **Step 4: Write RED for override reason requirement when lot/serial constraint is intentionally supplied**

Pure helper:

```ts
export function requiresFefoOverrideReason(
  input: {
    lot_id?: number
    serial_item_id?: number
  },
): boolean
```

When constrained lot or serial is present, form submission must require trimmed non-empty `fefo_override_reason`.

Location-only constraint does not automatically mean FEFO deviation.

- [ ] **Step 5: Write RED for FEFO evidence semantics**

`FEFOAllocationEvidence.vue` must read only returned reservation lines:

- `balance_id`;
- `lot_id`;
- `serial_item_id`;
- `reserved_quantity`;
- `fefo_rank`;
- `fefo_override_reason`.

It must not label any pre-submit client list as “server recommendation”.

- [ ] **Step 6: Write RED for return issue-transaction lookup**

Reservation return needs an `issue_transaction_id`. UI must query transactions using server filters:

```ts
{
  operation_type: 'ISSUE',
  reference_type: 'INVENTORY_RESERVATION',
  reference_id: String(reservation.id),
  sort_by: 'id',
  sort_order: 'desc',
  page: 1,
  page_size: 100,
}
```

If more than 100 matching ISSUE transactions exist, paginate all server pages before presenting selector; do not invent a transaction ID.

- [ ] **Step 7: Run Task 12B RED**

```powershell
pnpm --dir frontend test -- `
  src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: missing workflow/helper/component behavior only.

- [ ] **Step 8: STOP for Task 12B GREEN approval**

### Task 12B GREEN

- [ ] **Step 9: Implement ReservationDialog exact string form model**

Use string quantity field:

```ts
interface ReservationForm {
  owner_type: string
  owner_id: string
  spare_part_id: number | null
  warehouse_id: number | null
  requested_quantity: string
  allow_partial: boolean
  as_of: string
  expires_at: string
  location_id: number | null
  lot_id: number | null
  serial_item_id: number | null
  fefo_override_reason: string
}
```

Validate positive decimal with <=4 fraction digits without converting to number:

```ts
const POSITIVE_DECIMAL_18_4 =
  /^(?:0|[1-9]\d{0,13})(?:\.\d{1,4})?$/
```

Additionally reject zero via string normalization helper; backend remains final Numeric(18,4) authority.

- [ ] **Step 10: Implement reserve submission**

Sequence:

1. validate form;
2. collect all matching balance versions through Store;
3. reject locally if version map is empty with user-readable “reload/filter” state;
4. call Store create reservation;
5. render returned FEFO allocation evidence;
6. refresh balance/reservation list.

No FEFO rank is calculated before response.

- [ ] **Step 11: Implement reservation detail ordinary commands**

Issue:

```ts
{
  expected_version: reservation.version,
  lines: [
    {
      reservation_line_id: line.id,
      quantity: '1.0000',
    },
  ],
}
```

Release supports:

- explicit selected lines, or
- `lines: []` for backend “release all remaining” contract.

Cancel:

```ts
{ expected_version: reservation.version }
```

- [ ] **Step 12: Implement return flow**

Load filtered ISSUE transactions for this reservation.

User must choose one issue transaction.

Payload:

```ts
{
  expected_version: reservation.version,
  lines: selectedLines.map((line) => ({
    reservation_line_id: line.id,
    quantity: line.returnQuantity,
    issue_transaction_id: selectedIssueTransactionId,
  })),
}
```

Do not claim frontend can prove per-issue historical line quantity beyond public backend contract.

- [ ] **Step 13: Preserve form/context on conflict**

On normalized conflict:

- keep entered quantities/reason;
- display `expected_version`, `actual_version`, affected lines, `suggested_action` when present;
- offer reload;
- corrected resubmit starts new logical key.

- [ ] **Step 14: Run Task 12B GREEN + regression**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts

pnpm --dir frontend run type-check
```

Expected: PASS.

- [ ] **Step 15: Scope check and STOP**

---

## Task 12C: High-Risk Operations and Two-Stage Transfer

**Files:**

- Create: `frontend/src/components/maintenance/inventory/InventoryOperationPreviewDialog.vue`
- Create: `frontend/src/components/maintenance/inventory/TransferWorkflow.vue`
- Create: `frontend/src/components/maintenance/inventory/__tests__/inventory-operations.test.ts`
- Modify: `frontend/src/components/maintenance/inventory/inventory-workflow.ts`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryTransferDetail.vue`
- Modify: inventory locale module.

**Interfaces:**

Pure helpers:

```ts
export type HighRiskAction =
  | 'adjust'
  | 'freeze'
  | 'unfreeze'
  | 'reverse'

export function canExecuteHighRisk(
  action: HighRiskAction,
  permissions: MaintenancePermissions,
): boolean

export type LotFreezeUiState =
  | {
      available: false
      reason: 'NO_LOT' | 'LOT_CONCURRENCY_UNAVAILABLE'
    }
  | {
      available: true
      action: 'freeze' | 'unfreeze'
      balanceId: number
      balanceVersion: number
      lotId: number
      lotVersion: number
    }

export function lotFreezeUiState(
  balance: InventoryBalanceRead,
): LotFreezeUiState

export function buildLotStatePreviewRequest(
  balance: InventoryBalanceRead,
  reason: string,
): InventoryLotStatePreviewRequest | null
```

`lotFreezeUiState()` is the only UI action derivation for lot freeze state:

```text
lot_id == null                              -> unavailable / NO_LOT
lot_version == null                         -> unavailable / LOT_CONCURRENCY_UNAVAILABLE
lot_is_frozen == null                       -> unavailable / LOT_CONCURRENCY_UNAVAILABLE
lot_is_frozen == false + valid lot_version  -> action=freeze
lot_is_frozen == true + valid lot_version   -> action=unfreeze
```

Exact permission mapping:

```ts
export function canExecuteHighRisk(
  action: HighRiskAction,
  permissions: MaintenancePermissions,
): boolean {
  if (!permissions.confirmHighRisk) return false

  if (action === 'adjust') {
    return permissions.adjustInventory
  }

  if (action === 'freeze' || action === 'unfreeze') {
    return permissions.freezeInventory
  }

  return permissions.reverseInventory
}
```

Backend RBAC remains authoritative; this helper only controls affordances.

Transfer UI actions:

```ts
export type TransferUiAction =
  | 'dispatch'
  | 'receive'
  | 'cancel'

export function transferActions(
  status: InventoryTransferStatus,
  permissions: MaintenancePermissions,
): TransferUiAction[]
```

### Task 12C RED

- [ ] **Step 1: Write RED permission/action tests**

Expected:

```text
DRAFT admin -> dispatch, cancel
DISPATCHED admin -> receive
PARTIALLY_RECEIVED admin -> receive
COMPLETED/CANCELLED -> []
viewer/contributor -> []
```

- [ ] **Step 2: Write RED proving high-risk preview UI is metadata-only**

Read `InventoryOperationPreviewDialog.vue` source and require labels/data bindings for:

- command summary;
- transaction ID;
- operation type;
- transaction version;
- confirmation expiry.

Assert it does not bind nonexistent server fields such as:

```text
preview.before
preview.after
preview.warnings
preview.risks
```

- [ ] **Step 3: Write RED for preview/execute different keys**

Reuse Store test and add UI wiring assertion that execute calls Store method without caller-supplied token text input.

- [ ] **Step 4: Write RED for exact lot concurrency action/payload contract**

Pure helper tests must cover all states:

```ts
assert.deepEqual(
  lotFreezeUiState(balance({
    lot_id: null,
    lot_version: null,
    lot_is_frozen: null,
  })),
  { available: false, reason: 'NO_LOT' },
)

assert.deepEqual(
  lotFreezeUiState(balance({
    lot_id: 71,
    lot_version: null,
    lot_is_frozen: null,
  })),
  {
    available: false,
    reason: 'LOT_CONCURRENCY_UNAVAILABLE',
  },
)

assert.deepEqual(
  lotFreezeUiState(balance({
    id: 11,
    version: 5,
    lot_id: 71,
    lot_version: 9,
    lot_is_frozen: false,
  })),
  {
    available: true,
    action: 'freeze',
    balanceId: 11,
    balanceVersion: 5,
    lotId: 71,
    lotVersion: 9,
  },
)

assert.equal(
  lotFreezeUiState(balance({
    lot_id: 72,
    lot_version: 10,
    lot_is_frozen: true,
  })).action,
  'unfreeze',
)
```

`buildLotStatePreviewRequest()` must produce exactly:

```ts
{
  operation_type: 'FREEZE',
  balance_id: 11,
  expected_balance_version: 5,
  reason: 'quality hold',
  deltas: null,
  lot_id: 71,
  expected_lot_version: 9,
}
```

and map frozen state to `UNFREEZE`.

Also assert:

- `lot_version=null` or `lot_is_frozen=null` returns `null` command;
- no default `expected_lot_version=1`;
- no opposite-state action is exposed;
- no serial-item freeze action exists because current `OperationPreviewCommand` has no `serial_item_id`.

- [ ] **Step 5: Write RED for transfer lifecycle**

Source/pure tests assert:

- create captures exact source balance version;
- dispatch requires preview then execute;
- receive accepts explicit positive line quantities;
- `PARTIALLY_RECEIVED` remains receivable;
- successful execute reloads transfer/balances.

- [ ] **Step 6: Run Task 12C RED**

```powershell
pnpm --dir frontend test -- `
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: valid missing component/helper behavior.

- [ ] **Step 7: STOP for Task 12C GREEN approval**

### Task 12C GREEN

- [ ] **Step 8: Implement adjust and reconciled FREEZE/UNFREEZE command construction**

ADJUST payload:

```ts
{
  operation_type: 'ADJUST',
  balance_id: balance.id,
  expected_balance_version: balance.version,
  reason,
  deltas: {
    on_hand: onHandDelta,
    reserved: reservedDelta,
    damaged: damagedDelta,
    quarantined: quarantinedDelta,
    in_transit: inTransitDelta,
  },
}
```

All delta values remain strings.

For FREEZE/UNFREEZE, never let the component manually assemble the concurrency fields. It must call:

```ts
const state = lotFreezeUiState(balance)
const request = buildLotStatePreviewRequest(balance, reason)
```

The helper produces exactly:

```ts
{
  operation_type:
    balance.lot_is_frozen === false
      ? 'FREEZE'
      : 'UNFREEZE',
  balance_id: balance.id,
  expected_balance_version: balance.version,
  reason,
  deltas: null,
  lot_id: balance.lot_id,
  expected_lot_version: balance.lot_version,
}
```

This construction is allowed only after TypeScript/runtime narrowing proves:

```ts
balance.lot_id !== null
Number.isInteger(balance.lot_id)
balance.lot_id > 0

balance.lot_version !== null
Number.isInteger(balance.lot_version)
balance.lot_version > 0

balance.lot_is_frozen !== null
```

The backend contract already guarantees positive IDs/versions when non-null, but the frontend helper still fails closed on malformed runtime data. If any precondition is unavailable or invalid, disable the action with an explanatory fail-closed state; do not call preview.

The component must not provide separate FREEZE and UNFREEZE buttons at the same time. `lot_is_frozen=false` exposes Freeze only; `lot_is_frozen=true` exposes Unfreeze only.

- [ ] **Step 9: Implement reverse from transaction detail**

Only admin/owner with `reverseInventory && confirmHighRisk`.

Reverse preview payload:

```ts
{
  expected_transaction_version: transaction.version,
  reason,
}
```

Execute consumes Store preview state.

- [ ] **Step 10: Implement metadata-only preview dialog**

Display proposed command separately from server preview metadata.

Never label proposed deltas as server-computed resulting state.

- [ ] **Step 11: Enforce authoritative post-FREEZE/UNFREEZE refresh**

On execute success from a balance detail workflow:

```ts
await inventory.executeOperation()
await inventory.fetchBalanceDetail(balance.id)
await inventory.fetchBalances()
```

If `executeOperation()` already performs one or both refreshes centrally, the component must not duplicate them; the observable contract is that the next rendered Freeze/Unfreeze state comes only after authoritative reload.

Forbidden patterns:

```ts
balance.lot_is_frozen = !balance.lot_is_frozen
balance.lot_version += 1
balance.version += 1
```

A conflict response retires the old preview and triggers reload before the user can preview again.

- [ ] **Step 12: Implement transfer create**

Form:

- source warehouse/location;
- target warehouse/location;
- optional reference type/id;
- reason;
- one or more source balance lines;
- exact string quantities;
- each line uses current `expected_source_version`.

- [ ] **Step 13: Implement dispatch preview/execute**

Preview payload:

```ts
{ expected_version: transfer.version }
```

Execute payload generated by Store from preview metadata:

```ts
{
  transaction_id: preview.transactionId,
  expected_transaction_version:
    preview.transactionVersion,
  confirmation_token:
    preview.confirmationToken,
}
```

- [ ] **Step 14: Implement partial receive preview/execute**

Preview:

```ts
{
  expected_version: transfer.version,
  lines: [
    {
      transfer_line_id: line.id,
      quantity: line.receiveQuantity,
    },
  ],
}
```

Only positive exact-decimal lines are submitted.

After execute, reload aggregate; if status is `PARTIALLY_RECEIVED`, keep receive workflow available.

- [ ] **Step 15: Implement cancel**

```ts
{ expected_version: transfer.version }
```

- [ ] **Step 16: Run Task 12C GREEN + regression**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts

pnpm --dir frontend run type-check
```

Expected: PASS.

- [ ] **Step 17: Verify FREEZE/UNFREEZE concurrency contract end-to-end**

From tests and source confirm all of the following:

```text
read source:
  InventoryBalanceRead.lot_version
  InventoryBalanceRead.lot_is_frozen

null behavior:
  fail closed

action mapping:
  false -> FREEZE
  true  -> UNFREEZE

preview payload:
  expected_balance_version = refreshed balance.version
  lot_id                   = refreshed balance.lot_id
  expected_lot_version     = refreshed balance.lot_version

execute:
  consumes only preview transaction/version/token from Store
  uses a new idempotency key

success:
  authoritative balance detail/list reload
  no optimistic lot toggle/version increment

conflict:
  stale preview retired
  reload required
  new preview required
```

No hard-coded, guessed, private, or audit-derived lot version is allowed. Any mismatch is a STOP condition.

Then scope check and stop for 12D.

---

## Task 12D: Stocktake Lifecycle and Partial Conflict Recovery

**Files:**

- Create: `frontend/src/components/maintenance/inventory/StocktakeWorkflow.vue`
- Create: `frontend/src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts`
- Modify: `frontend/src/components/maintenance/inventory/inventory-workflow.ts`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue`
- Modify: inventory locale module.

**Interfaces:**

Pure helper:

```ts
export type StocktakeUiAction =
  | 'start'
  | 'count'
  | 'review'
  | 'confirm'
  | 'rebase'
  | 'cancel'

export function stocktakeActions(
  status: InventoryStocktakeStatus,
  permissions: MaintenancePermissions,
): StocktakeUiAction[]
```

Expected:

```text
viewer -> []
contributor:
  DRAFT -> start, cancel
  COUNTING -> count, review, cancel
  REVIEWING -> cancel
  CONFLICTED -> rebase, cancel
admin/owner:
  contributor actions +
  REVIEWING -> confirm, cancel
  CONFLICTED -> rebase, confirm when backend state permits
CONFIRMED/CANCELLED -> []
```

Backend final state validation always wins.

### Task 12D RED

- [ ] **Step 1: Write status/action RED**

Test viewer/contributor/admin exact behavior.

- [ ] **Step 2: Write count payload RED**

UI/store must send:

```ts
{
  expected_version: stocktake.version,
  expected_line_version: line.version,
  counted_quantity: '12.5000',
}
```

through the PATCH API with Idempotency-Key.

- [ ] **Step 3: Write RED for adjusted/resolved lines disabled**

Given lines:

```ts
[
  { id: 1, resolution: 'ADJUSTED' },
  { id: 2, resolution: 'CONFLICTED' },
]
```

helper returns only line 2 as rebase-eligible.

No rebase request may include line 1.

- [ ] **Step 4: Write RED for exact rebase actions**

Allowed:

```ts
'RECOUNT'
'BASELINE_ACCEPT'
```

No localized string is used in payload.

- [ ] **Step 5: Write RED for confirm preview/execute metadata flow**

Confirmation execute obtains transaction ID/version/token exclusively from Store previewed state and uses a new idempotency key.

- [ ] **Step 6: Run Task 12D RED**

```powershell
pnpm --dir frontend test -- `
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts
```

Expected: valid missing workflow/helper behavior.

- [ ] **Step 7: STOP for Task 12D GREEN approval**

### Task 12D GREEN

- [ ] **Step 8: Implement create/start/count/review**

Create:

```ts
{
  warehouse_id,
  location_id,
}
```

Start/review:

```ts
{ expected_version: stocktake.version }
```

Count uses stocktake and line versions.

- [ ] **Step 9: Implement confirm preview/execute**

Preview:

```ts
{ expected_version: stocktake.version }
```

Execute from Store preview state:

```ts
{
  transaction_id: preview.transactionId,
  expected_transaction_version:
    preview.transactionVersion,
  confirmation_token:
    preview.confirmationToken,
}
```

- [ ] **Step 10: Implement conflict rendering**

Display public `conflict_details` as structured evidence when object-like; preserve raw safe representation otherwise.

Already resolved/adjusted lines are disabled.

- [ ] **Step 11: Implement rebase only for unresolved conflict lines**

Payload:

```ts
{
  expected_version: stocktake.version,
  lines: selectedConflictLines.map((line) => ({
    line_id: line.id,
    action: line.rebaseAction,
  })),
}
```

Only `RECOUNT | BASELINE_ACCEPT`.

- [ ] **Step 12: Implement cancel**

```ts
{ expected_version: stocktake.version }
```

- [ ] **Step 13: Run Task 12D GREEN**

```powershell
pnpm --dir frontend test -- `
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts

pnpm --dir frontend run type-check
```

Expected: PASS.

---

## Task 12 Integrated Gate

- [ ] **Step 1: Run all Inventory focused frontend tests**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts `
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run Task 11 regressions plus relevant existing navigation/permission tests**

```powershell
pnpm --dir frontend test -- `
  src/stores/maintenance/__tests__/menu.test.ts `
  src/views/maintenance/__tests__/calculation-navigation.test.ts `
  src/views/maintenance/__tests__/demand-list-navigation.test.ts `
  src/views/maintenance/__tests__/master-data-navigation.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run type-check and production build**

```powershell
pnpm --dir frontend run type-check
pnpm --dir frontend build
```

Expected: PASS.

Any chunk-size warning is recorded separately; warning alone is not a failure unless new and materially caused by Inventory implementation.

- [ ] **Step 4: Run source guard scans**

```powershell
git grep -n -E "tenant_id" -- `
  frontend/src/api/maintenance/inventory.ts `
  frontend/src/stores/maintenance/inventory.ts `
  frontend/src/components/maintenance/inventory `
  frontend/src/views/maintenance/inventory-gap

git grep -n -E "localStorage|sessionStorage" -- `
  frontend/src/stores/maintenance/inventory.ts `
  frontend/src/components/maintenance/inventory `
  frontend/src/views/maintenance/inventory-gap

git grep -n -E "selectFefo|rankFefo|sort.*expiry|expiry.*sort" -- `
  frontend/src/components/maintenance/inventory `
  frontend/src/stores/maintenance/inventory.ts
```

Expected:

- no request/body/query `tenant_id` construction in Inventory frontend;
- no idempotency/token persistence;
- no client FEFO implementation.

A type declaration that mirrors backend read-only `tenant_id` in returned read interfaces is allowed; the review must distinguish read type from outbound request use.

- [ ] **Step 5: Diff/scope audit**

```powershell
git diff --check
git status --short
git diff --stat
git diff --name-only
```

Expected: only approved Task 12 frontend files plus any still-uncommitted approved scope.

No backend/shared-client/package dependency changes.

- [ ] **Step 6: STOP and request Task 12 feature commit approval**

Suggested commit message:

```text
feat(maintenance): activate inventory gap workflows
```

Do not push or update PR.

---

# Task 13 — Frontend Gate 2 Closure

Task 13 starts only after Task 12 commit is separately approved and verified.

**Files:**

- Create only after fresh evidence:
  `docs/superpowers/reviews/2026-08-16-maintenance-plan05-04b-frontend-gate.md`

**Interfaces:**

Produces a frontend Gate report that records:

- exact branch/HEAD;
- design SHA;
- Task 11/12 commit SHAs;
- focused test counts;
- full frontend test count;
- type-check result;
- production build result/warnings;
- backend contract audit;
- lot concurrency audit;
- route/permission audit;
- scope audit;
- known residual risks;
- explicit statement that backend was not changed;
- explicit handoff to final Plan 05-4B integration/closure Gate.

### Task 13 Gate

- [ ] **Step 1: Verify clean/staged-empty starting state**

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --name-only
```

Expected clean and staged empty before Gate report creation.

- [ ] **Step 2: Run fresh Inventory focused suite**

```powershell
pnpm --dir frontend test -- `
  src/api/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/inventory.test.ts `
  src/stores/maintenance/__tests__/permissions.test.ts `
  src/views/maintenance/__tests__/inventory-navigation.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts `
  src/components/maintenance/inventory/__tests__/reservation-workflow.test.ts `
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts `
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts `
  src/i18n/locales/maintenance-inventory.test.ts
```

Record exact pass/fail count and elapsed output.

- [ ] **Step 3: Run complete frontend test suite**

```powershell
pnpm --dir frontend test
```

Record exact total/pass/fail count.

- [ ] **Step 4: Run type-check**

```powershell
pnpm --dir frontend run type-check
```

Expected PASS.

- [ ] **Step 5: Run production build**

```powershell
pnpm --dir frontend build
```

Expected PASS.

Record warnings verbatim enough to identify whether they are pre-existing or newly introduced.

- [ ] **Step 6: Exact backend-contract audit**

Check `inventory.ts` against frozen backend source/OpenAPI evidence for:

- five list endpoint paths;
- five detail endpoint paths;
- all 23 write paths/methods;
- Idempotency-Key on every write;
- PATCH stocktake count;
- `InventoryPage` fields (`items/page/page_size/total/pages`);
- list filters/sorts/status enums;
- reservation fields;
- transfer fields;
- stocktake fields;
- preview fields;
- `InventoryBalanceRead.lot_version` and `lot_is_frozen` exact nullable read types;
- no `lot_version` / `lot_is_frozen` list filter or sort;
- FREEZE/UNFREEZE request union requires positive `expected_lot_version`;
- no outbound tenant;
- no private preview fields.

The audit must explicitly confirm frontend does not expect:

```text
balance.expiry
balance.risk
preview.before
preview.after
preview.warnings
preview.risks
```

The audit must also explicitly confirm the lot concurrency contract:

```text
balance.lot_version nullable
balance.lot_is_frozen nullable
null -> no Freeze/Unfreeze command
false -> Freeze only
true -> Unfreeze only
expected_lot_version comes from refreshed balance.lot_version
successful execute -> authoritative balance reload
no local lot_is_frozen toggle
no local version increment
conflict -> stale preview retired, reload + new preview
```

- [ ] **Step 7: Permission audit**

Confirm:

```text
viewer -> read only
contributor -> reservation + contributor stocktake
admin/owner -> contributor + transfer/high-risk/stocktake confirm
```

Confirm high-risk execute requires `confirmHighRisk` plus domain permission.

- [ ] **Step 8: Idempotency audit**

From tests/source confirm:

- uncertain same payload → same key;
- changed payload → new key;
- preview → one key;
- execute → different key;
- no persistence;
- no double submit while submitting;
- token/version only from preview state;
- a stale FREEZE/UNFREEZE preview is never auto-retried after lot/balance version conflict;
- the replacement preview gets a new key after authoritative reload.

- [ ] **Step 9: FEFO authority audit**

Confirm:

- no client FEFO sorter;
- reservation candidate versions collected across all server pages;
- FEFO evidence rendered from returned reservation lines/ranks;
- lot/serial constraint requires override reason in UI;
- backend remains final validator.

- [ ] **Step 10: Repository scope audit**

```powershell
git diff --check
git status --short
git log --oneline --decorate --max-count=12

git diff --name-status `
  952d7ceb13f214a079bb1871191ef27cfcc8db22...HEAD
```

Classify docs vs frontend changes.

Confirm no:

- backend production/test changes after `952d7ceb13f214a079bb1871191ef27cfcc8db22`;
- migration;
- dependency changes;
- shared request/client refactor;
- Plan 05-4C/05-4D code.

- [ ] **Step 11: Create Gate report from fresh evidence only**

Required report sections:

```markdown
# Plan 05-4B Frontend Gate 2 Review

## Baseline
## Approved Design
## Task 11 Commit
## Task 12 Commit
## Focused Inventory Tests
## Full Frontend Tests
## Type Check
## Production Build
## Backend Contract Audit
## Lot Concurrency Audit
## Permission Audit
## Idempotency Audit
## FEFO Authority Audit
## Changed File Scope
## Residual Risks
## Gate Decision
```

Required decision text when all gates pass:

```text
Plan 05-4B Frontend Gate 2: VERIFIED
Backend production changes in frontend phase: NONE
Ready for separately approved final Plan 05-4B integration/closure Gate: YES
PR merge authorization: NO
```

If any Gate fails, report must say NOT VERIFIED and no closure claim may be made.

- [ ] **Step 12: Review report self-consistency**

Check:

```powershell
git diff --check
git diff -- `
  docs/superpowers/reviews/2026-08-16-maintenance-plan05-04b-frontend-gate.md
```

Search report for stale claims or missing command output references.

- [ ] **Step 13: STOP and request Frontend Gate report/commit approval**

Suggested commit message after separate approval:

```text
test(maintenance): close inventory frontend gate
```

No push, PR update, ready, merge, or final Plan 05-4B closure starts automatically.

---

# Final Plan Self-Review Checklist

Before approving this plan for execution, verify:

- [ ] design SHA is exact;
- [ ] backend contract baseline is exact `952d7ceb13f214a079bb1871191ef27cfcc8db22`;
- [ ] current frontend test runner is `tsx --test`, not Vitest;
- [ ] type-check command is `pnpm --dir frontend run type-check`;
- [ ] no new test framework/dependency is introduced;
- [ ] Task 11 can type-check independently because routes are deferred until actual detail views exist in Task 12A;
- [ ] `maintenancePatch()` header limitation is solved inside `inventory.ts`, not by shared-client refactor;
- [ ] five list query matrices map to Task 10.5 exactly;
- [ ] no outbound `tenant_id`;
- [ ] Decimal quantities remain strings;
- [ ] all 23 writes have explicit idempotency key;
- [ ] uncertain failure key retention is tested;
- [ ] changed logical payload key rotation is tested;
- [ ] preview/execute key separation is tested;
- [ ] no token/key persistence;
- [ ] all-page balance-version collection is specified before FEFO reservation;
- [ ] no client FEFO algorithm exists;
- [ ] FEFO evidence comes from returned reservation lines;
- [ ] return flow obtains explicit ISSUE transaction IDs through server transaction filters;
- [ ] balance table omits unsupported expiry/risk/demand-gap authority;
- [ ] preview UI does not expect private rich preview fields;
- [ ] `InventoryBalanceRead` includes exact nullable `lot_version` / `lot_is_frozen` read fields;
- [ ] balance query/sort types do not add `lot_version` / `lot_is_frozen`;
- [ ] lot-only FREEZE/UNFREEZE public limitation is not silently widened;
- [ ] null lot concurrency state fails closed;
- [ ] `lot_is_frozen=false -> FREEZE` and `true -> UNFREEZE`;
- [ ] `expected_lot_version` comes only from current `balance.lot_version`;
- [ ] FREEZE/UNFREEZE success reloads authoritative balance before next affordance;
- [ ] no optimistic `lot_is_frozen` toggle or local lot/balance version increment exists;
- [ ] lot/balance conflict retires preview and requires reload + new preview/new key;
- [ ] stocktake count uses PATCH with Idempotency-Key;
- [ ] stocktake rebase only submits unresolved lines;
- [ ] hidden routes use `hideInMaintenanceMenu`;
- [ ] menu still contains only one Inventory Gap top-level entry;
- [ ] no `manageInventoryPolicies`;
- [ ] backend/Alembic scope is frozen;
- [ ] Task 11/12/13 each stop before commit;
- [ ] commit/push/PR update/ready/merge remain separate approvals;
- [ ] final Plan 05-4B integration/closure remains separately gated.

---

# Approval / Execution Boundary

Approval of this reconciled implementation plan authorizes **only this document as the execution blueprint**.

It does not by itself authorize:

- docs commit;
- Task 11A RED;
- any frontend production modification;
- Task 11A GREEN;
- later RED/GREEN tasks;
- feature commit;
- push;
- PR update;
- PR ready;
- merge;
- final Plan 05-4B closure.

This plan was previously approved in substance. Because the DESIGN/PLAN artifact bytes changed for consistency, the next gate is **explicit re-approval of the new DESIGN and PLAN SHA values**, followed by a separate docs-only commit attempt. Only after that docs commit is verified may Task 11A RED be requested.

The resolved lot-concurrency contract must remain exact during execution:

```text
backend contract baseline = 952d7ceb13f214a079bb1871191ef27cfcc8db22
lot_version               = positive integer | null
lot_is_frozen             = boolean | null
null                       = fail closed
false                      = Freeze only
true                       = Unfreeze only
execute success            = authoritative reload, no optimistic toggle
conflict                   = retire preview, reload, new preview
```

Any backend contract drift or need for a new backend field/endpoint is a STOP condition and returns to design/plan reconciliation rather than being solved ad hoc in frontend code.

No Task 11A test or production code may be written before the plan approval + docs-commit gate are explicitly passed.

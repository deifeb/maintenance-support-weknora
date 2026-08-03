# Plan 05-4B Inventory Operations and Stocktake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 05-4A 权威账本之上交付 FEFO、库存操作、预留与发退料、调拨、冻结、冲销和盘点，并完成可操作的库存缺口前端。

**Architecture:** 纯函数 `FEFOSelector` 产生可解释候选；`InventoryOperationService` 负责 PREVIEWED 到终态的事务编排；`ReservationService` 和 `StocktakeService` 管理各自状态机，但所有余额变化仍委托 05-4A `InventoryTransactionService`。前端用 typed API + Pinia 管理逻辑命令、幂等 key、expected version 和 stale response，页面只编排交互。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、pytest、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 进入条件：05-4A Closure Review 获批，数据库 head 是 `20260803_08`。本阶段 revision 是 `20260803_09`，`down_revision = "20260803_08"`。
- 所有库存变化只能调用 05-4A transaction service；本阶段 service 不直接赋 balance 数量。
- transaction 状态：`PREVIEWED -> COMPLETED | PARTIALLY_COMPLETED | FAILED | EXPIRED | REVERSED`。preview 无副作用，返回确认 token 并有过期时间；execute 必须事务内重算。
- reservation 状态：`ACTIVE -> PARTIALLY_ISSUED -> FULFILLED`，ACTIVE/PARTIALLY_ISSUED 可转 RELEASED/CANCELLED；每条 line 保留 requested/reserved/issued/released。
- stocktake 状态：`DRAFT -> COUNTING -> REVIEWING -> CONFIRMED | CONFLICTED`，DRAFT/COUNTING/REVIEWING/CONFLICTED 可转 CANCELLED；确认后禁止编辑。
- FEFO 先排除过期、冻结、隔离、损坏、拒收、非拣选库位和已预留量，再按有 expiry、expiry date、received date、lot ID、location ID、balance ID 确定性排序；不允许隐式替代或自动抢占。
- contributor 可 reserve/unreserve/issue/return；admin 才可 transfer/freeze/adjust/reverse/stocktake confirm。
- 所有 command 要求 actor tenant、Idempotency-Key、expected version；多余额锁顺序沿用 05-4A。
- 本阶段不实现 demand review 或 allocation rule/plan。

---

## Task 1: 增加 reservation 与 stocktake 持久化模型

**Files:**

- Modify: `extensions/maintenance-api/app/models/inventory_ledger.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260803_09_inventory_operations_stocktake.py`
- Create: `extensions/maintenance-api/tests/migrations/test_inventory_operations_migration.py`
- Create: `extensions/maintenance-api/tests/models/test_inventory_operation_models.py`

- [ ] **Step 1: 写 RED 模型/迁移测试**

断言创建 `inventory_reservations`、`inventory_reservation_lines`、`stocktakes`、`stocktake_lines`；tenant 外键组合一致；幂等/业务唯一约束存在；状态 check constraint 拒绝非法值；upgrade/downgrade/re-upgrade 保持 05-4A 余额和账本不变。

```python
def test_reservation_line_tracks_full_quantity_lifecycle(session, reservation):
    line = InventoryReservationLine(
        tenant_id=reservation.tenant_id,
        reservation_id=reservation.id,
        requested_quantity=Decimal("10"),
        reserved_quantity=Decimal("8"),
        issued_quantity=Decimal("3"),
        released_quantity=Decimal("0"),
        version=1,
    )
    session.add(line)
    session.commit()
    assert line.reserved_quantity - line.issued_quantity == Decimal("5")
```

- [ ] **Step 2: 运行 RED**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_operations_migration.py tests/models/test_inventory_operation_models.py -q
```

- [ ] **Step 3: 写最小模型与 revision `20260803_09`**

Reservation 保存 owner_type/owner_id、status、expires_at、version、actor/request 审计。Line 保存 part、location/lot/serial/balance、四类数量和 expected_balance_version。Stocktake 保存 warehouse/location scope、status、snapshot_at、version；line 保存 system quantity、counted quantity、variance、balance version at snapshot 和 resolution。

- [ ] **Step 4: 运行 GREEN 和迁移往返**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_operations_migration.py tests/models/test_inventory_operation_models.py -q
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_09
.\.venv\Scripts\python.exe -m alembic downgrade 20260803_08
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_09
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models extensions/maintenance-api/alembic/versions/20260803_09_inventory_operations_stocktake.py extensions/maintenance-api/tests/migrations/test_inventory_operations_migration.py extensions/maintenance-api/tests/models/test_inventory_operation_models.py
git commit -m "feat(maintenance): add inventory operation models"
```

## Task 2: 实现确定性 FEFO 与效期规则

**Files:**

- Create: `extensions/maintenance-api/app/services/inventory_fefo_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Modify: `extensions/maintenance-api/app/schemas/inventory_ledger.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_fefo_service.py`

- [ ] **Step 1: 写 RED 表驱动测试**

覆盖：最早有效 expiry 优先；无 expiry 排在有 expiry 后；同日按 received_date/lot ID/location ID/balance ID；过期、冻结、quarantined/damaged/rejected、非 pickable location、错误 serial state 和已预留量被排除；spare-part/category/tenant/default 180/90/30 日阈值优先级；部分拆分；人工改选必须保存推荐项、实际项和原因，否则 `FEFO_OVERRIDE_REASON_REQUIRED`；输入顺序不影响结果。

```python
@pytest.mark.parametrize("requested,expected", [
    (Decimal("3"), [("LOT-A", "3")]),
    (Decimal("7"), [("LOT-A", "5"), ("LOT-B", "2")]),
])
def test_fefo_is_deterministic(requested, expected, candidates):
    result = select_fefo(candidates[::-1], requested, as_of=date(2026, 8, 3))
    assert [(x.lot_code, str(x.quantity)) for x in result.lines] == expected
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_fefo_service.py -q
```

- [ ] **Step 3: 写纯函数选择器**

返回 `FEFOSelection(lines, unfilled_quantity, warnings, excluded)`，每个 excluded item 带稳定 reason code。Repository 只提供 tenant-scoped 候选，不在 SQL 中隐藏业务规则。

```python
eligible.sort(key=lambda row: (
    row.expiry_date is None,
    row.expiry_date or date.max,
    row.received_date,
    row.lot_id or 0,
    row.location_id,
    row.balance_id,
))
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_fefo_service.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/inventory_fefo_service.py extensions/maintenance-api/app/repositories/inventory_ledger_repository.py extensions/maintenance-api/app/schemas/inventory_ledger.py extensions/maintenance-api/tests/services/test_inventory_fefo_service.py
git commit -m "feat(maintenance): add deterministic FEFO selection"
```

## Task 3: 实现库存操作 preview/execute、冻结与冲销

**Files:**

- Create: `extensions/maintenance-api/app/services/inventory_operation_service.py`
- Modify: `extensions/maintenance-api/app/services/inventory_transaction_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_transaction_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_operation_service.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_reversal.py`

- [ ] **Step 1: 写 RED 状态机测试**

覆盖 OPENING_BALANCE/RECEIPT/RESERVE/UNRESERVE/ISSUE/RETURN/TRANSFER/FREEZE/UNFREEZE/ADJUST/REVERSE；preview 无余额/账本副作用并返回只存 hash 的 confirmation token；token 错误/过期 -> EXPIRED；execute 重算后 COMPLETED/PARTIALLY_COMPLETED/FAILED；冻结写零 delta 且 before/after state 改变；admin 调整；reverse 创建补偿 transaction 而非改旧账本；重复 execute/reverse 幂等；版本变化返回 `INVENTORY_VERSION_CONFLICT`。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_operation_service.py tests/services/test_inventory_reversal.py -q
```

- [ ] **Step 3: 写最小编排器**

Operation preview 保存规范化 request 和候选 balance versions。Execute 加锁后重新调用 FEFO/validation，用 transaction service 一次追加全部 entries。Reverse 从原 entry 生成反向 delta，并验证原事务可冲销、未被完整冲销且不会产生负数。

```python
def execute(self, session, actor, transaction_id, expected_version, key):
    preview = self.repo.lock_for_actor(session, actor, transaction_id)
    require_state(preview, "PREVIEWED")
    require_not_expired(preview)
    plan = self.revalidate_and_plan(session, actor, preview)
    return self.tx_service.apply_plan(session, actor, plan, key)
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_operation_service.py tests/services/test_inventory_reversal.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/inventory_operation_service.py extensions/maintenance-api/app/services/inventory_transaction_service.py extensions/maintenance-api/app/repositories/inventory_transaction_repository.py extensions/maintenance-api/tests/services/test_inventory_operation_service.py extensions/maintenance-api/tests/services/test_inventory_reversal.py
git commit -m "feat(maintenance): add inventory operation execution"
```

## Task 4: 实现预留、解预留、发料与退料

**Files:**

- Create: `extensions/maintenance-api/app/repositories/inventory_reservation_repository.py`
- Create: `extensions/maintenance-api/app/services/inventory_reservation_service.py`
- Create: `extensions/maintenance-api/app/schemas/inventory_reservation.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_reservation_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_reservation_repository.py`

- [ ] **Step 1: 写 RED 生命周期测试**

覆盖 FEFO 多批次预留、部分预留、预留使 available 降低但 on_hand 不变、部分 issue 同时减少 on_hand/reserved、release 只减少 reserved、return 增加 on_hand 并保留来源引用、到期取消、serial 单件约束、owner tenant 隔离、重复 key 与 version conflict。

```python
def test_partial_issue_keeps_reservation_active(session, actor_contributor, reservation):
    result = service.issue(
        session, actor_contributor, reservation.id,
        lines=[IssueLine(reservation_line_id=reservation.lines[0].id, quantity="2")],
        expected_version=reservation.version, idempotency_key="issue-1",
    )
    assert result.status == "ACTIVE"
    assert result.lines[0].issued_quantity == Decimal("2")
    assert result.lines[0].reserved_quantity == Decimal("5")
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_reservation_service.py tests/repositories/test_inventory_reservation_repository.py -q
```

- [ ] **Step 3: 写最小 service/repository/schema**

Reserve 在锁内调用 FEFO，并以一个 transaction 增加 reserved；issue/release/return 委托 transaction service。Return 增加 on_hand 并引用原 issue，但不自动恢复已完成预留。Reservation response 包含 line errors，使允许部分结果时明确哪些行未满足；调用方未声明 `allow_partial=true` 时任何不足整体回滚。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_reservation_service.py tests/repositories/test_inventory_reservation_repository.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/inventory_reservation_repository.py extensions/maintenance-api/app/services/inventory_reservation_service.py extensions/maintenance-api/app/schemas/inventory_reservation.py extensions/maintenance-api/tests/services/test_inventory_reservation_service.py extensions/maintenance-api/tests/repositories/test_inventory_reservation_repository.py
git commit -m "feat(maintenance): add inventory reservations and fulfillment"
```

## Task 5: 实现两阶段调拨与盘点

**Files:**

- Create: `extensions/maintenance-api/app/repositories/stocktake_repository.py`
- Create: `extensions/maintenance-api/app/services/stocktake_service.py`
- Create: `extensions/maintenance-api/app/schemas/stocktake.py`
- Modify: `extensions/maintenance-api/app/services/inventory_operation_service.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_transfer_service.py`
- Create: `extensions/maintenance-api/tests/services/test_stocktake_service.py`

- [ ] **Step 1: 写 RED 调拨/盘点测试**

调拨 preview/dispatch 在同一 transfer transaction 写成对 entry：源 balance 减 on_hand、目标 balance 加 in_transit；receive 仍关联该 transaction，成对写目标 in_transit 减少和 on_hand 增加；部分收货保持 PARTIALLY_COMPLETED；任一阶段失败不能留下单边 entry，同 warehouse/location 拒绝。盘点 snapshot 固定 system quantity/version；COUNTING 录入；REVIEWING 计算差异；confirm admin-only，对无冲突行生成 ADJUST transaction，对版本已变化行保留当前余额并将 stocktake 标为 CONFLICTED，要求重新计数或接受新基准。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_transfer_service.py tests/services/test_stocktake_service.py -q
```

- [ ] **Step 3: 写最小实现**

Transfer 在同一个 transaction identity 下追加 dispatch/receive 的成对 ledger entries，并用 transaction version 与状态防止重复接收。Stocktake confirm 按 balance ID 锁定，逐行比较 snapshot version；无冲突行写 adjustment，冲突行不改余额并返回 expected/actual，新状态为 CONFLICTED；全部无冲突时为 CONFIRMED。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_transfer_service.py tests/services/test_stocktake_service.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/stocktake_repository.py extensions/maintenance-api/app/services/stocktake_service.py extensions/maintenance-api/app/schemas/stocktake.py extensions/maintenance-api/app/services/inventory_operation_service.py extensions/maintenance-api/tests/services/test_inventory_transfer_service.py extensions/maintenance-api/tests/services/test_stocktake_service.py
git commit -m "feat(maintenance): add transfers and stocktakes"
```

## Task 6: 暴露 Inventory REST API 与安全合同

**Files:**

- Create: `extensions/maintenance-api/app/api/v1/inventory/__init__.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/router.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/inventory.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/reservations.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/stocktakes.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Create: `extensions/maintenance-api/tests/security/test_inventory_routes_actor_context.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_operations_api.py`

- [ ] **Step 1: 写 RED route inventory/API 测试**

实现规格 11.1 的 list/detail/policies/expiry rules/operations preview+execute+reverse/reservations issue+return+release/transfers/stocktakes routes。逐 route 断言角色、envelope/meta、tenant ownership、Idempotency-Key、expected_version 和错误码。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_inventory_operations_api.py tests/security/test_inventory_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 3: 写薄 route 并注册 `/api/v1/inventory`**

统一 aliases：`ViewerDep`、`ContributorDep`、`AdminDep`、`IdempotencyKeyDep`。Route 只解析 schema、调用 service、用 `success_response(result, actor=actor, version=result.version)`；不自行查 tenant row 或修改 model。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_inventory_operations_api.py tests/security/test_inventory_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api/v1/inventory extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/tests/api/test_inventory_operations_api.py extensions/maintenance-api/tests/security/test_inventory_routes_actor_context.py extensions/maintenance-api/tests/security/test_api_rbac.py
git commit -m "feat(maintenance): expose inventory operations API"
```

## Task 7: 建立前端 typed API、Store 与轮询安全

**Files:**

- Create: `frontend/src/api/maintenance/inventory.ts`
- Create: `frontend/src/api/maintenance/__tests__/inventory.test.ts`
- Create: `frontend/src/stores/maintenance/inventory.ts`
- Create: `frontend/src/stores/maintenance/__tests__/inventory.test.ts`
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`

- [ ] **Step 1: 写 RED API/Store 测试**

断言路径和 query encoding；所有 command 带 Idempotency-Key/expected_version；相同逻辑点击复用 key，成功/明确 4xx 后轮换，不确定 5xx 保留；旧响应不覆盖新筛选；dispose 中止/失效 pending 请求；权限与后端角色一致。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/inventory.test.ts src/stores/maintenance/__tests__/inventory.test.ts
```

- [ ] **Step 3: 写最小 API/Store**

沿用 `frontend/src/api/maintenance/demand-lists.ts` 的 client 注入与 `frontend/src/stores/maintenance/demandList.ts` 的 request generation 模式。Store 暴露 list/detail/preview/execute/reserve/issue/return/release/transfer/stocktake commands；不存 tenant。

- [ ] **Step 4: 运行 GREEN 和 typecheck**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/inventory.test.ts src/stores/maintenance/__tests__/inventory.test.ts
pnpm --dir frontend typecheck
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/inventory.ts frontend/src/api/maintenance/__tests__/inventory.test.ts frontend/src/stores/maintenance/inventory.ts frontend/src/stores/maintenance/__tests__/inventory.test.ts frontend/src/stores/maintenance/permission-matrix.ts
git commit -m "feat(maintenance): add inventory frontend state"
```

## Task 8: 激活 Inventory Gap 与隐藏库存详情页面

**Files:**

- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/StocktakeDetail.vue`
- Create: `frontend/src/components/maintenance/inventory/InventorySummaryTable.vue`
- Create: `frontend/src/components/maintenance/inventory/InventoryOperationDialog.vue`
- Create: `frontend/src/components/maintenance/inventory/ReservationPanel.vue`
- Create: `frontend/src/components/maintenance/inventory/StocktakePanel.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Create: `frontend/src/views/maintenance/__tests__/inventory-navigation.test.ts`
- Create: `frontend/src/components/maintenance/inventory/__tests__/inventory-workflow.test.ts`

- [ ] **Step 1: 写 RED 组件/导航测试**

覆盖 server-side filter/page、available/expiry/warning 展示、viewer 只读、contributor 预留/发退料、admin 调拨/冻结/调整/冲销/盘点确认、preview 二次确认、结构化冲突保留输入；三个隐藏路由 `/platform/maintenance/inventory-gap/balances/:balanceId`、`/transactions/:transactionId`、`/stocktakes/:stocktakeId` 均可直达且不增加菜单项。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/inventory-navigation.test.ts src/components/maintenance/inventory/__tests__/inventory-workflow.test.ts
```

- [ ] **Step 3: 写最小 UI**

使用 TDesign Table/Dialog/Drawer/Tag；所有状态判断使用英文枚举，不比较中文标签。页面 mounted load、route param 同步和 unmount dispose；表单提交调用 Store command，不拼 tenant/idempotency header。

- [ ] **Step 4: 运行 GREEN、typecheck、build**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/inventory-navigation.test.ts src/components/maintenance/inventory/__tests__/inventory-workflow.test.ts
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/maintenance/inventory-gap frontend/src/components/maintenance/inventory frontend/src/router/maintenance.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/views/maintenance/__tests__/inventory-navigation.test.ts
git commit -m "feat(maintenance): add inventory operations workspace"
```

## Task 9: 05-4B 集成 Gate 与关闭复审

**Files:**

- Create: `extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py`
- Create: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04b-closure-review.md`

- [ ] **Step 1: 写 RED 端到端工作流**

创建两批次和一个序列件，API preview/reserve/partial issue/return/release；执行 dispatch/partial receive；冻结/解冻；并发改变后 stocktake confirm 冲突。逐步断言余额守恒、ledger linkage、状态与稳定错误。

- [ ] **Step 2: 运行并修复集成 wiring**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_inventory_operations_workflow.py -q
```

- [ ] **Step 3: 运行完整阶段 Gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_operations_migration.py tests/services/test_inventory_fefo_service.py tests/services/test_inventory_operation_service.py tests/services/test_inventory_reversal.py tests/services/test_inventory_reservation_service.py tests/services/test_inventory_transfer_service.py tests/services/test_stocktake_service.py tests/api/test_inventory_operations_api.py tests/security/test_inventory_routes_actor_context.py tests/security/test_api_rbac.py tests/integration/test_inventory_operations_workflow.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
cd ..\..
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

预期：唯一 head `20260803_09`；后端/前端全量、typecheck、production build 全绿。

- [ ] **Step 4: 审查、验证、提交 Closure Review**

使用 `superpowers:requesting-code-review`，处理意见后使用 `superpowers:verification-before-completion` 重跑新鲜 Gate。Review 记录 FEFO 确定性、事务守恒、RBAC、页面权限和 build 证据。

```powershell
git add extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py docs/superpowers/reviews/2026-08-03-maintenance-plan05-04b-closure-review.md
git commit -m "test(maintenance): close plan05-4b inventory operations"
git status --short
```

- [ ] **Step 5: 停止并请求批准**

等待用户分别批准 05-4B push/PR 更新及进入 05-4C；不得自动开始 demand review。

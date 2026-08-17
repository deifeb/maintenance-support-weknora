# Plan 05-4B Inventory Operations and Stocktake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已关闭的 05-4A 权威库存账本上交付 FEFO、统一多余额事务、预留与发退料、两阶段调拨、冻结/调整/冲销、盘点、到期释放和可操作的 Inventory Gap 前端。

**Architecture:** `FEFOSelector` 是无数据库副作用的确定性选择器；reservation、transfer、stocktake 和高风险 operation service 负责领域状态机，但只生成 `InventoryMutationPlan`。所有余额、lot/serial 受审计状态和 ledger entry 由扩展后的 `InventoryTransactionService.apply_plan()` 在固定锁顺序下原子写入。05-4B 作为一个阶段交付，但设后端 Gate 1、前端 Gate 2 和统一集成 Gate。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic、pytest、Ruff、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 权威规格：`docs/superpowers/specs/2026-08-04-maintenance-plan05-04b-inventory-operations-design.md`。
- 进入基线：`feature/maintenance-frontend-plan05` 必须包含 05-4A merge commit `d75ff6b4d0b6467ee7c111316570292976e897b7`；不得从旧提交 `7fad43355e204e8980b8226df713e4800e6e8057` 开始。
- 迁移固定为 `20260803_11`，`down_revision = "20260803_10"`；05-4C/05-4D 保留 `20260803_12`/`20260803_13`。
- 所有库存数量变化只通过 `InventoryTransactionService.apply_plan()`；领域 service、API、worker 和前端不得直接写 balance 数量。
- 普通命令 `RESERVE/UNRESERVE/ISSUE/RETURN` 直接执行；`TRANSFER_DISPATCH/TRANSFER_RECEIVE/FREEZE/UNFREEZE/ADJUST/REVERSE/STOCKTAKE_CONFIRM` 强制 preview → execute。
- 预留默认全量满足；只有显式 `allow_partial=true` 允许部分预留。
- FEFO 偏离允许 contributor/admin，但必须记录推荐、实际选择和非空原因。
- 盘点允许部分确认；冲突行不改库存，已成功行不得重复调整。
- 到期预留由后台任务和请求惰性检查共同释放，使用同一 service 和稳定幂等 key。
- 请求 tenant 只能来自 `ActorContext.tenant_id`；禁止接受 query/body tenant ID。
- 每个写命令必须有 `Idempotency-Key`、版本前置条件、事务内重校验、响应快照和追加式审计。
- PostgreSQL 路径按 balance ID 升序 `SELECT ... FOR UPDATE`；SQLite 测试使用 barrier/双 session/唯一约束验证等价冲突语义，禁止用 `sleep` 猜竞争结果。
- 本地 Closure 不要求真实 PostgreSQL，但生产部署状态必须保持 blocked，直至真实 PostgreSQL Gate 通过。
- 不触碰主工作树已有未跟踪文件；不清理保留的 05-4A 工作树或 `codex/maintenance-plan05-4`。
- 计划批准不等于批准实现。开始实施、每个 task commit、push、PR 创建/更新/合并均需分别明确批准。

---

## File Map

### 后端新文件

- `extensions/maintenance-api/app/schemas/inventory_operation.py`：mutation plan、preview/execute 公共内部类型。
- `extensions/maintenance-api/app/schemas/inventory_reservation.py`：reservation command/read schema。
- `extensions/maintenance-api/app/schemas/inventory_transfer.py`：transfer command/read schema。
- `extensions/maintenance-api/app/schemas/inventory_stocktake.py`：stocktake command/read schema。
- `extensions/maintenance-api/app/repositories/inventory_reservation_repository.py`：reservation 聚合锁定、查询与状态持久化。
- `extensions/maintenance-api/app/repositories/inventory_transfer_repository.py`：transfer 聚合锁定、查询与 target balance resolution。
- `extensions/maintenance-api/app/repositories/inventory_stocktake_repository.py`：stocktake 聚合锁定、行查询与状态持久化。
- `extensions/maintenance-api/app/services/inventory_fefo_service.py`：确定性 FEFO 纯函数与选择结果。
- `extensions/maintenance-api/app/services/inventory_reservation_service.py`：reserve/release/issue/return/expire。
- `extensions/maintenance-api/app/services/inventory_transfer_service.py`：create/dispatch/receive/cancel。
- `extensions/maintenance-api/app/services/inventory_stocktake_service.py`：create/start/count/review/confirm/rebase/cancel。
- `extensions/maintenance-api/app/services/inventory_operation_service.py`：高风险 preview/execute、freeze/unfreeze/adjust/reverse。
- `extensions/maintenance-api/app/workers/inventory_reservation_expiry.py`：分批到期释放入口。
- `extensions/maintenance-api/app/api/v1/inventory/`：router、queries、reservations、operations、transfers、stocktakes。
- `extensions/maintenance-api/alembic/versions/20260803_11_inventory_operations_stocktake.py`：六张操作表与约束。

### 后端修改文件

- `extensions/maintenance-api/app/models/inventory_ledger.py`：新增六个 ORM model 与状态常量。
- `extensions/maintenance-api/app/models/__init__.py`：导出新 model。
- `extensions/maintenance-api/app/schemas/inventory_ledger.py`：扩展 operation type、transaction read/preview read，保持 05-4A 兼容。
- `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`：候选查询、固定顺序锁、target balance resolution 所需读取。
- `extensions/maintenance-api/app/repositories/inventory_transaction_repository.py`：PREVIEWED 创建/锁定/终态、N entry append。
- `extensions/maintenance-api/app/services/inventory_transaction_service.py`：`apply_plan()`，并把 opening/adjust 迁移到 plan。
- `extensions/maintenance-api/app/api/v1/router.py`：注册 inventory router。
- `extensions/maintenance-api/app/security/permissions.py`：仅在现有 permission helper 需要扩展时修改。
- `extensions/maintenance-api/app/workers/task_registry.py`：新增 reservation expiry registry，避免同进程重复批次。

### 前端新文件

- `frontend/src/api/maintenance/inventory.ts`：typed API。
- `frontend/src/stores/maintenance/inventory.ts`：query/detail/command state 与幂等 key 生命周期。
- `frontend/src/components/maintenance/inventory/`：FEFO、reservation、transfer、stocktake、preview confirmation 组件。
- `frontend/src/views/maintenance/inventory-gap/InventoryBalanceDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransactionDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryReservationDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryTransferDetail.vue`
- `frontend/src/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue`

### 前端修改文件

- `frontend/src/api/maintenance/types.ts`：仅放跨模块共享 envelope 类型；inventory 领域类型留在 `inventory.ts`。
- `frontend/src/stores/maintenance/permission-matrix.ts`：增加五个细粒度 inventory permission。
- `frontend/src/stores/maintenance/permissions.ts`：映射和 helper。
- `frontend/src/router/maintenance.ts`：Inventory Gap 与五个隐藏详情路由。
- `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`：替换占位页。
- `frontend/src/i18n/locales/maintenance-inventory.ts` 或现有 maintenance locale registry：库存文案，不作为状态判断来源。

## Execution Preflight

开始实现前执行；任何一项不满足都停止，不创建代码变更：

```powershell
$repoRoot = "E:\weknora_projects\maintenance-support-weknora"
$target = "feature/maintenance-frontend-plan05"
$requiredAncestor = "d75ff6b4d0b6467ee7c111316570292976e897b7"

& git.exe -C $repoRoot rev-parse --verify $requiredAncestor
if ($LASTEXITCODE -ne 0) { throw "缺少已批准的 05-4A merge commit" }

$targetHead = (& git.exe -C $repoRoot rev-parse $target).Trim()
if ($LASTEXITCODE -ne 0) { throw "无法解析目标分支" }

& git.exe -C $repoRoot merge-base --is-ancestor $requiredAncestor $targetHead
if ($LASTEXITCODE -ne 0) { throw "目标分支不包含 05-4A closure merge" }

& git.exe -C $repoRoot status --short
& git.exe -C $repoRoot worktree list --porcelain
```

随后使用 `superpowers:using-git-worktrees` 创建独立 05-4B 工作树。推荐分支 `codex/maintenance-plan05-4b`，推荐目录 `.worktrees/maintenance-plan05-4b`；实际创建动作需用户单独批准。

---

### Task 1: 建立 05-4B 持久化模型与迁移

**Files:**

- Modify: `extensions/maintenance-api/app/models/inventory_ledger.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260803_11_inventory_operations_stocktake.py`
- Create: `extensions/maintenance-api/tests/models/test_inventory_operation_models.py`
- Create: `extensions/maintenance-api/tests/migrations/test_inventory_operations_migration.py`

**Interfaces:**

- Produces: `InventoryReservation`, `InventoryReservationLine`, `InventoryTransfer`, `InventoryTransferLine`, `InventoryStocktake`, `InventoryStocktakeLine`。
- Produces status constants: `RESERVATION_STATUSES`, `TRANSFER_STATUSES`, `STOCKTAKE_STATUSES`, `STOCKTAKE_LINE_RESOLUTIONS`。
- Migration head after task: `20260803_11`。

- [ ] **Step 1: 写模型 RED 测试**

```python
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryReservationLine


def test_reservation_line_enforces_quantity_lifecycle(session, reservation):
    line = InventoryReservationLine(
        tenant_id=reservation.tenant_id,
        reservation_id=reservation.id,
        spare_part_id=1,
        balance_id=1,
        requested_quantity=Decimal("5.0000"),
        reserved_quantity=Decimal("4.0000"),
        issued_quantity=Decimal("3.0000"),
        released_quantity=Decimal("2.0000"),
        expected_balance_version=1,
        fefo_rank=1,
        version=1,
    )
    session.add(line)
    with pytest.raises(IntegrityError):
        session.commit()
```

同时写 transfer 超收、stocktake resolution 非法、serial 数量非 0/1、跨租户组合引用拒绝测试。

- [ ] **Step 2: 运行 RED 并保存输出**

```powershell
cd extensions/maintenance-api
$python = ".\.venv\Scripts\python.exe"
& $python -m pytest tests/models/test_inventory_operation_models.py -q
```

Expected: collection/import 或 table/model missing 导致失败；不得因 fixture 或语法错误失败。

- [ ] **Step 3: 写 migration RED 测试**

测试必须：从 `20260803_10` 写入 05-4A balance/transaction/ledger 样本，upgrade 到 `20260803_11`，验证六张表、check/unique/index，插入操作样本；清空 05-4B 业务数据后 downgrade，验证 05-4A 样本 hash 不变；重新 upgrade 并验证单 head。另写存在 05-4B 数据时 downgrade 拒绝测试和 PostgreSQL DDL 编译测试。

```python
def test_inventory_operations_revision_chain(alembic_script):
    revision = alembic_script.get_revision("20260803_11")
    assert revision.down_revision == "20260803_10"
    assert alembic_script.get_heads() == ["20260803_11"]
```

- [ ] **Step 4: 实现 ORM 与 revision**

模型字段和状态严格复制设计规格第 6 节。所有 Decimal 使用 `Numeric(18, 4)`；所有 tenant-scoped 聚合和 line 都有 `tenant_id`；业务引用使用 `RESTRICT`；status 用 non-native enum/check；常用过滤列建立索引。

迁移 downgrade 开头执行数据存在检查：

```python
def _assert_no_inventory_operation_data() -> None:
    bind = op.get_bind()
    tables = (
        "inventory_reservation_lines",
        "inventory_reservations",
        "inventory_transfer_lines",
        "inventory_transfers",
        "stocktake_lines",
        "stocktakes",
    )
    for table_name in tables:
        count = bind.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
        if int(count or 0) > 0:
            raise CommandError(
                "cannot downgrade inventory operations while 05-4B business data exists"
            )
```

- [ ] **Step 5: 运行 GREEN 与迁移往返**

```powershell
& $python -m pytest tests/models/test_inventory_operation_models.py tests/migrations/test_inventory_operations_migration.py -q
& $python -m alembic upgrade 20260803_11
& $python -m alembic downgrade 20260803_10
& $python -m alembic upgrade 20260803_11
& $python -m alembic heads
```

Expected: tests PASS；唯一 head 为 `20260803_11`。

- [ ] **Step 6: 范围审查并停止**

```powershell
& git.exe diff --check
& git.exe status --short
& git.exe diff -- extensions/maintenance-api/app/models extensions/maintenance-api/alembic/versions/20260803_11_inventory_operations_stocktake.py extensions/maintenance-api/tests/models/test_inventory_operation_models.py extensions/maintenance-api/tests/migrations/test_inventory_operations_migration.py
```

输出 review bundle，等待用户批准 Task 1。只有单独批准 commit 后才执行：

```powershell
& git.exe add extensions/maintenance-api/app/models extensions/maintenance-api/alembic/versions/20260803_11_inventory_operations_stocktake.py extensions/maintenance-api/tests/models/test_inventory_operation_models.py extensions/maintenance-api/tests/migrations/test_inventory_operations_migration.py
& git.exe commit -m "feat(maintenance): add inventory operation models"
```

---

### Task 2: 扩展统一多余额事务内核

**Files:**

- Create: `extensions/maintenance-api/app/schemas/inventory_operation.py`
- Modify: `extensions/maintenance-api/app/schemas/inventory_ledger.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_transaction_repository.py`
- Modify: `extensions/maintenance-api/app/services/inventory_transaction_service.py`
- Create: `extensions/maintenance-api/tests/schemas/test_inventory_operation_schemas.py`
- Modify: `extensions/maintenance-api/tests/services/test_inventory_transaction_service.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_mutation_plan.py`

**Interfaces:**

- Produces: `InventoryStateMutation`, `InventoryBalanceMutation`, `InventoryMutationPlan`。
- Produces: `InventoryTransactionService.apply_plan(session, actor, *, plan, idempotency_key, required_role, terminal_status)`。
- Preserves: `opening()` and `adjust()` signatures and 05-4A idempotent response shape。

- [ ] **Step 1: 写 schema RED**

```python
from app.schemas.inventory_operation import (
    InventoryBalanceMutation,
    InventoryMutationPlan,
)
from app.schemas.inventory_ledger import InventoryQuantityDelta


def test_plan_normalizes_balance_lock_order():
    plan = InventoryMutationPlan(
        operation_type="TRANSFER_DISPATCH",
        reason="dispatch transfer",
        mutations=(
            InventoryBalanceMutation(
                balance_id=20,
                expected_version=3,
                deltas=InventoryQuantityDelta(in_transit="2"),
            ),
            InventoryBalanceMutation(
                balance_id=10,
                expected_version=4,
                deltas=InventoryQuantityDelta(on_hand="-2"),
            ),
        ),
    )
    assert [item.balance_id for item in plan.mutations] == [10, 20]
```

另测重复 balance、纯零数量无 state mutation、非法 operation type、冻结全零但有 state mutation。

- [ ] **Step 2: 写 service RED**

覆盖多余额成功、固定锁顺序、任一 mutation 失败整体回滚、ledger/balance 一致、state mutation 原子性、幂等重放、same key/different hash、winner recovery、expected version 冲突、opening/adjust 回归。

```python
def test_apply_plan_rolls_back_all_balances_on_second_conflict(
    session, actor_admin, balance_a, balance_b, service
):
    before_a = balance_a.on_hand_quantity
    before_b = balance_b.in_transit_quantity
    plan = build_dispatch_plan(
        source=balance_a,
        target=balance_b,
        quantity="2",
        target_expected_version=balance_b.version + 1,
    )
    with pytest.raises(ConflictError):
        service.apply_plan(
            session,
            actor_admin,
            plan=plan,
            idempotency_key="dispatch-conflict",
            required_role=MaintenanceRole.ADMIN,
        )
    session.expire_all()
    assert balance_a.on_hand_quantity == before_a
    assert balance_b.in_transit_quantity == before_b
```

- [ ] **Step 3: 运行 RED**

```powershell
& $python -m pytest tests/schemas/test_inventory_operation_schemas.py tests/services/test_inventory_mutation_plan.py tests/services/test_inventory_transaction_service.py -q
```

Expected: 新类型或 `apply_plan` 缺失导致失败；现有 transaction 测试仍可收集。

- [ ] **Step 4: 实现 schema、repository 与 `apply_plan()`**

`InventoryLedgerRepository.lock_balances()` 必须把去重后的 IDs 排序，并验证返回 IDs 完整匹配；`InventoryTransactionRepository` 增加一次 append N entries 的方法，但每条 entry 仍独立不可变。

核心循环：

```python
locked_by_id = {
    balance.id: balance
    for balance in self.ledger_repository.lock_balances(
        session,
        actor.tenant_id,
        [mutation.balance_id for mutation in plan.mutations],
    )
}
for mutation in plan.mutations:
    balance = locked_by_id[mutation.balance_id]
    self._require_version(actor, balance, expected_version=mutation.expected_version)
    before_values = self._balance_values(balance)
    after_values = tuple(
        current + delta
        for current, delta in zip(
            before_values,
            self._delta_values(mutation.deltas),
            strict=True,
        )
    )
    self._validate_result(after_values)
```

把 state mutation 校验和写入放在 transaction/ledger 创建前，任何异常由 nested transaction 回滚。响应快照必须按 balance ID 顺序稳定。

- [ ] **Step 5: 把 opening/adjust 改为单 plan 适配器**

`opening()` 仍要求 contributor；`adjust()` 仍要求 admin；错误码和响应 shape 不变。原 `_apply_quantity_operation()` 可以保留为 thin wrapper 或删除，但不得保留第二套 balance 写逻辑。

- [ ] **Step 6: 运行 GREEN 与 05-4A 定向回归**

```powershell
& $python -m pytest tests/schemas/test_inventory_operation_schemas.py tests/services/test_inventory_mutation_plan.py tests/services/test_inventory_transaction_service.py tests/repositories/test_inventory_ledger_immutability.py tests/api/test_inventory_ledger_api.py -q
& $python -m ruff check app/schemas/inventory_operation.py app/services/inventory_transaction_service.py app/repositories/inventory_ledger_repository.py app/repositories/inventory_transaction_repository.py tests/schemas/test_inventory_operation_schemas.py tests/services/test_inventory_mutation_plan.py tests/services/test_inventory_transaction_service.py
```

- [ ] **Step 7: 范围审查并停止，等待 Task 2 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "refactor(maintenance): add multi-balance inventory plans"
```

---

### Task 3: 实现确定性 FEFO 与可解释候选

**Files:**

- Create: `extensions/maintenance-api/app/services/inventory_fefo_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_fefo_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_fefo_candidates.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class FEFOCandidate:
    balance_id: int
    location_id: int
    lot_id: int | None
    serial_item_id: int | None
    expiry_date: date | None
    received_date: date | None
    available_quantity: Decimal
    exclusion_facts: tuple[str, ...]

@dataclass(frozen=True)
class FEFOSelectionLine:
    balance_id: int
    quantity: Decimal
    rank: int

@dataclass(frozen=True)
class FEFOSelection:
    lines: tuple[FEFOSelectionLine, ...]
    unfilled_quantity: Decimal
    warnings: tuple[str, ...]
    excluded: tuple[FEFOExcludedCandidate, ...]

select_fefo(
    candidates: Sequence[FEFOCandidate],
    requested_quantity: Decimal,
    *,
    as_of: date,
) -> FEFOSelection
```

- [ ] **Step 1: 写表驱动 RED**

```python
@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (Decimal("3.0000"), [(11, "3.0000")]),
        (Decimal("7.0000"), [(11, "5.0000"), (12, "2.0000")]),
    ],
)
def test_fefo_is_deterministic(requested, expected, candidates):
    result = select_fefo(tuple(reversed(candidates)), requested, as_of=date(2026, 8, 4))
    assert [(line.balance_id, format(line.quantity, ".4f")) for line in result.lines] == expected
```

覆盖 expiry null 排后、received null 排后、lot/location/balance tie-break、过期、冻结、quality、location、serial、available=0、excluded reason、partial split 和 input permutation。

- [ ] **Step 2: 写 repository RED**

Repository 只返回 actor tenant 候选与事实，不在 SQL 中决定 FEFO 排序。测试跨租户行、非 active/pickable location、lot/serial join 和 Decimal available。

- [ ] **Step 3: 运行 RED**

```powershell
& $python -m pytest tests/services/test_inventory_fefo_service.py tests/repositories/test_inventory_fefo_candidates.py -q
```

- [ ] **Step 4: 实现选择器与候选查询**

排序 key：

```python
eligible.sort(
    key=lambda row: (
        row.expiry_date is None,
        row.expiry_date or date.max,
        row.received_date is None,
        row.received_date or date.max,
        row.lot_id is None,
        row.lot_id or 0,
        row.location_id,
        row.balance_id,
    )
)
```

所有 excluded reason 使用稳定英文枚举。选择器不读取数据库、不写日志、不读取当前时间；`as_of` 必须显式传入。

- [ ] **Step 5: 运行 GREEN、property permutation 与 Ruff**

```powershell
& $python -m pytest tests/services/test_inventory_fefo_service.py tests/repositories/test_inventory_fefo_candidates.py -q
& $python -m ruff check app/services/inventory_fefo_service.py app/repositories/inventory_ledger_repository.py tests/services/test_inventory_fefo_service.py tests/repositories/test_inventory_fefo_candidates.py
```

- [ ] **Step 6: 范围审查并停止，等待 Task 3 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add deterministic FEFO selection"
```

---

### Task 4: 实现预留、解预留、发料与退料

**Files:**

- Create: `extensions/maintenance-api/app/repositories/inventory_reservation_repository.py`
- Create: `extensions/maintenance-api/app/services/inventory_reservation_service.py`
- Create: `extensions/maintenance-api/app/schemas/inventory_reservation.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_reservation_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_reservation_service.py`

**Interfaces:**

```python
InventoryReservationService.reserve(session, actor, *, command, idempotency_key) -> ReservationRead
InventoryReservationService.release(session, actor, reservation_id, *, command, idempotency_key) -> ReservationRead
InventoryReservationService.issue(session, actor, reservation_id, *, command, idempotency_key) -> ReservationRead
InventoryReservationService.return_items(session, actor, reservation_id, *, command, idempotency_key) -> ReservationRead
InventoryReservationService.cancel(session, actor, reservation_id, *, expected_version, idempotency_key) -> ReservationRead
InventoryReservationService.expire(session, actor, reservation_id, *, observed_version, idempotency_key) -> ReservationRead
```

- [ ] **Step 1: 写 reservation repository RED**

测试 tenant-scoped get/list、聚合锁、line 稳定顺序、owner filter、到期批次扫描、跨租户不可见。

- [ ] **Step 2: 写 service RED**

覆盖：默认库存不足整体失败；`allow_partial=true`；多批次 FEFO；偏离原因必填；reserve 只增加 reserved；部分 issue 同时减少 on_hand/reserved；fulfilled；release/cancel；return 引用原 issue 且不恢复 reservation；serial 单件；幂等重放；same key/different request；version conflict。

```python
def test_reserve_is_all_or_nothing_by_default(session, actor_contributor, service):
    command = ReserveCommand(
        owner_type="MANUAL",
        owner_id="job-100",
        spare_part_id=1,
        warehouse_id=1,
        requested_quantity="6.0000",
        allow_partial=False,
        expected_balance_versions={1: 1},
    )
    with pytest.raises(BusinessValidationError) as exc_info:
        service.reserve(
            session,
            actor_contributor,
            command=command,
            idempotency_key="reserve-full-required",
        )
    assert exc_info.value.code == "INSUFFICIENT_AVAILABLE_INVENTORY"
```

- [ ] **Step 3: 运行 RED**

```powershell
& $python -m pytest tests/repositories/test_inventory_reservation_repository.py tests/services/test_inventory_reservation_service.py -q
```

- [ ] **Step 4: 实现 schema/repository/service**

Reserve 在锁定后再次生成 FEFO。用户实际选择与推荐不一致时，比较规范化 `(balance_id, quantity)` 序列；无 reason 拒绝。领域状态更新与 `apply_plan()` 在同一 session transaction 内完成。

Issue line delta：

```python
InventoryQuantityDelta(
    on_hand=-quantity,
    reserved=-quantity,
)
```

Release/expire delta：

```python
InventoryQuantityDelta(reserved=-remaining_quantity)
```

Return delta：

```python
InventoryQuantityDelta(on_hand=quantity)
```

- [ ] **Step 5: 运行 GREEN 与 transaction 回归**

```powershell
& $python -m pytest tests/repositories/test_inventory_reservation_repository.py tests/services/test_inventory_reservation_service.py tests/services/test_inventory_mutation_plan.py tests/services/test_inventory_transaction_service.py -q
& $python -m ruff check app/repositories/inventory_reservation_repository.py app/services/inventory_reservation_service.py app/schemas/inventory_reservation.py tests/repositories/test_inventory_reservation_repository.py tests/services/test_inventory_reservation_service.py
```

- [ ] **Step 6: 范围审查并停止，等待 Task 4 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add inventory reservation lifecycle"
```

---

### Task 5: 实现到期预留后台与惰性释放

**Files:**

- Create: `extensions/maintenance-api/app/workers/inventory_reservation_expiry.py`
- Modify: `extensions/maintenance-api/app/workers/task_registry.py`
- Modify: `extensions/maintenance-api/app/services/inventory_reservation_service.py`
- Create: `extensions/maintenance-api/tests/workers/test_inventory_reservation_expiry.py`
- Modify: `extensions/maintenance-api/tests/services/test_inventory_reservation_service.py`

**Interfaces:**

```python
expire_inventory_reservations(
    session_factory: Callable[[], Session],
    *,
    as_of: datetime,
    batch_size: int = 100,
) -> ExpiryBatchResult
```

- [ ] **Step 1: 写 RED**

覆盖：按 tenant/id 稳定批次；ACTIVE/PARTIALLY_ISSUED 扫描；已发数量不回滚；manual release 与 worker 竞争只一个成功；重复批次幂等；单项失败不中断其他项；reserve/issue/release 查询前惰性检查。

```python
def test_worker_and_lazy_expiry_release_once(concurrent_sessions, expired_reservation):
    worker_result, request_result = run_with_barrier(
        lambda session: expire_one(session, expired_reservation.id),
        lambda session: issue_after_lazy_expiry(session, expired_reservation.id),
    )
    assert count_unreserve_transactions(expired_reservation.id) == 1
    assert {worker_result.code, request_result.code} == {"EXPIRED", "RESERVATION_EXPIRED"}
```

- [ ] **Step 2: 运行 RED**

```powershell
& $python -m pytest tests/workers/test_inventory_reservation_expiry.py tests/services/test_inventory_reservation_service.py -q
```

- [ ] **Step 3: 实现 worker 与稳定 key**

```python
def expiry_idempotency_key(tenant_id: str, reservation_id: int, version: int) -> str:
    return f"reservation-expire:{tenant_id}:{reservation_id}:{version}"
```

每项使用独立 session/transaction，结构化结果记录 reservation ID、transaction ID、code、request ID。不要引入消息队列或全局 scheduler 依赖；提供可被现有运行入口调用的同步函数。

- [ ] **Step 4: 运行 GREEN 与确定性并发重复测试**

```powershell
1..5 | ForEach-Object {
    & $python -m pytest tests/workers/test_inventory_reservation_expiry.py -q
    if ($LASTEXITCODE -ne 0) { throw "expiry concurrency test failed" }
}
```

- [ ] **Step 5: 范围审查并停止，等待 Task 5 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): expire inventory reservations safely"
```

---

### Task 6: 实现高风险 preview/execute、冻结、调整与冲销

**Files:**

- Create: `extensions/maintenance-api/app/services/inventory_operation_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_transaction_repository.py`
- Modify: `extensions/maintenance-api/app/services/inventory_transaction_service.py`
- Modify: `extensions/maintenance-api/app/schemas/inventory_operation.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_operation_preview.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_freeze.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_reversal.py`

**Interfaces:**

```python
InventoryOperationService.preview(session, actor, *, command, idempotency_key) -> InventoryOperationPreviewRead
InventoryOperationService.execute(session, actor, transaction_id, *, command, idempotency_key) -> InventoryTransactionRead
InventoryOperationService.preview_reverse(session, actor, transaction_id, *, command, idempotency_key) -> InventoryOperationPreviewRead
```

- [ ] **Step 1: 写 confirmation RED**

测试 preview 无 balance/ledger 副作用、token 仅返回一次且数据库只存 hash、错误 token、过期 token、transaction version conflict、preview 后 balance version 改变、重复 execute 幂等、private extension 不出现在 read API schema。

- [ ] **Step 2: 写 freeze/adjust/reverse RED**

冻结全零 quantity + state mutation；冻结后 FEFO 排除；unfreeze 恢复；adjust admin-only；reverse 补偿 entries、原账本不变、重复冲销、负数保护、后续 reservation/transfer 依赖冲突。

```python
def test_freeze_records_state_without_quantity_change(session, actor_admin, lot_balance, service):
    preview = service.preview(
        session,
        actor_admin,
        command=freeze_command(lot_balance),
        idempotency_key="freeze-preview-1",
    )
    result = service.execute(
        session,
        actor_admin,
        preview.transaction_id,
        command=execute_command(preview),
        idempotency_key="freeze-execute-1",
    )
    assert all(entry.on_hand_delta == 0 for entry in result.entries)
    assert result.entries[0].state_before_json["lot_frozen"] is False
    assert result.entries[0].state_after_json["lot_frozen"] is True
```

- [ ] **Step 3: 运行 RED**

```powershell
& $python -m pytest tests/services/test_inventory_operation_preview.py tests/services/test_inventory_freeze.py tests/services/test_inventory_reversal.py -q
```

- [ ] **Step 4: 实现 PREVIEWED lifecycle**

Preview 创建 transaction，生成 `secrets.token_urlsafe(32)`，只保存 SHA-256。Execute 锁定 transaction，常量时间比较 token hash，检查 UTC expires_at，重新构造 plan。失败终态保存稳定错误 snapshot；结果不确定数据库异常不得伪装成业务 FAILED。

- [ ] **Step 5: 实现 freeze/adjust/reverse planner**

Reverse 读取原 transaction entries，按 entry 顺序生成反向 deltas；先检查 transaction 未被完整冲销，再检查当前 projection 可接受补偿。原 transaction 和 reverse transaction 的关联通过现有 `reversed_transaction_id` 与响应 extension 双向保存。

- [ ] **Step 6: 运行 GREEN、token 安全与回归**

```powershell
& $python -m pytest tests/services/test_inventory_operation_preview.py tests/services/test_inventory_freeze.py tests/services/test_inventory_reversal.py tests/services/test_inventory_transaction_service.py tests/repositories/test_inventory_ledger_immutability.py -q
& $python -m ruff check app/services/inventory_operation_service.py app/services/inventory_transaction_service.py app/repositories/inventory_transaction_repository.py app/schemas/inventory_operation.py tests/services/test_inventory_operation_preview.py tests/services/test_inventory_freeze.py tests/services/test_inventory_reversal.py
```

- [ ] **Step 7: 范围审查并停止，等待 Task 6 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add high-risk inventory operations"
```

---

### Task 7: 实现两阶段调拨

**Files:**

- Create: `extensions/maintenance-api/app/repositories/inventory_transfer_repository.py`
- Create: `extensions/maintenance-api/app/services/inventory_transfer_service.py`
- Create: `extensions/maintenance-api/app/schemas/inventory_transfer.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_transfer_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_transfer_service.py`

**Interfaces:**

```python
InventoryTransferService.create(session, actor, *, command, idempotency_key) -> TransferRead
InventoryTransferService.preview_dispatch(session, actor, transfer_id, *, command, idempotency_key) -> InventoryOperationPreviewRead
InventoryTransferService.execute_dispatch(session, actor, transfer_id, *, command, idempotency_key) -> TransferRead
InventoryTransferService.preview_receive(session, actor, transfer_id, *, command, idempotency_key) -> InventoryOperationPreviewRead
InventoryTransferService.execute_receive(session, actor, transfer_id, *, command, idempotency_key) -> TransferRead
InventoryTransferService.cancel(session, actor, transfer_id, *, expected_version, idempotency_key) -> TransferRead
```

- [ ] **Step 1: 写 RED**

覆盖 create、target zero balance resolution、dispatch preview 无副作用、dispatch source/on_hand 与 target/in_transit 原子变化、部分 receive、多次 receive、超收、相同库位、跨租户、serial、重复 execute、已 dispatch cancel 规则、并发 receive。

```python
def test_dispatch_is_atomic_across_source_and_target(session, actor_admin, service, transfer):
    preview = service.preview_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=dispatch_command(transfer),
        idempotency_key="dispatch-preview",
    )
    result = service.execute_dispatch(
        session,
        actor_admin,
        transfer.id,
        command=execute_command(preview),
        idempotency_key="dispatch-execute",
    )
    source, target = reload_transfer_balances(session, transfer)
    assert source.on_hand_quantity == Decimal("8.0000")
    assert target.in_transit_quantity == Decimal("2.0000")
    assert result.status == "DISPATCHED"
```

- [ ] **Step 2: 运行 RED**

```powershell
& $python -m pytest tests/repositories/test_inventory_transfer_repository.py tests/services/test_inventory_transfer_service.py -q
```

- [ ] **Step 3: 实现 target balance resolution 与聚合锁**

创建 transfer 时先按 05-4A balance identity 查询目标行；不存在时在 savepoint 中创建全零 row并处理唯一键 winner，然后保存 `target_balance_id`。dispatch/receive 先锁 transfer，再由 transaction service 按 balance ID 锁余额。

- [ ] **Step 4: 实现 dispatch/receive planner**

Dispatch plan：source `on_hand=-q`，target `in_transit=+q`。Receive plan：target `in_transit=-q, on_hand=+q`。每次执行后从 line 聚合更新 `DISPATCHED/PARTIALLY_RECEIVED/COMPLETED`。

- [ ] **Step 5: 运行 GREEN 与并发重复**

```powershell
& $python -m pytest tests/repositories/test_inventory_transfer_repository.py tests/services/test_inventory_transfer_service.py tests/services/test_inventory_mutation_plan.py -q
1..5 | ForEach-Object {
    & $python -m pytest tests/services/test_inventory_transfer_service.py -k concurrent -q
    if ($LASTEXITCODE -ne 0) { throw "transfer concurrency test failed" }
}
```

- [ ] **Step 6: 范围审查并停止，等待 Task 7 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add two-stage inventory transfers"
```

---

### Task 8: 实现盘点状态机与部分确认

**Files:**

- Create: `extensions/maintenance-api/app/repositories/inventory_stocktake_repository.py`
- Create: `extensions/maintenance-api/app/services/inventory_stocktake_service.py`
- Create: `extensions/maintenance-api/app/schemas/inventory_stocktake.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_stocktake_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_stocktake_service.py`

**Interfaces:**

```python
InventoryStocktakeService.create(session, actor, *, command, idempotency_key) -> StocktakeRead
InventoryStocktakeService.start(session, actor, stocktake_id, *, expected_version, idempotency_key) -> StocktakeRead
InventoryStocktakeService.record_count(session, actor, stocktake_id, line_id, *, command, idempotency_key) -> StocktakeRead
InventoryStocktakeService.review(session, actor, stocktake_id, *, expected_version, idempotency_key) -> StocktakeRead
InventoryStocktakeService.preview_confirm(session, actor, stocktake_id, *, command, idempotency_key) -> InventoryOperationPreviewRead
InventoryStocktakeService.execute_confirm(session, actor, stocktake_id, *, command, idempotency_key) -> StocktakeRead
InventoryStocktakeService.rebase_lines(session, actor, stocktake_id, *, command, idempotency_key) -> StocktakeRead
InventoryStocktakeService.cancel(session, actor, stocktake_id, *, expected_version, idempotency_key) -> StocktakeRead
```

- [ ] **Step 1: 写 RED**

覆盖 snapshot、count、review、全量无冲突、部分版本冲突、无冲突行一次调整、冲突 detail、rebase 仅冲突行、recount、admin baseline accept、取消规则、重复 execute 幂等。

```python
def test_confirm_adjusts_only_non_conflicting_lines(session, actor_admin, service, stocktake):
    mutate_one_balance_after_snapshot(session, stocktake.lines[1].balance_id)
    preview = service.preview_confirm(
        session,
        actor_admin,
        stocktake.id,
        command=confirm_preview_command(stocktake),
        idempotency_key="stocktake-preview",
    )
    result = service.execute_confirm(
        session,
        actor_admin,
        stocktake.id,
        command=execute_command(preview),
        idempotency_key="stocktake-execute",
    )
    assert result.status == "CONFLICTED"
    assert result.lines[0].resolution == "ADJUSTED"
    assert result.lines[1].resolution == "CONFLICTED"
```

- [ ] **Step 2: 运行 RED**

```powershell
& $python -m pytest tests/repositories/test_inventory_stocktake_repository.py tests/services/test_inventory_stocktake_service.py -q
```

- [ ] **Step 3: 实现 snapshot 和状态机**

Create 读取 scope 内 balances，按 balance ID 生成 lines 并保存 system quantity/version。Count 只允许 COUNTING；review 只允许所有 required line 有 counted quantity。confirmed line 后续更新必须拒绝。

- [ ] **Step 4: 实现部分确认**

Execute 重新锁定所有未解决 balance，分为 conflict 和 executable。只把 executable 行生成一个 `STOCKTAKE_CONFIRM` plan；成功后写 `confirmed_transaction_id` 和 `ADJUSTED`。存在 conflict 时 transaction terminal status 为 `PARTIALLY_COMPLETED`，stocktake 为 `CONFLICTED`。

- [ ] **Step 5: 运行 GREEN 与重复确认保护**

```powershell
& $python -m pytest tests/repositories/test_inventory_stocktake_repository.py tests/services/test_inventory_stocktake_service.py tests/services/test_inventory_operation_preview.py -q
& $python -m ruff check app/repositories/inventory_stocktake_repository.py app/services/inventory_stocktake_service.py app/schemas/inventory_stocktake.py tests/repositories/test_inventory_stocktake_repository.py tests/services/test_inventory_stocktake_service.py
```

- [ ] **Step 6: 范围审查并停止，等待 Task 8 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add inventory stocktakes"
```

---

### Task 9: 暴露 Inventory API、错误合同与 RBAC

**Files:**

- Create: `extensions/maintenance-api/app/api/v1/inventory/__init__.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/router.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/queries.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/reservations.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/operations.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/transfers.py`
- Create: `extensions/maintenance-api/app/api/v1/inventory/stocktakes.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Modify: `extensions/maintenance-api/app/services/inventory_query_service.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_reservations_api.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_operations_api.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_transfers_api.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_stocktakes_api.py`
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`

**Interfaces:**

- Prefix: `/api/v1/inventory`。
- All list endpoints return existing success envelope with `PageData`。
- All write endpoints read `Idempotency-Key` header and actor from existing dependencies。

- [ ] **Step 1: 写 route inventory/RBAC RED**

每个 route 覆盖 unauthenticated、viewer、contributor、admin、cross-tenant、not found、state conflict、version conflict、success meta 和 request ID。更新精确 route count 与函数角色映射。

- [ ] **Step 2: 写 API contract RED**

```python
def test_create_reservation_requires_idempotency_key(client, contributor_headers):
    response = client.post(
        "/api/v1/inventory/reservations",
        headers=contributor_headers,
        json=valid_reservation_payload(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
```

同时测试 body/query 提供 tenant ID 被 schema 拒绝；preview response 含 token；transaction read 不返回 token hash/private command；冲突 details 完整。

- [ ] **Step 3: 运行 RED**

```powershell
& $python -m pytest tests/api/test_inventory_queries_api.py tests/api/test_inventory_reservations_api.py tests/api/test_inventory_operations_api.py tests/api/test_inventory_transfers_api.py tests/api/test_inventory_stocktakes_api.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 4: 实现 router 与 schema binding**

所有 endpoint 只做 dependency、schema、service 调用和 envelope。不得在 route 中计算 FEFO、delta、状态转换或 tenant。高风险 execute body 必含 `expected_transaction_version` 和 confirmation token。

- [ ] **Step 5: 实现稳定错误映射**

错误码严格使用设计规格第 12 节；业务冲突 details 设置 `retryable=False`；结果不确定服务错误保留 `retryable=True`。不要根据异常 message 推断错误码。

- [ ] **Step 6: 运行 GREEN、OpenAPI 与 RBAC 回归**

```powershell
& $python -m pytest tests/api/test_inventory_queries_api.py tests/api/test_inventory_reservations_api.py tests/api/test_inventory_operations_api.py tests/api/test_inventory_transfers_api.py tests/api/test_inventory_stocktakes_api.py tests/security/test_api_rbac.py -q
& $python -m ruff check app/api/v1/inventory app/api/v1/router.py app/services/inventory_query_service.py tests/api/test_inventory_queries_api.py tests/api/test_inventory_reservations_api.py tests/api/test_inventory_operations_api.py tests/api/test_inventory_transfers_api.py tests/api/test_inventory_stocktakes_api.py tests/security/test_api_rbac.py
```

- [ ] **Step 7: 范围审查并停止，等待 Task 9 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): expose inventory operation APIs"
```

---

### Task 10: Gate 1 后端核心关闭

**Files:**

- Create: `extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py`
- Create: `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-backend-gate.md`；该文件只能在 Gate 命令使用新鲜输出后创建。

**Interfaces:** Gate 1 输出可供前端 Task 11 使用的冻结 API contract 和错误码清单。

- [ ] **Step 1: 写后端集成 RED，然后实现仅测试 fixture 缺口**

集成测试覆盖 reserve/issue/return/release、transfer、stocktake、expiry race；不得通过 API 外的直接 balance 写来构造成功路径，测试准备数据除外。

- [ ] **Step 2: 运行 focused suite**

```powershell
& $python -m pytest \
  tests/models/test_inventory_operation_models.py \
  tests/migrations/test_inventory_operations_migration.py \
  tests/schemas/test_inventory_operation_schemas.py \
  tests/services/test_inventory_mutation_plan.py \
  tests/services/test_inventory_fefo_service.py \
  tests/services/test_inventory_reservation_service.py \
  tests/workers/test_inventory_reservation_expiry.py \
  tests/services/test_inventory_operation_preview.py \
  tests/services/test_inventory_freeze.py \
  tests/services/test_inventory_reversal.py \
  tests/services/test_inventory_transfer_service.py \
  tests/services/test_inventory_stocktake_service.py \
  tests/api/test_inventory_queries_api.py \
  tests/api/test_inventory_reservations_api.py \
  tests/api/test_inventory_operations_api.py \
  tests/api/test_inventory_transfers_api.py \
  tests/api/test_inventory_stocktakes_api.py \
  tests/integration/test_inventory_operations_workflow.py -q
```

- [ ] **Step 3: 运行 migration 和 Ruff Gate**

```powershell
& $python -m alembic heads
& $python -m alembic current
& $python -m alembic downgrade 20260803_10
& $python -m alembic upgrade 20260803_11
& $python -m ruff check app tests
```

- [ ] **Step 4: 运行后端全量**

```powershell
& $python -m pytest -q
```

记录 passed/deselected/warnings 和完整命令，不用历史结果代替。

- [ ] **Step 5: 审查范围与残余风险**

```powershell
& git.exe diff --check
& git.exe status --short
& git.exe diff --stat
& git.exe diff --name-only
& git.exe grep -n -E "TODO|FIXME|HACK" -- extensions/maintenance-api/app extensions/maintenance-api/tests
```

Gate 报告必须写明真实 PostgreSQL 尚未运行，生产部署 blocked。

- [ ] **Step 6: 停止并请求 Gate 1 与 backend integration commit 的单独批准**

批准后建议 commit：

```powershell
& git.exe commit -m "test(maintenance): close inventory backend gate"
```

不得自动进入 Task 11。

---

### Task 11: 建立前端 typed API、Store、权限和隐藏路由

**Files:**

- Create: `frontend/src/api/maintenance/inventory.ts`
- Create: `frontend/src/api/maintenance/__tests__/inventory.test.ts`
- Create: `frontend/src/stores/maintenance/inventory.ts`
- Create: `frontend/src/stores/maintenance/__tests__/inventory.test.ts`
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`
- Modify: `frontend/src/stores/maintenance/permissions.ts`
- Modify: `frontend/src/stores/maintenance/__tests__/permissions.test.ts`
- Modify: `frontend/src/router/maintenance.ts`
- Create: `frontend/src/views/maintenance/__tests__/inventory-navigation.test.ts`

**Interfaces:**

```typescript
export type InventoryCommandState =
  | { phase: 'idle' }
  | { phase: 'submitting'; logicalId: string; idempotencyKey: string }
  | { phase: 'previewed'; transactionId: number; transactionVersion: number; confirmationToken: string }
  | { phase: 'succeeded'; transactionId?: number }
  | { phase: 'conflicted'; error: MaintenanceApiError }
  | { phase: 'uncertain'; idempotencyKey: string; error: MaintenanceApiError }
```

Store methods：`fetchBalances`, `fetchBalanceDetail`, `reserve`, `issue`, `release`, `returnItems`, `previewOperation`, `executeOperation`, `fetchTransfer`, `fetchStocktake`, `resetLogicalCommand`。

- [ ] **Step 1: 写 typed API RED**

测试 filter/sort/page 序列化、PageData 解包、Idempotency-Key、confirmation token、AbortSignal、稳定错误 details、无 tenant 参数。

- [ ] **Step 2: 写 Store RED**

覆盖 stale response generation、AbortController、重复点击复用 key、success/明确 4xx 后轮换、network/timeout/uncertain 5xx 保留、preview 与 execute 状态分离、冲突保留表单输入。

```typescript
it('keeps the idempotency key after an uncertain failure', async () => {
  const store = useInventoryStore()
  api.reserve.mockRejectedValueOnce(networkError())
  await expect(store.reserve(command)).rejects.toBeDefined()
  const firstKey = store.commandState.idempotencyKey
  api.reserve.mockResolvedValueOnce(reservationResponse)
  await store.reserve(command)
  expect(api.reserve.mock.calls[1][1].idempotencyKey).toBe(firstKey)
})
```

- [ ] **Step 3: 写 permissions/router RED**

增加 `freezeInventory`, `reverseInventory`, `createStocktake`, `confirmStocktake`, `manageInventoryPolicies`；验证 viewer/contributor/admin。隐藏详情路由 `meta.hidden=true` 且不进入 menu definition。

- [ ] **Step 4: 运行 RED**

```powershell
pnpm --dir frontend test -- \
  src/api/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/permissions.test.ts \
  src/views/maintenance/__tests__/inventory-navigation.test.ts
```

- [ ] **Step 5: 实现 API、Store、权限与 router**

API 类型直接反映后端英文枚举。Store 用 `crypto.randomUUID()` 创建逻辑 key；一个 logical command 在结果确定前不得生成新 key。每类详情请求维护 generation counter，旧响应不覆盖新状态。

- [ ] **Step 6: 运行 GREEN 与 typecheck**

```powershell
pnpm --dir frontend test -- \
  src/api/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/permissions.test.ts \
  src/views/maintenance/__tests__/inventory-navigation.test.ts
pnpm --dir frontend typecheck
```

- [ ] **Step 7: 范围审查并停止，等待 Task 11 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): add inventory frontend state"
```

---

### Task 12: 激活 Inventory Gap 与库存详情交互

**Files:**

- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- Create: `frontend/src/components/maintenance/inventory/InventoryBalanceTable.vue`
- Create: `frontend/src/components/maintenance/inventory/FEFOSelectionPanel.vue`
- Create: `frontend/src/components/maintenance/inventory/ReservationDialog.vue`
- Create: `frontend/src/components/maintenance/inventory/InventoryOperationPreviewDialog.vue`
- Create: `frontend/src/components/maintenance/inventory/TransferWorkflow.vue`
- Create: `frontend/src/components/maintenance/inventory/StocktakeWorkflow.vue`
- Create: five detail views listed in File Map
- Create: `frontend/src/components/maintenance/inventory/__tests__/inventory-gap.test.ts`
- Create: `frontend/src/components/maintenance/inventory/__tests__/fefo-selection.test.ts`
- Create: `frontend/src/components/maintenance/inventory/__tests__/inventory-operations.test.ts`
- Create: `frontend/src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts`

**Interfaces:** UI 只调用 Store；组件 emit 领域 command，不直接调用 HTTP client。

- [ ] **Step 1: 写页面/组件 RED**

覆盖 viewer 只读、contributor reserve/issue/return/create stocktake、admin transfer/freeze/adjust/reverse/confirm、FEFO 推荐与偏离 reason、两阶段 transfer、逐行 stocktake conflict、隐藏 route 直接访问、英文 status 驱动。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- \
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts \
  src/components/maintenance/inventory/__tests__/fefo-selection.test.ts \
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts \
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts
```

- [ ] **Step 3: 实现 Inventory Gap server table**

列固定包含 warehouse、location、part、lot、expiry、on hand、reserved、available、in transit、risk。筛选分页使用 Store；点击行进入隐藏 balance detail。

- [ ] **Step 4: 实现普通命令与 FEFO 偏离**

推荐与实际列表按 balance ID + quantity 比较；有偏离时 reason textarea required。错误 conflict detail 显示 expected/actual version 和 suggested action，保留输入。

- [ ] **Step 5: 实现高风险 preview/execute、transfer 与 stocktake**

Preview dialog 显示 before/after/warnings/risks；execute 只能用 Store 保存的 token/version。Stocktake conflict 只重送 unresolved line；已 ADJUSTED 行 disabled。

- [ ] **Step 6: 运行 GREEN、typecheck 与 production build**

```powershell
pnpm --dir frontend test -- \
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts \
  src/components/maintenance/inventory/__tests__/fefo-selection.test.ts \
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts \
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

- [ ] **Step 7: 范围审查并停止，等待 Task 12 commit 批准**

批准后建议 commit：

```powershell
& git.exe commit -m "feat(maintenance): activate inventory gap workflows"
```

---

### Task 13: Gate 2 前端集成关闭

**Files:**

- Create: `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-frontend-gate.md`；该文件只能在前端 Gate 使用新鲜输出后创建。

- [ ] **Step 1: 运行 inventory focused tests**

```powershell
pnpm --dir frontend test -- \
  src/api/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/inventory.test.ts \
  src/stores/maintenance/__tests__/permissions.test.ts \
  src/views/maintenance/__tests__/inventory-navigation.test.ts \
  src/components/maintenance/inventory/__tests__/inventory-gap.test.ts \
  src/components/maintenance/inventory/__tests__/fefo-selection.test.ts \
  src/components/maintenance/inventory/__tests__/inventory-operations.test.ts \
  src/components/maintenance/inventory/__tests__/stocktake-conflicts.test.ts
```

- [ ] **Step 2: 运行前端全量、typecheck、build**

```powershell
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

记录 bundle warning，但不得把 build warning 等同失败；若出现新 warning，说明来源和是否本阶段引入。

- [ ] **Step 3: 合同核对**

逐项核对 API method/path、request/response field、status enum、error code、permission、PageData、token/version。禁止靠测试 mock 掩盖后端字段不一致。

- [ ] **Step 4: 范围审查并停止，等待 Gate 2 与 commit 批准**

```powershell
& git.exe diff --check
& git.exe status --short
& git.exe diff --stat
```

批准后建议 commit：

```powershell
& git.exe commit -m "test(maintenance): close inventory frontend gate"
```

---

### Task 14: 统一集成 Gate 与 05-4B Closure Review

**Files:**

- Modify: `extensions/maintenance-api/tests/integration/test_inventory_operations_workflow.py`
- Create: `docs/superpowers/reviews/2026-08-04-maintenance-plan05-04b-closure.md`；该文件只能在完整新鲜验证后创建。
- Modify planning roadmap only if actual implementation facts differ from approved plan; any design change requires separate review。

- [ ] **Step 1: 运行四条完整业务链**

1. 创建批次库存 → FEFO → reserve → partial issue → return → release。
2. transfer create → dispatch preview/execute → partial receive → final receive → ledger/balance query。
3. stocktake → 一行并发变化 → partial confirm → rebase/recount → final confirm。
4. reservation 到期 → worker 与惰性检查竞争 → 单次 UNRESERVE。

```powershell
& $python -m pytest tests/integration/test_inventory_operations_workflow.py -q
```

- [ ] **Step 2: 重新运行新鲜后端 Gate**

```powershell
cd extensions/maintenance-api
& $python -m alembic heads
& $python -m pytest -q
& $python -m ruff check app tests
```

- [ ] **Step 3: 重新运行新鲜前端 Gate**

```powershell
cd ..\..
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

- [ ] **Step 4: 仓库与提交范围检查**

```powershell
& git.exe status --short
& git.exe diff --check
& git.exe log --oneline --decorate --max-count=20
& git.exe diff --name-status d75ff6b4d0b6467ee7c111316570292976e897b7...HEAD
```

确认没有触碰主工作树未跟踪文件、05-4A 保留工作树、05-4C/05-4D 代码或无关文件。

- [ ] **Step 5: 编写 Closure Review**

必须列出：实际文件、迁移链、每组命令与通过数、后端/前端全量、未执行验证、PostgreSQL 部署阻塞、残余风险、工作树/分支/未跟踪文件、允许进入 05-4C 的前置条件。

必须包含：

```text
Local 05-4B status: closed
Production deployment status: blocked until PostgreSQL gate passes
```

- [ ] **Step 6: 使用 verification-before-completion 自检**

不得用旧日志或“应该通过”替代新鲜输出。检查 plan/spec 覆盖、错误码、route inventory、迁移 head、占位标记和范围。

- [ ] **Step 7: 停止并分别请求批准**

依次请求：

1. 05-4B Closure Review 批准；
2. 最终 closure commit 批准；
3. push 批准；
4. PR 创建/更新批准；
5. PR ready/merge 批准；
6. 05-4C 规划或实施启动批准。

这些批准不得合并推定。

## Plan Self-Review Checklist

实施前和每次计划修改后执行：

- [ ] 设计规格每节都有 task 覆盖；
- [ ] migration 始终是 `20260803_11 -> 20260803_10`；
- [ ] `InventoryMutationPlan` 类型名和 `apply_plan()` 签名在 Task 2 之后保持一致；
- [ ] 普通命令与高风险 preview/execute 未混淆；
- [ ] reservation 默认全量，partial 显式；
- [ ] transfer 使用独立聚合和两阶段数量语义；
- [ ] stocktake partial confirm 不重复已成功行；
- [ ] expiry worker 和 lazy check 共享 service/key；
- [ ] API 不接受 tenant；
- [ ] FEFO 偏离原因、推荐、实际选择均被持久化；
- [ ] 前端幂等 key 对 uncertain failure 保留；
- [ ] PostgreSQL 是部署 blocker；
- [ ] 每个 task 都在 commit 前停下请求批准；
- [ ] 未提前实现 05-4C/05-4D。

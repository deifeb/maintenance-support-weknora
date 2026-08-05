# Plan 05-4B Inventory Operations and Stocktake 设计规格

**状态：** 已完成逐节评审并获用户批准；仅授权规划文档，不授权实现、提交、推送、PR 或清理。

**批准日期：** 2026-08-04

**目标基线：** `feature/maintenance-frontend-plan05` 包含 05-4A 合并提交 `d75ff6b4d0b6467ee7c111316570292976e897b7`。05-4B 实施分支必须从该提交或其经验证后继提交创建，不得从旧基线 `7fad43355e204e8980b8226df713e4800e6e8057` 开始。

## 1. 背景

05-4A 已建立库存事实层：库位、策略、效期规则、批次、序列件、余额、库存事务、不可变账本和目标收货幂等记录。05-4B 在该事实层之上交付可执行库存业务，但所有数量变化仍必须由统一库存事务内核完成。

现有 `InventoryTransactionService` 只支持单余额 `OPENING` 和 `ADJUST`。05-4B 需要在不破坏现有幂等回放、版本检查、Decimal 校验、余额守恒和 ledger append-only 约束的前提下，增加多余额 mutation plan、普通直接命令、高风险 preview/execute、预留、发退料、两阶段调拨、冻结、冲销和盘点。

## 2. 已批准的核心决策

| 决策 | 采用方案 |
|---|---|
| 阶段结构 | 单一 05-4B，内部设 Gate 1 后端核心与 Gate 2 前端集成 |
| PostgreSQL | 本地 Closure 可依赖 SQLite、迁移往返、方言编译和确定性并发测试；真实 PostgreSQL 是部署前强制 Gate |
| 命令模式 | 普通预留/解预留/发料/退料直接执行；高风险操作强制 preview → execute |
| 部分预留 | 默认全量满足；仅显式 `allow_partial=true` 允许部分预留 |
| 调拨 | 两阶段 dispatch/receive，目标先记 `in_transit`，支持部分收货 |
| 盘点冲突 | 无冲突行可确认，冲突行不改库存，盘点进入 `CONFLICTED` |
| FEFO 偏离 | contributor 与 admin 均可偏离，但必须填写原因并记录推荐与实际选择 |
| 到期预留 | 后台定期释放 + 操作时惰性检查；两条路径共享幂等释放服务 |
| 内核方案 | 扩展 05-4A 事务内核；领域服务只生成、校验和编排 mutation plan |

## 3. 范围

### 3.1 本阶段包含

- 迁移 `20260803_11`，`down_revision = "20260803_10"`；
- reservation、reservation line、transfer、transfer line、stocktake、stocktake line；
- 确定性 FEFO 和可解释排除原因；
- 多余额 `InventoryMutationPlan` 与统一 `apply_plan()`；
- 预留、解预留、发料、退料；
- 两阶段调拨与部分收货；
- 冻结、解冻、调整和补偿冲销；
- 盘点快照、计数、复核、部分确认、冲突重基线；
- 到期预留后台释放与惰性释放；
- `/api/v1/inventory` API、RBAC、租户隔离和稳定错误合同；
- typed frontend API、Pinia store、Inventory Gap、隐藏详情路由；
- 后端 Gate、前端 Gate、统一集成 Gate 和 Closure Review。

### 3.2 本阶段不包含

- 05-4C 权威需求审查；
- 05-4D allocation rule、simulation 或 assurance plan；
- 采购、财务、自动补货和自动抢占；
- 将 `in_transit` 计入可用量；
- 修改已存在 ledger entry；
- 自动覆盖 FEFO 偏离原因、盘点并发变化或调拨超收；
- 真实 PostgreSQL Gate 的豁免。

## 4. 总体架构

```text
InventoryQueryService / InventoryLedgerRepository
                  │
                  ├── FEFOSelector（纯函数）
                  │
                  ├── InventoryReservationService
                  ├── InventoryTransferService
                  ├── InventoryStocktakeService
                  └── InventoryOperationService
                              │
                              ▼
                    InventoryMutationPlan
                              │
                              ▼
             InventoryTransactionService.apply_plan()
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
      balance projection  serial/lot state  immutable ledger
```

领域服务不得直接给 `InventoryBalance` 数量字段赋值。它们可以读取和锁定领域聚合、生成 mutation plan、更新 reservation/transfer/stocktake 自身状态，但所有库存数量与 lot/serial 受审计状态变化必须由 `InventoryTransactionService.apply_plan()` 在同一数据库事务中完成。

## 5. 内部接口

### 5.1 Mutation 类型

在 `app/schemas/inventory_operation.py` 定义冻结 Pydantic 类型：

```python
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.inventory_ledger import InventoryQuantityDelta

InventoryOperationType = Literal[
    "OPENING",
    "ADJUST",
    "RESERVE",
    "UNRESERVE",
    "ISSUE",
    "RETURN",
    "TRANSFER_DISPATCH",
    "TRANSFER_RECEIVE",
    "FREEZE",
    "UNFREEZE",
    "REVERSE",
    "STOCKTAKE_CONFIRM",
]

class InventoryStateMutation(BaseModel):
    model_config = ConfigDict(frozen=True)
    lot_id: int | None = None
    serial_item_id: int | None = None
    state_before: dict[str, str | bool | None]
    state_after: dict[str, str | bool | None]

class InventoryBalanceMutation(BaseModel):
    model_config = ConfigDict(frozen=True)
    balance_id: int
    expected_version: int
    deltas: InventoryQuantityDelta
    state_mutations: tuple[InventoryStateMutation, ...] = ()

class InventoryMutationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    operation_type: InventoryOperationType
    reference_type: str | None = None
    reference_id: str | None = None
    reason: str
    mutations: tuple[InventoryBalanceMutation, ...]
    audit_context: dict[str, str | int | bool | list | dict] = Field(default_factory=dict)
```

`mutations` 在 schema 校验时按 `balance_id` 升序规范化并拒绝重复 balance。纯数量计划必须至少有一个非零 delta；全零 delta 只允许存在 lot/serial state mutation 的 `FREEZE` 或 `UNFREEZE`。

### 5.2 Transaction service

```python
InventoryTransactionService.apply_plan(
    session: Session,
    actor: ActorContext,
    *,
    plan: InventoryMutationPlan,
    idempotency_key: str,
    required_role: MaintenanceRole,
    terminal_status: Literal["COMPLETED", "PARTIALLY_COMPLETED"] = "COMPLETED",
) -> InventoryTransactionRead
```

执行顺序固定：

```text
规范化 reason/key/plan
→ 计算规范化请求 hash
→ 检查幂等 winner
→ 解析全部 balance ID
→ 按 balance ID 升序 SELECT ... FOR UPDATE
→ 再次检查幂等 winner
→ 校验 tenant、expected version、数量、lot/serial 状态
→ 应用 state mutation
→ 写 balance projection 与 version
→ 追加一条 transaction 和 N 条 ledger entries
→ 保存响应快照
→ 单次 commit 边界由调用者控制
```

现有 `opening()` 和 `adjust()` 保留公开签名，并改为构造单 mutation plan 后调用 `apply_plan()`，保证 05-4A 行为与回归测试不变。

### 5.3 高风险 preview

高风险 preview 使用现有 `InventoryTransaction` 字段：

- `status = PREVIEWED`；
- `confirmation_token_hash` 保存 SHA-256，不保存明文；
- `confirmation_expires_at` 保存过期时间；
- `response_snapshot_json` 保存公开 preview 响应；
- 私有规范化命令保存于 `response_snapshot_json["_extensions"]["preview_command"]`，读取 API 必须过滤 `_extensions`；
- `request_hash` 是私有命令的 canonical hash。

execute 必须锁定 PREVIEWED transaction，校验 transaction version、token、expires_at，并重新读取库存生成新计划。旧 preview 中的 delta 只能用于风险对比，不能直接执行。

## 6. 持久化模型

### 6.1 Migration

```text
revision = 20260803_11
down_revision = 20260803_10
```

新增六张表，不复制 05-4A 余额、批次、序列件、transaction 或 ledger。迁移必须为 tenant、状态、数量关系、幂等业务键和常用查询列建立约束与索引。

### 6.2 Reservation

`inventory_reservations`：

- `id`, `tenant_id`；
- `owner_type`, `owner_id`：05-4B 作为非 FK 审计引用；05-4D 接入时再验证 allocation plan；
- `status`: `ACTIVE | PARTIALLY_ISSUED | FULFILLED | RELEASED | CANCELLED | EXPIRED`；
- `expires_at`, `allow_partial`；
- `actor_user_id`, `actor_roles_json`, `request_id`；
- `version`, timestamps。

`inventory_reservation_lines`：

- reservation、spare part、balance、lot、serial 引用；
- `requested_quantity`, `reserved_quantity`, `issued_quantity`, `released_quantity`；
- `expected_balance_version`, `fefo_rank`；
- `fefo_override_reason`, `recommended_selection_json`, `actual_selection_json`；
- `version`, timestamps。

约束：

```text
requested_quantity >= 0
reserved_quantity >= 0
issued_quantity >= 0
released_quantity >= 0
issued_quantity + released_quantity <= reserved_quantity
serial line 的 requested/reserved/issued/released 只能为 0 或 1
```

### 6.3 Transfer

`inventory_transfers`：

- source/target warehouse 与 location；
- `status`: `DRAFT | DISPATCHED | PARTIALLY_RECEIVED | COMPLETED | CANCELLED`；
- reference、reason、actor、request、version 与时间戳。

`inventory_transfer_lines`：

- spare part、source balance、target balance、lot、serial；
- requested、dispatched、received；
- source/target expected version；
- version。

创建 transfer 时解析或幂等创建零数量 target balance，避免 dispatch 过程中出现未受统一锁顺序控制的目标行创建。target balance 身份必须沿用 05-4A 唯一键和 tenant 校验。

### 6.4 Stocktake

`stocktakes`：

- warehouse/location scope；
- `status`: `DRAFT | COUNTING | REVIEWING | CONFIRMED | CONFLICTED | CANCELLED`；
- `snapshot_at`, actor、request、version 与时间戳。

`stocktake_lines`：

- balance、spare part、lot、serial；
- system、counted、variance；
- snapshot balance version；
- confirmed transaction ID；
- `resolution`: `PENDING | ADJUSTED | CONFLICTED | RECOUNT_REQUIRED | BASELINE_ACCEPTED`；
- conflict details、version。

已 `ADJUSTED` 行禁止再次生成调整。`BASELINE_ACCEPTED` 只表示 admin 接受新系统基准并要求重新确认，不代表自动调整。

### 6.5 Downgrade

- 无 05-4B 业务数据时允许 downgrade 到 `20260803_10`；
- 存在 reservation、transfer 或 stocktake 数据时默认拒绝破坏性 downgrade；
- downgrade 不逆转任何库存 transaction 或 ledger；
- upgrade/downgrade/re-upgrade 必须证明 05-4A 数据、数量和账本不变；
- Alembic 只有一个 head：`20260803_11`。

## 7. FEFO

### 7.1 排除

候选必须 tenant-scoped，并排除：

- `expiry_date < as_of`；
- lot 或 serial frozen；
- lot quality 为 `QUARANTINED`, `DAMAGED`, `REJECTED`；
- location 非 active 或非 pickable；
- serial 状态不允许拣选；
- `available_quantity <= 0`；
- 请求指定的 warehouse/location/lot/serial 不匹配。

### 7.2 排序

```text
有 expiry_date 优先
→ expiry_date 升序
→ received_date 升序（NULL 最后）
→ lot_id 升序（NULL 使用稳定 sentinel）
→ location_id 升序
→ balance_id 升序
```

输入顺序不得影响输出。返回：

- `recommended_lines`；
- `unfilled_quantity`；
- `warnings`；
- `excluded_candidates`，每项含稳定 reason code。

### 7.3 偏离

contributor 与 admin 可以选择非推荐候选，但必须提交非空原因。后端重新计算 FEFO，并同时保存推荐与实际选择到 reservation line、transaction response snapshot 和 ledger audit context。缺少原因返回 `FEFO_OVERRIDE_REASON_REQUIRED`。

## 8. 操作语义

### 8.1 普通直接命令

`RESERVE`, `UNRESERVE`, `ISSUE`, `RETURN` 不建立 PREVIEWED transaction，但仍要求：

- `Idempotency-Key`；
- expected reservation/balance version；
- 事务内重校验；
- 相同 key + 相同 request 返回原快照；
- 相同 key + 不同 request 返回 `IDEMPOTENCY_KEY_REUSED`。

预留默认全量满足。库存不足时整体回滚并返回 `INSUFFICIENT_AVAILABLE_INVENTORY`；仅显式 `allow_partial=true` 可保存部分预留，并返回 requested/reserved/unfilled。

Issue：

```text
on_hand_delta = -quantity
reserved_delta = -quantity
```

Unreserve/expire：

```text
reserved_delta = -remaining_reserved
```

Return：

```text
on_hand_delta = +quantity
```

退料必须引用原 issue transaction 或 reservation line，不自动恢复原预留。

### 8.2 高风险操作

强制 preview → execute：

- `TRANSFER_DISPATCH`；
- `TRANSFER_RECEIVE`；
- `FREEZE`, `UNFREEZE`；
- `ADJUST`；
- `REVERSE`；
- `STOCKTAKE_CONFIRM`。

preview 无库存副作用。execute 发现 token、transaction version、balance version 或业务状态变化时不得沿用旧计划。

### 8.3 Transfer

Dispatch 在一个 mutation plan 内：

```text
source.on_hand -= quantity
target.in_transit += quantity
```

Receive：

```text
target.in_transit -= received_quantity
target.on_hand += received_quantity
```

支持部分收货；未收数量保留在途。源与目标不得相同，不得跨租户，receive 不得超过 dispatched - received。dispatch 与每次 receive 各自幂等，且不得留下单边 ledger entry。

### 8.4 Freeze/Unfreeze

冻结可以是数量全零计划，但必须包含 lot/serial state mutation。ledger entry 的 `state_before_json` 和 `state_after_json` 同时包含数量状态和冻结状态。冻结库存立即被 FEFO 排除。

### 8.5 Reverse

- 不修改原 transaction 或原 ledger；
- 新建 `REVERSE` transaction 和补偿 entries；
- 原事务通过 `reversed_transaction_id` 或 response extension 与冲销事务双向关联；
- 已完整冲销不得再次冲销；
- 补偿后不得产生负数、超额 reserved 或非法 serial/reservation 状态；
- 有后续依赖时返回明确不可冲销冲突，而不是静默修改依赖业务。

### 8.6 Stocktake

确认时按 balance ID 锁定并逐行比较 snapshot version：

- 无冲突行汇总为一个 `STOCKTAKE_CONFIRM` mutation plan；
- 冲突行不改余额，记录 expected/actual version；
- 存在冲突时 transaction 为 `PARTIALLY_COMPLETED`，stocktake 为 `CONFLICTED`；
- 已调整行不再送入后续确认；
- 冲突行必须重新计数，或由 admin 接受新基准后再计数/确认。

## 9. 到期预留

新增 `expire_inventory_reservations` worker entry：

```text
按 tenant、reservation ID 分批扫描
→ 锁定 reservation
→ 再查状态和 expires_at
→ 计算未发未释放数量
→ 调用 InventoryReservationService.expire()
→ 通过 UNRESERVE transaction 写账本
→ 更新 reservation = EXPIRED
```

系统幂等键：

```text
reservation-expire:{tenant_id}:{reservation_id}:{version}
```

reserve、issue、release 和查询可用量前执行相关 reservation 的惰性到期检查。后台与请求竞争时只允许一个 winner；已发数量不回滚。

## 10. API

路由前缀：`/api/v1/inventory`。

读取：balances、transactions、reservations、transfers、stocktakes、expiry-rules、policies 的列表和详情。所有列表使用 server-side filter/sort/pagination 与现有 `PageData` envelope。

普通命令：

```text
POST /reservations
POST /reservations/{id}/issue
POST /reservations/{id}/release
POST /reservations/{id}/return
POST /reservations/{id}/cancel
```

高风险通用入口：

```text
POST /operations/preview
POST /operations/{transaction_id}/execute
POST /operations/{transaction_id}/reverse/preview
POST /operations/{transaction_id}/reverse/execute
```

调拨：

```text
POST /transfers
POST /transfers/{id}/dispatch/preview
POST /transfers/{id}/dispatch/execute
POST /transfers/{id}/receive/preview
POST /transfers/{id}/receive/execute
POST /transfers/{id}/cancel
```

盘点：

```text
POST /stocktakes
POST /stocktakes/{id}/start
PUT  /stocktakes/{id}/lines/{line_id}
POST /stocktakes/{id}/review
POST /stocktakes/{id}/confirm/preview
POST /stocktakes/{id}/confirm/execute
POST /stocktakes/{id}/rebase-lines
POST /stocktakes/{id}/cancel
```

租户只能来自 `ActorContext.tenant_id`，不得接受 query/body tenant ID。

## 11. RBAC

| 能力 | viewer | contributor | admin |
|---|---:|---:|---:|
| 读取库存、流水、预留、调拨、盘点 | ✓ | ✓ | ✓ |
| 预留、解预留、发料、退料 |  | ✓ | ✓ |
| FEFO 偏离并填写原因 |  | ✓ | ✓ |
| 创建盘点、录入数量 |  | ✓ | ✓ |
| 调拨、冻结、解冻 |  |  | ✓ |
| 调整、冲销 |  |  | ✓ |
| 盘点确认、接受新基准 |  |  | ✓ |
| 管理库存策略与效期规则 |  |  | ✓ |

前端权限矩阵增加：

```text
freezeInventory
reverseInventory
createStocktake
confirmStocktake
manageInventoryPolicies
```

不得用 `adjustInventory` 代替所有管理员能力。

## 12. 稳定错误合同

必须实现并测试：

```text
INVENTORY_VERSION_CONFLICT
INVENTORY_TRANSACTION_VERSION_CONFLICT
INSUFFICIENT_AVAILABLE_INVENTORY
INVENTORY_NEGATIVE_BALANCE
INVENTORY_OPERATION_STATE_CONFLICT
INVENTORY_CONFIRMATION_TOKEN_INVALID
INVENTORY_CONFIRMATION_EXPIRED
LOT_EXPIRED
LOT_FROZEN
LOT_QUARANTINED
FEFO_OVERRIDE_REASON_REQUIRED
FEFO_SELECTION_INVALID
SERIAL_STATE_CONFLICT
RESERVATION_STATE_CONFLICT
RESERVATION_EXPIRED
TRANSFER_STATE_CONFLICT
TRANSFER_RECEIPT_EXCEEDS_DISPATCH
STOCKTAKE_VERSION_CONFLICT
STOCKTAKE_LINE_ALREADY_CONFIRMED
IDEMPOTENCY_KEY_REQUIRED
IDEMPOTENCY_KEY_REUSED
```

冲突 details 至少包含：

```text
conflict_object
object_id
expected_version
actual_version
affected_lines
retryable
suggested_action
```

明确业务冲突 `retryable: false`；结果不确定的网络/服务故障 `retryable: true`。

## 13. 前端

新增 typed API 与 Pinia store，管理：筛选、分页、详情、pending command、逻辑幂等 key、request generation、AbortController 和 stale response 丢弃。

幂等 key：同一逻辑提交重复点击复用；成功或明确 4xx 后轮换；网络中断、超时或结果不确定 5xx 保留；Store 不保存 tenant ID。

Inventory Gap 展示 warehouse、location、part、lot、expiry、on hand、reserved、available、in transit 与风险状态。隐藏详情路由：

```text
/platform/maintenance/inventory-gap/balances/:balanceId
/platform/maintenance/inventory-gap/transactions/:transactionId
/platform/maintenance/inventory-gap/reservations/:reservationId
/platform/maintenance/inventory-gap/transfers/:transferId
/platform/maintenance/inventory-gap/stocktakes/:stocktakeId
```

冲突时保留用户输入，不自动重放高风险 execute，不重新提交已成功盘点行。业务判断使用英文枚举，不依赖中文文案。

## 14. Gate

### Gate 1：后端核心

- Alembic 单一 head `20260803_11`；
- migration upgrade/downgrade/re-upgrade；
- FEFO、mutation plan、reservation、expiry、transfer、freeze/adjust/reverse、stocktake；
- API/RBAC/tenant/idempotency/token；
- Ruff 与后端全量测试；
- 修改范围和未跟踪文件审查。

Gate 1 通过后只允许申请进入前端集成；不自动提交或推送。

### Gate 2：前端集成

- typed API、store、permissions、router；
- Inventory Gap 与详情页组件测试；
- stale response、AbortController、幂等 key 生命周期；
- typecheck、production build、前端全量测试；
- 前后端合同核对。

### 统一集成 Gate

覆盖：

1. FEFO → reserve → partial issue → return → release；
2. transfer create → dispatch preview/execute → partial receive → complete；
3. stocktake → 并发变化 → partial confirm → rebase → confirm；
4. reservation expiry worker 与惰性检查竞争，只释放一次。

## 15. PostgreSQL 部署边界

本地 Closure 可以关闭 05-4B，但必须写明：

```text
Local 05-4B status: closed
Production deployment status: blocked until PostgreSQL gate passes
```

部署前必须在真实 PostgreSQL 验证 migration、`SELECT ... FOR UPDATE`、多余额锁顺序、唯一键竞争、幂等并发插入、reservation 释放竞争、transfer 并发、stocktake 版本冲突、死锁和重试。方言编译不得描述为真实 PostgreSQL 运行验证。

## 16. 批准与执行边界

- 本规格及配套计划获批，只授权规划文件；
- 开始实现前需要单独批准；
- 创建分支/工作树前需要执行 `using-git-worktrees` 并核对基线；
- 每个 Task 必须先 RED、再 GREEN、再范围审查；
- 每个 Task 的 commit、push、PR 操作均需单独明确批准；
- 不清理保留的 05-4A 工作树或 `codex/maintenance-plan05-4`；
- 不触碰主工作树已有未跟踪文件；
- 05-4C 只有在 05-4B Closure Review 获批后才能启动。

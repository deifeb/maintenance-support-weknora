# Plan 05-4 Inventory, Review and Allocation 设计

**状态：** 已批准设计，待书面规格复核

**日期：** 2026-08-03

**目标分支：** `codex/maintenance-plan05-4`

**实施基线：** `56760095017875f98ad90b645914f41696bdb06c`

**前置结果：** PR #4 已合并，Plan 05-3 Closure Review Remediation Gate 全绿

## 1. 背景

Plan 05-3 已交付场景草稿、并行计算、结果比较和需求清单生命周期。当前系统已经具备：

- 租户隔离、`viewer` / `contributor` / `admin` 角色和结构化错误响应；
- 仓库和仓库级器材库存聚合表 `warehouse_inventories`；
- 需求清单 DRAFT、PENDING_CONFIRMATION、CONFIRMED、PUBLISHED、VOIDED 状态机；
- 可追溯的需求清单条目、事件和幂等回放；
- 通用 `AIReviewRun` / `AIReviewFinding` 及确定性审查引擎；
- 前端 `InventoryGapPage` 和 `ReviewList` 路由占位页；
- 前端库存、审查、分配权限矩阵。

现有库存仍是仓库＋器材维度的可变聚合记录，普通 CRUD 可以直接修改数量；系统尚未具备库位、批次、序列号、不可变库存流水、FEFO、预留、领退调拨、盘点、正式需求审查或保障分配方案。现有通用 AI 审查接口接收调用方提交的任意 item 数据，不能作为正式需求清单的权威审查状态。

仓库中已有 `2026-07-24-maintenance-plan05-04-inventory-review-allocation.md`。该文件保留为历史基线，但其文件路径、角色假设、Demand List 集成方式和一次性交付范围已不符合当前代码。本设计以合并后的真实仓库状态重新建立 Plan 05-4 边界。

## 2. 目标

Plan 05-4 将已发布需求清单连接到可审计库存和人工确认的保障分配闭环：

1. 用不可变流水和版本化余额投影替代直接库存数量修改；
2. 支持库位、批次、有效期和序列号追踪；
3. 支持 FEFO、预留、解除、领用、退回、调拨、冻结、修正和基础盘点；
4. 对当前已发布需求清单执行权威、确定性的领域审查；
5. 将审查决定原子地应用到派生需求清单版本，不覆盖来源版本；
6. 支持版本化优先级规则、无副作用模拟和多任务竞争分配；
7. 生成独立保障方案，预览影响并经用户确认后执行库存预留；
8. 激活现有库存缺口和需求审查页面，保持 WeKnora 原生 Vue 体验；
9. 保持租户隔离、RBAC、Decimal、幂等、乐观锁和审计合同。

## 3. 非目标

本阶段不实现：

- 采购申请、供应商选择、订单、收货财务或库存估值；
- 会计期间、成本层、移动平均价或批次成本；
- 高级仓储波次、拣选路径、包装、运输或条码设备集成；
- 完整维修工单、安装拆卸履历或修理车间排程；
- 报告中心、DOCX 报告、聊天业务卡片或 Plan 05-5 验收；
- LLM 自动修改需求数量、库存、规则或保障方案；
- 自动抢占其他任务已确认的库存；
- 独立库存微服务、消息队列或新的 SSE 协议；
- 与 Plan 05-4 无关的 WeKnora 核心、知识库、聊天或组织功能重构。

## 4. 方案比较

### 4.1 方案 A：四个纵向阶段重新基线（采用）

使用一个总体设计和总体路线图，将执行拆成 05-4A 库存账本、05-4B 库存操作与盘点、05-4C 需求审查、05-4D 分配与保障方案。每个阶段同时交付迁移、服务、API、前端或集成面，并拥有独立 Gate 和关闭复审。

该方案使高风险库存一致性、需求版本和竞争分配可以分别审查；失败不会把整个 Plan 05-4 留在不可验证的中间状态。代价是文档和批准边界更多，但每个边界都对应一个可运行的业务增量。

### 4.2 方案 B：单体十三任务计划

在一个计划中连续实现全部模型、服务和页面。文档数量少，但数据库迁移、库存事务、审查派生和分配算法共享一个长期分支，回归和评审范围过大。该方案不采用。

### 4.3 方案 C：仅交付库存 MVP

只实现库存账本、FEFO 和预留，延后审查、规则模拟和保障方案。范围最小，但会破坏已批准的 Plan 05 路线图和 Plan 05-5 前置合同。该方案不采用。

## 5. 总体架构与阶段依赖

```text
05-4A Inventory Ledger Foundation
  locations / lots / serials / policies / balances / ledger
                         |
                         v
05-4B Inventory Operations and Stocktake
  FEFO / reserve / issue / return / transfer / freeze / count
                         |
                         v
05-4C Demand Review
  deterministic findings / decisions / derived demand-list version
                         |
                         v
05-4D Allocation and Assurance Plan
  rule versions / simulation / competition / plan / reservation execute
```

依赖规则：

- 05-4A 只建立权威库存事实和查询合同，不实现保障方案；
- 05-4B 只通过 05-4A 的事务服务改变库存；
- 05-4C 可以读取 05-4A/05-4B 的库存能力，但不创建预留；
- 05-4D 读取当前发布清单、发布规则和库存快照，执行时委托 05-4B 的预留服务；
- 后一阶段不得绕过前一阶段的 Service 或直接更新其表；
- 每个阶段的关闭复审通过后才能批准下一阶段代码实施。

## 6. 05-4A：库存账本基础

### 6.1 权威数据模型

#### `warehouse_locations`

```text
id, tenant_id, warehouse_id, code, name, location_type,
is_pickable, is_active, version, created_at, updated_at
```

租户内仓库＋代码唯一。每个仓库拥有迁移创建的 `DEFAULT` 库位。

#### `inventory_policies`

```text
id, tenant_id, warehouse_id, spare_part_id,
safety_stock, reorder_point, maximum_stock,
notes, version, created_at, updated_at
```

仓库＋器材维度保存库存策略，避免把安全库存复制到每个批次余额。

#### `inventory_expiry_rules`

```text
id, tenant_id, scope_type, category, spare_part_id,
warning_days_json, version, created_at, updated_at
```

`scope_type` 为 TENANT、CATEGORY 或 SPARE_PART。阈值按 spare part → category → tenant → 系统默认 180/90/30 天解析；同一租户和 scope 只允许一个有效规则。

#### `inventory_lots`

```text
id, tenant_id, spare_part_id, lot_code,
manufacture_date, received_date, expiry_date,
quality_status, is_frozen, freeze_reason,
version, created_at, updated_at
```

`quality_status` 为 AVAILABLE、QUARANTINED、DAMAGED 或 REJECTED。风险等级根据当前日期和 policy 阈值动态计算，不固化为批次字段。

#### `serialized_items`

```text
id, tenant_id, spare_part_id, serial_number, lot_id,
warehouse_id, location_id, status,
equipment_id, installation_position,
version, created_at, updated_at
```

关键件和可修件为单件数量。状态为 IN_STOCK、RESERVED、ISSUED、INSTALLED、AWAITING_REPAIR、IN_REPAIR、REPAIRED、SCRAPPED 或 FROZEN。

#### `inventory_balances`

```text
id, tenant_id, warehouse_id, location_id, spare_part_id, lot_id,
on_hand_quantity, reserved_quantity, damaged_quantity,
quarantined_quantity, in_transit_quantity,
version, created_at, updated_at
```

普通件业务键为 tenant＋warehouse＋location＋spare_part＋lot。数量均为 `Numeric(18,4)` 且非负；reserved＋damaged＋quarantined 不得超过 on_hand。

#### `inventory_transactions`

```text
id, tenant_id, operation_type, status,
idempotency_key, request_hash, response_snapshot_json,
reference_type, reference_id, reason,
confirmation_token_hash, confirmation_expires_at,
actor_user_id, actor_roles_json, request_id,
reversed_transaction_id, version,
created_at, completed_at, failed_at
```

状态为 PREVIEWED、COMPLETED、PARTIALLY_COMPLETED、FAILED、EXPIRED 或 REVERSED。tenant＋operation_type＋idempotency key 唯一；同一逻辑键以不同 request hash 复用时返回冲突。

#### `inventory_ledger_entries`

```text
id, tenant_id, transaction_id, balance_id,
spare_part_id, warehouse_id, location_id, lot_id, serial_item_id,
on_hand_delta, reserved_delta, damaged_delta,
quarantined_delta, in_transit_delta,
state_before_json, state_after_json,
before_balance_version, resulting_balance_version,
created_at
```

Ledger entry 只追加不更新、不删除。数量操作至少一个 delta 非零；冻结、解冻和 serial 状态操作必须保存不同的 state before/after。反向操作创建新的 transaction 和反向 entry，不修改原记录。

### 6.2 数量口径

```text
可用库存 = on_hand - reserved - damaged - quarantined
预计可用 = 可用库存 + in_transit + expected_repair
净需求缺口 = demand - 预计可用
```

`expected_repair` 是分配计算输入，不写入库存余额。安全库存是 policy，不作为余额分量；保障分配时从可用库存中保留。

### 6.3 兼容迁移

新 Alembic revision 基于当前 head `20260731_07`：

1. 创建 location、policy、expiry rule、lot、serial、balance、transaction 和 ledger 表；
2. 为每个现有仓库创建 `DEFAULT` 库位；
3. 每个 `warehouse_inventories` 行生成一条 policy 和一条 lot 为 NULL 的 DEFAULT balance；
4. 生成系统 `MIGRATION_OPENING` transaction 和 ledger，保留来源行 ID；
5. 校验每个租户、仓库和器材的五类数量聚合完全相等；
6. 应用切换后删除旧 `warehouse_inventories` 表及直接数量模型；
7. `/master-data/inventories` 查询由新 query service 聚合返回兼容结构；
8. 旧 create、update、adjust 写路径改为 policy 或 inventory operation，不得直接更新 balance。

升级、降级、再次升级必须在迁移测试数据上通过。若升级后已产生非默认库位、批次或序列号数据，自动降级会拒绝执行，避免静默丢失细粒度事实；此时必须先按运维流程导出和清理新域数据。

## 7. 05-4B：库存操作、FEFO、预留与盘点

### 7.1 FEFO

确定性顺序：

```text
排除过期、冻结、隔离、损坏、拒收、非拣选库位和已预留库存
→ 有 expiry_date 的批次优先
→ expiry_date 由近到远
→ 无 expiry_date 或同日期按 received_date 由早到晚
→ 同日期按 lot_id、location_id、balance_id 升序
```

默认预警阈值为 180、90、30 天。租户管理员可配置 tenant/category/spare part 规则。人工改选必须提交推荐选择、实际选择和原因。

### 7.2 库存操作

支持 OPENING_BALANCE、RECEIPT、RESERVE、UNRESERVE、ISSUE、RETURN、TRANSFER、FREEZE、UNFREEZE、ADJUST 和 REVERSE。

所有写操作遵循：

```text
preview
→ 返回选择建议、前后数量、版本、风险和确认 token
→ 用户确认
→ 按 balance_id 升序锁定
→ 重校验版本、FEFO、状态和可用量
→ 追加 ledger
→ 更新 balance / serial projection
→ 写审计和幂等回执
→ 单次 commit
```

### 7.3 预留

新增 `inventory_reservations` 和 `inventory_reservation_lines`。预留必须关联 demand list、allocation plan 或明确的业务 reference。

```text
ACTIVE → PARTIALLY_ISSUED → FULFILLED
ACTIVE / PARTIALLY_ISSUED → RELEASED | CANCELLED
```

预留数量通过 ledger 的 reserved_delta 反映。领用同时减少 on_hand 和 reserved。退回增加 on_hand，但不会自动恢复已完成预留。

### 7.4 调拨

调拨使用同一 transaction 的成对 ledger entries。源余额减少 on_hand，目标在途增加；接收确认后目标 in_transit 减少且 on_hand 增加。任一侧失败都不得留下单边完成状态。

### 7.5 盘点

新增 `stocktakes` 和 `stocktake_lines`：

```text
DRAFT → COUNTING → REVIEWING → CONFIRMED
                  ↘ CONFLICTED
DRAFT / COUNTING / REVIEWING / CONFLICTED → CANCELLED
```

创建盘点时保存目标余额版本和基准数量。盘点不冻结整个仓库。确认时重新读取版本；无冲突行生成 ADJUST transaction，冲突行保留当前余额并要求重新计数或接受新基准。

## 8. 05-4C：权威需求审查

### 8.1 领域所有权

正式审查使用独立模型：

- `demand_list_reviews`；
- `demand_list_review_findings`；
- `demand_list_review_decisions`；
- `demand_list_review_events`。

现有 `AIReviewRun` 和 `AIReviewFinding` 可提供非权威解释，但不保存正式决定、不生成数量，也不控制派生状态。

### 8.2 来源与快照

正式审查只能基于当前 PUBLISHED demand list。服务端按 ID 读取权威聚合并保存：

- demand list、item 和事件版本；
- 场景、计算与决策快照；
- 构型、替代、配套和技术依据；
- 库存、修理和保障能力快照；
- 确定性规则集版本和输入 hash。

浏览器不得提交 items 或 tenant_id 作为权威事实。

### 8.3 发现与决定

确定性范围包括完整性、构型适用性、配套缺失、比例、互斥、共用重复、替代有效性、可靠性异常、模型异常、库存缺口和证据有效性。

每个 finding 决定为 PENDING、ACCEPTED、REJECTED 或 EDIT_ACCEPTED。EDIT_ACCEPTED 必须保存建议数量、最终数量和原因。批量处理只能处理同一 review version 的明确 finding ID 列表。

### 8.4 状态机与派生

```text
CREATED → RUNNING → OPEN → READY_TO_DERIVE → DERIVED
                    ↘ FAILED
OPEN / READY_TO_DERIVE → VOIDED
```

阻断 finding 未处理时允许保存草稿，但不能进入 READY_TO_DERIVE。派生操作在一个服务事务中复制来源 PUBLISHED 清单、应用已接受决定并创建新的 DRAFT；来源版本保持不变。派生 DRAFT 继续走 Plan 05-3 的 submit、confirm、publish 生命周期。

## 9. 05-4D：规则、模拟与保障方案

### 9.1 规则版本

`allocation_rule_versions` 保存 lineage、version number、hard rules、weights、normalization、适用范围、生效期、修改原因和发布审计。

```text
DRAFT → SIMULATED → PUBLISHED → RETIRED
```

修改已模拟或已发布规则会创建新 DRAFT 版本。一个租户在同一适用范围和时间只能有一个有效 PUBLISHED 版本。

### 9.2 无副作用模拟

`allocation_simulations` 和 `allocation_simulation_results` 保存新旧规则、样本、输入快照、差异和发布阻断原因。

```text
PENDING → RUNNING → COMPLETED | FAILED | CANCELLED
```

大型模拟使用持久化任务和前端轮询，不新增 SSE。模拟只读取快照；开始和结束库存指纹必须完全一致。没有最新成功模拟、权重不为 1、硬规则违规或高优先级任务退化超过阈值时禁止发布。

### 9.3 保障方案

`allocation_plans`、`allocation_plan_lines` 和 `allocation_plan_events` 保存：

- 来源 demand list、规则版本和库存快照；
- 原件可分配量、替代建议、在途和预计修复；
- 推荐仓库、库位、批次或序列号；
- 需求、已满足、部分满足和剩余缺口；
- 安全库存、其他任务、临期、调拨和修理风险；
- 人工调整、确认、冲突和差异重生成链接。

```text
DRAFT → PREVIEWED → CONFIRMED → EXECUTING
                              → COMPLETED
                              → PARTIALLY_COMPLETED
                              → FAILED
DRAFT / PREVIEWED / CONFIRMED → VOIDED
```

CONFIRMED 或当前 PUBLISHED 清单可以生成和预览方案。执行预留时，来源必须已经是当前 PUBLISHED，且规则、方案和全部余额版本重新校验通过。非冲突行可以完成，冲突行明确返回错误和重新生成建议；系统不自动抢占库存。

## 10. 服务边界

```text
InventoryPolicyService        # policy and thresholds
ExpiryRuleService             # tenant/category/item expiry thresholds
InventoryBalanceService       # tenant-scoped balance queries
InventoryTransactionService   # preview, execute, replay, reverse
FefoService                   # deterministic eligible selection
ReservationService            # reserve, release, issue, return
StocktakeService              # baseline, count, conflict, confirm
DemandReviewService           # run, decide, derive
AllocationRuleService         # version, rank, publish, retire
AllocationSimulationService   # side-effect-free comparison
AllocationPlanService         # generate, preview, execute
```

Repository 只执行租户作用域查询和 flush，不 commit。Service 持有状态机、权限后的领域校验和事务边界。Router 只负责依赖、请求/响应模型和 envelope。

## 11. API 合同

### 11.1 Inventory

```text
GET  /api/v1/inventory/locations
POST /api/v1/inventory/locations
PUT  /api/v1/inventory/locations/{location_id}
GET  /api/v1/inventory/policies
PUT  /api/v1/inventory/policies/{policy_id}
GET  /api/v1/inventory/expiry-rules
POST /api/v1/inventory/expiry-rules
PUT  /api/v1/inventory/expiry-rules/{rule_id}
GET  /api/v1/inventory/lots
POST /api/v1/inventory/lots
GET  /api/v1/inventory/lots/{lot_id}
GET  /api/v1/inventory/serials
GET  /api/v1/inventory/serials/{serial_id}

GET  /api/v1/inventory/balances
GET  /api/v1/inventory/balances/{balance_id}
GET  /api/v1/inventory/transactions
GET  /api/v1/inventory/transactions/{transaction_id}
POST /api/v1/inventory/operations/preview
POST /api/v1/inventory/operations/{transaction_id}/execute
POST /api/v1/inventory/operations/{transaction_id}/reverse

POST /api/v1/inventory/reservations/preview
POST /api/v1/inventory/reservations/{reservation_id}/execute
POST /api/v1/inventory/reservations/{reservation_id}/release
POST /api/v1/inventory/reservations/{reservation_id}/issue

GET  /api/v1/inventory/stocktakes
POST /api/v1/inventory/stocktakes
GET  /api/v1/inventory/stocktakes/{stocktake_id}
PUT  /api/v1/inventory/stocktakes/{stocktake_id}/lines/{line_id}
POST /api/v1/inventory/stocktakes/{stocktake_id}/start
POST /api/v1/inventory/stocktakes/{stocktake_id}/review
POST /api/v1/inventory/stocktakes/{stocktake_id}/confirm
POST /api/v1/inventory/stocktakes/{stocktake_id}/cancel
```

### 11.2 Reviews

```text
GET  /api/v1/reviews/demand-lists
POST /api/v1/reviews/demand-lists/{demand_list_id}/run
GET  /api/v1/reviews/demand-lists/{review_id}
PUT  /api/v1/reviews/demand-lists/{review_id}/findings/{finding_id}/decision
POST /api/v1/reviews/demand-lists/{review_id}/batch-decisions
POST /api/v1/reviews/demand-lists/{review_id}/derive
POST /api/v1/reviews/demand-lists/{review_id}/void
```

### 11.3 Allocations

```text
GET  /api/v1/allocations/rules
POST /api/v1/allocations/rules
POST /api/v1/allocations/rules/{rule_id}/simulate
POST /api/v1/allocations/rules/{rule_id}/publish
POST /api/v1/allocations/rules/{rule_id}/retire

GET  /api/v1/allocations/plans
POST /api/v1/allocations/plans
GET  /api/v1/allocations/plans/{plan_id}
POST /api/v1/allocations/plans/{plan_id}/preview
PUT  /api/v1/allocations/plans/{plan_id}/lines/{line_id}
POST /api/v1/allocations/plans/{plan_id}/confirm
POST /api/v1/allocations/plans/{plan_id}/execute
POST /api/v1/allocations/plans/{plan_id}/void
```

所有 API 使用现有 Maintenance success/error envelope 和 `PageData`。请求不包含 tenant_id。Route inventory、actor dependency、RBAC 和 tenant ownership 由现有安全测试扩展验证。

## 12. RBAC

| 能力 | viewer | contributor | admin |
|---|---:|---:|---:|
| 查看余额、批次、流水、审查和方案 | 是 | 是 | 是 |
| 维护普通库位和批次基础信息 | 否 | 是 | 是 |
| 处理普通审查 finding | 否 | 是 | 是 |
| 预留、解除、领用、退回 | 否 | 是 | 是 |
| 编辑保障方案普通行 | 否 | 是 | 是 |
| 修改安全库存、有效期和分配 policy | 否 | 否 | 是 |
| 调拨、冻结、解冻、库存修正 | 否 | 否 | 是 |
| 反向库存事务 | 否 | 否 | 是 |
| 确认盘点 | 否 | 否 | 是 |
| 接受高风险审查调整 | 否 | 否 | 是 |
| 发布或退役分配规则 | 否 | 否 | 是 |

后端角色依赖是最终权威。现有 `/master-data/inventories/{id}/adjust` 的 contributor 权限必须在 05-4A 被关闭或改为 admin operation，修复与前端权限矩阵的不一致。

## 13. 幂等、并发和审计

### 13.1 幂等

库存执行、反向、审查运行、派生、规则发布、方案确认和方案执行均要求 Idempotency-Key。逻辑身份为 tenant＋action＋key；transaction 或 domain event 保存 request hash 和非递归响应快照。库存 transaction 的唯一约束为 tenant＋operation_type＋idempotency_key，与该逻辑身份一致。

- 同键同 hash 返回原结果；
- 同键不同 hash 返回 `IDEMPOTENCY_KEY_REUSED`；
- 无回执返回 `IDEMPOTENT_RESPONSE_UNAVAILABLE`；
- 前端对结果不确定的可重试失败保留同一逻辑命令 key；
- 成功、明确不可重试失败、输入变化或 dispose 后释放 key。

### 13.2 并发

库存执行按 balance ID 升序获取锁，避免交叉事务锁顺序不一致。PostgreSQL 使用 `SELECT ... FOR UPDATE`；SQLite 测试使用版本条件、唯一约束和受控写事务验证相同行为。执行前重新计算可用量、FEFO、serial state、policy 和其他 reservation。

批量方案采用逐行结果，但所有已完成行仍属于一个可审计 execution transaction。部分失败不会伪装成完整成功，也不会重复执行成功行。

### 13.3 审计

关键 transaction、review、rule 和 plan event 保存：

```text
tenant_id, actor_user_id, actor_roles, request_id,
idempotency_key, object type/id/version,
before summary, after summary, result, error code, occurred_at
```

数量、规则、finding decision 和 plan line 的历史不能从当前投影反推，必须以追加式 event 或 ledger 保存。

## 14. 稳定错误合同

### Inventory

```text
INVENTORY_VERSION_CONFLICT
INSUFFICIENT_AVAILABLE_INVENTORY
INVENTORY_NEGATIVE_BALANCE
INVENTORY_OPERATION_STATE_CONFLICT
LOT_EXPIRED
LOT_FROZEN
LOT_QUARANTINED
FEFO_OVERRIDE_REASON_REQUIRED
SERIAL_STATE_CONFLICT
STOCKTAKE_VERSION_CONFLICT
```

### Review

```text
DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED
REVIEW_FINDINGS_UNRESOLVED
REVIEW_VERSION_CONFLICT
REVIEW_DERIVATION_CONFLICT
```

### Allocation

```text
ALLOCATION_RULE_SIMULATION_REQUIRED
ALLOCATION_RULE_VERSION_CONFLICT
ALLOCATION_SOURCE_NOT_CURRENT
ALLOCATION_INVENTORY_CONFLICT
```

### Shared

```text
IDEMPOTENCY_KEY_REQUIRED
IDEMPOTENCY_KEY_REUSED
IDEMPOTENT_RESPONSE_UNAVAILABLE
```

错误 details 包含 `conflict_object`、expected/actual version、受影响 line 和建议动作。明确业务冲突为 `retryable: false`；网络或 5xx 结果不确定时为 `retryable: true`。

## 15. 前端信息架构

不增加一级菜单。激活现有：

- `InventoryGapPage.vue`：库存指标、余额、缺口、流水、盘点和方案入口；
- `ReviewList.vue`：审查列表、状态、阻断项和待处理数量。

新增隐藏详情路由：

```text
/platform/maintenance/inventory-gap/balances/:balanceId
/platform/maintenance/inventory-gap/transactions/:transactionId
/platform/maintenance/inventory-gap/stocktakes/:stocktakeId
/platform/maintenance/inventory-gap/allocations/:planId
/platform/maintenance/inventory-gap/rules
/platform/maintenance/reviews/:reviewId
```

前端按领域拆分：

```text
src/api/maintenance/inventory.ts
src/api/maintenance/reviews.ts
src/api/maintenance/allocations.ts

src/stores/maintenance/inventory.ts
src/stores/maintenance/review.ts
src/stores/maintenance/allocation.ts
```

Store 负责 stale response 防护、结构化错误、轮询和逻辑命令幂等 key。页面负责路由、对话框和用户确认，不构造 tenant 或业务回执。

所有库存写对话框先展示后端 preview：器材、库位、批次/序列号、前后数量、需求缺口、其他任务影响、风险和权限。确认后调用 execute；版本冲突时保留表单并提供重新加载和差异比较。

`SparePartDetail` 的库存、替代和配套标签页只显示领域查询与深链，不直接写 balance。

## 16. 测试策略

### 16.1 05-4A Gate

- Alembic upgrade、downgrade、upgrade；
- 旧库存数量和 policy 无损迁移；
- tenant unique constraints 和跨租户不可见；
- ledger immutable、delta 守恒和 balance nonnegative；
- 旧 quantity CRUD 无法绕过 ledger；
- Plan 05-1 至 05-3 受影响回归。

### 16.2 05-4B Gate

- FEFO 确定排序和排除规则；
- 过期、冻结、隔离、损坏、serial state；
- 幂等回放和并发 reservation；
- issue、return、transfer、reverse 守恒；
- stocktake baseline 和 version conflict；
- inventory API、Store、页面、权限和生产构建。

### 16.3 05-4C Gate

- current PUBLISHED source authority；
- deterministic findings reproducibility；
- AI explanation 无正式副作用；
- finding/batch decision optimistic locking；
- unresolved blockers prevent derive；
- atomic derived DRAFT 和 immutable source；
- review API、Store、页面和 RBAC。

### 16.4 05-4D Gate

- hard rule before weighted scoring；
- deterministic scores and weight validation；
- simulation inventory fingerprint unchanged；
- publish blocked without successful simulation；
- plan snapshot and current-source revalidation；
- per-line partial conflict and idempotent retry；
- end-to-end published list → review → derived publish → plan → reservation → ledger；
- full frontend test、type-check、build 和后端 Ruff。

浏览器 E2E、报告和聊天卡片留给 Plan 05-5；Plan 05-4 Gate 使用后端 integration tests 和现有前端 Node/static tests 建立确定性合同。

## 17. 文档与实施计划拆分

本设计批准后生成：

```text
docs/superpowers/plans/2026-08-03-maintenance-plan05-04-implementation-roadmap.md
docs/superpowers/plans/2026-08-03-maintenance-plan05-04a-inventory-ledger-foundation.md
docs/superpowers/plans/2026-08-03-maintenance-plan05-04b-inventory-operations-stocktake.md
docs/superpowers/plans/2026-08-03-maintenance-plan05-04c-demand-review.md
docs/superpowers/plans/2026-08-03-maintenance-plan05-04d-allocation-assurance.md
```

路线图只定义依赖、共享合同、Gate 和批准边界。四份子计划包含完整文件图、接口、RED/GREEN 命令、最小实现和独立 commit 边界。

## 18. 批准边界

本设计文档提交只授权文档工作，不授权 Plan 05-4 的生产代码、迁移或测试实现。书面规格复核通过后才编写总体路线图和四份实施计划；实施计划再次批准后，05-4A 才能进入 TDD。

05-4A、05-4B、05-4C、05-4D 的代码实施和 push 均为独立批准边界。不得因为前一阶段文档或代码通过而自动开始后一阶段。

## 19. 设计自检结论

- 当前状态：模型、API、前端占位、RBAC 和 Alembic head 均以 `56760095` 仓库状态为准；
- 范围：覆盖库存、审查、分配，明确排除采购、报告、聊天和 Plan 05-5；
- 单一事实源：balance 是 ledger 投影，旧聚合表不与新域双写；
- 权威边界：正式审查从服务端读取当前发布清单，AI 仅解释；
- 一致性：库存执行均经 preview、版本重校验、ledger 和单次 commit；
- 版本：review 生成派生 DRAFT，allocation 执行只接受当前 PUBLISHED；
- 可实施性：四个阶段均有独立数据、服务、API、前端或集成交付和 Gate；
- 完整性：文档不含占位符、未完成标记或未定义的后续决策。

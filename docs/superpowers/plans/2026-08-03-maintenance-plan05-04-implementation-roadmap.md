# Plan 05-4 Inventory, Review and Allocation Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按四个可独立验收的纵向阶段，把 Plan 05-4 的库存事实、库存操作、权威需求审查和保障分配能力落到当前代码基线。

**Architecture:** 05-4A 先用批次/序列号余额和不可变账本替代聚合库存事实；05-4B 只经库存事务服务执行 FEFO、预留、发料、退料、调拨、冻结、冲销和盘点；05-4C 建立与 AI 解释分离的权威需求审查；05-4D 用版本化规则和持久化模拟生成保障方案，并在执行时委托 05-4B 预留服务。各阶段拥有独立迁移、API、安全检查、前端或集成 Gate，后一阶段不得绕过前一阶段公开合同。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic、pytest、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 执行基线是分支 `codex/maintenance-plan05-4` 上的提交 `ca59e7e24eff3c52da2b0d887dfd74f23e1f1173`；其代码父基线是已合并并验证的 `56760095017875f98ad90b645914f41696bdb06c`。
- 权威规格是 `docs/superpowers/specs/2026-08-03-maintenance-plan05-04-inventory-review-allocation-design.md`。本路线图和四份阶段计划不得降低该规格中的状态机、RBAC、幂等、并发、审计、错误合同或批准边界。
- 历史文件 `docs/superpowers/plans/2026-07-24-maintenance-plan05-04-inventory-review-allocation.md` 只用于追溯，不得修改，也不得作为新的执行入口。
- 每个生产变更都遵循严格 RED → GREEN → REFACTOR：先运行新增测试并确认因缺少目标行为而失败，再写最小实现，再运行局部与阶段 Gate。
- 请求中的租户只能来自 `ActorContext.tenant_id`；禁止接受、信任或回显调用方提供的 `tenant_id`。
- 所有业务写操作要求 `Idempotency-Key`、版本前置条件、事务内重新校验和追加式审计；读取使用现有 Maintenance success/error envelope 与 `PageData`。
- PostgreSQL 执行路径使用固定 balance ID 顺序和 `SELECT ... FOR UPDATE`；SQLite 测试使用版本条件、唯一约束与受控写事务验证等价冲突语义。
- 前端只激活现有 Maintenance 菜单项；详情页面使用隐藏路由。页面不得生成 tenant，逻辑命令的幂等 key 由 Store 管理。
- 本计划不包含采购、财务、报告中心、聊天业务卡片、Plan 05-5 或自动抢占库存。
- 一个阶段只有在其完整 Gate、关闭复审和显式批准通过后，才能 push 或进入下一阶段。

---

## 1. 执行文档与顺序

| 顺序 | 执行文档 | 主要交付 | Alembic revision | 进入条件 |
|---|---|---|---|---|
| 1 | `2026-08-03-maintenance-plan05-04a-inventory-ledger-foundation.md` | 权威库存模型、兼容迁移、账本事务、查询与旧消费者迁移 | `20260803_08` | 本路线图和四份计划获批 |
| 2 | `2026-08-03-maintenance-plan05-04b-inventory-operations-stocktake.md` | FEFO、库存操作、预留、调拨、冻结、冲销、盘点及库存 UI | `20260803_09` | 05-4A 关闭复审获批 |
| 3 | `2026-08-03-maintenance-plan05-04c-demand-review.md` | 权威审查、发现决定、批量处理、原子派生及审查 UI | `20260803_10` | 05-4B 关闭复审获批 |
| 4 | `2026-08-03-maintenance-plan05-04d-allocation-assurance.md` | 规则版本、异步模拟、保障方案、预览与委托预留及 UI | `20260803_11` | 05-4C 关闭复审获批 |

迁移链必须严格为：

```text
20260731_07
  -> 20260803_08 (05-4A)
  -> 20260803_09 (05-4B)
  -> 20260803_10 (05-4C)
  -> 20260803_11 (05-4D)
```

同一阶段内按阶段计划列出的 task 顺序提交。禁止把后续阶段模型预先塞入较早迁移，也禁止在后续阶段继续写 `warehouse_inventories`。

## 2. 共享领域合同

### 2.1 库存数量与锁定顺序

库存余额统一使用 Decimal 字符串穿过 API，在数据库中使用固定精度 Numeric。可用量定义为：

```text
available = on_hand - reserved - damaged - quarantined
```

`in_transit` 不计入可用量；预计可用量另定义为 `available + in_transit + expected_repair`，其中 `expected_repair` 只作为分配输入，不写余额。负数余额默认禁止，且 `reserved + damaged + quarantined <= on_hand`。事务涉及多个余额时，先解析全部目标 balance，按 balance ID 升序加锁，然后在同一数据库事务内重新检查 policy、批次、序列号、预留和版本。

### 2.2 幂等与审计

库存事务唯一键为 `(tenant_id, operation_type, idempotency_key)`；相同 key 和相同规范化请求返回原响应，相同 key 和不同请求哈希返回 `IDEMPOTENCY_KEY_REUSED`。Review 与 Allocation 写命令采用同样语义，并在各自 event 表记录：actor、roles、request_id、idempotency_key、request_hash、before、after、result/error 和 occurred_at。

### 2.3 角色矩阵

| 能力 | viewer | contributor | admin |
|---|---:|---:|---:|
| 查询库存、审查、规则、模拟、方案 | ✓ | ✓ | ✓ |
| 普通库位/批次维护、审查决定、预留/解预留/发退料、方案行编辑 |  | ✓ | ✓ |
| policy/效期/规则发布、调拨/冻结/调整/冲销、盘点确认、高风险审查 |  |  | ✓ |

后端 dependency 是最终权威。每次新增 route 必须同步更新 `extensions/maintenance-api/tests/security/test_api_rbac.py` 的精确计数和函数角色映射，并覆盖 actor tenant ownership。

### 2.4 错误响应

阶段实现只使用规格第 14 节定义的稳定错误码：

```text
Inventory:
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

Review:
DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED
REVIEW_FINDINGS_UNRESOLVED
REVIEW_VERSION_CONFLICT
REVIEW_DERIVATION_CONFLICT

Allocation:
ALLOCATION_RULE_SIMULATION_REQUIRED
ALLOCATION_RULE_VERSION_CONFLICT
ALLOCATION_SOURCE_NOT_CURRENT
ALLOCATION_INVENTORY_CONFLICT

Shared:
IDEMPOTENCY_KEY_REQUIRED
IDEMPOTENCY_KEY_REUSED
IDEMPOTENT_RESPONSE_UNAVAILABLE
```

冲突 details 至少包含 `conflict_object`、expected/actual version、受影响 line 和建议动作；明确业务冲突标为 `retryable: false`，结果不确定的网络/5xx 标为 `retryable: true`。

## 3. 阶段交付与退出条件

### 3.1 05-4A：Inventory Ledger Foundation

交付 `warehouse_locations`、`inventory_policies`、`inventory_expiry_rules`、`inventory_lots`、`serialized_items`、`inventory_balances`、`inventory_transactions`、`inventory_ledger_entries`。迁移把旧聚合库存写入每个仓库的 `DEFAULT` 库位，并生成 `MIGRATION_OPENING` 账本；完成后删除旧表。Dashboard、需求计算、AI adapter、主数据导入导出和 seed 全部改读新查询合同。

退出条件：迁移 upgrade/downgrade/re-upgrade 与有细粒度数据时拒绝 downgrade；余额守恒、租户隔离、幂等、并发冲突和账本不可变测试通过；旧聚合表不再有运行时引用；全量后端回归通过。

### 3.2 05-4B：Inventory Operations and Stocktake

交付 FEFO 选择器、操作 preview/execute、预留生命周期、发退料、调拨、冻结、调整、冲销、盘点状态机，以及 Inventory Gap 和隐藏库存详情 UI。所有库存变化委托 05-4A 事务服务，禁止 API/导入/方案直接改余额。

退出条件：FEFO/效期/序列号、部分履约、两阶段调拨、冻结零 delta 状态、冲销补偿、盘点冲突、API/RBAC、Store/UI 和生产构建 Gate 通过。

### 3.3 05-4C：Demand Review

交付 `demand_list_reviews`、`demand_list_review_findings`、`demand_list_review_decisions`、`demand_list_review_events`，只允许当前 `PUBLISHED` demand list 发起正式审查。AIReviewRun 仍是非权威解释。接受/编辑接受的决定在单事务中派生新的 DRAFT，来源保持不可变。

退出条件：快照确定性、finding 决定状态机、高风险 admin 门槛、批量原子性、派生回滚、API/RBAC、ReviewList/详情 UI 和全量回归通过。

### 3.4 05-4D：Allocation and Assurance Plan

交付版本化 allocation rules、持久化无副作用模拟、保障方案和行级事件。模拟用后台 executor 与 REST polling；预览允许 CONFIRMED 或当前 PUBLISHED，执行只允许当前 PUBLISHED，并委托 05-4B reservation service。

退出条件：规则版本状态机、模拟隔离/取消/失败、确定性评分、方案并发冲突、部分成功、无自动抢占、轮询停止/可见性、API/RBAC、UI 和最终全量 Gate 通过。

## 4. 阶段统一工作流

每份阶段计划都按以下检查点执行：

- [ ] 从上一批准提交创建阶段分支/工作树，并确认 `git status --short` 为空。
- [ ] 执行阶段计划中的每个 Task；每一步先记录 RED 输出，再提交 GREEN 变更。
- [ ] 每个 commit 只包含当前 Task 的测试、实现和必要文档，不跨阶段攒提交。
- [ ] 运行阶段局部 Gate，再运行计划列出的全量 Gate；保存命令、通过数和已知 warning。
- [ ] 使用 `superpowers:requesting-code-review` 做代码审查，并逐条处理有效意见。
- [ ] 使用 `superpowers:verification-before-completion` 重新运行新鲜验证，检查迁移 head、route inventory、占位标记和工作树范围。
- [ ] 编写该阶段 Closure Review，列出规格覆盖、残留风险和下一阶段前置条件。
- [ ] 获得用户对该阶段关闭、push/PR 更新以及下一阶段启动的分别批准。

## 5. 统一验证命令

后端命令在 `extensions/maintenance-api` 下运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current
```

前端命令在仓库根运行：

```powershell
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

若当前环境没有已准备好的 `.venv` 或 pnpm 依赖，先按仓库已有安装方式恢复依赖，不改变锁文件版本。验证失败必须先使用 `superpowers:systematic-debugging` 定位原因，不能把失败标成“与本阶段无关”后继续关闭。

## 6. 计划级完成定义

Plan 05-4 只有在以下全部成立时完成：

- [ ] 四个 migration revision 按既定链部署且只有一个 Alembic head。
- [ ] 所有库存写入均可追溯到 inventory transaction 与 ledger entries，旧聚合库存表和直接写路径消失。
- [ ] 正式 demand review 与 AI 非权威 review 在模型、API 和 UI 上清晰分离。
- [ ] allocation simulation 无库存副作用，plan execute 只委托 reservation service。
- [ ] viewer/contributor/admin、tenant ownership、idempotency、expected version 和审计均有自动化证明。
- [ ] Inventory Gap、Review List 和隐藏详情路由完成；逻辑状态不依赖中文文案。
- [ ] 后端全量测试、前端全量测试、typecheck 和 production build 使用新鲜输出通过。
- [ ] 最终 Closure Review 明确 Plan 05-5 尚未开始，并取得用户批准。

## 7. 批准边界

本路线图与四份详细计划的提交只授权规划文档，不授权任何生产代码、迁移或测试实现。五份文档经复核批准后，只能开始 05-4A 的 TDD；05-4B、05-4C、05-4D 仍各自需要前序阶段关闭后的显式批准。push、PR 更新和合并也分别需要用户授权。

# Plan 05-4 Inventory, Review and Allocation Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按四个可独立验收的纵向阶段交付库存事实、库存操作、权威需求审查和保障分配，并保持每个阶段的迁移、API、安全、前端、验证和批准边界清晰。

**Architecture:** 05-4A 提供批次/序列号余额、不可变 ledger 和统一 transaction foundation；05-4B 通过 mutation plan 和领域服务交付库存操作；05-4C 建立与 AI 解释分离的权威需求审查；05-4D 用版本化规则和持久化模拟生成保障方案，并只通过 05-4B reservation service 执行预留。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic、pytest、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 权威总规格：`docs/superpowers/specs/2026-08-03-maintenance-plan05-04-inventory-review-allocation-design.md`。
- 05-4B 细化规格：`docs/superpowers/specs/2026-08-04-maintenance-plan05-04b-inventory-operations-design.md`；它对 05-4B 的命令模式、持久化、Gate 和批准边界具有更具体的约束。
- 历史文件 `docs/superpowers/plans/2026-07-24-maintenance-plan05-04-inventory-review-allocation.md` 只用于追溯，不得作为执行入口。
- 每个生产变更遵循 RED → GREEN → REFACTOR；每个 task 在 commit 前必须完成测试、范围审查和用户批准。
- 请求 tenant 只能来自 `ActorContext.tenant_id`。
- 所有业务写操作要求 Idempotency-Key、版本前置条件、事务内重校验、响应快照和追加式审计。
- PostgreSQL 使用固定锁顺序；SQLite 使用确定性并发测试验证等价冲突语义。
- 前端只激活现有 Maintenance 菜单项；详情页面用隐藏路由；页面和 Store 不生成 tenant。
- 不包含采购、财务、Plan 05-5、自动抢占或绕过库存事务服务的余额写入。
- 阶段关闭、commit、push、PR、merge 和下一阶段启动分别需要显式批准。

---

## 1. 当前状态与权威基线

| 阶段 | 状态 | 权威提交/文档 | 备注 |
|---|---|---|---|
| 05-4A | 已合并并关闭 | merge `d75ff6b4d0b6467ee7c111316570292976e897b7` | source head `8e138d8f2af77ddb624fb9875af2d6b27ebeaf90`；迁移已占用至 `20260803_10` |
| 05-4B | 设计已批准，尚未实施 | `2026-08-04-maintenance-plan05-04b-inventory-operations-design.md` | 开始实现仍需单独批准 |
| 05-4C | 未启动 | `2026-08-03-maintenance-plan05-04c-demand-review.md` | migration 改为 `20260803_12` |
| 05-4D | 未启动 | `2026-08-03-maintenance-plan05-04d-allocation-assurance.md` | migration 改为 `20260803_13` |

05-4B 实施分支必须从 `feature/maintenance-frontend-plan05` 中包含 `d75ff6b4d0b6467ee7c111316570292976e897b7` 的提交创建。不得从旧基线 `7fad43355e204e8980b8226df713e4800e6e8057` 创建，也不得复用保留的 05-4A 工作树，除非另有明确批准。

主工作树已有未跟踪文件属于保留状态，不得由 05-4B 脚本清理、stash、reset 或覆盖。`codex/maintenance-plan05-4` 和 05-4A 工作树继续保留。

## 2. 执行文档与迁移顺序

| 顺序 | 执行文档 | 主要交付 | Alembic revision | 进入条件 |
|---|---|---|---|---|
| 1 | `2026-08-03-maintenance-plan05-04a-inventory-ledger-foundation.md` | 权威库存模型、账本事务、查询与旧消费者迁移 | `20260803_08`、`20260803_09`、`20260803_10` | 已完成 |
| 2 | `2026-08-03-maintenance-plan05-04b-inventory-operations-stocktake.md` | FEFO、mutation plan、预留、发退料、调拨、冻结、冲销、盘点和 Inventory UI | `20260803_11` | 05-4A Closure 获批；05-4B 实施另行批准 |
| 3 | `2026-08-03-maintenance-plan05-04c-demand-review.md` | 权威审查、发现决定、批量处理、原子派生和 Review UI | `20260803_12` | 05-4B Closure 获批 |
| 4 | `2026-08-03-maintenance-plan05-04d-allocation-assurance.md` | 规则版本、异步模拟、保障方案、委托预留和 UI | `20260803_13` | 05-4C Closure 获批 |

权威迁移链：

```text
20260731_07
  -> 20260803_08  05-4A ledger foundation
  -> 20260803_09  05-4A target receipts
  -> 20260803_10  05-4A import execution principal
  -> 20260803_11  05-4B inventory operations and stocktake
  -> 20260803_12  05-4C demand review
  -> 20260803_13  05-4D allocation assurance
```

同一阶段不得预占后续 migration。05-4C 和 05-4D 详细计划在启动前必须把旧 revision 文本同步为 `20260803_12` 和 `20260803_13`，并重新复核实际 head。

## 3. 共享领域合同

### 3.1 数量和锁顺序

```text
available = on_hand - reserved - damaged - quarantined
```

`in_transit` 不计入 available。负数默认禁止，且 `reserved + damaged + quarantined <= on_hand`。多余额 transaction 先解析全部 balance，按 balance ID 升序锁定，再重新检查 tenant、版本、policy、lot、serial 和领域状态。

### 3.2 幂等和审计

库存 transaction 唯一键继续为 `(tenant_id, operation_type, idempotency_key)`。相同 key + 相同 canonical request 返回原 response snapshot；相同 key + 不同 request hash 返回 `IDEMPOTENCY_KEY_REUSED`。

05-4B reservation/transfer/stocktake 聚合记录 actor、roles、request ID、reference、version 和时间戳；所有数量变化仍可追溯到 transaction/ledger。05-4C/05-4D 的 event 表沿用相同 actor/request/idempotency/before/after 语义。

### 3.3 角色矩阵

| 能力 | viewer | contributor | admin |
|---|---:|---:|---:|
| 查询库存、审查、规则、模拟、方案 | ✓ | ✓ | ✓ |
| 预留/解预留/发退料、创建和录入盘点、审查决定、方案行编辑 |  | ✓ | ✓ |
| FEFO 人工偏离并填写原因 |  | ✓ | ✓ |
| 调拨、冻结、调整、冲销、盘点确认 |  |  | ✓ |
| policy/效期/规则发布、高风险审查 |  |  | ✓ |

后端 dependency 是最终权威。新增 route 必须更新 `tests/security/test_api_rbac.py` 的精确 route inventory 和 actor tenant ownership 测试。

### 3.4 稳定错误

05-4B 使用其细化规格列出的 inventory 错误码；05-4C/05-4D 保持总规格第 14 节错误合同。所有冲突 details 至少提供 conflict object、expected/actual version、affected lines、retryable 和 suggested action。

## 4. 阶段交付与退出条件

### 4.1 05-4A：Inventory Ledger Foundation（已关闭）

已交付 warehouse locations、policies、expiry rules、lots、serialized items、balances、transactions、ledger entries 和 target receipts；旧库存消费者已迁移到 ledger query/transaction contract。

关闭证据包括：

- integration 3 passed；
- focused 143 passed；
- migration 26 passed；
- full backend 878 passed, 8 deselected；
- Ruff passed；
- Alembic head `20260803_10`。

真实 PostgreSQL migration/locking 尚未执行，这一事实延续为后续部署边界，不应被方言编译替代。

### 4.2 05-4B：Inventory Operations and Stocktake

交付：

- revision `20260803_11`；
- reservation/transfer/stocktake 聚合；
- deterministic FEFO；
- `InventoryMutationPlan` 和 `InventoryTransactionService.apply_plan()`；
- 普通 reserve/release/issue/return；
- 高风险 preview/execute；
- 两阶段 transfer；
- freeze/unfreeze/adjust/reverse；
- stocktake partial confirm；
- expiry worker + lazy check；
- Inventory API/RBAC/error contracts；
- typed API/Pinia/Inventory Gap/hidden details。

内部 Gate：

1. Gate 1 后端核心；
2. Gate 2 前端集成；
3. 统一业务链和 Closure Review。

本地退出条件：迁移往返、领域/并发/API/RBAC、后端全量、前端全量、typecheck/build 和范围审查全部通过。

生产退出条件额外要求真实 PostgreSQL Gate。Closure 必须同时写：

```text
Local 05-4B status: closed
Production deployment status: blocked until PostgreSQL gate passes
```

### 4.3 05-4C：Demand Review

交付权威 review、findings、decisions、events 和 Review UI。只允许当前 PUBLISHED demand list 发起正式审查；AI review 继续是非权威解释。接受或编辑接受在单事务中派生新 DRAFT，来源保持不可变。

启动前必须：

- 05-4B Closure 获批；
- 迁移改为 `20260803_12`，down revision `20260803_11`；
- 重新确认 05-4B API 和 reservation contract 未被绕过。

### 4.4 05-4D：Allocation and Assurance

交付版本化 allocation rules、持久化无副作用 simulation、assurance plan 和行级 events。simulation 使用后台 executor + REST polling；execute 只允许当前 PUBLISHED 来源并委托 05-4B reservation service。

启动前必须：

- 05-4C Closure 获批；
- 迁移改为 `20260803_13`，down revision `20260803_12`；
- reservation owner/reference integration 通过正式 service，不直接写 reserved quantity。

## 5. 阶段统一工作流

每个阶段按以下顺序执行：

- [ ] 用户批准阶段实施；
- [ ] 使用 `using-git-worktrees` 从已验证基线创建独立工作树；
- [ ] 确认 worktree clean、branch/head、ancestor 和 migration head；
- [ ] 按 task 做 RED，确认失败原因来自缺失行为；
- [ ] 写最小 GREEN，运行 focused regression 和 `diff --check`；
- [ ] 输出 task review bundle；
- [ ] 用户批准后才 commit；
- [ ] stage Gate 使用新鲜输出；
- [ ] 使用 requesting-code-review 处理有效意见；
- [ ] 使用 verification-before-completion 重新验证；
- [ ] 编写 Closure Review；
- [ ] 分别申请 closure、commit、push、PR、merge 和下一阶段批准。

## 6. 统一验证命令

后端，在 `extensions/maintenance-api`：

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m pytest -q
& $python -m ruff check app tests
& $python -m alembic heads
& $python -m alembic current
```

前端，在仓库根：

```powershell
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

失败必须先使用 systematic-debugging 定位，不得标记“与本阶段无关”后继续关闭。缺少依赖时按仓库既有方式恢复，不擅自升级锁文件。

## 7. PostgreSQL 部署 Gate

05-4B 起，真实 PostgreSQL 部署 Gate 至少验证：

- revision `20260803_08` 到当前 head 的 upgrade/downgrade/re-upgrade；
- `SELECT ... FOR UPDATE` 和多余额固定锁顺序；
- idempotency unique winner；
- target balance concurrent create；
- reservation expiry/manual release race；
- transfer dispatch/receive race；
- stocktake confirm version conflict；
- deadlock 观测、错误映射和可控 retry。

05-4C/05-4D 如果在 PostgreSQL Gate 尚未完成前继续本地开发，仍不得解除 production blocker。

## 8. Plan 05-4 完成定义

Plan 05-4 只有在以下全部成立时完成：

- [ ] Alembic 单一 head 为 `20260803_13`；
- [ ] 所有库存写入可追溯到 transaction/ledger，旧聚合表和直接写路径消失；
- [ ] reservation、transfer、stocktake 状态机有自动化证明；
- [ ] 正式 demand review 与 AI 非权威 review 在 model/API/UI 分离；
- [ ] allocation simulation 无库存副作用，execute 只委托 reservation service；
- [ ] viewer/contributor/admin、tenant、idempotency、version、audit 有自动化证明；
- [ ] Inventory Gap、Review List 和隐藏详情完成；
- [ ] 后端/前端全量、typecheck、build 和真实 PostgreSQL deployment Gate 通过；
- [ ] 最终 Closure 明确 Plan 05-5 尚未开始并获批准。

## 9. 批准边界

本路线图修订和 05-4B 设计/计划只授权规划文档。当前明确未授权：

- 创建 05-4B branch/worktree；
- 修改生产代码、迁移或测试；
- commit/push；
- 创建、更新、ready 或 merge PR；
- 清理 05-4A branch/worktree；
- 启动 05-4C。

任何后续动作必须以用户最新明确批准为准。

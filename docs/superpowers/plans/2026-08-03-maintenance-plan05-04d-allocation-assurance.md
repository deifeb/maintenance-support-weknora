# Plan 05-4D Allocation and Assurance Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付版本化分配规则、无副作用持久化模拟和可审计保障方案，并在当前发布需求清单上把确认方案安全地执行为 05-4B 库存预留。

**Architecture:** `AllocationRuleService` 管理不可变版本和发布门槛，`AllocationSimulationService` 冻结输入并由独立 executor 异步评分，`AllocationPlanService` 用已发布规则与库存快照生成/编辑/预览方案。执行器逐行重新验证并调用 `InventoryReservationService`，保存一个可审计 execution 及每行结果；不直接写余额，不自动抢占。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、ThreadPoolExecutor 持久化 worker、pytest、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 进入条件：05-4C Closure Review 获批，Alembic head 是 `20260803_10`。本阶段 revision 是 `20260803_11`，`down_revision = "20260803_10"`。
- rule 状态：`DRAFT -> SIMULATED -> PUBLISHED -> RETIRED`。修改 SIMULATED/PUBLISHED 规则必须创建同 lineage 的新 DRAFT；不能原地改历史版本。
- simulation 状态：`PENDING -> RUNNING -> COMPLETED | FAILED | CANCELLED`；使用持久化 row + 后台 executor + REST polling，不新增 SSE。GET rules 返回 `latest_simulation` 供轮询。
- plan 状态：`DRAFT -> PREVIEWED -> CONFIRMED -> EXECUTING -> COMPLETED | PARTIALLY_COMPLETED | FAILED`；DRAFT/PREVIEWED/CONFIRMED 可转 VOIDED。
- CONFIRMED 或当前 PUBLISHED demand list 可生成/preview；execute 时 source 必须是当前 PUBLISHED。
- simulation 完全无库存副作用；开始与结束 inventory fingerprint 必须一致。plan execute 只能调用 05-4B reservation service。
- hard rules 先于 scoring；weights 规范化后总和必须精确为 Decimal `1.000000`。相同 snapshot/rule 的排名和 tie-break 必须确定。
- 批量 execute 逐行记录成功/冲突；成功行不能因另一行失败而重复，部分成功不能伪装成完整成功。
- admin 才能发布/退役规则；contributor 可创建草稿、运行模拟、创建和编辑 plan；viewer 只读。
- 本阶段不包含采购下单、成本/预算、自动抢占、报告中心、聊天卡片或 Plan 05-5。

---

## Task 1: 建立 allocation 模型与最终迁移

**Files:**

- Create: `extensions/maintenance-api/app/models/allocation.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260803_11_allocation_assurance.py`
- Create: `extensions/maintenance-api/tests/migrations/test_allocation_migration.py`
- Create: `extensions/maintenance-api/tests/models/test_allocation_models.py`

- [ ] **Step 1: 写 RED 模型/迁移测试**

断言创建 `allocation_rule_versions`、`allocation_simulations`、`allocation_simulation_results`、`allocation_plans`、`allocation_plan_lines`、`allocation_plan_events`；lineage/version 唯一；published scope/effective range 冲突可检测；状态 constraint；simulation/plan idempotency；tenant-scoped FK；upgrade/downgrade/re-upgrade 不损坏 review/inventory/demand facts。

```python
def test_rule_lineage_version_is_unique(session, rule):
    session.add(AllocationRuleVersion(
        tenant_id=rule.tenant_id, lineage_id=rule.lineage_id,
        version_number=rule.version_number, status="DRAFT",
        scope_json={"warehouse_ids": [1]}, hard_rules_json={},
        weights_json={"criticality": "1.000000"}, normalization_json={},
        change_reason="duplicate version test", version=1,
    ))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: 运行 RED**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_allocation_migration.py tests/models/test_allocation_models.py -q
```

- [ ] **Step 3: 写最小模型与 `20260803_11`**

Rule 保存 lineage/version/status/scope/effective interval/hard rules/weights/normalization/change reason/publish audit/version。Simulation 保存 candidate/baseline rule、sample/source refs、input snapshot/fingerprint、status、blockers、timestamps/error/version；results 保存 demand item/candidate、baseline/candidate ranks/scores/delta/reasons。Plan 保存 source list/version、rule、inventory fingerprint/status/version；line 保存 part、recommended balance/lot/serial、demand/allocated/gap、risks/manual override、expected balance version、reservation/result；event 保存完整审计 envelope。

- [ ] **Step 4: 运行 GREEN 与完整迁移链**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_allocation_migration.py tests/models/test_allocation_models.py -q
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_11
.\.venv\Scripts\python.exe -m alembic downgrade 20260803_10
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic heads
```

预期：唯一 head `20260803_11`。

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/allocation.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260803_11_allocation_assurance.py extensions/maintenance-api/tests/migrations/test_allocation_migration.py extensions/maintenance-api/tests/models/test_allocation_models.py
git commit -m "feat(maintenance): add allocation assurance schema"
```

## Task 2: 实现规则版本、确定性评分与发布门槛

**Files:**

- Create: `extensions/maintenance-api/app/repositories/allocation_repository.py`
- Create: `extensions/maintenance-api/app/schemas/allocation.py`
- Create: `extensions/maintenance-api/app/services/allocation_scoring.py`
- Create: `extensions/maintenance-api/app/services/allocation_rule_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_allocation_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_rule_service.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_scoring.py`

- [ ] **Step 1: 写 RED rule/scoring 测试**

覆盖 tenant scope；weights 精确求和 1；hard rule 先过滤冻结/过期/不可用候选；normalization 边界；score 使用 Decimal；相同分数按 warehouse priority/location/expiry/lot/balance ID tie-break；修改 SIMULATED/PUBLISHED 创建新 DRAFT；无最新成功模拟、规则 hash 不一致、hard-rule blocker 或高优先级退化超阈值时发布返回 `ALLOCATION_RULE_SIMULATION_REQUIRED`；scope/effective overlap 拒绝；publish/retire admin-only 与幂等。

```python
def test_scoring_is_input_order_independent(rule, candidates):
    first = rank_candidates(rule, candidates)
    second = rank_candidates(rule, list(reversed(candidates)))
    assert [x.balance_id for x in first] == [x.balance_id for x in second]
    assert [x.score for x in first] == [x.score for x in second]
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_allocation_repository.py tests/services/test_allocation_rule_service.py tests/services/test_allocation_scoring.py -q
```

- [ ] **Step 3: 写最小 repository/schema/service**

使用 `Decimal(str(value))` 解析权重，量化到统一 scale；`RuleSnapshot.canonical_hash` 覆盖 hard rules、weights、normalization、scope/effective interval。发布在锁内重新读取 latest simulation 和 overlapping published rule，写 PUBLISHED event，并退役同 scope 旧版本或拒绝不明确 overlap。

```python
def validate_weights(weights: Mapping[str, Decimal]) -> None:
    if sum(weights.values(), Decimal("0")) != Decimal("1.000000"):
        raise DomainError(
            "ALLOCATION_RULE_VERSION_CONFLICT",
            "Allocation weights must sum to 1.000000",
            details={"actual_total": str(sum(weights.values(), Decimal("0")))},
        )
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_allocation_repository.py tests/services/test_allocation_rule_service.py tests/services/test_allocation_scoring.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/allocation_repository.py extensions/maintenance-api/app/schemas/allocation.py extensions/maintenance-api/app/services/allocation_scoring.py extensions/maintenance-api/app/services/allocation_rule_service.py extensions/maintenance-api/tests/repositories/test_allocation_repository.py extensions/maintenance-api/tests/services/test_allocation_rule_service.py extensions/maintenance-api/tests/services/test_allocation_scoring.py
git commit -m "feat(maintenance): add versioned allocation rules"
```

## Task 3: 实现持久化无副作用模拟与 executor

**Files:**

- Create: `extensions/maintenance-api/app/services/allocation_simulation_service.py`
- Create: `extensions/maintenance-api/app/workers/allocation_simulation_executor.py`
- Modify: `extensions/maintenance-api/app/core/config.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_simulation_service.py`
- Create: `extensions/maintenance-api/tests/workers/test_allocation_simulation_executor.py`

- [ ] **Step 1: 写 RED 异步模拟测试**

覆盖 submit 立即持久化 PENDING；worker 原子 claim 为 RUNNING；冻结 demand/inventory/rule snapshot；baseline vs candidate results；开始/结束 inventory fingerprint 相同；任何 balance/transaction/ledger/reservation row count 与值不变；异常 -> FAILED + sanitized error；shutdown/明确取消 -> CANCELLED；重复 worker claim 不重复 results；相同 idempotency 返回同 simulation；规则列表能读 `latest_simulation`。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_simulation_service.py tests/workers/test_allocation_simulation_executor.py -q
```

- [ ] **Step 3: 写最小 service/executor**

沿用 `app/workers/calculation_group_executor.py` 的惰性 ThreadPoolExecutor、独立 SessionLocal 和 tenant+ID registry 模式。Worker 只读 snapshot 进行评分，批量写 simulation results，重算 fingerprint 后才 COMPLETED。应用 shutdown 调用 executor.shutdown；测试可注入同步 executor。

```python
def _run(tenant_id: str, simulation_id: int) -> None:
    session = SessionLocal()
    try:
        simulation = service.claim(session, tenant_id, simulation_id)
        if simulation is None:
            return
        service.run_claimed(session, tenant_id, simulation_id)
    except Exception as exc:
        service.fail_safely(tenant_id, simulation_id, exc)
    finally:
        session.close()
        registry.unregister((tenant_id, simulation_id))
```

- [ ] **Step 4: 运行 GREEN 和副作用扫描测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_simulation_service.py tests/workers/test_allocation_simulation_executor.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/allocation_simulation_service.py extensions/maintenance-api/app/workers/allocation_simulation_executor.py extensions/maintenance-api/app/core/config.py extensions/maintenance-api/tests/services/test_allocation_simulation_service.py extensions/maintenance-api/tests/workers/test_allocation_simulation_executor.py
git commit -m "feat(maintenance): add persistent allocation simulations"
```

## Task 4: 生成、编辑和预览保障方案

**Files:**

- Create: `extensions/maintenance-api/app/services/allocation_plan_service.py`
- Modify: `extensions/maintenance-api/app/repositories/allocation_repository.py`
- Modify: `extensions/maintenance-api/app/schemas/allocation.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_plan_generation.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_plan_preview.py`

- [ ] **Step 1: 写 RED 生成/预览测试**

覆盖 source 仅 CONFIRMED/current PUBLISHED；选择匹配 scope 的 PUBLISHED rule；冻结 source/rule/inventory fingerprint；按 demand item 确定生成行并计算 allocated/gap/risk；替代只建议不自动替换；in_transit/repair 只作为风险信息不计 available；contributor 可编辑普通行但必须 reason/expected version；编辑量不能负且不能超过 policy；preview 重算并保存 PREVIEWED；source/rule/balance 变化返回结构化冲突和 regenerate link。

```python
def test_plan_generation_does_not_reserve_inventory(session, actor_contributor, source):
    before = inventory_facts(session)
    plan = service.create(session, actor_contributor, source.id,
                          idempotency_key="plan-create-1")
    assert plan.status == "DRAFT"
    assert inventory_facts(session) == before
    assert all(line.reservation_id is None for line in plan.lines)
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_plan_generation.py tests/services/test_allocation_plan_preview.py -q
```

- [ ] **Step 3: 写最小 plan service**

生成用 scoring service 的相同 hard rules/tie-break；line 保存推荐 identity 和生成时 expected balance version。Edit 追加 LINE_EDITED event，不覆盖历史。Preview 在锁内重读 source/rule/current balances，写差异与 PREVIEWED event；无库存写入。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_plan_generation.py tests/services/test_allocation_plan_preview.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/allocation_plan_service.py extensions/maintenance-api/app/repositories/allocation_repository.py extensions/maintenance-api/app/schemas/allocation.py extensions/maintenance-api/tests/services/test_allocation_plan_generation.py extensions/maintenance-api/tests/services/test_allocation_plan_preview.py
git commit -m "feat(maintenance): generate and preview allocation plans"
```

## Task 5: 确认并逐行执行为库存预留

**Files:**

- Modify: `extensions/maintenance-api/app/services/allocation_plan_service.py`
- Modify: `extensions/maintenance-api/app/services/inventory_reservation_service.py`
- Modify: `extensions/maintenance-api/app/schemas/allocation.py`
- Create: `extensions/maintenance-api/tests/services/test_allocation_plan_execution.py`

- [ ] **Step 1: 写 RED 执行测试**

覆盖只有 PREVIEWED 可 CONFIRMED；execute 前 source 必须 current PUBLISHED，否则 `ALLOCATION_SOURCE_NOT_CURRENT`；rule 仍 published；plan expected version；每行 balance version/available/FEFO 重验证；委托 reservation service 并保存 reservation ID；成功全部 -> COMPLETED，部分冲突 -> PARTIALLY_COMPLETED，全部失败 -> FAILED；成功行重试不重复 reserve；无自动抢占；冲突返回 `ALLOCATION_INVENTORY_CONFLICT`、line、expected/actual 与 regenerate suggestion。

```python
def test_execute_delegates_each_successful_line_once(session, actor_contributor, plan, spy):
    result = service.execute(session, actor_contributor, plan.id,
                             expected_version=plan.version,
                             idempotency_key="plan-exec-1")
    assert result.status == "COMPLETED"
    assert spy.reserve.call_count == len(plan.lines)
    replay = service.execute(session, actor_contributor, plan.id,
                             expected_version=plan.version,
                             idempotency_key="plan-exec-1")
    assert replay.id == result.id
    assert spy.reserve.call_count == len(plan.lines)
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_plan_execution.py -q
```

- [ ] **Step 3: 写最小 confirm/execute**

Confirm 冻结 preview snapshot 并追加 event。Execute 把 plan 标为 EXECUTING，按 line ID 逐行调用 reservation service，子幂等 key 固定为 `allocation-plan:{plan_id}:line:{line_id}:execute:{execution_id}`；每行在 savepoint 内完成，失败写 line error/event，成功行立即有审计且重放可识别。汇总状态不隐藏失败。

- [ ] **Step 4: 运行 GREEN 与 05-4B reservation 回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_allocation_plan_execution.py tests/services/test_inventory_reservation_service.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/allocation_plan_service.py extensions/maintenance-api/app/services/inventory_reservation_service.py extensions/maintenance-api/app/schemas/allocation.py extensions/maintenance-api/tests/services/test_allocation_plan_execution.py
git commit -m "feat(maintenance): execute allocation plans as reservations"
```

## Task 6: 暴露 Allocations API 与安全合同

**Files:**

- Create: `extensions/maintenance-api/app/api/v1/allocations/__init__.py`
- Create: `extensions/maintenance-api/app/api/v1/allocations/router.py`
- Create: `extensions/maintenance-api/app/api/v1/allocations/rules.py`
- Create: `extensions/maintenance-api/app/api/v1/allocations/plans.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Create: `extensions/maintenance-api/tests/security/test_allocation_routes_actor_context.py`
- Create: `extensions/maintenance-api/tests/api/test_allocations_api.py`

- [ ] **Step 1: 写 RED API/RBAC 测试**

覆盖规格 11.3：rules list/create/simulate/publish/retire；plans list/create/get/preview/update line/confirm/execute/void。GET rules item 必须含 `latest_simulation` 状态、进度、blockers 和 results summary，使客户端无需新增 SSE 或额外未批准 route 即可轮询。断言角色、tenant 404、PageData/envelope/meta、Idempotency-Key、expected version 和稳定错误。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_allocations_api.py tests/security/test_allocation_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 3: 写薄 route 并注册 `/api/v1/allocations`**

GET 使用 ViewerDep；create/simulate/plan edits/preview/confirm/execute 使用 ContributorDep；publish/retire 使用 AdminDep。所有 write route 用 Header alias `Idempotency-Key`，route 不提交事务、不构造 tenant、不直接调用 inventory repository。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_allocations_api.py tests/security/test_allocation_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api/v1/allocations extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/tests/api/test_allocations_api.py extensions/maintenance-api/tests/security/test_allocation_routes_actor_context.py extensions/maintenance-api/tests/security/test_api_rbac.py
git commit -m "feat(maintenance): expose allocation assurance API"
```

## Task 7: 建立 allocation 前端 API、Store 与可见性轮询

**Files:**

- Create: `frontend/src/api/maintenance/allocations.ts`
- Create: `frontend/src/api/maintenance/__tests__/allocations.test.ts`
- Create: `frontend/src/stores/maintenance/allocation.ts`
- Create: `frontend/src/stores/maintenance/__tests__/allocation.test.ts`
- Create: `frontend/src/composables/maintenance/useAllocationSimulationPolling.ts`
- Create: `frontend/src/composables/maintenance/__tests__/allocation-simulation-polling.test.ts`
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`

- [ ] **Step 1: 写 RED API/Store/轮询测试**

断言 URL/body/header/type；command key 生命周期；规则/方案 stale response；simulate 后立即轮询 GET rules，PENDING/RUNNING 继续，COMPLETED/FAILED/CANCELLED 停止；页面 hidden 时暂停、恢复时立即刷新；无重叠请求；dispose 清 timer 和 pending key；publish/retire admin permission；不使用 EventSource/SSE。

```typescript
test('polling stops at a terminal simulation state', async () => {
  const controller = createAllocationSimulationPolling({
    load: sequence('PENDING', 'RUNNING', 'COMPLETED'),
    timers,
  })
  await controller.start()
  await timers.runNext()
  await timers.runNext()
  assert.equal(timers.pendingCount(), 0)
})
```

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/allocations.test.ts src/stores/maintenance/__tests__/allocation.test.ts src/composables/maintenance/__tests__/allocation-simulation-polling.test.ts
```

- [ ] **Step 3: 写最小 API/Store/composable**

轮询组合 `usePageVisibilityPolling.ts`，interval 2000 ms，可注入 timer 便于测试。Store 暴露 rule list/create/simulate/publish/retire 和 plan list/create/load/edit/preview/confirm/execute/void；不保存 tenant，不使用中文状态作为逻辑。

- [ ] **Step 4: 运行 GREEN 与 typecheck**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/allocations.test.ts src/stores/maintenance/__tests__/allocation.test.ts src/composables/maintenance/__tests__/allocation-simulation-polling.test.ts
pnpm --dir frontend typecheck
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/allocations.ts frontend/src/api/maintenance/__tests__/allocations.test.ts frontend/src/stores/maintenance/allocation.ts frontend/src/stores/maintenance/__tests__/allocation.test.ts frontend/src/composables/maintenance/useAllocationSimulationPolling.ts frontend/src/composables/maintenance/__tests__/allocation-simulation-polling.test.ts frontend/src/stores/maintenance/permission-matrix.ts
git commit -m "feat(maintenance): add allocation frontend state"
```

## Task 8: 实现规则与保障方案 UI

**Files:**

- Create: `frontend/src/views/maintenance/inventory-gap/AllocationRuleList.vue`
- Create: `frontend/src/views/maintenance/inventory-gap/AllocationPlanDetail.vue`
- Create: `frontend/src/components/maintenance/allocation/RuleEditor.vue`
- Create: `frontend/src/components/maintenance/allocation/SimulationComparison.vue`
- Create: `frontend/src/components/maintenance/allocation/AllocationPlanTable.vue`
- Create: `frontend/src/components/maintenance/allocation/PlanExecutionSummary.vue`
- Modify: `frontend/src/views/maintenance/inventory-gap/InventoryGapPage.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Create: `frontend/src/views/maintenance/__tests__/allocation-navigation.test.ts`
- Create: `frontend/src/components/maintenance/allocation/__tests__/allocation-workflow.test.ts`

- [ ] **Step 1: 写 RED UI/导航测试**

覆盖隐藏 `/platform/maintenance/inventory-gap/rules` 与 `/allocations/:planId`；rule weights 合计/硬规则验证；simulate progress/terminal blocker；只有 admin 发布/退役；从 CONFIRMED/PUBLISHED list 生成 plan；风险/缺口/推荐 identity；普通行编辑 reason；preview/confirm/execute 二次确认；PARTIALLY_COMPLETED 显示成功和冲突行及 regenerate link；不增加一级菜单。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/allocation-navigation.test.ts src/components/maintenance/allocation/__tests__/allocation-workflow.test.ts
```

- [ ] **Step 3: 写最小 UI**

规则页使用表单和比较表；方案页使用 server data + line edit dialog + execution summary。所有动作通过 Store；页面只生成用户确认，不生成 tenant/header。结构化冲突保留编辑并显示 expected/actual/retryable/suggested_action。

- [ ] **Step 4: 运行 GREEN、typecheck、build**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/allocation-navigation.test.ts src/components/maintenance/allocation/__tests__/allocation-workflow.test.ts
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/maintenance/inventory-gap frontend/src/components/maintenance/allocation frontend/src/router/maintenance.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/views/maintenance/__tests__/allocation-navigation.test.ts
git commit -m "feat(maintenance): add allocation assurance workspace"
```

## Task 9: 05-4D 最终集成 Gate 与 Plan 05-4 关闭复审

**Files:**

- Create: `extensions/maintenance-api/tests/integration/test_allocation_assurance_workflow.py`
- Create: `extensions/maintenance-api/tests/integration/test_plan05_04_cross_domain_invariants.py`
- Create: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04d-closure-review.md`
- Create: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04-final-closure-review.md`

- [ ] **Step 1: 写 RED 跨域端到端测试**

从 current PUBLISHED demand list + inventory lots 创建 rule，异步 simulation 完成且 inventory fingerprint 不变，admin publish，create/edit/preview/confirm/execute plan；一行成功、一行并发冲突，断言 PARTIALLY_COMPLETED、成功 reservation 只一次、冲突不抢占、ledger/review/rule/plan events 链路完整。再覆盖 source superseded 时 execute 阻断。

- [ ] **Step 2: 运行 RED 并只修接线**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_allocation_assurance_workflow.py tests/integration/test_plan05_04_cross_domain_invariants.py -q
```

- [ ] **Step 3: 运行 05-4D 阶段 Gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_allocation_migration.py tests/models/test_allocation_models.py tests/repositories/test_allocation_repository.py tests/services/test_allocation_rule_service.py tests/services/test_allocation_scoring.py tests/services/test_allocation_simulation_service.py tests/workers/test_allocation_simulation_executor.py tests/services/test_allocation_plan_generation.py tests/services/test_allocation_plan_preview.py tests/services/test_allocation_plan_execution.py tests/api/test_allocations_api.py tests/security/test_allocation_routes_actor_context.py tests/security/test_api_rbac.py tests/integration/test_allocation_assurance_workflow.py tests/integration/test_plan05_04_cross_domain_invariants.py -q
```

- [ ] **Step 4: 运行 Plan 05-4 最终全量 Gate**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current
rg -n "WarehouseInventory|warehouse_inventories" app --glob "*.py"
cd ..\..
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

预期：唯一 head/current `20260803_11`；旧运行时库存引用为零；全部后端/前端测试、typecheck、production build 使用新鲜输出通过。

- [ ] **Step 5: 审查并编写双层 Closure Review**

使用 `superpowers:requesting-code-review`。05-4D Review 覆盖 rule/simulation/plan；Final Review 逐项映射批准规格第 1–18 节、四个阶段 Gate、迁移链、跨域 invariant、已知 warning 和残留风险，并明确采购/报告/chat/Plan 05-5 未开始。

- [ ] **Step 6: 最终验证并提交 review**

使用 `superpowers:verification-before-completion` 重跑 Step 3–4 后：

```powershell
git add extensions/maintenance-api/tests/integration/test_allocation_assurance_workflow.py extensions/maintenance-api/tests/integration/test_plan05_04_cross_domain_invariants.py docs/superpowers/reviews/2026-08-03-maintenance-plan05-04d-closure-review.md docs/superpowers/reviews/2026-08-03-maintenance-plan05-04-final-closure-review.md
git commit -m "test(maintenance): close plan05-4 allocation assurance"
git status --short
```

- [ ] **Step 7: 停止并请求批准**

报告全部 commits、迁移 head、测试/build 新鲜证据和 Final Closure Review；等待用户分别批准 push、PR 更新、合并或进入 Plan 05-5。不得自动执行任何一项。

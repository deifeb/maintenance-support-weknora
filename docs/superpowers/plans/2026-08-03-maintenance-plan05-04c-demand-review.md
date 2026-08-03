# Plan 05-4C Authoritative Demand Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立只面向当前发布需求清单的权威审查域，支持确定性 findings、逐条/批量决定和原子派生新 DRAFT，并完成 Review List 与隐藏详情页。

**Architecture:** 新的 `DemandReviewService` 在运行时复制 demand list 与库存/规则证据快照，产生独立 review/finding/decision/event 记录；现有 `AIReviewRun` 只保留非权威解释职责。决定修改 review 投影但不改来源清单；derive 在单事务中调用现有 `DemandListService` 创建新 DRAFT 和应用已接受决定，任一失败整体回滚。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic、pytest、Vue 3.5、Pinia 3、TypeScript 6、TDesign Vue Next、Vitest、Vite 7。

## Global Constraints

- 进入条件：05-4B Closure Review 获批，Alembic head 是 `20260803_09`。本阶段 revision 是 `20260803_10`，`down_revision = "20260803_09"`。
- 正式 review 只接受 actor tenant 下 `status=PUBLISHED AND is_current=true` 的 DemandList；调用方不能提交 items 或 tenant。
- review source snapshot、finding evidence 和决定历史不可从可变表反推；event 只追加。
- finding decision 状态：`PENDING | ACCEPTED | REJECTED | EDIT_ACCEPTED`。普通 finding contributor 可处理；高风险接受或编辑接受需要 admin。
- review 状态严格为 `CREATED -> RUNNING -> OPEN -> READY_TO_DERIVE -> DERIVED`，RUNNING 可转 FAILED，OPEN/READY_TO_DERIVE 可转 VOIDED；有未处理 blocking finding 时保持 OPEN。
- derive 前所有 blocking finding 必须有最终决定；来源清单永不修改。派生结果固定为同 lineage 的新 DRAFT，并保留 source review/decision lineage。
- run、batch decision、derive、void 要求 Idempotency-Key 和 expected version；repository 不 commit，service 持有事务边界。
- 现有 `/api/v1/ai/reviews/demand-lists`、`AIReviewRun` 和 AI finding 不升级为权威记录，也不得被新 API 返回为 formal review。
- 本阶段读取库存能力但不创建 reservation，不实现 allocation rules/plans。

---

## Task 1: 建立权威 review 模型与迁移

**Files:**

- Create: `extensions/maintenance-api/app/models/demand_review.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260803_10_authoritative_demand_review.py`
- Create: `extensions/maintenance-api/tests/migrations/test_demand_review_migration.py`
- Create: `extensions/maintenance-api/tests/models/test_demand_review_models.py`

- [ ] **Step 1: 写 RED 迁移/模型测试**

断言四张表 `demand_list_reviews`、`demand_list_review_findings`、`demand_list_review_decisions`、`demand_list_review_events`；tenant-scoped 外键/索引；review run idempotency 唯一键；finding stable key 在 review 内唯一；每次决定追加 decision/event；非法状态和非法 severity 被 constraint 拒绝；upgrade/downgrade/re-upgrade 不影响 demand list 与 inventory facts。

```python
def test_finding_identity_is_stable_inside_review(session, review):
    session.add_all([
        DemandReviewFinding(tenant_id=review.tenant_id, review_id=review.id,
                            finding_key="QUANTITY_SPIKE:part-1", finding_type="QUANTITY_SPIKE",
                            severity="HIGH", blocking=True, evidence_snapshot_json={},
                            suggestion_snapshot_json={}, status="PENDING"),
        DemandReviewFinding(tenant_id=review.tenant_id, review_id=review.id,
                            finding_key="QUANTITY_SPIKE:part-1", finding_type="QUANTITY_SPIKE",
                            severity="HIGH", blocking=True, evidence_snapshot_json={},
                            suggestion_snapshot_json={}, status="PENDING"),
    ])
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: 运行 RED**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_demand_review_migration.py tests/models/test_demand_review_models.py -q
```

- [ ] **Step 3: 写最小模型和 `20260803_10`**

Review 保存 demand_list_id/version、status、snapshot_json、summary counts、derived_demand_list_id、version 和 run actor/request/idempotency。Finding 保存 stable key、type、severity、blocking、demand_list_item_id、evidence/suggestion snapshot 与当前 decision status。Decision 保存 action、suggested_quantity、final_quantity、reason、actor/roles、before/after、request hash。Event 保存完整审计 envelope。SQLAlchemy `__tablename__` 必须分别使用上述四个完整表名。

- [ ] **Step 4: 运行 GREEN 与迁移往返**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_demand_review_migration.py tests/models/test_demand_review_models.py -q
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_10
.\.venv\Scripts\python.exe -m alembic downgrade 20260803_09
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_10
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models/demand_review.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260803_10_authoritative_demand_review.py extensions/maintenance-api/tests/migrations/test_demand_review_migration.py extensions/maintenance-api/tests/models/test_demand_review_models.py
git commit -m "feat(maintenance): add authoritative demand review schema"
```

## Task 2: 建立 repository、schema 与确定性 review runner

**Files:**

- Create: `extensions/maintenance-api/app/repositories/demand_review_repository.py`
- Create: `extensions/maintenance-api/app/schemas/demand_review.py`
- Create: `extensions/maintenance-api/app/services/demand_review_rules.py`
- Create: `extensions/maintenance-api/app/services/demand_review_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_demand_review_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_demand_review_runner.py`

- [ ] **Step 1: 写 RED runner 测试**

覆盖非 PUBLISHED/非 current source 返回 `DEMAND_LIST_REVIEW_SOURCE_NOT_PUBLISHED`；snapshot 包含 source list/version/items/events、场景/计算/决定、构型/替代/配套/技术依据、库存/修理/保障能力和规则版本/input hash；相同 snapshot 产生相同 finding keys/order；完整性、构型适用性、配套缺失、比例、互斥、共用重复、替代有效性、可靠性异常、模型异常、库存缺口和证据有效性均有表驱动 finding 用例；tenant B source 为 404；相同 key/hash 返回原 review，不同 hash 报 `IDEMPOTENCY_KEY_REUSED`。

```python
def test_runner_uses_server_side_published_source(session, actor_contributor, published_list):
    review = demand_review_service.run(
        session, actor_contributor, published_list.id,
        idempotency_key="review-run-1",
    )
    assert review.source_demand_list_version == published_list.version
    assert review.source_snapshot_json["items"][0]["id"] == published_list.items[0].id
    assert "tenant_id" not in review.source_snapshot_json["request"]
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_demand_review_repository.py tests/services/test_demand_review_runner.py -q
```

- [ ] **Step 3: 写最小规则与 service**

规则函数接收不可变 `DemandReviewSnapshot` 并返回按 `(severity_rank, demand_list_item_id, finding_key)` 排序的 findings。Runner 先写 CREATED/RUNNING，在同一服务事务读取 current published list、调用 inventory query、冻结 snapshot、写 findings/OPEN event 和 response snapshot；规则异常时用独立受控事务保存 FAILED 与脱敏错误，不留下半套 findings。

```python
def run_rules(snapshot: DemandReviewSnapshot) -> Sequence[FindingDraft]:
    findings = [*quantity_findings(snapshot), *inventory_findings(snapshot),
                *expiry_findings(snapshot), *criticality_findings(snapshot)]
    return tuple(sorted(findings, key=lambda x: (
        SEVERITY_ORDER[x.severity], x.demand_list_item_id or 0, x.finding_key
    )))
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_demand_review_repository.py tests/services/test_demand_review_runner.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/demand_review_repository.py extensions/maintenance-api/app/schemas/demand_review.py extensions/maintenance-api/app/services/demand_review_rules.py extensions/maintenance-api/app/services/demand_review_service.py extensions/maintenance-api/tests/repositories/test_demand_review_repository.py extensions/maintenance-api/tests/services/test_demand_review_runner.py
git commit -m "feat(maintenance): add deterministic demand review runner"
```

## Task 3: 实现 finding 决定、批量原子性与 review 状态机

**Files:**

- Modify: `extensions/maintenance-api/app/services/demand_review_service.py`
- Modify: `extensions/maintenance-api/app/repositories/demand_review_repository.py`
- Modify: `extensions/maintenance-api/app/schemas/demand_review.py`
- Create: `extensions/maintenance-api/tests/services/test_demand_review_decisions.py`

- [ ] **Step 1: 写 RED 决定测试**

覆盖 ACCEPTED/REJECTED/EDIT_ACCEPTED；EDIT_ACCEPTED 必须保存建议数量、正 Decimal 最终数量和 reason；普通 contributor 可处理普通 finding；高风险接受需 admin，但拒绝可由 contributor；expected review/finding version 冲突 -> `REVIEW_VERSION_CONFLICT`；batch 任一非法则全部回滚；有 blocking PENDING 时保持 OPEN，全部 blocking 已处理时进入 READY_TO_DERIVE；每次变化追加 decision 与 event，旧 decision 不修改。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_demand_review_decisions.py -q
```

- [ ] **Step 3: 写最小决定状态机**

批量命令先按 finding ID 排序锁 review/findings，验证所有 action/RBAC/version，再一次应用。Review summary 从当前 finding 投影重算；不能靠客户端传 counts。Review 已 VOIDED/DERIVED 时拒绝决定。

```python
with session.begin_nested():
    review = repo.lock_review(session, actor.tenant_id, review_id)
    findings = repo.lock_findings(session, actor.tenant_id, sorted(ids))
    validated = [
        validate_decision(actor, review, finding_by_id[command.finding_id], command)
        for command in commands
    ]
    for decision in validated:
        append_decision_and_event(session, actor, review, decision)
    refresh_review_counts(review)
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_demand_review_decisions.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/demand_review_service.py extensions/maintenance-api/app/repositories/demand_review_repository.py extensions/maintenance-api/app/schemas/demand_review.py extensions/maintenance-api/tests/services/test_demand_review_decisions.py
git commit -m "feat(maintenance): add demand review decisions"
```

## Task 4: 原子派生新 DRAFT 并保护来源不可变

**Files:**

- Modify: `extensions/maintenance-api/app/services/demand_review_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_list_service.py`
- Modify: `extensions/maintenance-api/app/models/demand_list.py`
- Modify: `extensions/maintenance-api/app/schemas/demand_review.py`
- Create: `extensions/maintenance-api/tests/services/test_demand_review_derivation.py`

- [ ] **Step 1: 写 RED 派生测试**

断言 unresolved blocking finding -> `REVIEW_FINDINGS_UNRESOLVED`；source 不再 current/version 变化 -> `REVIEW_DERIVATION_CONFLICT`；ACCEPTED 使用建议，EDIT_ACCEPTED 使用编辑 quantity，REJECTED 保持原值；新 list 是 DRAFT、同 lineage、`derived_from_id=source.id`；source/items/version 完全不变；中途一个 item 失败时 review/list/events 全回滚；重复 key 返回同一 derived list。

```python
before = snapshot_demand_list(session, source.id)
result = service.derive(session, actor_admin, review.id,
                        expected_version=review.version,
                        idempotency_key="derive-review-1")
assert result.demand_list.status.value == "DRAFT"
assert result.demand_list.derived_from_id == source.id
assert snapshot_demand_list(session, source.id) == before
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_demand_review_derivation.py -q
```

- [ ] **Step 3: 增加内部原子派生接口**

在 `DemandListService` 增加接受现有 session/actor、source ID、变更 map 和 lineage metadata 的内部方法；它只 flush 不 commit。Review service 持有外层事务，锁 review/source，重新验证 current published 和版本，创建 list、应用 changes、写双方 event，最后设置 review DERIVED。

- [ ] **Step 4: 运行 GREEN 与现有 demand list 回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_demand_review_derivation.py tests/services/test_demand_list_service.py tests/api/test_demand_lists.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/demand_review_service.py extensions/maintenance-api/app/services/demand_list_service.py extensions/maintenance-api/app/models/demand_list.py extensions/maintenance-api/app/schemas/demand_review.py extensions/maintenance-api/tests/services/test_demand_review_derivation.py
git commit -m "feat(maintenance): derive demand drafts from reviews"
```

## Task 5: 暴露独立 Reviews API 与 RBAC

**Files:**

- Create: `extensions/maintenance-api/app/api/v1/reviews/__init__.py`
- Create: `extensions/maintenance-api/app/api/v1/reviews/router.py`
- Create: `extensions/maintenance-api/app/api/v1/reviews/demand_lists.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Create: `extensions/maintenance-api/tests/security/test_review_routes_actor_context.py`
- Create: `extensions/maintenance-api/tests/api/test_demand_reviews_api.py`

- [ ] **Step 1: 写 RED API/RBAC 测试**

覆盖规格 11.2 七条 route：list、run、get、single decision、batch decisions、derive、void。精确断言 viewer reads、contributor run/普通决定、admin 高风险/derive/void，Idempotency-Key 和 expected_version，PageData/envelope/meta，tenant B 404，以及与 `/api/v1/ai/reviews/demand-lists` 响应类型明确不同。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_demand_reviews_api.py tests/security/test_review_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 3: 写薄 route 并注册 `/api/v1/reviews`**

函数名稳定为 `list_demand_list_reviews`、`run_demand_list_review`、`get_demand_list_review`、`decide_demand_review_finding`、`batch_decide_demand_review_findings`、`derive_demand_list_from_review`、`void_demand_list_review`，同步安全测试精确映射与 route count。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_demand_reviews_api.py tests/security/test_review_routes_actor_context.py tests/security/test_api_rbac.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api/v1/reviews extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/tests/api/test_demand_reviews_api.py extensions/maintenance-api/tests/security/test_review_routes_actor_context.py extensions/maintenance-api/tests/security/test_api_rbac.py
git commit -m "feat(maintenance): expose authoritative review API"
```

## Task 6: 建立 review 前端 API 与 Pinia Store

**Files:**

- Create: `frontend/src/api/maintenance/demand-reviews.ts`
- Create: `frontend/src/api/maintenance/__tests__/demand-reviews.test.ts`
- Create: `frontend/src/stores/maintenance/demandReview.ts`
- Create: `frontend/src/stores/maintenance/__tests__/demand-review.test.ts`
- Modify: `frontend/src/stores/maintenance/permission-matrix.ts`

- [ ] **Step 1: 写 RED API/Store 测试**

断言所有 URL/query/body/header；逻辑 command key 的保留/释放规则；list/detail 请求 generation；run 后导航数据；batch decision 失败保持用户选择；derive 成功返回新 demand list ID；dispose 后旧响应不能写 state；高风险 action permission 与 admin 对齐。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/demand-reviews.test.ts src/stores/maintenance/__tests__/demand-review.test.ts
```

- [ ] **Step 3: 写最小 API/Store**

沿用 Maintenance client injection、`MaintenanceResult` 和 demandList Store 的 stale-response/command-key 模式。类型包含 review/finding/decision/event、稳定 enum 和 DecimalString；不复用 AI review 类型，不保存 tenant。

- [ ] **Step 4: 运行 GREEN 与 typecheck**

```powershell
pnpm --dir frontend test -- src/api/maintenance/__tests__/demand-reviews.test.ts src/stores/maintenance/__tests__/demand-review.test.ts
pnpm --dir frontend typecheck
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/demand-reviews.ts frontend/src/api/maintenance/__tests__/demand-reviews.test.ts frontend/src/stores/maintenance/demandReview.ts frontend/src/stores/maintenance/__tests__/demand-review.test.ts frontend/src/stores/maintenance/permission-matrix.ts
git commit -m "feat(maintenance): add demand review frontend state"
```

## Task 7: 激活 Review List 与隐藏 Review Detail

**Files:**

- Modify: `frontend/src/views/maintenance/reviews/ReviewList.vue`
- Create: `frontend/src/views/maintenance/reviews/ReviewDetail.vue`
- Create: `frontend/src/components/maintenance/reviews/ReviewSummary.vue`
- Create: `frontend/src/components/maintenance/reviews/FindingTable.vue`
- Create: `frontend/src/components/maintenance/reviews/FindingDecisionDialog.vue`
- Modify: `frontend/src/router/maintenance.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Create: `frontend/src/views/maintenance/__tests__/review-navigation.test.ts`
- Create: `frontend/src/components/maintenance/reviews/__tests__/review-workflow.test.ts`

- [ ] **Step 1: 写 RED UI 测试**

覆盖 list status/blocking/pending counts、从 current published list 发起 run、hidden `/platform/maintenance/reviews/:reviewId`、finding filter/selection、单条和批量决定、高风险按钮隐藏/禁用、EDIT_ACCEPTED quantity/reason 验证、冲突详情、derive 确认并跳转新 DemandListDetail、AI 非权威标签不混入列表。

- [ ] **Step 2: 运行 RED**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/review-navigation.test.ts src/components/maintenance/reviews/__tests__/review-workflow.test.ts
```

- [ ] **Step 3: 写最小页面/组件**

页面只调用 Store，使用英文 enum 驱动标签/按钮；i18n 提供中文和英文文案。结构化冲突在对话框内展示 expected/actual 和建议动作，不清空用户编辑。隐藏详情 route 不加入 menu definition。

- [ ] **Step 4: 运行 GREEN、typecheck、build**

```powershell
pnpm --dir frontend test -- src/views/maintenance/__tests__/review-navigation.test.ts src/components/maintenance/reviews/__tests__/review-workflow.test.ts
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/maintenance/reviews frontend/src/components/maintenance/reviews frontend/src/router/maintenance.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/views/maintenance/__tests__/review-navigation.test.ts
git commit -m "feat(maintenance): add authoritative review workspace"
```

## Task 8: 05-4C 集成 Gate 与关闭复审

**Files:**

- Create: `extensions/maintenance-api/tests/integration/test_authoritative_review_workflow.py`
- Create: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04c-closure-review.md`

- [ ] **Step 1: 写 RED 端到端测试**

发布 current demand list，建立库存风险，run review，contributor 拒绝普通 finding，admin 编辑接受高风险 finding，derive 新 DRAFT；断言 source 不变、新 list lineage/quantity、所有 decision/event actor/idempotency/request hash，以及 AI review 表没有被当作 formal source。

- [ ] **Step 2: 运行 RED 并只修 wiring**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_authoritative_review_workflow.py -q
```

- [ ] **Step 3: 运行完整阶段 Gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_demand_review_migration.py tests/models/test_demand_review_models.py tests/repositories/test_demand_review_repository.py tests/services/test_demand_review_runner.py tests/services/test_demand_review_decisions.py tests/services/test_demand_review_derivation.py tests/api/test_demand_reviews_api.py tests/security/test_review_routes_actor_context.py tests/security/test_api_rbac.py tests/integration/test_authoritative_review_workflow.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
cd ..\..
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

预期：唯一 head `20260803_10`；后端/前端全量、typecheck、production build 全绿。

- [ ] **Step 4: 审查、验证并提交 Closure Review**

使用 `superpowers:requesting-code-review`，处理意见后用 `superpowers:verification-before-completion` 获取新鲜 Gate。Review 必须证明 source published/current gate、AI/正式域分离、批量原子性、source immutability、派生 rollback、RBAC 与 UI 权限。

```powershell
git add extensions/maintenance-api/tests/integration/test_authoritative_review_workflow.py docs/superpowers/reviews/2026-08-03-maintenance-plan05-04c-closure-review.md
git commit -m "test(maintenance): close plan05-4c demand review"
git status --short
```

- [ ] **Step 5: 停止并请求批准**

等待用户分别批准 05-4C push/PR 更新及进入 05-4D；不得自动开始 allocation。

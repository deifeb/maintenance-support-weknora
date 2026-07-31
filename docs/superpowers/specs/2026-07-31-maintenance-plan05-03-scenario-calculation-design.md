# Plan 05-3 场景、并行需求计算与需求清单设计

**状态：** 已确认
**确认日期：** 2026-07-31
**目标分支：** `feature/maintenance-frontend-plan05`
**依赖：** Plan 05-1、Plan 05-2 已通过验收门禁

## 1. 背景

Plan 05-1 已建立 WeKnora 到 Maintenance API 的认证代理、internal JWT、租户隔离、RBAC、幂等和审计基础。Plan 05-2 已交付原生维护导航、工作台、基础数据页面、详情页和 Excel 导入导出闭环。

当前仓库已经具备：

- `DemandScenarioTemplate`、`DemandScenarioVersion` 及阶段、机群、年龄组、参数覆盖和共同冲击等正式场景模型；
- 单次 `DemandCalculation`、计算运行、器材结果和贡献明细；
- `ANALYTICAL`、`MONTE_CARLO`、`COMPARE` 执行模式；
- `EXPONENTIAL`、`WEIBULL`、`BINOMIAL`、`NEGATIVE_BINOMIAL` 等可靠性模型；
- AI 会话、快照、持久化事件和 SSE；
- tenant-aware 后台任务执行器；
- Vue 维护模块的 API 客户端、权限矩阵、服务器分页、轮询和通用状态组件。

场景和计算前端目前仍是占位页面。现有后端能够完成正式场景和单次需求计算，但尚未提供可恢复的六步草稿向导、确定性候选推荐、多候选独立编排、组级 SSE、逐项结果决策和版本化需求清单。

## 2. 设计目标

本设计交付一条完整且可恢复的业务链：

```text
AI 会话或人工创建
→ 场景草稿与六步向导
→ 正式 DemandScenarioVersion
→ 确定性候选推荐
→ CalculationGroup
→ 多个独立 DemandCalculation
→ 结果标准化、比较和逐项决策
→ 版本化 DemandList
```

必须满足：

- 草稿服务端持久化，浏览器状态不作为权威来源；
- 高风险必填字段未经确认不能进入正式计算；
- 模型推荐由确定性规则生成，LLM 只能解释，不能改变适用性或排序；
- 可靠性模型和计算执行模式是两个独立维度；
- 每个候选方案是独立计算任务，单项失败不取消其他候选；
- SSE 可按持久化序号断线续接并去重；
- 原始计算结果不可被人工决策修改；
- 正式需求数量只能来自成功的确定性结果或有审计记录的人工调整；
- 发布后的需求清单不可原地修改；
- 所有业务记录、任务、事件和导出结果保持租户隔离。

## 3. 非目标

以下内容不属于 Plan 05-3：

- 库存预留、领用、退回、调拨、冻结和盘点；
- 需求审查规则引擎及批量审查建议；
- 库存缺口保障方案和多任务分配；
- 报告中心及 Markdown、JSON、DOCX 报告版本；
- WeKnora 聊天中的最终业务卡片渲染。

Plan 05-3 会返回稳定的场景草稿导航数据，供 Plan 05-5 的聊天卡片使用；不会提前实现 Plan 05-5 的聊天 UI。

## 4. 关键语义修正

原始计划把 `MONTE_CARLO` 与四种可靠性模型并列为同一种 `model_type`。这与现有需求引擎的领域模型不一致。

本设计明确区分：

```text
reliability_model:
  EXPONENTIAL
  WEIBULL
  BINOMIAL
  NEGATIVE_BINOMIAL

execution_mode:
  ANALYTICAL
  MONTE_CARLO
  COMPARE
```

一个候选方案由以下二元组唯一描述：

```text
(reliability_model, execution_mode)
```

例如：

```text
WEIBULL + ANALYTICAL
WEIBULL + MONTE_CARLO
EXPONENTIAL + ANALYTICAL
```

确定性推荐先判断可靠性模型适用性，再为该模型选择执行模式。`COMPARE` 表示同一可靠性模型同时产生解析法和蒙特卡洛运行结果，不代表新的可靠性模型。

## 5. 方案决策

采用“轻量后端编排层复用现有计算能力”：

- 正式场景继续由现有 `ScenarioService` 管理；
- 单次候选计算继续由现有 `DemandCalculationService` 和 `DemandTaskExecutor` 执行；
- 新增 `CalculationGroup` 聚合根编排多个独立计算；
- 新增持久化组事件支持 SSE；
- 新增逐项决策记录，保持原始结果只读；
- 新增版本化 `DemandList` 聚合根。

不把多候选状态塞入现有 `DemandCalculation`，也不让前端承担权威编排职责。

## 6. 阶段拆分

### 6.1 05-3A：场景草稿与六步向导

交付：

- 人工创建和 AI 创建的场景草稿；
- 基于 AI 会话快照的服务端持久化；
- 六步向导；
- 防抖自动保存、冲突处理和页面离开保护；
- 字段来源、置信度、风险、证据和人工确认；
- 草稿校验及正式场景转换。

### 6.2 05-3B：模型推荐、并行计算与结果决策

交付：

- 确定性模型推荐；
- 输入快照预览；
- 候选方案选择；
- 计算组、独立子任务和失败项重试；
- 持久化组事件、SSE 恢复和轮询降级；
- 标准化结果比较；
- 器材级模型选择和人工数量调整。

### 6.3 05-3C：版本化需求清单

交付：

- 从计算决策生成需求清单草稿；
- 条目来源快照；
- `DRAFT → PENDING_CONFIRMATION → CONFIRMED → PUBLISHED → VOIDED` 生命周期；
- 高风险管理员确认；
- 发布不可变、派生新版本和谱系管理；
- 完整审计及双租户、三角色验收。

每个子阶段必须独立通过门禁后才能进入下一阶段。

## 7. 场景草稿设计

### 7.1 权威存储

继续使用现有：

```text
AISession
AISessionSnapshot
```

快照字段职责：

- `scenario_draft_json`：六步向导结构化业务内容；
- `field_sources_json`：字段来源、置信度、风险、确认和证据引用；
- `execution_context_json`：来源类型、当前步骤、完成度、阻断字段和校验摘要；
- `snapshot_version`：乐观锁版本。

人工新建草稿时创建结构化 AI 会话和初始快照，但不调用 LLM。`execution_context_json.origin` 使用 `MANUAL` 或 `AI`，便于审计和恢复。

### 7.2 字段状态

每个受控字段具备：

```text
value
source
confidence
risk
confirmed
evidence_refs
```

`source` 至少支持：

```text
MASTER_DATA
USER_INPUT
AI_INFERRED
SYSTEM_DEFAULT
DERIVED
```

`risk` 使用：

```text
LOW
MEDIUM
HIGH
BLOCKING
```

高风险必填字段未确认时加入 `blocking_fields`。正式化前，服务器重新计算完成度和阻断项，不信任前端提交的校验结果。

### 7.3 六步向导

固定步骤：

1. 基础信息：名称、任务编码、起止时间、描述和优先级；
2. 装备构型：装备型号、构型版本、机群、数量和年龄组；
3. 任务条件：有序阶段、时长、利用率、环境和任务强度；
4. 可靠性与修理：参数来源、失效过程、周转策略、修复返回和共同冲击；
5. 计算设置：服务水平、执行偏好、仿真配置和缺参策略；
6. 确认提交：来源汇总、假设、未解决项、变更摘要和正式化操作。

### 7.4 草稿 API

Maintenance API 内部路径：

```text
POST /api/v1/demand/scenario-drafts
GET  /api/v1/demand/scenario-drafts/{session_id}
PUT  /api/v1/demand/scenario-drafts/{session_id}
POST /api/v1/demand/scenario-drafts/{session_id}/validate
POST /api/v1/demand/scenario-drafts/{session_id}/materialize
```

浏览器统一经过：

```text
/api/maintenance/v1/demand/scenario-drafts/*
```

保存请求包含 `expected_version`。冲突返回稳定错误码 `SCENARIO_DRAFT_VERSION_CONFLICT`、服务器当前版本和冲突对象摘要。

`materialize` 必须：

- 校验 `expected_version`；
- 无阻断字段；
- 重新校验所有主数据引用的租户和有效性；
- 接受 `Idempotency-Key`；
- 调用现有 `ScenarioService` 创建模板、版本及全部子记录，执行正式校验并发布该版本；
- 在同一事务中写入审计及草稿正式化结果。

任一子记录或发布校验失败时回滚整个事务，不留下部分正式场景。成功响应返回状态为 `PUBLISHED` 的 `scenario_version_id`。幂等重放返回同一个正式场景及版本，不重复创建业务记录。

### 7.5 AI 草稿桥接

现有 allowlist 中的场景工具继续作为唯一 AI 写入入口：

```text
create_scenario_draft
update_scenario_draft
validate_scenario_draft
get_scenario_preview
```

这些工具调用同一个 `ScenarioDraftService`，不能直接写正式场景表。工具结果返回：

```text
session_id
draft_version
status
blocking_fields
navigation_url
```

`navigation_url` 指向：

```text
/platform/maintenance/scenarios/new?session_id={session_id}
```

AI 工具不能执行 `materialize`。正式化必须由经过权限校验的用户在六步向导中显式触发。

## 8. 确定性模型推荐

推荐器不调用 LLM 决定排序。输入为已发布场景版本和当前可验证参数快照。

每个候选返回：

```text
candidate_key
reliability_model
execution_mode
applicable
score
reasons
missing_requirements
parameter_sources
risk
rule_version
```

推荐规则版本固定记录为：

```text
MODEL-RECOMMENDATION-1
```

适用性规则示例：

- `EXPONENTIAL` 要求失效率、装机数量和任务时长；
- `WEIBULL` 要求形状、尺度、装机数量和任务时长；
- `BINOMIAL` 要求单周期失效概率和试验数量；
- `NEGATIVE_BINOMIAL` 要求均值和离散参数；
- `MONTE_CARLO` 执行模式要求随机种子和仿真上限；
- 存在共同冲击、维修管道、多阶段或参数不确定性时，提高蒙特卡洛执行模式得分。

LLM 可提供解释文本，但不能修改 `applicable`、`score`、`reasons`、`missing_requirements` 或 `rule_version`。

接口：

```text
POST /api/v1/demand/model-recommendations
```

## 9. 计算组设计

### 9.1 数据模型

新增：

```text
calculation_groups
calculation_group_children
calculation_group_events
calculation_item_decisions
```

`calculation_groups` 保存：

- tenant、场景版本和聚合状态；
- 主候选键；
- 推荐结果快照；
- 参数选择快照；
- 乐观锁版本；
- 创建者和时间。

`calculation_group_children` 保存：

- `candidate_key`；
- `reliability_model`；
- `execution_mode`；
- 关联 `calculation_id`；
- `attempt_number`；
- `is_current_attempt`；
- 选择理由和创建时间。

子任务运行状态以关联的 `DemandCalculation` 为权威来源。计算组缓存聚合状态用于列表查询，但每次转换都由当前子任务状态重新计算。

`calculation_group_events` 保存单调递增的组内 `sequence`、子任务引用、事件类型、载荷和时间。

`calculation_item_decisions` 保存：

- 器材 ID；
- 系统推荐子任务；
- 用户选择子任务；
- 原始数量和最终数量；
- 决策类型和理由；
- 风险等级；
- 是否需要管理员确认；
- 风险规则版本；
- 乐观锁版本。

### 9.2 约束

唯一约束至少包括：

```text
(tenant_id, group_id, candidate_key, attempt_number)
(tenant_id, group_id, sequence)
(tenant_id, group_id, spare_part_id)
```

创建新尝试时，旧尝试保留且 `is_current_attempt = false`。成功尝试不会因为其他候选重试而重复执行。

### 9.3 状态

计算组状态：

```text
PENDING
RUNNING
COMPLETED
PARTIALLY_COMPLETED
FAILED
CANCELLED
INTERRUPTED
```

解析规则：

- 全部待执行为 `PENDING`；
- 任意当前子任务运行或待执行为 `RUNNING`；
- 全部成功为 `COMPLETED`；
- 全部失败为 `FAILED`；
- 成功与失败、取消或中断并存为 `PARTIALLY_COMPLETED`；
- 全部取消为 `CANCELLED`；
- 没有成功结果且存在中断为 `INTERRUPTED`；
- 没有成功结果、没有中断且失败与取消并存时为 `FAILED`。

### 9.4 API

```text
POST /api/v1/demand/calculation-groups
GET  /api/v1/demand/calculation-groups
GET  /api/v1/demand/calculation-groups/{group_id}
POST /api/v1/demand/calculation-groups/{group_id}/retry-failed
POST /api/v1/demand/calculation-groups/{group_id}/cancel-running

GET  /api/v1/demand/calculation-groups/{group_id}/events
GET  /api/v1/demand/calculation-groups/{group_id}/events/stream
GET  /api/v1/demand/calculation-groups/{group_id}/comparison

PUT  /api/v1/demand/calculation-groups/{group_id}/decisions/{spare_part_id}
```

创建、失败重试和取消接受 `Idempotency-Key`。决策更新接受 `expected_version`。

### 9.5 任务恢复

- `PENDING` 子任务在服务恢复时重新入队；
- 超过恢复阈值的 `RUNNING` 子任务标记为 `INTERRUPTED`；
- `INTERRUPTED` 不自动重算，需要用户显式重试；
- 已成功子任务不重新执行；
- 任务注册键包含 `tenant_id` 和计算 ID；
- 子任务状态更新和对应组事件在同一事务中提交。

## 10. SSE 和进度恢复

事件至少覆盖：

```text
group.created
child.queued
child.started
child.progress
child.completed
child.failed
child.cancelled
group.status_changed
decision.updated
```

服务端以事件 `sequence` 作为 SSE `id`。客户端通过最后接收的序号恢复，只返回缺失事件。

`heartbeat` 是连接级临时帧，不写入事件表、不占用业务事件序号。

前端规则：

- reducer 只接受严格大于当前序号的事件；
- 路由或 group ID 变化使旧连接和旧请求失效；
- 浏览器隐藏时关闭 SSE；
- 重新可见时从最后序号立即连接；
- 连续连接失败后降级为有限频率状态轮询；
- SSE 恢复后停止降级轮询；
- 页面卸载释放连接和定时器。

## 11. 结果比较与逐项决策

比较只使用成功子任务。每个器材统一展示：

- 推荐数量；
- 均值和分位数；
- 预测或置信范围；
- 可用库存和净缺口；
- 风险等级；
- 参数来源及警告；
- 运行耗时、随机种子和收敛状态。

默认决策采用系统推荐候选。以下操作必须填写理由：

- 选择非系统首选候选；
- 人工修改数量；
- 采用非默认执行模式结果。

原始计算结果始终只读。决策是独立记录，不能回写 `DemandRunItemResult`。

比较集合是全部成功候选器材结果的并集。某个候选缺少某器材结果时显示明确的 `NO_RESULT`，不得把缺失值解释为零。系统默认只能选择实际包含该器材成功结果的候选。

风险规则版本：

```text
DEMAND-DECISION-RISK-1
```

以下情况需要管理员确认：

- 关键件或高风险器材被人工下调；
- 最终数量比选定结果建议低 10% 及以上；
- 最终数量超出所有成功候选的预测范围；
- 用户选择与系统首选不同且差异达到规则阈值；
- 结果存在缺参、未收敛或高等级警告。

风险判断由服务器执行并保存规则版本，前端只呈现结果。

## 12. 需求清单设计

### 12.1 数据模型

新增：

```text
demand_lists
demand_list_items
```

每个 `demand_lists` 记录代表一个独立版本，包含：

- `lineage_id`；
- `version_number`；
- `derived_from_id`；
- `scenario_version_id`；
- `calculation_group_id`；
- 状态和乐观锁版本；
- 是否为当前发布版本；
- `superseded_by_id` 和 `superseded_at`；
- 提交、确认、发布、作废的 actor 和时间。

`demand_list_items` 保存生成时的不可变来源快照：

- 器材身份快照；
- 来源计算组、子任务、计算和运行；
- 可靠性模型和执行模式；
- 原始模型数量；
- 最终数量；
- 调整类型、理由和风险；
- 参数、区间、警告和库存摘要。

需求数量及相关数值使用 `Numeric/Decimal`。

对外 JSON 中的 Decimal 使用十进制字符串传输，前端只在展示边界格式化，不能经过二进制浮点往返后再提交。

### 12.2 生命周期

唯一生命周期：

```text
DRAFT
→ PENDING_CONFIRMATION
→ CONFIRMED
→ PUBLISHED
→ VOIDED
```

规则：

- `DRAFT` 可编辑，不参与正式保障统计；
- `PENDING_CONFIRMATION` 等待管理员处理风险项；
- `CONFIRMED` 内容冻结，可发布；
- `PUBLISHED` 成为当前有效版本，不可原地修改；
- `VOIDED` 保留历史和审计，不参与新业务；
- 发布新派生版本后，旧发布版本保持 `PUBLISHED` 历史状态，但 `is_current = false` 并记录 superseded 关系；
- 同一 `lineage_id` 在任一时刻最多一个 `is_current = true` 的发布版本。

### 12.3 API

```text
POST /api/v1/demand/demand-lists
GET  /api/v1/demand/demand-lists
GET  /api/v1/demand/demand-lists/{list_id}
PUT  /api/v1/demand/demand-lists/{list_id}/items/{item_id}

POST /api/v1/demand/demand-lists/{list_id}/submit
POST /api/v1/demand/demand-lists/{list_id}/confirm
POST /api/v1/demand/demand-lists/{list_id}/publish
POST /api/v1/demand/demand-lists/{list_id}/derive
POST /api/v1/demand/demand-lists/{list_id}/void
```

清单创建、状态迁移和派生接受 `Idempotency-Key`。条目更新和状态迁移接受 `expected_version`。

发布事务锁定同一谱系，重新校验当前发布版本，并在同一事务中更新新旧版本关系和审计。

从计算组生成清单前必须满足：

- 计算组已经进入终态；
- 至少存在一个成功候选；
- 比较并集中的每个器材都有已保存决策；
- 所有决策引用当前尝试的成功结果；
- 不存在未处理的结构校验错误。

未确认的高风险决策可以生成并提交 `PENDING_CONFIRMATION` 清单，但不能进入 `CONFIRMED` 或 `PUBLISHED`。

## 13. 权限

### viewer

- 查看场景、计算组、比较、决策和需求清单；
- 不能保存草稿、启动计算、重试、取消、修改决策或迁移清单状态。

### contributor

- 创建和编辑场景草稿；
- 正式化无阻断场景；
- 发起计算组；
- 重试失败任务和取消运行任务；
- 记录逐项决策；
- 生成、编辑和提交需求清单草稿。

### admin

- 具备 contributor 能力；
- 确认高风险决策；
- 确认、发布、派生和作废需求清单。

权限由前端能力矩阵和后端依赖同时执行。后端是最终权威。

## 14. 前端设计

### 14.1 路由

```text
/platform/maintenance/scenarios
/platform/maintenance/scenarios/new
/platform/maintenance/scenarios/:scenarioId
/platform/maintenance/scenarios/:scenarioId/versions/:versionId

/platform/maintenance/calculations
/platform/maintenance/calculations/new
/platform/maintenance/calculations/:groupId/progress
/platform/maintenance/calculations/:groupId/comparison

/platform/maintenance/demand-lists/:listId
```

场景和计算列表保留一级维护菜单入口。详情路由设置 `hideInMaintenanceMenu`，并继承登录、初始化和权限元数据。

### 14.2 API 边界

按业务职责拆分：

```text
frontend/src/api/maintenance/scenarios.ts
frontend/src/api/maintenance/model-recommendations.ts
frontend/src/api/maintenance/calculation-groups.ts
frontend/src/api/maintenance/demand-lists.ts
```

所有请求复用现有 maintenance client。浏览器代码不得包含 Maintenance API 地址、internal JWT secret 或 tenant 选择字段。

### 14.3 状态和控制器

核心状态：

```text
scenarioDraft store
calculationGroup store
demandList store
```

纯 TypeScript 控制器：

```text
debounced autosave
resumable SSE
calculation group event reducer
comparison decision reducer
```

草稿保存状态：

```text
idle → dirty → saving → saved
                   ↘ error
                   ↘ conflict
```

自动保存规则：

- 800ms 防抖；
- 保存请求串行执行；
- 后续编辑在当前保存完成后继续保存；
- 旧响应不能覆盖新 generation；
- 保存失败保持 dirty；
- 手动重试复用最新本地内容；
- 页面离开前 flush，失败时由用户选择停留或放弃。

### 14.4 页面

场景：

```text
ScenarioList
ScenarioWizard
ScenarioDetail
```

计算：

```text
CalculationList
CalculationSetup
CalculationProgress
CalculationComparison
```

需求清单：

```text
DemandListDetail
```

计算设置页展示输入快照、确定性推荐和候选选择。不适用候选可查看原因，但不能选中。

进度页为每个子任务显示模型、执行模式、尝试次数、阶段、百分比和错误。部分失败不遮挡成功结果。

比较页以器材为行、候选为列。切换候选或人工调整打开决策抽屉，要求填写原因并展示服务器风险判断。

需求清单详情展示版本谱系、来源、条目、风险、生命周期时间线和审计摘要。

## 15. 并发、一致性和审计

保护方式：

- 草稿保存：`expected_version`；
- 草稿正式化：`expected_version + Idempotency-Key`；
- 计算组创建、重试、取消：`Idempotency-Key`；
- 逐项决策：决策 `expected_version`；
- 清单修改：清单 `expected_version`；
- 清单迁移：`expected_version + Idempotency-Key`；
- 发布：事务锁、谱系唯一约束和事务内重检。

冲突响应必须包含：

- 稳定错误码；
- 当前对象版本；
- 冲突对象或字段；
- 建议的用户动作；
- `request_id`；
- `retryable`。

前端不自动覆盖服务器数据，只提供重新加载、差异比较和重新提交。

关键操作审计：

- 场景草稿正式化；
- 计算组创建；
- 子任务重试和取消；
- 人工模型选择和数量调整；
- 清单提交、确认、发布、派生和作废。

审计保存 actor、tenant、request ID、幂等键、对象版本、前后摘要、关联对象和失败原因。

## 16. 异常与降级

| 异常 | 处理 |
|---|---|
| Maintenance API 暂时不可用 | 草稿保持 dirty/error，允许手动重试，不显示已保存 |
| 自动保存版本冲突 | 保留本地和服务器版本，禁止自动覆盖 |
| 主数据引用失效 | 正式化和计算前重新校验并返回阻断字段 |
| 单个候选计算失败 | 组进入 `PARTIALLY_COMPLETED`，保留其他结果 |
| 全部候选失败 | 禁止比较决策和需求清单生成 |
| SSE 中断 | 按最后序号恢复；连续失败后降级轮询 |
| 服务重启 | 恢复待执行任务，中断超时任务，不重复成功任务 |
| AI 或外部模型不可用 | 关闭 AI 草稿生成，手工向导和确定性业务继续 |
| 跨租户访问 | 返回安全的 404 或权限拒绝并记录安全审计 |
| 发布竞争 | 事务内重检谱系当前版本，冲突请求返回 409 |

计算使用不可变输入快照。计算启动后的主数据变化不修改历史结果。

## 17. 测试设计

### 17.1 05-3A

后端测试文件：

```text
tests/services/test_scenario_draft_service.py
tests/api/test_scenario_draft_api.py
tests/integration/test_ai_scenario_wizard_handoff.py
```

覆盖：

- 人工与 AI 草稿；
- 快照版本递增；
- 版本冲突；
- 租户隔离和 RBAC；
- 阻断字段；
- 引用重检；
- 幂等正式化；
- AI 不可用时的手工降级。

前端测试文件：

```text
src/composables/maintenance/__tests__/autosave.test.ts
src/stores/maintenance/__tests__/scenario-draft.test.ts
src/components/maintenance/scenario/__tests__/wizard-validation.test.ts
src/views/maintenance/__tests__/scenario-navigation.test.ts
```

覆盖六步校验、防抖、串行保存、stale response、冲突、页面离开和角色能力。

### 17.2 05-3B

后端测试文件：

```text
tests/services/test_model_recommendation_service.py
tests/services/test_calculation_group_service.py
tests/api/test_calculation_groups.py
tests/workers/test_calculation_group_recovery.py
tests/migrations/test_calculation_group_migration.py
```

覆盖确定性排序、语义分离、独立子任务、部分失败、失败项重试、事件序号、恢复、租户隔离和决策风险。

前端测试文件：

```text
src/composables/maintenance/__tests__/resumable-sse.test.ts
src/stores/maintenance/__tests__/calculation-group.test.ts
src/components/maintenance/calculation/__tests__/model-selection.test.ts
src/components/maintenance/calculation/__tests__/comparison-decisions.test.ts
src/views/maintenance/__tests__/calculation-navigation.test.ts
```

覆盖候选禁用、互斥请求、SSE 恢复、轮询降级、旧响应隔离、部分成功、理由和风险显示。

### 17.3 05-3C

后端测试文件：

```text
tests/services/test_demand_list_service.py
tests/api/test_demand_lists.py
tests/migrations/test_demand_list_migration.py
```

覆盖生命周期、非法迁移、权限、幂等、不可变发布、派生谱系、唯一当前版本、数值精度和审计。

前端测试文件：

```text
src/stores/maintenance/__tests__/demand-list.test.ts
src/components/maintenance/calculation/__tests__/demand-list-lifecycle.test.ts
src/views/maintenance/__tests__/demand-list-navigation.test.ts
```

覆盖状态操作、角色边界、高风险确认、发布只读、派生跳转和时间线。

### 17.4 端到端业务链

集成测试：

```text
tests/integration/test_plan05_scenario_calculation.py
```

完整链路：

```text
contributor 创建或恢复场景草稿
→ 六步确认并正式化
→ 推荐候选
→ 启动三个独立子任务
→ 一个失败、两个成功
→ SSE 中断恢复
→ 仅重试失败项
→ 比较全部成功结果
→ 切换部分器材模型并调整数量
→ 生成需求清单草稿
→ contributor 提交
→ admin 确认并发布
→ 派生第二版并发布
→ 第一版保留且标记 superseded
→ 第二租户不可见
→ viewer 写操作全部被拒绝
```

## 18. 验收门禁

### 18.1 05-3A 门禁

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py `
  tests/integration/test_ai_scenario_wizard_handoff.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

### 18.2 05-3B 门禁

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_model_recommendation_service.py `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/workers/test_calculation_group_recovery.py `
  tests/migrations/test_calculation_group_migration.py `
  -v
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

### 18.3 05-3C 和最终门禁

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest `
  tests/services/test_scenario_draft_service.py `
  tests/api/test_scenario_draft_api.py `
  tests/services/test_model_recommendation_service.py `
  tests/services/test_calculation_group_service.py `
  tests/api/test_calculation_groups.py `
  tests/services/test_demand_list_service.py `
  tests/api/test_demand_lists.py `
  tests/integration/test_plan05_scenario_calculation.py `
  -v
.\.venv\Scripts\python.exe -m ruff check app tests

cd ..\..\frontend
npm run test
npm run type-check
npm run build

cd ..
go test ./internal/maintenanceproxy ./internal/router
git diff --check
```

## 19. 验收证据

阶段完成时保存：

- 人工创建和 AI 创建的场景草稿；
- 六步向导和草稿恢复；
- 保存成功、失败和冲突状态；
- 字段来源、证据、风险和阻断项；
- 不适用模型及缺失条件；
- 三个候选中单项失败的进度；
- SSE 恢复前后事件序号；
- 仅失败项重试；
- 结果比较和人工决策审计；
- 需求清单生命周期和版本谱系；
- viewer、contributor、admin 权限矩阵；
- 双租户隔离；
- 后端、前端、迁移、Ruff、Go 和 diff 检查输出。

截图是人工 UX 验收证据，不能替代自动化测试。

## 20. 实施与提交边界

实施计划拆成三份：

```text
05-3A 场景草稿与六步向导
05-3B 模型推荐、计算组与结果决策
05-3C 需求清单生命周期与最终验收
```

每份计划内部继续采用测试先行、小步提交。数据库迁移、后端状态机和前端大页面不合并成一个提交。

建议提交边界：

- 场景草稿后端合同；
- 前端自动保存与 store；
- 六步向导；
- AI 草稿桥接；
- 确定性模型推荐；
- 计算组迁移与服务；
- 计算设置与进度；
- SSE 恢复；
- 比较与逐项决策；
- 需求清单迁移与状态机；
- 需求清单 UI；
- 最终验收和文档。

## 21. 回滚策略

- 前端路由和页面可独立回滚，不影响已有 Plan 05-2 页面；
- 新增 API 路由可从 demand router 移除，不改变现有场景和单次计算端点；
- 新表通过独立 Alembic 迁移创建，迁移必须支持逐版本降级；
- 新计算组只引用现有计算，不改变历史 `DemandCalculation` 的语义；
- 发布清单回滚通过作废或派生版本完成，不删除审计历史；
- 不使用破坏性 Git 操作或清理用户现有工作树内容。

## 22. 设计决策汇总

- 采用后端轻量编排层，复用现有正式场景和单次计算服务；
- 把可靠性模型与执行模式分开；
- Plan 05-3 拆为 05-3A、05-3B、05-3C 三个独立门禁；
- 场景草稿保存在 AI 会话快照；
- 手工流程不依赖 LLM；
- 多候选计算由 `CalculationGroup` 编排；
- 每个候选对应独立 `DemandCalculation`；
- 组事件持久化并支持 SSE 序号恢复；
- 原始结果只读，人工选择保存在独立决策记录；
- 需求清单使用严格五状态生命周期；
- 发布版本不可原地修改，修改必须派生；
- contributor 准备和提交，admin 确认高风险并发布；
- 库存、审查、分配和报告继续留在 Plan 05-4、05-5。

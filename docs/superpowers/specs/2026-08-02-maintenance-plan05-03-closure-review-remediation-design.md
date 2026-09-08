# Plan 05-3 Closure Review Remediation 设计

**状态：** 待批准实施

**日期：** 2026-08-02

**目标分支：** `feature/maintenance-frontend-plan05`

**审查基准：** `027de0bf7eda07f845b1555d063603e072ecb7d0`

**关联 PR：** `#4`

## 1. 背景与关闭条件

Plan 05-3 的自动化 Gate 已通过，但关闭代码审查发现四项仍会破坏幂等、审计或服务端权威边界的问题：

1. 创建需求清单及 submit、confirm、publish、derive、void 的前端重试会生成新幂等键；
2. `DemandListRead` 回放快照递归携带历史事件的 `response_snapshot_json`；
3. `ITEM_UPDATED` 事件不足以恢复被覆盖的历史决策状态；
4. 服务端可以从空比较结果创建零条目的 DRAFT。

本整改只关闭上述审查项。只有整改测试、Plan 05-3 Gate 和关闭复审全部通过后，PR #4 才能进入合并决策；Plan 05-4 在此之前保持冻结。

## 2. 目标与非目标

### 2.1 目标

- 同一逻辑命令在结果不确定的可重试失败后复用同一幂等键；
- 成功、明确不可重试失败、输入变化或页面释放后，后续逻辑命令使用新键；
- 所有持久化回放快照均为非递归的 `DemandListRead`，且首次响应与幂等回放完全一致；
- 每个 `ITEM_UPDATED` 事件独立保存更新前后的完整可变决策状态；
- 空比较结果在创建任何 list、item 或 event 之前被服务端拒绝；
- 保持现有路由、数据库结构、公开请求体和响应模型兼容。

### 2.2 非目标

- 不新增幂等回执表或数据库迁移；
- 不删除事件模型公开的 `response_snapshot_json`；
- 不修改计算组比较规则、风险判定规则或生命周期状态机；
- 不处理 Vite 500 kB 分块警告；
- 不开始 Plan 05-4，不合并 PR #4，不清理工作树。

## 3. 方案比较

### 3.1 方案 A：现有边界内的无迁移整改（采用）

在 `DemandListService` 增加空结果断言、规范化回放快照和决策摘要构造器；在 `demandList` Store 中集中生成并保留逻辑命令键；页面不再自行生成键。

优点是变更面与四项审查发现一一对应，不改变数据库和 HTTP 合同，能够用现有服务测试、Store 测试和全量 Gate 证明。代价是每个事件仍保存一份线性大小的规范化读取快照，但不会再递归嵌套或指数式膨胀。

### 3.2 方案 B：新增独立幂等回执模型

新增回执表，将请求哈希和规范化响应从审计事件中拆出。边界最清晰，也便于将来设置保留策略，但需要迁移、仓储层、回填与更多并发验证，超出关闭审查的最小整改范围。

### 3.3 方案 C：仅在页面缓存键并隐藏嵌套快照

页面级变量可以覆盖当前两个页面，却不能保证未来调用方或 Store 复用；只在序列化时隐藏字段也不能修复已经持久化的递归结构。该方案不能建立稳定的领域合同，因此不采用。

## 4. 总体设计

整改保持四个独立单元：

```text
CalculationComparison / DemandListDetail
                |
                | 无幂等键参数
                v
        demandList Store
        - 识别逻辑命令
        - 生成/复用/释放键
                |
                | 现有 Idempotency-Key HTTP 合同
                v
        DemandListService
        - 拒绝空比较结果
        - 保存非递归回放快照
        - 保存完整 ITEM_UPDATED 摘要
```

四项整改不互相共享持久化状态，可分别完成 RED、GREEN 和审查。最终 Gate 才把它们作为一个关闭整改整体进行验证。

## 5. 前端逻辑命令幂等

### 5.1 Store 为唯一键所有者

`frontend/src/stores/maintenance/demandList.ts` 成为创建和五个生命周期命令的幂等键所有者。Store 的公开方法改为：

```ts
create(request: DemandListCreateRequest): Promise<DemandList>
submit(): Promise<DemandList>
confirm(confirmationNote: string): Promise<DemandList>
publish(): Promise<DemandList>
derive(): Promise<DemandList>
voidList(): Promise<DemandList>
```

Store 到 API 的内部接口不变，仍显式传递 `idempotencyKey`。

### 5.2 逻辑命令身份

每个待定命令由 `action + fingerprint` 标识：

- create：`calculation_group_id + normalized name + normalized description`；
- submit、publish、derive、void：`demand_list_id + expected_version`；
- confirm：`demand_list_id + expected_version + exact confirmation note`。

Store 为每个 action 保留至多一个 `{ fingerprint, idempotencyKey }`。相同 action 和 fingerprint 重试时复用键。输入变化表示用户发起了新的逻辑命令，替换旧 fingerprint 并生成新键。

### 5.3 键生命周期

| 结果 | 键处理 |
|---|---|
| 成功并获得服务端响应 | 删除该逻辑命令键 |
| `retryable: true` 或无 HTTP 状态的网络失败 | 保留键 |
| `retryable: false` | 删除键 |
| 输入发生变化 | 生成新逻辑命令键 |
| `dispose()` | 清空全部待定键，表示用户离开并放弃当前页面命令 |

键工厂注入 `createDemandListState`，测试使用确定性序列；生产默认使用 `crypto.randomUUID()`，缺失时使用时间戳与随机串组合。页面删除 `requestKey()`，错误重试自然重新调用 Store 的同一个逻辑命令。

## 6. 非递归回放快照

`DemandListService` 增加一个纯规范化函数：深拷贝 `DemandListRead`，将副本中所有 `events[*].response_snapshot_json` 置为 `None`。创建和五个生命周期命令在提交前统一：

1. 构造当前 `DemandListRead`；
2. 生成规范化副本；
3. 将规范化副本写入当前事件的 `response_snapshot_json`；
4. 将同一规范化副本作为首次响应返回。

因此首次响应、顺序幂等回放和并发竞争恢复仍严格相等；顶层事件回执仍可被 `DemandListRead.model_validate` 校验；任何回执内部的事件快照均为 `null`，递归在一层终止。普通 GET 仍可读取每个顶层事件的规范化回执，不改变响应字段。

已有数据不做迁移。整改生效后新事件不再制造递归；旧事件只有在被新快照引用时才以清空嵌套字段的副本进入新回执。

## 7. ITEM_UPDATED 审计合同

服务增加 `_item_decision_summary(item)`，在修改前和 `flush()` 后各调用一次。before/after 均固定包含：

```text
item_id
original_quantity
final_quantity
decision_reason
decision_type
decision_risk
requires_admin_confirmation
confirmed_by_admin
risk_rule_version
version
```

枚举和 Decimal 继续使用现有 JSON 规范化函数。连续两次更新必须满足“第一次 after 等于第二次 before”，并能分别恢复两次调整理由、风险、管理员确认要求、确认状态、规则版本和项目版本。审计摘要是追加式事实，不从当前 item 行反推历史状态。

## 8. 空 DRAFT 服务端拒绝

`create_from_group` 在取得权威 `comparison` 后、检查缺失决策和创建任何聚合记录前执行：

```python
if not comparison.rows:
    raise BusinessValidationError(
        "demand list cannot be empty",
        code="DEMAND_LIST_EMPTY",
    )
```

复用 submit/publish 已有的 `DEMAND_LIST_EMPTY` 领域错误码。测试必须构造“计算组终态且存在成功 current child，但权威比较行为零行”的场景，并断言 list、item、event 三张表均无新增记录。前端保守门保持不变，服务端仍是最终权威。

## 9. 错误、兼容与安全边界

- 现有 `IDEMPOTENCY_KEY_REUSED`、`IDEMPOTENT_RESPONSE_UNAVAILABLE` 和竞争恢复行为保持不变；
- 不把 tenant 参数引入前端命令身份或请求；
- 不把原始错误字符串作为 retry 判定，统一使用 `normalizeMaintenanceError(value).retryable`；
- 非幂等的 item update 不纳入本整改，继续依赖 optimistic version 防止重复覆盖；
- 不修改 RBAC，页面仍由现有 capability 和状态机决定可用操作；
- 不回填旧审计事件；验收覆盖整改后生成的新事件合同。

## 10. 测试策略与实施顺序

实施按四个可独立审查的 TDD 任务推进：

1. 空比较结果 RED，最小服务端校验 GREEN；
2. 递归快照 RED，统一规范化写入与首次响应 GREEN；
3. 连续两次 item 更新审计 RED，完整摘要 GREEN；
4. Store 可重试失败键复用 RED，页面委托 Store GREEN。

每项只在其 RED 测试以预期原因失败后写生产代码。四项通过后运行：

- `tests/services/test_demand_list_service.py`；
- `tests/api/test_demand_lists.py`；
- `tests/api/test_scenario_draft_api.py`、`tests/api/test_calculation_groups.py` 与 Plan 05-3 集成测试；
- 前端 demand-list Store、navigation 和 API 聚焦测试；
- 前端完整测试、type-check、生产构建；
- `git diff --check`、精确范围检查和关闭复审。

## 11. 验收标准

- 同一创建或生命周期逻辑命令在可重试失败后第二次调用使用完全相同的键；
- 成功、不可重试失败、输入变化和 dispose 后使用新键；
- 页面源码不再定义或调用 demand-list `requestKey()`；
- 每个新回执可验证为 `DemandListRead`，且其 `events[*].response_snapshot_json` 全部为 `null`；
- 所有动作首次响应等于其持久化回执和后续回放；
- 连续两次更新的审计链完整且前后衔接；
- 空比较创建返回 `DEMAND_LIST_EMPTY`，数据库无 list、item、event 写入；
- 无迁移、无公开 API 路径变化、无 Plan 05-4 文件；
- Plan 05-3 完整 Gate 绿色，关闭复审无剩余 Important 或 Moderate 项。

## 12. 批准边界

本设计和配套实施计划可以作为一个文档提交进入 PR #4。该提交不授权业务代码或测试代码整改。开始第一个 RED 测试前必须获得明确批准：

```text
批准进入 Plan 05-3 Closure Review Remediation TDD 整改
```

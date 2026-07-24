# Maintenance Demand Calculation Engine Design

## 1. 目标与范围

本阶段在现有 `extensions/maintenance-api` 和静态主数据基础上建设维修器材需求计算引擎。系统面向多装备、多构型、多任务阶段的连续保障场景，利用装备构型、单机安装数、可靠性参数、修理参数和库存状态，计算毛需求、修理周转需求、净消耗需求、推荐初始备件量和库存缺口。

本阶段包含：五类可靠性模型、解析与蒙特卡洛计算、多阶段时间轴、年龄分组、修理周转、共同冲击、自适应收敛、场景版本、同步和异步任务、完整输入快照、结果贡献明细、模型对比和 JSON/XLSX 导出。

本阶段不包含：跨库调拨、采购优化、供应商选择、维修资源调度、Redis/Celery、MCP 和 WeKnora Core 修改。

## 2. 已确认的设计决策

- 场景粒度：多装备、多构型、多任务阶段。
- 模型选择：自动选择并允许阶段、群组和器材级覆盖。
- 库存参与：输出毛需求和库存缺口，不生成调拨或采购方案。
- 初始寿命：场景默认值加装备群组级年龄分组覆盖。
- 故障过程：按器材属性和模型自动选择，可人工覆盖。
- 保障率：器材级覆盖优先，其次关键度规则，最后场景默认值。
- 计算模式：`AUTO`、`ANALYTICAL`、`MONTE_CARLO`、`COMPARE`。
- 执行机制：快速任务同步，大规模仿真和模型对比异步。
- 环境影响：不同模型采用专属参数调整规则。
- 缺失参数：`STRICT`、`WARN_AND_SKIP`、`FALLBACK`。
- 结果粒度：器材汇总、阶段汇总和需求贡献明细。
- 历史复现：完整输入快照，支持 `REPLAY_SNAPSHOT` 和 `RERUN_LATEST`。
- 蒙特卡洛：自适应收敛。
- 故障相关性：独立故障加场景级共同冲击。
- 可修复器材：同时计算更换、修理周转、净消耗和推荐初始备件量。
- 阶段汇总：按完整任务时间轴连续推进。
- 修理参数：独立 `repair_profiles` 档案。
- 场景管理：模板、版本、阶段和生命周期管理。
- 工程架构：纯算法包 `demand-engine` 加 `maintenance-api` 编排。

## 3. 总体架构

```text
WeKnora / Streamlit / 后续 MCP
              │
              ▼
extensions/maintenance-api
├─ 场景与修理档案管理
├─ 主数据展开和参数自动选择
├─ 完整输入快照
├─ 同步/异步任务编排
├─ 结果持久化与库存缺口
└─ REST API 和导出
              │
              ▼
extensions/demand-engine
├─ 纯领域输入输出模型
├─ 解析计算器
├─ 威布尔更新过程
├─ 蒙特卡洛时间轴
├─ 修理管线与共同冲击
├─ 自适应收敛
└─ 诊断和分位数
```

依赖方向严格为 `maintenance-api → demand-engine`。`demand-engine` 不依赖 FastAPI、SQLAlchemy、Alembic、数据库、HTTP 或 WeKnora。

统一入口：

```python
result = DemandCalculationEngine().calculate(calculation_input)
```

## 4. 文件边界

### 4.1 `extensions/demand-engine`

```text
pyproject.toml
README.md
src/demand_engine/
├─ enums.py
├─ exceptions.py
├─ version.py
├─ cli.py
├─ engine.py
├─ models/{scenario,reliability,repair,simulation,result}.py
├─ analytical/{exponential_poisson,binomial,negative_binomial,empirical,quantiles}.py
├─ weibull/{conditional_failure,renewal_process,numerical_solver}.py
├─ simulation/{random_source,monte_carlo,timeline,common_shock,repair_pipeline,convergence}.py
├─ adjustment/{exponential,weibull,count_models,empirical}.py
└─ selection/execution_mode.py
```

### 4.2 `extensions/maintenance-api/app`

```text
models/{repair,demand_scenario,demand_calculation}.py
schemas/{repair,demand_scenario,demand_calculation,demand_result}.py
repositories/{repair_repository,demand_scenario_repository,demand_calculation_repository}.py
services/{repair_service,scenario_service,reliability_selection_service,
          repair_selection_service,snapshot_service,demand_calculation_service,
          calculation_task_service,inventory_gap_service,
          calculation_comparison_service}.py
workers/{executor,task_registry,recovery}.py
api/v1/demand/{router,repair_profiles,scenarios,calculations,comparisons}.py
```

## 5. 新增数据模型

本阶段新增 13 张表。

### 5.1 `repair_profiles`

核心字段：`profile_code`、`spare_part_id`、可选 `configuration_version_id`、`maintenance_level`、`repair_success_rate`、`condemnation_rate`、`repair_turnaround_hours`、`turnaround_std_hours`、`initial_repair_pipeline_quantity`、数据来源、有效期和启停状态。

约束：所有概率在 `[0,1]`；修复成功率与报废率之和不大于 1；周转时间大于 0；标准差和初始在修数量非负；有效期合法。

自动匹配顺序：任务覆盖 → 构型与维修级别 → 构型 → 维修级别 → 器材通用 → 场景默认。

### 5.2 场景表

- `demand_scenario_templates`：模板编码、名称、分类、标签和启停。
- `demand_scenario_versions`：版本、状态、默认保障率、关键度保障率映射、缺失参数策略、执行模式、默认年龄、默认修理参数、仿真配置和公式版本。
- `demand_scenario_stages`：阶段顺序、时长、利用率、任务强度、环境、高温、粉尘、湿度和振动系数。
- `demand_fleet_groups`：跨阶段连续的同一批装备、构型版本、初始数量和默认年龄。
- `demand_age_groups`：年龄比例和 FIXED/UNIFORM/NORMAL/TRIANGULAR 分布参数。
- `demand_stage_fleet_usages`：各阶段使用的群组、活动数量及覆盖系数。
- `demand_parameter_overrides`：器材级可靠性、修理、模型、保障率、排除和调整参数覆盖。
- `demand_common_shock_rules`：阶段级共同冲击概率、倍数、作用模式和影响范围。

场景版本生命周期：

```text
DRAFT      可编辑
PUBLISHED  输入锁定，可运行、复制和停用
RETIRED    只读，只允许历史快照重放
```

### 5.3 计算表

- `demand_calculations`：计算任务、场景来源、执行方式、请求模式、状态、进度、取消标记、幂等键、完整输入快照、快照哈希、库存快照时间、警告、摘要和错误。
- `demand_calculation_runs`：解析或蒙特卡洛运行、尝试次数、前序运行、随机种子、引擎和公式版本、实际样本数、收敛指标、耗时和错误。
- `demand_run_item_results`：每种器材的模型选择、参数快照、期望、方差、P50/P80/P90/P95/P99、目标分位数、三类需求、推荐量、库存和缺口。
- `demand_run_contributions`：需求来自哪个阶段、装备群组、构型、安装位置及其期望、更换、净消耗、修理管线和共同冲击贡献。

分位数不做简单贡献分摊，只在器材汇总层保存。

## 6. 输入快照和版本

快照必须包含场景、阶段、装备群组、阶段使用数量、构型明细、安装数、更换比例、年龄分组、可靠性档案、修理档案、人工覆盖、共同冲击、库存、保障率、缺失参数策略、执行模式、随机种子和仿真配置。

规范化 JSON 计算 SHA-256。字段顺序不得影响哈希，十进制值使用规范字符串。历史重放只使用快照，不重新读取主数据。

版本字段：

```text
engine_version = 0.1.0
formula_version = DEMAND-FORMULA-1
input_schema_version = 1.0
result_schema_version = 1.0
```

## 7. 可靠性和修理参数选择

可靠性档案优先级：

```text
人工指定
→ 构型完全匹配
→ 器材通用
→ 有效期匹配
→ 数据来源优先级
→ 高置信度
→ 大样本量
→ 较新估计时间
→ profile_code 字典序兜底
```

数据来源默认排序：维修记录 → 试验数据 → 设计参数 → 人工估计 → 专家判断 → 文献。

结果保存候选、淘汰原因、选中理由、人工覆盖、回退来源和最终参数快照。

## 8. 缺失参数和故障过程

缺失策略：

```text
STRICT         任务失败并返回缺失器材
WARN_AND_SKIP  跳过并返回 PARTIAL_SUCCESS
FALLBACK       使用临时、同类或场景默认参数并告警
```

故障过程默认映射：

```text
不可修复器材             SINGLE_FAILURE
可修复 + 指数            RENEWAL / 泊松过程
可修复 + 威布尔          RENEWAL / 威布尔更新过程
二项、负二项、经验模型   COUNT_DISTRIBUTION
```

## 9. 数学模型

阶段综合系数：

\[
F=F_mF_eF_tF_dF_hF_vF_qF_o
\]

实际运行时间：

\[
t_{run}=t_{stage}u
\]

### 9.1 指数模型

\[
\lambda_{eff}=\lambda F
\]

不可修复件失效概率：

\[
P_f=1-e^{-\lambda_{eff}t_{run}}
\]

不可修复需求服从二项分布，可修复更新过程服从泊松分布。

### 9.2 威布尔模型

不直接修改形状参数，调整等效年龄增量：

\[
\Delta a=t_{run}F
\]

条件失效概率：

\[
P_f(a,\Delta a)=1-\exp\left[-\left(\frac{a+\Delta a}{\eta}\right)^\beta+\left(\frac{a}{\eta}\right)^\beta\right]
\]

更换后恢复如新。更新期望通过更新方程数值求解，分位数优先使用蒙特卡洛。

### 9.3 二项模型

\[
p_{eff}=1-(1-p)^{Fr_t}
\]

### 9.4 负二项模型

\[
\mu=\frac{r(1-p)}{p},\quad \mu_{eff}=\mu Fr_t,\quad p_{eff}=\frac{r}{r+\mu_{eff}}
\]

### 9.5 经验模型

存在样本、直方图或概率质量函数时直接抽样；只有均值和方差时，按方差与均值关系选择泊松、负二项或二项近似，并记录警告。

### 9.6 安装数与更换比例

\[
n=Q_{equipment}Q_{install}
\]

`replacement_ratio` 表示故障后使用该器材的概率或比例，不直接改变安装位置数。离散仿真中在故障后抽样是否更换。

## 10. 蒙特卡洛时间轴

采用事件驱动而不是固定小时步长：阶段开始 → 年龄抽样 → 共同冲击抽样 → 故障事件 → 器材领用 → 拆下件进入修理管线 → 修复或报废 → 修复件返回 → 保存阶段末状态 → 下一阶段。

阶段之间连续传递部件年龄、库存、在修事件、累计净消耗和共同冲击贡献。修理完成事件使用按时间排序的最小堆。

可修复器材输出：

```text
gross_replacement_demand
repair_pipeline_demand
repair_pipeline_peak
net_consumption_demand
recommended_spare_quantity
```

推荐初始备件量取整个时间轴最大累计净领用缺口的目标分位数。

## 11. 保障率和自适应收敛

保障率优先级：器材级覆盖 → 关键度规则 → 场景默认值。

标准输出：期望、方差、标准差、P50、P80、P90、P95、P99 和目标保障率需求量。

默认蒙特卡洛配置：

```text
min_runs=1000
max_runs=50000
batch_size=1000
mean_relative_tolerance=0.01
quantile_absolute_tolerance=1
required_stable_batches=3
```

包含 P99 时有效最小次数至少为 10,000。连续批次满足均值、目标分位数和标准误阈值后提前停止。达到上限仍未收敛时保留结果并产生 `MONTE_CARLO_NOT_CONVERGED`。

## 12. 库存缺口和模型对比

库存结果：账面库存、可用库存、在途、安全库存保留量、本任务可用库存、净缺口、覆盖率、风险等级、库存最低点和最大同时缺口。

COMPARE 模式分别生成解析和蒙特卡洛运行，并比较均值、标准差、P50/P80/P90/P95/P99、推荐量、净缺口和覆盖率。只标记 `CONSISTENT`、`MINOR_DEVIATION`、`MAJOR_DEVIATION`，不自动宣称哪个模型正确。

## 13. API

统一前缀：`/api/v1/demand`。

主要接口：

```text
/repair-profiles
/scenarios
/scenarios/{id}/versions
/scenario-versions/{id}/publish
/scenario-versions/{id}/retire
/scenario-versions/{id}/clone
/scenario-versions/{id}/full
/scenario-versions/{id}/validate
/scenario-versions/{id}/stages
/scenario-versions/{id}/fleet-groups
/fleet-groups/{id}/age-groups
/stages/{id}/fleet-usages
/scenario-versions/{id}/parameter-overrides
/stages/{id}/common-shocks
/calculations/preview
/calculations
/calculations/{id}/status
/calculations/{id}/cancel
/calculations/{id}/retry
/calculations/{id}/replay
/calculations/{id}/rerun-latest
/calculations/{id}/results/items
/calculations/{id}/results/contributions
/calculations/{id}/results/stages
/calculations/{id}/runs
/calculations/{id}/comparison
/calculations/{id}/export
/comparisons
```

场景发布一次返回全部校验问题。正式提交必须重新读取主数据并生成快照，不复用预检结果。

## 14. 同步、异步、取消和恢复

复杂度按阶段数、安装位置数、有效仿真次数和时间轴复杂度估算。纯解析和预计小于 5 秒的小型仿真同步执行；威布尔更新、大型年龄分组、COMPARE 和预计超时任务异步执行。

首版采用 `ThreadPoolExecutor`，默认工作线程 2。后台任务只接收 `calculation_id`，自行创建独立数据库 Session。长时间计算期间不持有数据库写锁。

取消为协作式取消，在阶段边界和仿真批次边界检查。失败或中断重试新建 `attempt_number`，保留旧诊断。应用启动时遗留 RUNNING 任务改为 INTERRUPTED，PENDING 不自动重跑。

支持 `Idempotency-Key`。相同快照可告警但不强制阻止，以允许不同随机种子的科研重复实验。

## 15. 导出、错误和安全

导出 JSON 或 XLSX。Excel 包含任务摘要、器材结果、阶段汇总、贡献明细、参数快照、库存缺口、警告诊断和模型对比。导出文本防止公式注入。

主要错误码：

```text
SCENARIO_NOT_PUBLISHED
SCENARIO_VALIDATION_FAILED
CONFIGURATION_NOT_AVAILABLE
RELIABILITY_PROFILE_MISSING
REPAIR_PROFILE_MISSING
PARAMETER_SELECTION_CONFLICT
INVALID_MODEL_PARAMETERS
INVALID_AGE_DISTRIBUTION
INVALID_SERVICE_LEVEL
SYNC_COMPLEXITY_EXCEEDED
CALCULATION_ALREADY_RUNNING
CALCULATION_NOT_RETRYABLE
CALCULATION_CANCELLED
WORKER_INTERRUPTED
MONTE_CARLO_NOT_CONVERGED
RESULT_NOT_AVAILABLE
SNAPSHOT_HASH_MISMATCH
UNSUPPORTED_FORMULA_VERSION
UNSUPPORTED_SNAPSHOT_VERSION
```

错误响应和日志不返回 SQL、数据库路径、环境变量、内部堆栈或完整敏感快照。JSON 只接受预定义 Schema，不执行表达式、代码或 `eval`。

## 16. 迁移和依赖

新增独立 Alembic 迁移，不修改实施计划 02 的历史迁移。必须验证 upgrade、downgrade 一版和再次 upgrade，且原 10 张主数据表和数据保持不变。

`demand-engine` 依赖 Python 3.11、NumPy 和 SciPy。随机数统一使用注入的 `numpy.random.Generator`，禁止使用全局随机状态。

## 17. 测试与性能

算法测试覆盖指数—泊松、威布尔条件失效、威布尔更新过程、二项、负二项、经验近似、共同冲击、修理管线和自适应收敛。固定快照和随机种子必须完全可复现。

性质测试至少验证：任务时长、装备数量、安装数、失效率和保障率增加时需求不下降；库存增加时缺口不增加；修复成功率提高时净消耗不增加。

API 测试覆盖场景生命周期、发布校验、参数覆盖、预检、同步、异步、取消、重试、恢复、幂等、快照重放、最新数据重算、结果分页、比较和导出。测试执行器使用可控实现，避免线程时序不稳定。

性能目标：100 种器材、10 阶段解析任务算法小于 2 秒；50 种器材、5 阶段、10,000 次蒙特卡洛可在本地完成且不阻塞状态查询；1000 条结果分页单页目标小于 500ms。

## 18. 资源限制与样例

环境变量建议：

```text
DEMAND_WORKER_COUNT=2
DEMAND_SYNC_TIMEOUT_SECONDS=5
DEMAND_MAX_PENDING_TASKS=20
DEMAND_MAX_MONTE_CARLO_RUNS=50000
DEMAND_MAX_SCENARIO_STAGES=100
DEMAND_MAX_FLEET_GROUPS=500
DEMAND_MAX_DEMAND_ITEMS=5000
DEMAND_RESULT_EXPORT_MAX_ROWS=100000
```

提供幂等样例命令：

```powershell
python -m app.scripts.seed_demand_scenarios
```

提供纯算法 CLI：

```powershell
python -m demand_engine.cli calculate --input scenario.json --output result.json
```

## 19. 批量实施和验收

一次性包：

```text
maintenance-demand-engine-phase-batch.zip
├─ apply-demand-engine-phase.ps1
├─ demand-engine-payload/
├─ maintenance-api-payload/
└─ docs/
```

脚本检查分支和干净工作区、备份文件、写入两个模块、安装依赖、执行迁移、运行算法和 API 测试、运行全部既有测试、Ruff、迁移回退与再升级、样例初始化及同步/异步/导出冒烟测试。脚本不自动提交或推送。

验收必须满足：纯算法包可独立安装；五类模型可运行；支持多装备多构型多阶段；支持年龄、修理、共同冲击和自适应收敛；场景版本和参数覆盖可用；同步异步任务可取消、重试和恢复；输入快照可复现；结果包含标准分位数、库存缺口和贡献明细；模型对比及 JSON/XLSX 导出可用；迁移可回退；实施计划 01、02 测试继续通过；Ruff 无错误；Swagger 展示全部接口。

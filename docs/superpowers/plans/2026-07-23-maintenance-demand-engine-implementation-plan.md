# 维修器材需求计算引擎实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有维修主数据 API 基础上，新增可独立复用的纯 Python 需求计算引擎，以及场景版本、参数选择、快照、同步/异步任务、结果持久化、库存缺口、模型对比和结果导出能力。

**Architecture:** `extensions/demand-engine` 只实现领域对象、解析计算、威布尔更新、事件驱动蒙特卡洛、修理管线、共同冲击和收敛检测，不依赖数据库或 Web 框架。`extensions/maintenance-api` 负责读取现有构型与可靠性主数据、管理需求场景和修理参数、生成不可变输入快照、编排同步或异步运行，并持久化结果。

**Tech Stack:** Python 3.11、NumPy、SciPy、FastAPI、Pydantic 2、SQLAlchemy 2 同步 API、Alembic、SQLite/PostgreSQL 兼容 SQL、openpyxl、pytest、HTTPX、Ruff、ThreadPoolExecutor。

## Global Constraints

- 只在 `feature/demand-calculation-engine` 或其隔离工作树上实施，禁止在 `main` 或 `master` 上修改。
- 不修改 WeKnora Core。
- 保留实施计划 01、02 的全部既有行为和测试。
- `maintenance-api` 继续使用 Python `>=3.11,<3.12`、同步 SQLAlchemy 2.x 和统一成功/错误响应。
- `demand-engine` 不得依赖 FastAPI、SQLAlchemy、Alembic、openpyxl、数据库、HTTP、Redis、Celery 或 WeKnora。
- `demand-engine` 只依赖 NumPy 和 SciPy；不引入 Pandas。
- 数据库金额、数量、概率和可靠性参数继续使用 `Decimal`/`Numeric`；算法边界校验后才转换为 `float64`。
- 随机数必须通过 `numpy.random.Generator` 和显式种子注入，禁止直接调用全局 `numpy.random`。
- 首版公式版本固定为 `DEMAND-FORMULA-1`，输入和结果结构版本固定为 `1.0`。
- 蒙特卡洛采用自适应收敛，生产最大次数不得超过 `50000`。
- 后台执行器使用进程内 `ThreadPoolExecutor`，后台线程必须创建独立数据库 Session。
- SQLite 长时间计算期间不得持有写事务。
- 输入快照必须规范化并计算 SHA-256；历史重放不得读取最新主数据。
- 结果贡献明细不对 P90、P95、P99 做可加性错误分摊。
- Excel 导出必须防止公式注入。
- 任一任务完成后必须运行聚焦测试、相关测试和全量回归测试，再提交 Git。
- 执行实现前必须使用 `superpowers:using-git-worktrees` 建立或验证隔离工作区。

---

## 里程碑与独立交付物

### 里程碑 A：纯算法包

完成 Task 1–9 后，`demand-engine` 必须能够独立安装，通过纯算法测试，并通过 CLI 对完整快照 JSON 进行计算。该里程碑不需要数据库。

### 里程碑 B：场景与持久化

完成 Task 10–14 后，`maintenance-api` 必须能够迁移 13 张新表，管理修理档案和场景版本，发布前完成完整校验，并生成稳定输入快照。

### 里程碑 C：任务执行与结果

完成 Task 15–18 后，系统必须支持同步、异步、取消、重试、恢复、库存缺口、模型对比和导出。

### 里程碑 D：批量交付

Task 19 生成一次性 PowerShell 安装包，并在基础项目副本上完成全量验证。

---

## File Map

### 新建纯算法包

```text
extensions/demand-engine/
├─ pyproject.toml
├─ README.md
├─ src/demand_engine/
│  ├─ __init__.py
│  ├─ version.py
│  ├─ enums.py
│  ├─ exceptions.py
│  ├─ engine.py
│  ├─ cli.py
│  ├─ models/
│  │  ├─ __init__.py
│  │  ├─ scenario.py
│  │  ├─ reliability.py
│  │  ├─ repair.py
│  │  ├─ simulation.py
│  │  └─ result.py
│  ├─ analytical/
│  │  ├─ __init__.py
│  │  ├─ exponential_poisson.py
│  │  ├─ binomial.py
│  │  ├─ negative_binomial.py
│  │  ├─ empirical.py
│  │  └─ quantiles.py
│  ├─ weibull/
│  │  ├─ __init__.py
│  │  ├─ conditional_failure.py
│  │  ├─ renewal_process.py
│  │  └─ numerical_solver.py
│  ├─ adjustment/
│  │  ├─ __init__.py
│  │  ├─ exponential.py
│  │  ├─ weibull.py
│  │  ├─ count_models.py
│  │  └─ empirical.py
│  ├─ simulation/
│  │  ├─ __init__.py
│  │  ├─ random_source.py
│  │  ├─ age_sampling.py
│  │  ├─ common_shock.py
│  │  ├─ repair_pipeline.py
│  │  ├─ timeline.py
│  │  ├─ convergence.py
│  │  └─ monte_carlo.py
│  └─ selection/
│     ├─ __init__.py
│     └─ execution_mode.py
└─ tests/
   ├─ conftest.py
   ├─ analytical/
   ├─ weibull/
   ├─ adjustment/
   ├─ simulation/
   ├─ test_engine.py
   └─ test_cli.py
```

### 新建或扩展 Maintenance API

```text
extensions/maintenance-api/
├─ alembic/versions/20260723_03_add_demand_calculation_schema.py
├─ app/
│  ├─ models/
│  │  ├─ repair.py
│  │  ├─ demand_scenario.py
│  │  └─ demand_calculation.py
│  ├─ schemas/
│  │  ├─ repair.py
│  │  ├─ demand_scenario.py
│  │  ├─ demand_calculation.py
│  │  └─ demand_result.py
│  ├─ repositories/
│  │  ├─ repair_repository.py
│  │  ├─ demand_scenario_repository.py
│  │  └─ demand_calculation_repository.py
│  ├─ services/
│  │  ├─ repair_service.py
│  │  ├─ scenario_service.py
│  │  ├─ reliability_selection_service.py
│  │  ├─ repair_selection_service.py
│  │  ├─ snapshot_service.py
│  │  ├─ demand_preview_service.py
│  │  ├─ demand_calculation_service.py
│  │  ├─ calculation_task_service.py
│  │  ├─ inventory_gap_service.py
│  │  ├─ result_persistence_service.py
│  │  └─ calculation_comparison_service.py
│  ├─ workers/
│  │  ├─ __init__.py
│  │  ├─ executor.py
│  │  ├─ task_registry.py
│  │  └─ recovery.py
│  ├─ exporters/
│  │  ├─ __init__.py
│  │  ├─ demand_json.py
│  │  └─ demand_excel.py
│  ├─ api/v1/demand/
│  │  ├─ __init__.py
│  │  ├─ router.py
│  │  ├─ repair_profiles.py
│  │  ├─ scenarios.py
│  │  ├─ calculations.py
│  │  └─ comparisons.py
│  └─ scripts/
│     └─ seed_demand_scenarios.py
└─ tests/
   ├─ models/
   ├─ schemas/
   ├─ repositories/
   ├─ services/
   ├─ workers/
   ├─ api/
   ├─ exporters/
   ├─ migrations/
   └─ performance/
```

### 修改现有文件

```text
extensions/maintenance-api/app/core/config.py
extensions/maintenance-api/app/core/exceptions.py
extensions/maintenance-api/app/main.py
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/models/__init__.py
extensions/maintenance-api/app/models/enums.py
extensions/maintenance-api/app/repositories/__init__.py
extensions/maintenance-api/app/services/__init__.py
extensions/maintenance-api/requirements.txt
extensions/maintenance-api/requirements-dev.txt
extensions/maintenance-api/pyproject.toml
extensions/maintenance-api/.env.example
extensions/maintenance-api/README.md
.gitignore
```

---

### Task 1: 建立隔离分支与纯算法包骨架

**Files:**
- Create: `extensions/demand-engine/pyproject.toml`
- Create: `extensions/demand-engine/README.md`
- Create: `extensions/demand-engine/src/demand_engine/__init__.py`
- Create: `extensions/demand-engine/src/demand_engine/version.py`
- Create: `extensions/demand-engine/tests/test_package.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 当前提交 `74caf07c` 或包含该提交的 `feature/maintenance-foundation`。
- Produces: 可编辑安装包 `demand-engine==0.1.0`，导出 `__version__`、`ENGINE_VERSION`、`FORMULA_VERSION`、`INPUT_SCHEMA_VERSION`、`RESULT_SCHEMA_VERSION`。

- [ ] **Step 1: 创建或验证隔离工作树**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora
git status --short
git worktree add ..\maintenance-demand-engine-worktree -b feature/demand-calculation-engine feature/maintenance-foundation
cd ..\maintenance-demand-engine-worktree
git branch --show-current
```

Expected:

```text
feature/demand-calculation-engine
```

且 `git status --short` 无输出。

- [ ] **Step 2: 先写包版本失败测试**

```python
from demand_engine import (
    ENGINE_VERSION,
    FORMULA_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    __version__,
)


def test_public_versions_are_stable():
    assert __version__ == "0.1.0"
    assert ENGINE_VERSION == "0.1.0"
    assert FORMULA_VERSION == "DEMAND-FORMULA-1"
    assert INPUT_SCHEMA_VERSION == "1.0"
    assert RESULT_SCHEMA_VERSION == "1.0"
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
cd extensions\demand-engine
python -m pytest tests\test_package.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'demand_engine'`.

- [ ] **Step 4: 写入包配置和版本实现**

`pyproject.toml` 必须包含：

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demand-engine"
version = "0.1.0"
description = "Pure maintenance spare demand calculation engine"
requires-python = ">=3.11,<3.12"
dependencies = [
  "numpy>=2.0,<3.0",
  "scipy>=1.14,<2.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<10.0",
  "ruff>=0.9,<1.0",
]

[project.scripts]
demand-engine = "demand_engine.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = ["E501"]
```

`version.py`：

```python
ENGINE_VERSION = "0.1.0"
FORMULA_VERSION = "DEMAND-FORMULA-1"
INPUT_SCHEMA_VERSION = "1.0"
RESULT_SCHEMA_VERSION = "1.0"
```

`__init__.py`：

```python
from demand_engine.version import (
    ENGINE_VERSION,
    FORMULA_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
)

__version__ = ENGINE_VERSION

__all__ = [
    "__version__",
    "ENGINE_VERSION",
    "FORMULA_VERSION",
    "INPUT_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
]
```

- [ ] **Step 5: 安装并验证**

Run:

```powershell
python -m pip install -e .[dev]
python -m pytest tests\test_package.py -v
python -m ruff check src tests
```

Expected: `1 passed` and `All checks passed!`.

- [ ] **Step 6: 提交**

```powershell
git add .gitignore extensions\demand-engine
git commit -m "feat: establish pure demand engine package"
```

---

### Task 2: 定义领域枚举、不可变输入和结果对象

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/enums.py`
- Create: `extensions/demand-engine/src/demand_engine/exceptions.py`
- Create: `extensions/demand-engine/src/demand_engine/models/scenario.py`
- Create: `extensions/demand-engine/src/demand_engine/models/reliability.py`
- Create: `extensions/demand-engine/src/demand_engine/models/repair.py`
- Create: `extensions/demand-engine/src/demand_engine/models/simulation.py`
- Create: `extensions/demand-engine/src/demand_engine/models/result.py`
- Create: `extensions/demand-engine/src/demand_engine/models/__init__.py`
- Test: `extensions/demand-engine/tests/test_models.py`

**Interfaces:**
- Produces:
  - `CalculationInput`
  - `StageInput`
  - `FleetGroupInput`
  - `AgeGroupInput`
  - `DemandItemInput`
  - `ReliabilityInput`
  - `RepairInput`
  - `InventoryInput`
  - `SimulationConfig`
  - `CalculationResult`
  - `ItemResult`
  - `ContributionResult`
  - `EngineValidationError`

- [ ] **Step 1: 写不可变和校验失败测试**

```python
from dataclasses import FrozenInstanceError

import pytest

from demand_engine.enums import (
    ExecutionMode,
    FailureProcessMode,
    MissingParameterPolicy,
    ReliabilityModelType,
)
from demand_engine.exceptions import EngineValidationError
from demand_engine.models import SimulationConfig, StageInput


def test_stage_input_is_frozen():
    stage = StageInput(
        code="S1",
        name="训练",
        order=1,
        duration_hours=100.0,
        utilization_rate=0.8,
    )
    with pytest.raises(FrozenInstanceError):
        stage.duration_hours = 120.0


def test_simulation_config_rejects_invalid_bounds():
    with pytest.raises(EngineValidationError):
        SimulationConfig(
            min_runs=2000,
            max_runs=1000,
            batch_size=100,
            mean_relative_tolerance=0.01,
            quantile_absolute_tolerance=1.0,
            required_stable_batches=3,
            quantiles=(0.5, 0.95),
        )


def test_required_enums_are_available():
    assert ExecutionMode.AUTO.value == "AUTO"
    assert FailureProcessMode.RENEWAL.value == "RENEWAL"
    assert MissingParameterPolicy.STRICT.value == "STRICT"
    assert ReliabilityModelType.WEIBULL.value == "WEIBULL"
```

- [ ] **Step 2: 运行确认失败**

Run:

```powershell
python -m pytest tests\test_models.py -v
```

Expected: import failure for missing models and enums.

- [ ] **Step 3: 实现枚举和冻结数据类**

枚举至少包含：

```python
class ExecutionMode(str, Enum):
    AUTO = "AUTO"
    ANALYTICAL = "ANALYTICAL"
    MONTE_CARLO = "MONTE_CARLO"
    COMPARE = "COMPARE"


class FailureProcessMode(str, Enum):
    AUTO = "AUTO"
    SINGLE_FAILURE = "SINGLE_FAILURE"
    RENEWAL = "RENEWAL"
    COUNT_DISTRIBUTION = "COUNT_DISTRIBUTION"


class ReliabilityModelType(str, Enum):
    EXPONENTIAL = "EXPONENTIAL"
    WEIBULL = "WEIBULL"
    BINOMIAL = "BINOMIAL"
    NEGATIVE_BINOMIAL = "NEGATIVE_BINOMIAL"
    EMPIRICAL = "EMPIRICAL"
```

`SimulationConfig` 必须在 `__post_init__` 中校验：

```python
if self.min_runs <= 0:
    raise EngineValidationError("min_runs must be positive")
if self.max_runs < self.min_runs:
    raise EngineValidationError("max_runs must be greater than or equal to min_runs")
if self.batch_size <= 0:
    raise EngineValidationError("batch_size must be positive")
if not self.quantiles or any(q <= 0 or q >= 1 for q in self.quantiles):
    raise EngineValidationError("quantiles must be between 0 and 1")
```

所有输入数据类使用：

```python
@dataclass(frozen=True, slots=True)
```

结果数据类允许构建后读取，不允许算法外部修改。

- [ ] **Step 4: 补充模型组合校验测试**

测试必须覆盖：

- 阶段顺序、时长和利用率。
- 年龄分组分布参数。
- 可靠性模型必要参数。
- 修理成功率与报废率之和。
- 保障率范围。
- 库存数量非负。
- 输入公式版本和结构版本。

- [ ] **Step 5: 运行模型测试和 Ruff**

```powershell
python -m pytest tests\test_models.py -v
python -m ruff check src tests
```

Expected: all tests pass.

- [ ] **Step 6: 提交**

```powershell
git add extensions\demand-engine
git commit -m "feat: define demand engine domain contracts"
```

---

### Task 3: 实现解析分布计算与分位数

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/analytical/quantiles.py`
- Create: `extensions/demand-engine/src/demand_engine/analytical/exponential_poisson.py`
- Create: `extensions/demand-engine/src/demand_engine/analytical/binomial.py`
- Create: `extensions/demand-engine/src/demand_engine/analytical/negative_binomial.py`
- Create: `extensions/demand-engine/src/demand_engine/analytical/empirical.py`
- Test: `extensions/demand-engine/tests/analytical/test_exponential_poisson.py`
- Test: `extensions/demand-engine/tests/analytical/test_count_distributions.py`
- Test: `extensions/demand-engine/tests/analytical/test_empirical.py`

**Interfaces:**
- Produces:
  - `DistributionStats(mean, variance, standard_deviation, quantiles)`
  - `exponential_single_failure_stats(...)`
  - `exponential_renewal_stats(...)`
  - `binomial_stats(...)`
  - `negative_binomial_stats(...)`
  - `empirical_stats(...)`

- [ ] **Step 1: 写指数基准失败测试**

```python
import math

from demand_engine.analytical.exponential_poisson import (
    exponential_renewal_stats,
    exponential_single_failure_stats,
)


def test_exponential_renewal_matches_poisson_mean_and_variance():
    stats = exponential_renewal_stats(
        installed_positions=100,
        failure_rate=0.001,
        duration_hours=100,
        adjustment_factor=1.0,
        replacement_ratio=1.0,
        quantiles=(0.5, 0.95, 0.99),
    )
    assert stats.mean == 10.0
    assert stats.variance == 10.0


def test_exponential_single_failure_matches_binomial_formula():
    stats = exponential_single_failure_stats(
        installed_positions=100,
        failure_rate=0.001,
        initial_age_hours=0,
        duration_hours=100,
        adjustment_factor=1.0,
        replacement_ratio=1.0,
        quantiles=(0.95,),
    )
    p = 1 - math.exp(-0.1)
    assert math.isclose(stats.mean, 100 * p, rel_tol=1e-12)
    assert math.isclose(stats.variance, 100 * p * (1 - p), rel_tol=1e-12)
```

- [ ] **Step 2: 写二项、负二项和经验模型失败测试**

测试必须直接用 `scipy.stats.binom`、`nbinom` 和 `poisson` 作为基准，验证均值、方差和 P95。

- [ ] **Step 3: 运行确认失败**

```powershell
python -m pytest tests\analytical -v
```

Expected: missing analytical modules.

- [ ] **Step 4: 实现解析计算**

核心结构：

```python
@dataclass(frozen=True, slots=True)
class DistributionStats:
    mean: float
    variance: float
    standard_deviation: float
    quantiles: dict[float, float]
    approximation: str | None = None
    warnings: tuple[str, ...] = ()
```

分位数必须使用离散分布的 `ppf`，返回非负值。经验模型矩匹配规则：

```python
if math.isclose(variance, mean, rel_tol=0.05, abs_tol=1e-12):
    return poisson_approximation(mean, quantiles)
if variance > mean:
    return negative_binomial_from_moments(mean, variance, quantiles)
return binomial_from_moments(mean, variance, quantiles)
```

- [ ] **Step 5: 验证零暴露量和边界概率**

覆盖：

```text
installed_positions = 0
duration_hours = 0
replacement_ratio = 0
binomial p = 0
binomial p = 1
```

Expected: 不抛出数值异常，均值和分位数符合边界。

- [ ] **Step 6: 运行与提交**

```powershell
python -m pytest tests\analytical -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add analytical demand distributions"
```

---

### Task 4: 实现威布尔条件失效与更新过程

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/weibull/conditional_failure.py`
- Create: `extensions/demand-engine/src/demand_engine/weibull/numerical_solver.py`
- Create: `extensions/demand-engine/src/demand_engine/weibull/renewal_process.py`
- Test: `extensions/demand-engine/tests/weibull/test_conditional_failure.py`
- Test: `extensions/demand-engine/tests/weibull/test_renewal_process.py`

**Interfaces:**
- Produces:
  - `weibull_conditional_failure_probability(age, duration, shape, scale, factor)`
  - `weibull_renewal_mean(duration, shape, scale, step_hours)`
  - `weibull_single_failure_stats(...)`
  - `weibull_renewal_approximation(...)`

- [ ] **Step 1: 写条件失效基准测试**

```python
import math

from demand_engine.weibull.conditional_failure import (
    weibull_conditional_failure_probability,
)


def test_weibull_conditional_probability_matches_formula():
    value = weibull_conditional_failure_probability(
        initial_age_hours=500,
        duration_hours=100,
        shape=2,
        scale=1000,
        adjustment_factor=1,
    )
    expected = 1 - math.exp(-((600 / 1000) ** 2) + ((500 / 1000) ** 2))
    assert math.isclose(value, expected, rel_tol=1e-12)


def test_shape_one_matches_exponential_probability():
    value = weibull_conditional_failure_probability(
        initial_age_hours=500,
        duration_hours=100,
        shape=1,
        scale=1000,
        adjustment_factor=1,
    )
    assert math.isclose(value, 1 - math.exp(-0.1), rel_tol=1e-12)
```

- [ ] **Step 2: 写更新过程性质测试**

必须验证：

- `duration=0` 时均值为 0。
- 任务时长增加时更新次数不下降。
- `shape=1` 时接近 `duration/scale`。
- `step_hours` 减半时结果差异低于规定容差。

- [ ] **Step 3: 运行确认失败**

```powershell
python -m pytest tests\weibull -v
```

- [ ] **Step 4: 实现条件失效和离散更新方程**

更新方程使用离散卷积，必须限制：

```python
if duration_hours < 0 or shape <= 0 or scale <= 0:
    raise EngineValidationError(...)
```

数值求解返回：

```python
@dataclass(frozen=True, slots=True)
class RenewalSolution:
    expected_renewals: float
    step_hours: float
    grid_points: int
    converged: bool
```

- [ ] **Step 5: 实现显式解析模式近似警告**

强制解析威布尔更新分位数时返回 `WEIBULL_RENEWAL_QUANTILES_APPROXIMATED`，并使用矩匹配计数分布，不伪装为精确结果。

- [ ] **Step 6: 运行与提交**

```powershell
python -m pytest tests\weibull -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add Weibull failure and renewal models"
```

---

### Task 5: 实现场景参数调整与执行模式选择

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/adjustment/exponential.py`
- Create: `extensions/demand-engine/src/demand_engine/adjustment/weibull.py`
- Create: `extensions/demand-engine/src/demand_engine/adjustment/count_models.py`
- Create: `extensions/demand-engine/src/demand_engine/adjustment/empirical.py`
- Create: `extensions/demand-engine/src/demand_engine/selection/execution_mode.py`
- Test: `extensions/demand-engine/tests/adjustment/test_adjustments.py`
- Test: `extensions/demand-engine/tests/test_execution_mode.py`

**Interfaces:**
- Produces:
  - `combined_adjustment_factor(stage, fleet_usage, override)`
  - `adjust_exponential_rate(...)`
  - `adjust_weibull_age_increment(...)`
  - `adjust_binomial_probability(...)`
  - `adjust_negative_binomial(...)`
  - `select_execution_mode(calculation_input)`

- [ ] **Step 1: 写模型专属调整失败测试**

```python
import math

from demand_engine.adjustment.count_models import (
    adjust_binomial_probability,
    adjust_negative_binomial,
)


def test_binomial_probability_transform_stays_in_range():
    p = adjust_binomial_probability(
        base_probability=0.2,
        adjustment_factor=2,
        duration_ratio=1.5,
    )
    assert 0 <= p <= 1
    assert math.isclose(p, 1 - (1 - 0.2) ** 3, rel_tol=1e-12)


def test_negative_binomial_preserves_dispersion_parameter():
    adjusted = adjust_negative_binomial(
        r=5,
        p=0.5,
        adjustment_factor=2,
        duration_ratio=1,
    )
    assert adjusted.r == 5
    assert math.isclose(adjusted.mean, 10, rel_tol=1e-12)
```

- [ ] **Step 2: 写 AUTO 模式选择失败测试**

AUTO 必须在以下条件选择蒙特卡洛：

- 威布尔更新过程。
- 多年龄分组。
- 共同冲击。
- 修理管线。
- 人工随机扰动。
- COMPARE 显式请求时返回两个运行模式。

纯指数—泊松、二项和负二项简单场景选择解析模式。

- [ ] **Step 3: 实现综合调整因子**

```python
factor = (
    stage.mission_intensity_factor
    * stage.environment_factor
    * stage.temperature_factor
    * stage.dust_factor
    * stage.humidity_factor
    * stage.vibration_factor
    * fleet_usage.equipment_intensity_factor
    * override.adjustment_factor
)
```

所有因子必须大于 0，原始和最终参数写入 `AdjustmentSnapshot`。

- [ ] **Step 4: 实现执行模式选择理由**

返回：

```python
@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    modes: tuple[ExecutionMode, ...]
    reasons: tuple[str, ...]
    requires_timeline: bool
```

- [ ] **Step 5: 运行与提交**

```powershell
python -m pytest tests\adjustment tests\test_execution_mode.py -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add model adjustments and mode selection"
```

---

### Task 6: 实现随机源、年龄抽样和共同冲击

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/simulation/random_source.py`
- Create: `extensions/demand-engine/src/demand_engine/simulation/age_sampling.py`
- Create: `extensions/demand-engine/src/demand_engine/simulation/common_shock.py`
- Test: `extensions/demand-engine/tests/simulation/test_random_source.py`
- Test: `extensions/demand-engine/tests/simulation/test_age_sampling.py`
- Test: `extensions/demand-engine/tests/simulation/test_common_shock.py`

**Interfaces:**
- Produces:
  - `RandomSource(seed)`
  - `sample_initial_ages(age_groups, quantity, random_source)`
  - `sample_common_shocks(stage_rules, random_source)`

- [ ] **Step 1: 写种子复现测试**

```python
from demand_engine.simulation.random_source import RandomSource


def test_random_source_is_reproducible():
    left = RandomSource(20260723).poisson(2.5, size=20)
    right = RandomSource(20260723).poisson(2.5, size=20)
    assert left.tolist() == right.tolist()
```

- [ ] **Step 2: 写年龄分组测试**

覆盖 FIXED、UNIFORM、NORMAL、TRIANGULAR；NORMAL 负值必须截断到 0；各分组抽样数量总和必须精确等于装备数量。

- [ ] **Step 3: 写共同冲击测试**

固定种子验证：

- 概率 0 从不发生。
- 概率 1 必然发生。
- 影响范围按器材类别、关键度和器材编码过滤。
- `maximum_occurrences` 生效。

- [ ] **Step 4: 实现统一随机 API**

`RandomSource` 只暴露算法需要的方法：

```python
def poisson(self, lam: float, size: int | None = None): ...
def binomial(self, n: int, p: float, size: int | None = None): ...
def negative_binomial(self, n: float, p: float, size: int | None = None): ...
def uniform(self, low: float, high: float, size: int): ...
def normal(self, mean: float, std: float, size: int): ...
def triangular(self, left: float, mode: float, right: float, size: int): ...
def random(self, size: int | None = None): ...
```

- [ ] **Step 5: 运行与提交**

```powershell
python -m pytest tests\simulation\test_random_source.py tests\simulation\test_age_sampling.py tests\simulation\test_common_shock.py -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add reproducible simulation primitives"
```

---

### Task 7: 实现修理管线和多阶段事件驱动时间轴

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/simulation/repair_pipeline.py`
- Create: `extensions/demand-engine/src/demand_engine/simulation/timeline.py`
- Test: `extensions/demand-engine/tests/simulation/test_repair_pipeline.py`
- Test: `extensions/demand-engine/tests/simulation/test_timeline.py`

**Interfaces:**
- Produces:
  - `RepairPipeline`
  - `TimelineState`
  - `TimelineOutcome`
  - `simulate_timeline_once(calculation_input, random_source, cancel_check)`

- [ ] **Step 1: 写修理事件最小堆测试**

```python
from demand_engine.simulation.repair_pipeline import RepairPipeline


def test_repair_pipeline_releases_completed_items_in_time_order():
    pipeline = RepairPipeline()
    pipeline.schedule(completion_time=20, quantity=1, success=True)
    pipeline.schedule(completion_time=10, quantity=2, success=True)

    first = pipeline.release_until(10)
    second = pipeline.release_until(20)

    assert first.returned_quantity == 2
    assert second.returned_quantity == 1
```

- [ ] **Step 2: 写连续阶段状态测试**

等价的单阶段 200 小时与两个连续 100 小时阶段，在无阶段差异、无修理返回和相同种子下，应得到一致状态和统计量。

- [ ] **Step 3: 写修理周转性质测试**

验证：

- 周转时间大于任务总时长时，本任务无修复返回。
- 周转时间接近 0 时，修理管线峰值下降。
- 修复成功率提高时净消耗不增加。
- 初始在修数量按完成时间进入管线。
- 可修复件更换后年龄归零。

- [ ] **Step 4: 实现事件驱动时间轴**

不得逐小时循环。每次仿真使用故障事件和修理完成事件推进：

```python
while event_queue:
    event_time, event = heapq.heappop(event_queue)
    if event_time > stage_end:
        break
    release = repair_pipeline.release_until(event_time)
    state.available_inventory += release.returned_quantity
    process_failure_event(event, state, repair_pipeline, random_source)
```

- [ ] **Step 5: 增加取消检查点**

`cancel_check()` 至少在阶段开始、阶段结束和每处理规定数量事件后调用；返回真时抛出 `CalculationCancelledError`。

- [ ] **Step 6: 运行与提交**

```powershell
python -m pytest tests\simulation\test_repair_pipeline.py tests\simulation\test_timeline.py -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add repair pipeline and continuous timeline"
```

---

### Task 8: 实现自适应收敛和蒙特卡洛聚合

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/simulation/convergence.py`
- Create: `extensions/demand-engine/src/demand_engine/simulation/monte_carlo.py`
- Test: `extensions/demand-engine/tests/simulation/test_convergence.py`
- Test: `extensions/demand-engine/tests/simulation/test_monte_carlo.py`

**Interfaces:**
- Produces:
  - `effective_minimum_runs(config)`
  - `ConvergenceTracker`
  - `run_adaptive_monte_carlo(input, random_source, progress_callback, cancel_check)`
  - `MonteCarloResult`

- [ ] **Step 1: 写 P99 有效最小次数测试**

```python
from demand_engine.models import SimulationConfig
from demand_engine.simulation.convergence import effective_minimum_runs


def test_p99_requires_at_least_ten_thousand_runs():
    config = SimulationConfig(
        min_runs=1000,
        max_runs=50000,
        batch_size=1000,
        mean_relative_tolerance=0.01,
        quantile_absolute_tolerance=1,
        required_stable_batches=3,
        quantiles=(0.5, 0.8, 0.9, 0.95, 0.99),
    )
    assert effective_minimum_runs(config) == 10000
```

- [ ] **Step 2: 写稳定批次和最大次数测试**

覆盖：

- 连续三批满足均值和目标分位数阈值后停止。
- 低均值器材使用绝对变化，不除以接近 0 的均值。
- 达到最大次数未收敛时保留结果并产生 `MONTE_CARLO_NOT_CONVERGED`。

- [ ] **Step 3: 写解析对照测试**

指数泊松简单场景固定种子，蒙特卡洛均值必须在统计容差内接近解析均值。

- [ ] **Step 4: 实现批次聚合**

不得保存全部原始样本。实现在线累积：

```python
count += batch_size
sum_x += batch.sum(axis=0)
sum_x2 += (batch ** 2).sum(axis=0)
```

为分位数保留受控的每批器材需求数组；不得持久化每轮样本到数据库。

- [ ] **Step 5: 实现进度回调**

回调签名：

```python
ProgressCallback = Callable[[int, int, dict[str, float]], None]
```

参数依次为 `completed_runs`、`max_runs`、当前收敛摘要。

- [ ] **Step 6: 运行与提交**

```powershell
python -m pytest tests\simulation\test_convergence.py tests\simulation\test_monte_carlo.py -v
python -m ruff check src tests
git add extensions\demand-engine
git commit -m "feat: add adaptive Monte Carlo simulation"
```

---

### Task 9: 实现统一引擎门面、COMPARE 和 CLI

**Files:**
- Create: `extensions/demand-engine/src/demand_engine/engine.py`
- Create: `extensions/demand-engine/src/demand_engine/cli.py`
- Modify: `extensions/demand-engine/src/demand_engine/__init__.py`
- Test: `extensions/demand-engine/tests/test_engine.py`
- Test: `extensions/demand-engine/tests/test_cli.py`
- Create: `extensions/demand-engine/tests/fixtures/simple_snapshot.json`

**Interfaces:**
- Produces:
  - `DemandCalculationEngine.calculate(input, progress_callback=None, cancel_check=None)`
  - CLI `demand-engine calculate --input <json> --output <json>`
  - `ComparisonResult`

- [ ] **Step 1: 写端到端引擎失败测试**

```python
from demand_engine import DemandCalculationEngine
from tests.conftest import build_simple_exponential_input


def test_auto_engine_calculates_item_quantiles():
    result = DemandCalculationEngine().calculate(build_simple_exponential_input())
    item = result.runs[0].items[0]

    assert result.formula_version == "DEMAND-FORMULA-1"
    assert item.expected_demand > 0
    assert item.p95 >= item.p50
    assert item.recommended_spare_quantity >= item.target_quantile_demand
```

- [ ] **Step 2: 写 COMPARE 测试**

COMPARE 必须生成 ANALYTICAL 与 MONTE_CARLO 两个运行，并生成均值、分位数、推荐量和库存缺口差异，等级为 `CONSISTENT`、`MINOR_DEVIATION` 或 `MAJOR_DEVIATION`。

- [ ] **Step 3: 实现模型分派**

按 `ReliabilityModelType` 和 `FailureProcessMode` 调用已完成模块，不在 `engine.py` 重复数学公式。

- [ ] **Step 4: 实现 CLI JSON 解析和输出**

CLI 使用标准库 `argparse`；输入版本不支持时返回非零退出码并输出明确错误。输出必须包含 `engine_version`、`formula_version`、`input_schema_version` 和 `result_schema_version`。

- [ ] **Step 5: 完成纯算法包里程碑验证**

```powershell
cd extensions\demand-engine
python -m pytest -v
python -m ruff check src tests
demand-engine calculate --input tests\fixtures\simple_snapshot.json --output .tmp-result.json
python -c "import json; d=json.load(open('.tmp-result.json', encoding='utf-8')); assert d['formula_version']=='DEMAND-FORMULA-1'"
Remove-Item .tmp-result.json
```

Expected: 全部测试通过，CLI 输出有效 JSON。

- [ ] **Step 6: 提交**

```powershell
git add extensions\demand-engine
git commit -m "feat: expose demand calculation engine and CLI"
```

---

### Task 10: 扩展 API 配置、枚举和 13 张 ORM 表

**Files:**
- Modify: `extensions/maintenance-api/app/core/config.py`
- Modify: `extensions/maintenance-api/app/models/enums.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/app/models/repair.py`
- Create: `extensions/maintenance-api/app/models/demand_scenario.py`
- Create: `extensions/maintenance-api/app/models/demand_calculation.py`
- Test: `extensions/maintenance-api/tests/models/test_demand_models.py`
- Test: `extensions/maintenance-api/tests/test_demand_settings.py`

**Interfaces:**
- Produces 13 张表对应的 ORM 类，以及需求任务资源限制配置。

- [ ] **Step 1: 写配置失败测试**

```python
from app.core.config import Settings


def test_demand_settings_have_safe_defaults(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        _env_file=None,
    )
    assert settings.demand_worker_count == 2
    assert settings.demand_sync_timeout_seconds == 5
    assert settings.demand_max_pending_tasks == 20
    assert settings.demand_max_monte_carlo_runs == 50000
    assert settings.demand_max_scenario_stages == 100
    assert settings.demand_max_fleet_groups == 500
    assert settings.demand_max_demand_items == 5000
    assert settings.demand_result_export_max_rows == 100000
```

- [ ] **Step 2: 写 ORM 表、约束和关系失败测试**

测试必须断言以下 13 个表名、关键外键、唯一约束、Check Constraint 和关系导航：

```text
repair_profiles
demand_scenario_templates
demand_scenario_versions
demand_scenario_stages
demand_fleet_groups
demand_age_groups
demand_stage_fleet_usages
demand_parameter_overrides
demand_common_shock_rules
demand_calculations
demand_calculation_runs
demand_run_item_results
demand_run_contributions
```

- [ ] **Step 3: 实现枚举**

至少新增：

```text
ScenarioVersionStatus
MissingParameterPolicy
DemandExecutionMode
CalculationExecutionType
CalculationStatus
CalculationRunStatus
RerunMode
AgeDistributionType
FailureProcessMode
ShockApplicationMode
ItemCalculationStatus
ShortageRiskLevel
ComparisonConsistencyLevel
```

- [ ] **Step 4: 实现 ORM 模型**

模型字段必须与批准设计一致。JSON 字段使用 SQLAlchemy `JSON`，数值使用规定精度。`demand_calculation_runs` 唯一约束为：

```text
calculation_id + run_mode + attempt_number
```

- [ ] **Step 5: 验证现有 Base 元数据包含 23 张表**

```powershell
cd extensions\maintenance-api
python -m pytest tests\models\test_demand_models.py tests\test_demand_settings.py -v
python -c "from app.db.base import Base; import app.models; assert len(Base.metadata.tables) >= 23"
```

- [ ] **Step 6: 提交**

```powershell
git add extensions\maintenance-api\app\core\config.py extensions\maintenance-api\app\models extensions\maintenance-api\tests
git commit -m "feat: add demand scenario and calculation models"
```

---

### Task 11: 新增 Alembic 迁移并验证升级回退

**Files:**
- Create: `extensions/maintenance-api/alembic/versions/20260723_03_add_demand_calculation_schema.py`
- Test: `extensions/maintenance-api/tests/migrations/test_demand_schema_migration.py`

**Interfaces:**
- Consumes: 实施计划 02 当前 Alembic head。
- Produces: revision `20260723_03`，仅新增需求计算相关结构。

- [ ] **Step 1: 写迁移失败测试**

测试流程：

```python
command.upgrade(config, previous_head)
assert_existing_master_data_tables(engine)
command.upgrade(config, "20260723_03")
assert_demand_tables(engine)
command.downgrade(config, previous_head)
assert_existing_master_data_tables(engine)
assert_no_demand_tables(engine)
command.upgrade(config, "20260723_03")
```

- [ ] **Step 2: 生成确定性迁移文件**

Run:

```powershell
python -m alembic revision --autogenerate --rev-id 20260723_03 -m "add demand calculation schema"
```

Alembic 自动填写当前 head 为 `down_revision`，禁止猜测或手工替换为不存在的 revision。

- [ ] **Step 3: 人工审查迁移**

确认：

- 仅新增 13 张表、索引和外键。
- 未删除或重建现有 10 张主数据表。
- SQLite 和 PostgreSQL 均不使用专属 JSONB。
- downgrade 按外键反向顺序删除新表。

- [ ] **Step 4: 运行迁移测试**

```powershell
python -m pytest tests\migrations\test_demand_schema_migration.py -v
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```

- [ ] **Step 5: 提交**

```powershell
git add extensions\maintenance-api\alembic extensions\maintenance-api\tests\migrations
git commit -m "feat: add demand calculation database migration"
```

---

### Task 12: 实现 Pydantic Schema 与 Repository

**Files:**
- Create: `extensions/maintenance-api/app/schemas/repair.py`
- Create: `extensions/maintenance-api/app/schemas/demand_scenario.py`
- Create: `extensions/maintenance-api/app/schemas/demand_calculation.py`
- Create: `extensions/maintenance-api/app/schemas/demand_result.py`
- Create: `extensions/maintenance-api/app/repositories/repair_repository.py`
- Create: `extensions/maintenance-api/app/repositories/demand_scenario_repository.py`
- Create: `extensions/maintenance-api/app/repositories/demand_calculation_repository.py`
- Modify: `extensions/maintenance-api/app/repositories/__init__.py`
- Test: `extensions/maintenance-api/tests/schemas/test_demand_schemas.py`
- Test: `extensions/maintenance-api/tests/repositories/test_demand_repositories.py`

**Interfaces:**
- Produces创建、更新、读取、发布、复制、预检、提交、状态、结果和导出 Schema。
- Produces Repository 查询方法，用于场景完整加载、参数候选选择、任务锁定、结果分页和重试历史。

- [ ] **Step 1: 写 Schema 校验失败测试**

覆盖：

- 修复成功率与报废率。
- 阶段顺序、时长和系数。
- 年龄分布必要参数。
- 年龄比例。
- 装备活动数量。
- 保障率。
- 仿真次数和批次。
- 覆盖作用域。
- 共同冲击概率和倍数。
- 临时场景与 `scenario_version_id` 二选一。
- `SYNC` 不能绕过复杂度限制。

- [ ] **Step 2: 实现 Schema**

所有 Decimal 输入接受字符串并输出 Decimal；JSON 子结构使用明确的 Pydantic Model，禁止任意表达式和代码字符串。

- [ ] **Step 3: 写 Repository 失败测试**

必须验证：

- Repository 不提交事务。
- 完整场景使用受控 eager loading，避免循环 N+1。
- 可靠性候选查询排序稳定。
- 修理档案有效期查询。
- 当前运行 attempt 查询。
- 结果分页和筛选。
- 幂等键查询。

- [ ] **Step 4: 实现 Repository**

关键接口：

```python
class DemandScenarioRepository:
    def get_full_version(self, session: Session, version_id: int) -> DemandScenarioVersion | None: ...
    def list_publish_issues(self, session: Session, version_id: int) -> list[dict[str, object]]: ...


class DemandCalculationRepository:
    def lock_calculation(self, session: Session, calculation_id: int) -> DemandCalculation | None: ...
    def get_by_idempotency_key(self, session: Session, key: str) -> DemandCalculation | None: ...
    def list_item_results(self, session: Session, run_id: int, **filters) -> tuple[list, int]: ...
```

SQLite 下 `lock_calculation` 使用短事务和状态条件更新，不依赖 `SELECT FOR UPDATE`。

- [ ] **Step 5: 运行与提交**

```powershell
python -m pytest tests\schemas\test_demand_schemas.py tests\repositories\test_demand_repositories.py -v
python -m ruff check app tests
git add extensions\maintenance-api
git commit -m "feat: add demand schemas and repositories"
```

---

### Task 13: 实现修理档案与场景生命周期服务

**Files:**
- Create: `extensions/maintenance-api/app/services/repair_service.py`
- Create: `extensions/maintenance-api/app/services/scenario_service.py`
- Modify: `extensions/maintenance-api/app/services/__init__.py`
- Test: `extensions/maintenance-api/tests/services/test_repair_service.py`
- Test: `extensions/maintenance-api/tests/services/test_scenario_service.py`

**Interfaces:**
- Produces:
  - `RepairService`
  - `ScenarioService.create_version`
  - `ScenarioService.validate_version`
  - `ScenarioService.publish_version`
  - `ScenarioService.retire_version`
  - `ScenarioService.clone_version`
  - `ScenarioService.get_full_version`

- [ ] **Step 1: 写修理档案服务失败测试**

覆盖：

- 引用器材、构型必须存在。
- 有效期冲突。
- 停用记录不参与自动选择。
- 被场景覆盖或历史结果直接引用时禁止物理删除。
- 允许删除未引用错误记录。

- [ ] **Step 2: 写场景发布失败测试**

一次返回全部问题，至少覆盖：

```text
NO_STAGES
NON_CONTIGUOUS_STAGE_ORDER
NO_FLEET_GROUPS
STAGE_HAS_NO_FLEET_USAGE
ACTIVE_QUANTITY_EXCEEDED
CONFIGURATION_NOT_PUBLISHED
AGE_GROUP_PROPORTION_INVALID
INVALID_SIMULATION_CONFIG
DUPLICATE_OVERRIDE_SCOPE
INVALID_COMMON_SHOCK
KNOWN_PARAMETER_GAP_IN_STRICT_MODE
```

- [ ] **Step 3: 实现场景 DRAFT 锁定规则**

PUBLISHED 与 RETIRED 的阶段、群组、年龄分组、覆盖和冲击子资源均拒绝修改，返回 409。

- [ ] **Step 4: 实现深复制**

复制必须重建：

- 阶段 ID。
- 装备群组 ID。
- 年龄分组外键。
- 阶段装备使用外键。
- 参数覆盖作用域外键。
- 共同冲击阶段外键。

新版本状态为 DRAFT，不继承 `published_at` 和 `retired_at`。

- [ ] **Step 5: 运行与提交**

```powershell
python -m pytest tests\services\test_repair_service.py tests\services\test_scenario_service.py -v
python -m ruff check app tests
git add extensions\maintenance-api
git commit -m "feat: add repair and scenario lifecycle services"
```

---

### Task 14: 实现参数选择、快照与计算预检

**Files:**
- Create: `extensions/maintenance-api/app/services/reliability_selection_service.py`
- Create: `extensions/maintenance-api/app/services/repair_selection_service.py`
- Create: `extensions/maintenance-api/app/services/snapshot_service.py`
- Create: `extensions/maintenance-api/app/services/demand_preview_service.py`
- Test: `extensions/maintenance-api/tests/services/test_parameter_selection.py`
- Test: `extensions/maintenance-api/tests/services/test_snapshot_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_preview_service.py`

**Interfaces:**
- Produces:
  - `ReliabilitySelection`
  - `RepairSelection`
  - `SnapshotBuildResult`
  - `DemandPreview`
  - `SnapshotService.build_from_version`
  - `SnapshotService.build_from_temporary_scenario`
  - `SnapshotService.canonical_hash`

- [ ] **Step 1: 写可靠性选择排序测试**

候选顺序严格为：

```text
人工指定
→ 构型完全匹配
→ 器材通用
→ 有效期
→ 数据来源
→ 置信水平
→ 样本量
→ 估计时间
→ profile_code
```

每个被淘汰候选必须有机器可读原因。

- [ ] **Step 2: 写修理档案选择测试**

优先级：

```text
器材覆盖
→ 构型 + 维修级别
→ 构型
→ 维修级别
→ 器材通用
→ 场景默认
```

不可修复器材不强制要求修理档案。

- [ ] **Step 3: 写缺失策略测试**

```text
STRICT          → 整体失败并返回缺失清单
WARN_AND_SKIP   → 标记 SKIPPED，预检可继续
FALLBACK        → 保存来源和风险警告
```

不得把跳过器材写成需求 0。

- [ ] **Step 4: 写快照规范化测试**

```python
def test_snapshot_hash_is_order_and_decimal_scale_independent(snapshot_service):
    left = {"b": "1.00", "a": [{"x": "2.0"}]}
    right = {"a": [{"x": "2.000"}], "b": "1.0"}
    assert snapshot_service.canonical_hash(left) == snapshot_service.canonical_hash(right)
```

规范化必须处理 Decimal、Enum、date、datetime、tuple 和排序键。

- [ ] **Step 5: 实现预检复杂度估计**

返回：

```text
stage_count
fleet_group_count
configuration_item_count
demand_item_count
installed_position_estimate
calculable_count
skipped_count
fallback_count
manual_override_count
recommended_mode
recommended_execution_type
effective_minimum_runs
complexity_score
warnings
```

- [ ] **Step 6: 运行与提交**

```powershell
python -m pytest tests\services\test_parameter_selection.py tests\services\test_snapshot_service.py tests\services\test_demand_preview_service.py -v
python -m ruff check app tests
git add extensions\maintenance-api
git commit -m "feat: add demand selection snapshots and preview"
```

---

### Task 15: 实现同步计算、结果持久化、库存缺口和比较

**Files:**
- Create: `extensions/maintenance-api/app/services/result_persistence_service.py`
- Create: `extensions/maintenance-api/app/services/inventory_gap_service.py`
- Create: `extensions/maintenance-api/app/services/calculation_comparison_service.py`
- Create: `extensions/maintenance-api/app/services/demand_calculation_service.py`
- Test: `extensions/maintenance-api/tests/services/test_result_persistence.py`
- Test: `extensions/maintenance-api/tests/services/test_inventory_gap_service.py`
- Test: `extensions/maintenance-api/tests/services/test_demand_calculation_service.py`
- Test: `extensions/maintenance-api/tests/services/test_calculation_comparison.py`

**Interfaces:**
- Produces:
  - `DemandCalculationService.preview`
  - `DemandCalculationService.submit`
  - `DemandCalculationService.run_synchronously`
  - `ResultPersistenceService.persist_run`
  - `InventoryGapService.apply`
  - `CalculationComparisonService.compare_runs`

- [ ] **Step 1: 将 demand-engine 加入 API 开发依赖**

`requirements.txt` 增加：

```text
numpy>=2.0,<3.0
scipy>=1.14,<2.0
-e ../demand-engine
```

批量脚本中优先执行 `pip install -e ..\demand-engine`，确保 Windows 路径可用。

- [ ] **Step 2: 写同步任务状态转换失败测试**

合法转换：

```text
PENDING → RUNNING
RUNNING → SUCCEEDED
RUNNING → PARTIAL_SUCCESS
RUNNING → FAILED
RUNNING → CANCELLED
```

输入快照在 RUNNING 后不可修改。

- [ ] **Step 3: 写结果事务测试**

若器材结果或贡献明细持久化中途失败：

- 当前运行回滚全部结果明细。
- 任务标记 FAILED。
- 不存在半数器材已写入的正式结果。

- [ ] **Step 4: 实现库存缺口**

统一定义：

```python
usable_inventory = max(
    0,
    available_quantity + in_transit_quantity - safety_stock_reserved,
)
net_demand_gap = max(0, recommended_spare_quantity - usable_inventory)
inventory_coverage_rate = (
    usable_inventory / recommended_spare_quantity
    if recommended_spare_quantity > 0
    else 1
)
```

风险等级阈值放在明确函数中，并写单元测试，不散落在 Router。

- [ ] **Step 5: 实现结果映射**

持久化：

- 器材汇总。
- 阶段、群组、构型明细贡献。
- 选择理由和参数快照。
- 仿真收敛指标。
- 警告。
- COMPARE 差异。

不得保存逐次蒙特卡洛样本。

- [ ] **Step 6: 运行同步集成测试**

```powershell
python -m pytest tests\services\test_result_persistence.py tests\services\test_inventory_gap_service.py tests\services\test_demand_calculation_service.py tests\services\test_calculation_comparison.py -v
```

- [ ] **Step 7: 提交**

```powershell
git add extensions\maintenance-api
git commit -m "feat: add synchronous demand calculation workflow"
```

---

### Task 16: 实现异步执行器、取消、重试与启动恢复

**Files:**
- Create: `extensions/maintenance-api/app/workers/task_registry.py`
- Create: `extensions/maintenance-api/app/workers/executor.py`
- Create: `extensions/maintenance-api/app/workers/recovery.py`
- Create: `extensions/maintenance-api/app/services/calculation_task_service.py`
- Modify: `extensions/maintenance-api/app/main.py`
- Test: `extensions/maintenance-api/tests/workers/test_task_registry.py`
- Test: `extensions/maintenance-api/tests/workers/test_executor.py`
- Test: `extensions/maintenance-api/tests/workers/test_recovery.py`
- Test: `extensions/maintenance-api/tests/services/test_calculation_task_service.py`

**Interfaces:**
- Produces:
  - `DemandTaskExecutor.submit(calculation_id)`
  - `DemandTaskExecutor.shutdown(wait)`
  - `TaskRegistry.register/unregister/is_running`
  - `CalculationTaskService.cancel/retry/replay/rerun_latest`
  - `recover_interrupted_calculations(session)`

- [ ] **Step 1: 写可控测试执行器**

测试不依赖真实等待；注入：

```python
class InlineTestExecutor:
    def submit(self, calculation_id: int) -> None:
        self.runner(calculation_id)
```

真实实现使用 `ThreadPoolExecutor(max_workers=settings.demand_worker_count)`。

- [ ] **Step 2: 写独立 Session 测试**

后台 runner 必须调用 `SessionLocal()` 创建新 Session，不能接收请求 Session。

- [ ] **Step 3: 写重复提交和队列上限测试**

- 同一 calculation_id 重复提交返回 409。
- PENDING 数量达到 `DEMAND_MAX_PENDING_TASKS` 返回 429。
- Idempotency-Key 命中时返回原任务，不重复排队。

- [ ] **Step 4: 写取消和安全检查点测试**

取消请求只设置 `cancel_requested`；算法在阶段或批次检查后更新最终 CANCELLED。

- [ ] **Step 5: 写重试、快照重放、最新数据重算与恢复测试**

- FAILED/INTERRUPTED 可重试。
- 新 attempt_number 递增。
- previous_run_id 正确。
- 旧运行保留。
- `REPLAY_SNAPSHOT` 使用原 `input_snapshot_json` 和原哈希，不读取当前主数据。
- `RERUN_LATEST` 重新选择当前构型、可靠性、修理参数和库存，并创建新哈希。
- 启动时遗留 RUNNING 改为 INTERRUPTED。
- PENDING 不自动执行。

- [ ] **Step 6: 注册应用生命周期**

在 FastAPI lifespan 中：

```python
@asynccontextmanager
async def lifespan(application: FastAPI):
    recover_interrupted_calculations()
    yield
    demand_task_executor.shutdown(wait=False)
```

不要在模块 import 时启动线程。

- [ ] **Step 7: 运行与提交**

```powershell
python -m pytest tests\workers tests\services\test_calculation_task_service.py -v
python -m ruff check app tests
git add extensions\maintenance-api
git commit -m "feat: add asynchronous demand task execution"
```

---

### Task 17: 暴露 REST API、结果查询和 JSON/Excel 导出

**Files:**
- Create: `extensions/maintenance-api/app/api/v1/demand/router.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/repair_profiles.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/scenarios.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/calculations.py`
- Create: `extensions/maintenance-api/app/api/v1/demand/comparisons.py`
- Create: `extensions/maintenance-api/app/exporters/demand_json.py`
- Create: `extensions/maintenance-api/app/exporters/demand_excel.py`
- Modify: `extensions/maintenance-api/app/api/v1/router.py`
- Modify: `extensions/maintenance-api/app/core/exceptions.py`
- Test: `extensions/maintenance-api/tests/api/test_demand_routes.py`
- Test: `extensions/maintenance-api/tests/api/test_calculation_routes.py`
- Test: `extensions/maintenance-api/tests/exporters/test_demand_exports.py`

**Interfaces:**
- Produces批准设计中的 `/api/v1/demand` 全部路由和导出格式。

- [ ] **Step 1: 写路由注册失败测试**

```python
def test_demand_routes_are_registered(app):
    paths = {route.path for route in app.routes}
    assert "/api/v1/demand/calculations" in paths
    assert "/api/v1/demand/calculations/preview" in paths
    assert "/api/v1/demand/scenario-versions/{version_id}/publish" in paths
```

- [ ] **Step 2: 实现修理档案和场景 API**

Router 只调用 Service，不直接执行 SQL。响应继续使用 `success_response` 和现有 `SuccessResponse`。

- [ ] **Step 3: 实现计算 API**

包括：

```text
POST /calculations/preview
POST /calculations
GET  /calculations
GET  /calculations/{id}
GET  /calculations/{id}/status
POST /calculations/{id}/cancel
POST /calculations/{id}/retry
POST /calculations/{id}/replay
POST /calculations/{id}/rerun-latest
```

SYNC 超复杂度返回 422 和 `SYNC_COMPLEXITY_EXCEEDED`。

- [ ] **Step 4: 实现结果和比较 API**

包括器材结果、贡献、阶段汇总、运行、收敛、单任务 COMPARE 和两个历史任务比较。

- [ ] **Step 5: 实现 JSON 和 Excel 导出**

Excel 工作表固定为：

```text
01_任务摘要
02_器材需求结果
03_阶段汇总
04_需求贡献明细
05_模型与参数快照
06_库存缺口
07_警告与诊断
08_模型对比
```

文本以 `=`, `+`, `-`, `@` 开头时前置单引号。超过最大行数返回 422。

- [ ] **Step 6: 验证错误不泄露内部信息**

API 测试必须断言响应不包含：

```text
sqlite:///
Traceback
SELECT
E:\weknora_projects
DATABASE_URL
```

- [ ] **Step 7: 运行与提交**

```powershell
python -m pytest tests\api\test_demand_routes.py tests\api\test_calculation_routes.py tests\exporters\test_demand_exports.py -v
python -m ruff check app tests
git add extensions\maintenance-api
git commit -m "feat: expose demand calculation APIs and exports"
```

---

### Task 18: 样例场景、文档、全量回归与性能验证

**Files:**
- Create: `extensions/maintenance-api/app/scripts/seed_demand_scenarios.py`
- Create: `extensions/maintenance-api/tests/test_seed_demand_scenarios.py`
- Create: `extensions/maintenance-api/tests/performance/test_demand_performance.py`
- Modify: `extensions/maintenance-api/.env.example`
- Modify: `extensions/maintenance-api/README.md`
- Modify: `extensions/demand-engine/README.md`
- Modify: `extensions/maintenance-api/pyproject.toml`
- Modify: `.gitignore`

**Interfaces:**
- Produces幂等示例场景、运行说明、性能标记和最终回归验证。

- [ ] **Step 1: 写种子幂等失败测试**

两次运行后计数不变化，并至少包含：

- 年度训练场景。
- 高强度多阶段场景。
- 共同冲击场景。
- 修理参数。
- 年龄分组。
- 器材级覆盖。

- [ ] **Step 2: 实现种子脚本**

脚本依赖实施计划 02 样例主数据；缺少主数据时输出明确指导，不创建孤立外键。

- [ ] **Step 3: 更新环境变量示例**

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

- [ ] **Step 4: 写性能测试**

标记：

```python
@pytest.mark.performance
```

覆盖：

- 100 器材、10 阶段解析计算。
- 50 器材、5 阶段、10000 次蒙特卡洛。
- 1000 条结果分页。
- 100 器材预检。

性能测试记录耗时并按批准目标断言；普通 `pytest` 默认排除 performance，最终脚本显式运行。

- [ ] **Step 5: 运行两个项目全量验证**

```powershell
cd extensions\demand-engine
python -m pytest -v
python -m ruff check src tests

cd ..\maintenance-api
python -m pytest -v
python -m ruff check app tests
python -m pytest -m performance -v
python -m app.scripts.seed_master_data
python -m app.scripts.seed_demand_scenarios
python -m app.scripts.seed_demand_scenarios
```

- [ ] **Step 6: 启动冒烟验证**

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

手工确认 Swagger 中存在 `master-data` 与 `demand` 路由；完成后停止服务。

- [ ] **Step 7: 提交**

```powershell
git add .gitignore extensions\demand-engine extensions\maintenance-api
git commit -m "docs: add demand engine examples and verification"
```

---

### Task 19: 构建一次性 PowerShell 安装包并完成最终验收

**Files:**
- Create: `delivery/maintenance-demand-engine-phase/apply-demand-engine-phase.ps1`
- Create: `delivery/maintenance-demand-engine-phase/demand-engine-payload/**`
- Create: `delivery/maintenance-demand-engine-phase/maintenance-api-payload/**`
- Create: `delivery/maintenance-demand-engine-phase/docs/README.txt`
- Create: `/mnt/data/maintenance-demand-engine-phase-batch.zip`

**Interfaces:**
- Produces一次性、可停止、可备份、不自动提交 Git 的实施包。

- [ ] **Step 1: 编写预检和备份逻辑**

脚本必须检查：

```powershell
$branch = git branch --show-current
if ($branch -in @("main", "master")) { throw "Refusing to run on $branch" }
if (git status --porcelain) { throw "Working tree must be clean" }
```

备份到：

```text
.phase03-backup-YYYYMMDD-HHMMSS
```

- [ ] **Step 2: 实现文件写入和依赖安装**

顺序：

```text
复制 demand-engine payload
→ pip install -e extensions/demand-engine
→ 复制 maintenance-api payload
→ pip install -r requirements-dev.txt
```

任一命令 `$LASTEXITCODE -ne 0` 时立即 `throw`。

- [ ] **Step 3: 实现迁移验证**

```powershell
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```

- [ ] **Step 4: 实现测试、Ruff 和冒烟检查**

```powershell
python -m pytest -v
python -m ruff check app tests
python -m app.scripts.seed_master_data
python -m app.scripts.seed_demand_scenarios
```

算法包单独执行测试和 Ruff。

- [ ] **Step 5: 在基础项目副本执行安装包**

使用仅包含提交 `74caf07c` 和实施计划 02 的一次性副本，确认脚本能够从干净状态完成全部安装和验证。

- [ ] **Step 6: 最终验证清单**

必须确认：

```text
demand-engine 全部测试通过
maintenance-api 全部既有和新增测试通过
性能标记测试通过
Ruff 零错误
Alembic 升级、回退、再升级成功
23 张以上表注册
样例场景幂等
同步任务成功
异步任务成功
取消与重试成功
JSON 导出成功
Excel 导出成功
Swagger 包含需求路由
```

- [ ] **Step 7: 打包和校验**

```powershell
Compress-Archive -Path delivery\maintenance-demand-engine-phase\* `
  -DestinationPath maintenance-demand-engine-phase-batch.zip -Force
Get-FileHash maintenance-demand-engine-phase-batch.zip -Algorithm SHA256
```

- [ ] **Step 8: 输出 Git 提交命令但不自动执行**

```powershell
git status --short
git --no-pager diff --check
git add .gitignore docs\superpowers extensions\demand-engine extensions\maintenance-api
git commit -m "feat: add maintenance demand calculation engine"
git push -u origin feature/demand-calculation-engine
```

---

## Final Verification Commands

```powershell
cd E:\weknora_projects\maintenance-demand-engine-worktree

cd extensions\demand-engine
python -m pip install -e .[dev]
python -m pytest -v
python -m ruff check src tests
demand-engine calculate --input tests\fixtures\simple_snapshot.json --output .tmp-result.json
Remove-Item .tmp-result.json

cd ..\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install -e ..\demand-engine
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
python -m pytest -v
python -m pytest -m performance -v
python -m ruff check app tests
python -m app.scripts.seed_master_data
python -m app.scripts.seed_demand_scenarios
python -m app.scripts.seed_demand_scenarios
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Expected:

```text
所有 demand-engine 测试通过
所有 maintenance-api 既有与新增测试通过
性能测试达到设计目标
Ruff: All checks passed!
Alembic upgrade/downgrade/upgrade 无错误
样例数据与场景脚本幂等
Swagger 同时展示 /api/v1/master-data 与 /api/v1/demand
```

## Implementation Review Checkpoints

### Checkpoint 1：Task 1–4

审查纯领域对象、解析数学公式和威布尔数值方法。未通过前不开发复杂蒙特卡洛时间轴。

### Checkpoint 2：Task 5–9

审查完整纯算法包、随机复现、收敛、COMPARE 和 CLI。该检查点要求 `demand-engine` 独立通过全部测试。

### Checkpoint 3：Task 10–14

审查 13 张表、迁移、场景生命周期、参数选择和快照。未通过前不启动异步执行。

### Checkpoint 4：Task 15–17

审查同步/异步任务、取消、重试、恢复、结果持久化和 API。

### Checkpoint 5：Task 18–19

执行全量回归、性能验证和批量安装包验收。

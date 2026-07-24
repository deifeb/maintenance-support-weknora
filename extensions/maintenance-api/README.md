# Maintenance Support API

维修器材需求管理系统的独立 Python 业务服务。当前阶段提供装备型号、多版本构型、部件、维修器材、可靠性参数、多库房库存、供应商报价、Excel 主数据导入和样例数据。

## 安装

```powershell
cd E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env -ErrorAction SilentlyContinue
```

## 数据库迁移

```powershell
python -m alembic upgrade head
python -m alembic current
```

回退和重新升级：

```powershell
python -m alembic downgrade base
python -m alembic upgrade head
```

## 样例数据与 Excel 模板

```powershell
python -m app.scripts.seed_master_data
python -m app.scripts.generate_import_template
```

模板路径：`templates/master_data_import_template.xlsx`。

## 启动

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

- Swagger：`http://127.0.0.1:8100/docs`
- 主数据前缀：`/api/v1/master-data`
- Excel 模板：`GET /api/v1/master-data/import/template`
- Excel 校验：`POST /api/v1/master-data/import/validate`
- Excel 执行：`POST /api/v1/master-data/import/execute`

## 验证

```powershell
python -m pytest -v
python -m ruff check app tests
```

## Demand calculation engine

The demand subsystem is available under `/api/v1/demand` and uses the sibling pure-Python package `../demand-engine`.

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m pip install -e ..\demand-engine
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.scripts.seed_master_data
python -m app.scripts.seed_demand_scenarios
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Main capabilities:

- reusable demand scenario templates and immutable published versions;
- exponential, Weibull, binomial, negative-binomial and empirical calculations;
- analytical, adaptive Monte Carlo, AUTO and COMPARE execution modes;
- synchronous and background calculation tasks;
- input snapshots, idempotency keys, cancellation, retry and replay;
- inventory gap analysis and JSON/XLSX exports.

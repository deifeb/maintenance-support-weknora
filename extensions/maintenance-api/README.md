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

## Maintenance AI orchestration

Phase 04 在 `/api/v1/ai` 下提供持久化业务会话、自然语言场景解析、模型路由、确定性工具编排、关键操作确认、SSE 事件续传、需求清单审查和报告导出。

### 初始化

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip "setuptools>=75" wheel
python -m pip install -e ..\maintenance-ai[dev]
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.scripts.seed_master_data
python -m app.scripts.seed_demand_scenarios
python -m app.scripts.seed_ai_configuration
```

`seed_ai_configuration` 校验以下配置并输出稳定摘要：

```text
config/ai-models.yaml
config/ai-routes.yaml
config/ai-tools.yaml
config/ai-prompts.yaml
config/review-rules.yaml
config/report-templates.yaml
```

### 模型配置

本地模式默认读取：

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

远程 OpenAI-compatible 模式默认关闭。启用时配置：

```dotenv
AI_REMOTE_ENABLED=true
OPENAI_COMPATIBLE_BASE_URL=https://your-compatible-endpoint/v1
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_MODEL=...
```

密钥不得提交到 Git。`CONFIDENTIAL` 和 `RESTRICTED` 会话不能调用远程模型。

### 核心接口

- `POST /api/v1/ai/sessions`：创建持久化 AI 业务会话；
- `POST /api/v1/ai/sessions/{id}/messages`：解析任务、澄清场景或发起正式流程；
- `GET /api/v1/ai/sessions/{id}/stream`：按事件序号订阅 SSE；
- `POST /api/v1/ai/confirmations/{id}/approve`：批准结构化确认请求；
- `GET /api/v1/ai/model-routes`：查看模型路由；
- `GET /api/v1/ai/providers/health`：检查 Provider 状态；
- `POST /api/v1/ai/reviews/demand-lists`：执行确定性需求清单审查；
- `POST /api/v1/ai/reports`：创建报告；
- `GET /api/v1/ai/reports/{id}/exports/{format}`：导出 Markdown、JSON 或 DOCX。

普通聊天中的“确认”不能替代确认接口。正式需求计算、正式报告、场景发布和取消任务均由后端固定确认策略控制。

### 离线验收

```powershell
python -m pytest -v
python -m pytest tests\performance -m performance -v
python -m ruff check app tests
python -m ruff format app tests --check
python -m compileall -q app
```

### 真实模型冒烟测试

```powershell
python -m pytest tests\external\test_ollama_smoke.py -m "external and ollama" -v
python -m pytest tests\external\test_openai_compatible_smoke.py `
  -m "external and openai_compatible" -v
```

Ollama 测试要求配置的本地模型已经存在；系统不会自动下载大型模型。OpenAI-compatible 未完整配置时测试会跳过。

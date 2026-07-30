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
- Excel 上传任务：`POST /api/v1/master-data/import/tasks`
- Excel 预览：`POST /api/v1/master-data/import/tasks/{task_id}/preview`
- Excel 显式执行：`POST /api/v1/master-data/import/tasks/{task_id}/execute`

## 验证

```powershell
python -m pytest -v
python -m ruff check app tests
```

## Phase 05-2：浏览器主数据工作区

### 浏览器边界与路由

浏览器只调用 WeKnora 的相对路径 `/api/maintenance/*`。Go 应用在
`/api/maintenance/*` 上完成登录态解析，并向 FastAPI 转发已签发的 actor JWT；
FastAPI 负责租户边界、RBAC 和业务规则。浏览器不选择、发送或显示租户 ID，
也不连接 Maintenance API 的 `8100` 端口，不持有内部签名密钥。

Maintenance 前端路由均要求初始化和认证：

| 页面 | 路由 |
| --- | --- |
| 仪表盘 | `/platform/maintenance/dashboard` |
| 主数据 | `/platform/maintenance/master-data` |
| 构型详情（菜单隐藏） | `/platform/maintenance/master-data/configurations/:configurationId` |
| 备件详情（菜单隐藏） | `/platform/maintenance/master-data/spare-parts/:sparePartId` |
| 场景、计算、库存缺口、审查、报告 | `/platform/maintenance/scenarios`、`/calculations`、`/inventory-gap`、`/reviews`、`/reports` |

菜单只显示仪表盘、主数据、场景、计算、库存缺口、审查和报告；构型与备件详情
只能由主数据页进入。仪表盘挂载时立即刷新，之后每 30 秒刷新一次；浏览器标签隐藏
或路由不再处于 Maintenance 时暂停，恢复可见且活动时立即刷新。

### 主数据角色和详情行为

查看者可以查看行、下载 Excel 模板和当前筛选结果的导出；不能新建、编辑、停用或
导入。贡献者可在已上线的普通主数据上查看、新建、编辑、停用、导入和导出。管理员
包含贡献者能力；库存汇总的行级新建/编辑使用 `adjustInventory` 能力，因此仅管理员
可写入库存，而库存的模板、导出和导入仍只由 `editMasterData` 决定。计划中资源只显示
查看，不提供导入、导出或模板操作。

构型详情页展示版本事实和构型树：草稿可编辑版本与树节点，非草稿通过“克隆为草稿”
继续维护。备件详情按需加载概览、库存、可靠性和供应页签；适用性、批次/序列号、
替代、套件、证据和审计页签会标为未开放，且不会发起猜测请求。

### 扩展通用主数据注册表

1. 先在 FastAPI 提供并测试该资源的、受 actor 租户/RBAC 保护的列表、写入和导出契约。
2. 在 `frontend/src/components/maintenance/master-data/MasterDataRegistry.ts` 增加资源 key 与
   `defineResource` 定义：`endpoint`、`rowKey`、`availability`、`operations`、列、表单和
   行操作；使用 `writeCapability: 'adjustInventory'` 只适用于库存调整，其余默认
   `editMasterData`。
3. 对已上线且可传输的资源添加 `transfer: { exportKey, importable: true }`。`exportKey` 必须
   与后端导出资源一致；计划资源使用 `plannedResource`，不添加 transfer 元数据。
4. 为新增资源补充注册表、权限和传输契约测试。页面从注册表读取配置，因此无需另写
   租户参数或专用传输分支。

### Excel 导入和导出

导出继承当前关键字、停用项和排序筛选。导入严格依次为：下载模板 → 上传任务 →
字段映射 → 预览 → 明确确认 → 执行 → 轮询 → 结果或错误工作簿。预览显示每个工作表的
行数、字段映射、错误和警告；只有有效预览且用户勾选确认后才能执行。任务状态使用
`GET /api/v1/master-data/import/tasks/{task_id}` 轮询，任务过期或 404 时必须重新上传；失败
或可重试网络错误可重试状态查询，校验问题则下载错误工作簿并修正后重新上传。不要把
旧的 `/validate` 或直接 `/execute` 调用作为浏览器工作流。

### 本地联调（PowerShell）

以下三个终端使用同一个未提交的 `$secret`。可先生成一次并保存在安全的本地会话/密钥
管理器，再将同一值设置到两个服务终端；不要把真实值写入 Git 或前端变量。

```powershell
# 仅生成一次；将输出保存在安全位置并在两个服务终端复用。
$secretBytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($secretBytes) } finally { $rng.Dispose() }
$secret = [Convert]::ToBase64String($secretBytes)
```

终端 1（FastAPI）：

```powershell
Set-Location E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
$env:INTERNAL_JWT_SECRET = $secret
$env:INTERNAL_JWT_ISSUER = 'weknora'
$env:INTERNAL_JWT_AUDIENCE = 'maintenance-api'
& .\.venv\Scripts\python.exe -m alembic upgrade head
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

终端 2（Go 代理；`$secret` 必须与终端 1 相同）：

```powershell
Set-Location E:\weknora_projects\maintenance-support-weknora
$env:WEKNORA_MAINTENANCE_ENABLED = 'true'
$env:WEKNORA_MAINTENANCE_BASE_URL = 'http://127.0.0.1:8100'
$env:WEKNORA_MAINTENANCE_SIGNING_SECRET = $secret
$env:WEKNORA_MAINTENANCE_ISSUER = 'weknora'
$env:WEKNORA_MAINTENANCE_AUDIENCE = 'maintenance-api'
go run ./cmd/server
```

终端 3（Vite；目标必须是 Go 的 `8080`，不是 FastAPI）：

```powershell
Set-Location E:\weknora_projects\maintenance-support-weknora\frontend
$env:VITE_DEV_PROXY_TARGET = 'http://127.0.0.1:8080'
npm run dev
```

### Phase 05-2 验证命令

```powershell
Set-Location E:\weknora_projects\maintenance-support-weknora\frontend
npm ci
npm run test
npm run type-check
npm run build

Set-Location E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
& .\.venv\Scripts\python.exe -m pytest tests/api/test_dashboard_api.py tests/services/test_dashboard_service.py tests/api/test_master_data_api.py tests/api/test_master_data_import_tasks.py tests/imports tests/exporters -v
& .\.venv\Scripts\python.exe -m ruff check app tests

Set-Location E:\weknora_projects\maintenance-support-weknora
$env:CGO_ENABLED = '0'
go test ./internal/types -run TestNonCGOJiebaFallback -count=1
go test ./internal/searchutil
go test ./internal/utils
go test ./internal/maintenanceproxy ./internal/router
```

本阶段不包含采购、财务核算或移动离线扫码。

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


## WeKnora 私有代理与生产部署

Maintenance API 只通过 Compose 的 `WeKnora-network` 接收 WeKnora
应用代理请求。`maintenance-api` 服务仅声明内部 `expose: 8100`，
不配置浏览器可访问的宿主机 `ports`。浏览器始终调用
`/api/maintenance/*`，不得直接连接该 Python 服务。

WeKnora 与 Maintenance API 必须配置完全相同的内部 JWT 密钥。
生产环境拒绝 `.env.example` 中的示例占位符。使用 PowerShell
生成 48 字节随机密钥：

```powershell
$secretBytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($secretBytes)
}
finally {
    $rng.Dispose()
}
$secret = [Convert]::ToBase64String($secretBytes)

$env:WEKNORA_MAINTENANCE_SIGNING_SECRET = $secret
$env:INTERNAL_JWT_SECRET = $secret
```

将同一个 `$secret` 持久写入部署密钥存储或根目录 `.env` 的
`WEKNORA_MAINTENANCE_SIGNING_SECRET`。不要把真实密钥提交到 Git。

在启动或升级服务前，必须先成功完成数据库迁移；迁移失败时不能把
服务视为就绪：

```powershell
docker compose run --rm maintenance-api `
    python -m alembic upgrade head
docker compose up -d maintenance-api app
```

`/health` 保持无认证，用于容器内部健康检查，但 Maintenance API
没有浏览器可访问的宿主机端口。`MAINTENANCE_LEGACY_TENANT_ID`
只允许在明确的一次性旧数据回填中使用，不是运行时租户选择机制。

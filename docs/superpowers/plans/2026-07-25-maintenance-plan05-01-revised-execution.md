# Plan 05-1 集成与安全基础修订实施方案

> **执行模式：** Subagent-Driven。每个实施单元使用独立执行上下文；每个单元完成 TDD、聚焦测试、受影响回归、规格审查和代码质量审查后，才允许进入下一个单元。

**目标：** 在真实基线 `c36dca46` 上建立浏览器 → WeKnora Gin → Maintenance FastAPI 的安全内部调用链，完成短时 JWT 身份交换、42 张业务表租户隔离、角色控制、幂等、数据库级乐观并发和审计基础。

**基线：**

```text
repository: deifeb/maintenance-support-weknora
worktree: E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
branch: feature/maintenance-frontend-plan05
head: c36dca464ba9c1c0de59c35a0a9bfb2e3477053b
parent: baf71615504606331ad4634fb6507843b6df5452
```

## 一、不可变约束

1. 不在 `main` 或主工作树直接开发。
2. 浏览器只调用 `/api/maintenance/*`，不知道 Maintenance API 地址或签名密钥。
3. internal JWT 使用 HS256，`iss=weknora`、`aud=maintenance-api`，寿命恰好 180 秒。
4. JWT claims 必含 `sub`、`tenant_id`、`roles`、`aud`、`iss`、`iat`、`exp`、`jti`、`request_id`。
5. FastAPI 只信任已验证 JWT 中的 tenant、actor 和 role；请求参数、请求头和正文不能选择租户。
6. 42 张现有 Maintenance 业务表全部持久化 `tenant_id`；所有租户内唯一约束包含 `tenant_id`。
7. Repository 不提交事务；Service 负责事务边界。
8. viewer 只读；contributor 执行普通维护与工作流；admin 执行发布及高风险操作。
9. 幂等、业务修改和审计必须位于同一数据库事务中。
10. 乐观锁必须使用数据库条件更新，不能仅在 Python 内存中比较版本。
11. 每个单元按“红灯测试 → 最小实现 → 聚焦测试 → 受影响回归 → 审查 → 提交”执行。
12. 不顺带重构知识库、聊天、组织、Agent 等无关模块。

## 二、已经确认的契约校正

### 2.1 Go 配置契约

最终接口固定为：

```text
MaintenanceConfig.Enabled        bool
MaintenanceConfig.BaseURL        string
MaintenanceConfig.SigningSecret  string（仅环境变量，禁止 YAML/JSON 序列化）
MaintenanceConfig.Issuer         string
MaintenanceConfig.Audience       string
MaintenanceConfig.TokenTTL       time.Duration（启用时必须为 180s）
MaintenanceConfig.RequestTimeout time.Duration（默认 30s）
MaintenanceProxyEnabled(*Config) bool
```

规范环境变量：

```text
WEKNORA_MAINTENANCE_ENABLED
WEKNORA_MAINTENANCE_BASE_URL
WEKNORA_MAINTENANCE_SIGNING_SECRET
WEKNORA_MAINTENANCE_ISSUER
WEKNORA_MAINTENANCE_AUDIENCE
WEKNORA_MAINTENANCE_TOKEN_TTL
WEKNORA_MAINTENANCE_REQUEST_TIMEOUT
```

默认本机地址为 `http://127.0.0.1:8100`；Docker 环境通过变量覆盖为 `http://maintenance-api:8100`。

### 2.2 配置文件路径

真实仓库没有 `config/config.yaml.example`。所有原计划对该文件的修改，在本分支统一落到：

```text
config/config.yaml
```

不复制一份可能长期漂移的完整示例配置。

### 2.3 Migration 链

迁移提交后不回头改写：

```text
20260724_05_add_tenant_security_foundation.py
20260725_06_add_idempotency_records.py
20260725_07_add_audit_events.py
```

## 三、实施单元与审查门禁

### Unit 0：持久化设计、计划和进度台账

**目的：** 先把已经找回并验证的计划保存进 Git，避免再次依赖对话记忆。

**文件：**

- 新增 `docs/superpowers/specs/2026-07-24-maintenance-frontend-plan05-design.md`
- 新增 `docs/superpowers/plans/2026-07-24-maintenance-frontend-plan05-implementation-roadmap.md`
- 新增 05-1 至 05-5 五份计划
- 新增 `docs/superpowers/plans/2026-07-25-maintenance-plan05-01-revised-execution.md`
- 新增 `.superpowers/sdd/progress.md`

**验证：**

```powershell
git diff --check
git status --short
Get-FileHash docs\superpowers\plans\2026-07-24-maintenance-plan05-01-integration-security.md -Algorithm SHA256
```

期望 05-1 哈希：

```text
F97CD86F6F82E68BE9A69C7493CC0270F88EC7388E068B6A1AFA07028448500C
```

**提交：** `docs: preserve approved maintenance plan 05`

**审查：** 文件齐全、哈希一致、无业务代码变化。

---

### Unit 1：校正现有 Maintenance 配置提交

**文件：**

- 修改 `internal/config/maintenance.go`
- 修改 `internal/config/maintenance_test.go`
- 修改 `internal/config/config.go`
- 修改 `.env.example`
- 修改 `config/config.yaml`

**红灯测试：**

- `TestMaintenanceConfigDefaultsMatchPlan`
- `TestMaintenanceProxyEnabledIsNilSafe`
- `TestMaintenanceConfigFillsDefaultsForPartialYAML`
- `TestMaintenanceConfigUsesCanonicalEnvironmentOverrides`
- `TestMaintenanceConfigRejectsInvalidBooleanEnvironment`
- `TestMaintenanceConfigRejectsInvalidDurationEnvironment`
- `TestMaintenanceConfigRequiresExactly180SecondTTLWhenEnabled`
- `TestMaintenanceConfigRejectsNonHTTPBaseURL`
- `TestMaintenanceSigningSecretIsNotSerialized`

**实现边界：**

- 先构造默认值，再覆盖 YAML 非零值，再覆盖规范环境变量。
- 非法 bool、duration、URL、空 issuer/audience、短密钥全部使启动失败。
- `SigningSecret` 不带 YAML/JSON/mapstructure 可写标签。
- 不兼容保留当前未发布的 `MAINTENANCE_*` 别名，避免双重配置源。

**聚焦验证：**

```powershell
go test ./internal/config -run Maintenance -v
go test ./internal/config
```

**提交：** `fix: align maintenance proxy configuration contract`

**审查重点：** 密钥不泄漏、错误不静默、接口名与 Tasks 2–4 一致。

---

### Unit 2：内部 JWT claims 与 signer

**文件：**

- 新增 `internal/maintenanceproxy/claims.go`
- 新增 `internal/maintenanceproxy/signer.go`
- 新增 `internal/maintenanceproxy/signer_test.go`

**接口：**

```text
Actor{UserID, TenantID, Roles, RequestID}
Claims{TenantID, Roles, RequestID, jwt.RegisteredClaims}
NewSigner(secret, issuer, audience, ttl) (*Signer, error)
Signer.Sign(actor) (string, error)
```

**红灯覆盖：**

- 正确 claims、HS256、jti、UTC 时间和 180 秒期限；
- 短密钥、空 issuer/audience、非 180 秒 TTL 被拒绝；
- actor 缺 user、tenant、request ID 或 role 被拒绝；
- 未知角色、重复角色、空白角色被拒绝或规范化；
- Sign 不修改调用方传入的 roles 切片。

**验证：**

```powershell
go test ./internal/maintenanceproxy -run Signer -v
go test ./internal/maintenanceproxy
```

**提交：** `feat: sign maintenance actor tokens`

---

### Unit 3：HTTP 与 SSE 反向代理

**文件：**

- 新增 `internal/maintenanceproxy/proxy.go`
- 新增 `internal/maintenanceproxy/proxy_test.go`

**接口：**

```text
ActorResolver func(*gin.Context) (Actor, error)
New(baseURL, signer, actorResolver, timeout) (*Proxy, error)
Proxy.ServeHTTP(*gin.Context)
```

**安全行为：**

- `/api/maintenance/v1/...` 重写为上游 `/api/v1/...`；
- 保留查询字符串、请求体、Content-Type、Idempotency-Key；
- 删除浏览器 `Authorization`、`Cookie`、`X-API-Key`、租户/用户/角色/内部签名头；
- 注入新签发的内部 Bearer token 和可信 request ID；
- 克隆默认 Transport，并设置 30 秒连接/响应头等待；
- SSE 立即 flush，不施加会截断长流的总请求 timeout；
- 上游不可用返回稳定 502，包含 request ID，不暴露 host 和密钥。

**测试：** 路径、查询、伪造头、cookie、普通 JSON、上游断开、SSE 首事件及时到达。

**验证：**

```powershell
go test ./internal/maintenanceproxy -run Proxy -v
go test ./internal/maintenanceproxy
```

**提交：** `feat: proxy maintenance http and sse traffic`

---

### Unit 4：接入 WeKnora 认证上下文和路由

**文件：**

- 新增 `internal/router/maintenance_routes.go`
- 新增 `internal/router/maintenance_routes_test.go`
- 修改 `internal/router/router.go`

**准确接入点：** 全局 `middleware.Auth(...)` 之后、`/api/v1` 组创建之前，在 `/api` 组下注册 `/maintenance/*path`。

**actor 映射：**

- `TenantRoleOwner`、`TenantRoleAdmin` → `admin`
- `TenantRoleContributor` → `contributor`
- `TenantRoleViewer` → `viewer`
- `uint64 tenant_id` 使用十进制字符串写入 claim
- request ID 从 `types.RequestIDFromContext` 获取
- tenantless、缺 user、无 request ID、合成 API-key 用户均拒绝

**验证：**

```powershell
go test ./internal/router -run Maintenance -v
go test ./internal/router ./internal/maintenanceproxy ./internal/middleware
```

**提交：** `feat: register authenticated maintenance routes`

---

### Unit 5：FastAPI internal JWT 验证

**文件：**

- 新增 `extensions/maintenance-api/app/security/__init__.py`
- 新增 `app/security/actor.py`
- 新增 `app/security/internal_jwt.py`
- 新增 `app/security/dependencies.py`
- 修改 `app/core/config.py`
- 修改 `app/core/exceptions.py`
- 修改 `requirements.txt`
- 修改 `.env.example`
- 修改 `tests/conftest.py`
- 新增 `tests/security/test_internal_jwt.py`

**行为：**

- 使用 `PyJWT>=2.10,<3`，只允许 HS256；
- 要求所有 claims 存在且类型正确；
- 检验 issuer、audience、exp、iat、jti；
- 拒绝 `exp <= iat`、寿命超过 180 秒、未来 iat 超出允许时钟偏差；
- roles 只能为 viewer/contributor/admin；
- 返回 frozen、slots 的 `ActorContext`；
- 无 token、错误 token 和过期 token 通过统一 AppException 信封返回 401；
- `SecretStr` 或等效方式确保配置 repr/错误不泄漏密钥。

**验证：**

```powershell
cd extensions\maintenance-api
python -m pytest tests/security/test_internal_jwt.py -v
python -m ruff check app/security tests/security/test_internal_jwt.py
```

**提交：** `feat: verify internal maintenance identity`

---

### Unit 6：权限依赖、稳定错误与响应 metadata

**文件：**

- 新增 `app/security/permissions.py`
- 修改 `app/core/responses.py`
- 修改 `app/schemas/common.py`
- 修改 `app/core/exceptions.py`
- 修改 `app/main.py`（仅在保持旧端点响应形状所需时）
- 新增 `tests/security/test_permissions.py`
- 新增 `tests/test_responses.py`

**接口：**

```text
require_viewer
require_contributor
require_admin
ApiMeta{request_id, tenant_id, version?}
actor-aware maintenance success response
```

**关键决定：**

- 权限不足抛项目级 `PermissionDeniedError`，不直接抛裸 `HTTPException`；
- 业务端点错误统一为 `success=false/error={code,message,details,request_id,retryable?}`；
- `/`、`/health`、`/api/v1/system/info` 既有响应不出现 `meta:null`；
- Maintenance 业务成功响应必须有 request ID 和 tenant ID。

**验证：**

```powershell
python -m pytest tests/security/test_permissions.py tests/test_responses.py tests/test_health.py tests/test_system.py -v
python -m ruff check app tests/security tests/test_responses.py
```

**提交：** `feat: enforce maintenance roles and response metadata`

---

### Unit 7A：42 张业务表的租户与版本模型契约

**文件：**

- 修改 `app/models/mixins.py`
- 修改现有 14 个业务模型模块
- 修改 `app/models/__init__.py`
- 新增 `tests/models/test_tenant_models.py`

**TenantScopedMixin：** `tenant_id: String(64), non-null, indexed`。

**42 张 tenant 表：**

```text
ai_confirmation_requests, ai_events, ai_evidence_items, ai_evidence_packages,
ai_execution_plans, ai_messages, ai_model_calls, ai_plan_steps,
ai_report_citations, ai_report_exports, ai_report_jobs, ai_report_sections,
ai_report_validation_findings, ai_report_versions, ai_review_findings,
ai_review_runs, ai_session_snapshots, ai_sessions, ai_tool_calls,
configuration_items, configuration_versions, demand_age_groups,
demand_calculation_runs, demand_calculations, demand_common_shock_rules,
demand_fleet_groups, demand_parameter_overrides, demand_run_contributions,
demand_run_item_results, demand_scenario_stages, demand_scenario_templates,
demand_scenario_versions, demand_stage_fleet_usages, equipment_models, parts,
reliability_profiles, repair_profiles, spare_parts, supplier_offers, suppliers,
warehouse_inventories, warehouses
```

**VersionedMixin 用于可变聚合根：** 装备、构型版本、零部件、器材、可靠性、仓库、库存、供应商、报价、修理参数、场景模板/版本、计算、AI session/plan/review/report job。

**约束：** 所有 `unique=True` 和 `UniqueConstraint` 加入 tenant_id；跨表引用测试必须验证父子 tenant 一致。

**验证：**

```powershell
python -m pytest tests/models/test_tenant_models.py tests/models -v
python -m ruff check app/models tests/models
```

**提交：** `feat: define tenant-scoped maintenance models`

---

### Unit 7B：可逆租户安全迁移

**文件：**

- 新增 `alembic/versions/20260724_05_add_tenant_security_foundation.py`
- 新增 `tests/migrations/test_tenant_security_migration.py`

**升级流程：**

1. 对 42 张表增加 nullable tenant_id；对版本表增加 version=1。
2. 若任意表存在历史行而 `MAINTENANCE_LEGACY_TENANT_ID` 为空，立即中止。
3. 使用明确变量回填全部历史行。
4. tenant_id 改为 non-null，并创建索引。
5. 用 tenant 复合唯一约束替换全局唯一索引。
6. SQLite 使用 batch alter；PostgreSQL 使用正常 DDL。

**降级保护：** 若发现多个 distinct tenant_id，拒绝降级；单租户时恢复旧约束后再删除 tenant/version 字段。

**验证：**

```powershell
python -m alembic upgrade head
python -m pytest tests/migrations/test_tenant_security_migration.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
```

**提交：** `feat: migrate maintenance data to tenant scope`

---

### Unit 8A：基础数据仓储、服务与 API 的 tenant 传播

**范围：** equipment、catalog、reliability、inventory、supplier、repair。

**文件：**

- 修改 `app/repositories/base.py`
- 修改上述领域 repositories/services
- 修改相应 master-data API 调用点，使其先取得通用 ActorContext
- 修改 `tests/conftest.py`
- 新增/修改 tenant scope 测试

**接口：** repository 的 get/list/create/update/delete 都显式接收 tenant_id；create 强制覆盖 payload 中任何 tenant 字段；service 接收 ActorContext。

**门禁：** 同一 code 可存在于两个租户；任何跨租户 ID、code、外键引用均表现为 404/业务拒绝，不泄漏目标存在性。

**验证：**

```powershell
python -m pytest tests/repositories tests/services/test_services.py tests/api/test_master_data_api.py -v
python -m ruff check app/repositories app/services app/api/v1/master_data tests
```

**提交：** `fix: scope maintenance master data by tenant`

---

### Unit 8B：需求、AI、worker 的 tenant 传播

**范围：** demand_scenario、demand_calculation、AI session/execution/evidence/review/report，以及后台恢复和执行器。

**要求：**

- 所有 repository/service 查询显式 tenant；
- API 将 ActorContext 传入业务服务；
- 异步任务持久化 tenant_id、user_id、request_id；
- worker 从任务记录恢复 tenant 上下文，不使用全局默认租户；
- direct `session.get` 和不带 tenant 条件的业务 `select` 全部清除；
- 两租户同时运行相同计算 code/session code 不冲突。

**验证：**

```powershell
python -m pytest tests/repositories tests/services tests/api tests/workers tests/integration -v
python -m ruff check app tests
```

**提交：** `fix: scope maintenance workflows by tenant`

---

### Unit 9A：幂等记录与并发重放

**文件：**

- 新增 `app/models/idempotency.py`
- 新增 `app/repositories/idempotency_repository.py`
- 新增 `app/services/idempotency_service.py`
- 修改 `app/models/__init__.py`
- 新增 `alembic/versions/20260725_06_add_idempotency_records.py`
- 新增 `tests/services/test_idempotency_service.py`
- 新增迁移测试

**唯一键：** `(tenant_id, user_id, method, path, idempotency_key)`。

**行为：**

- 同 key + 同请求 hash：完成后重放原 status/body；
- 同 key + 不同 hash：409 `IDEMPOTENCY_KEY_REUSED`；
- 另一个 actor、tenant、method 或 path 不共享记录；
- 两个事务并发 begin 通过数据库唯一约束收敛；
- IN_PROGRESS 超时和 FAILED 状态具有明确重试策略；
- JSON 响应持久化前做稳定可序列化转换。

**验证：**

```powershell
python -m alembic upgrade head
python -m pytest tests/services/test_idempotency_service.py tests/migrations -v
```

**提交：** `feat: add maintenance idempotency records`

---

### Unit 9B：数据库级乐观锁与同事务审计

**文件：**

- 新增 `app/models/audit.py`
- 新增 `app/repositories/audit_repository.py`
- 新增 `app/services/audit_service.py`
- 修改 `app/repositories/base.py` 或新增 version helper
- 修改 `app/core/exceptions.py`
- 修改 `app/models/__init__.py`
- 新增 `alembic/versions/20260725_07_add_audit_events.py`
- 新增 `tests/services/test_audit_service.py`
- 新增 `tests/services/test_optimistic_versioning.py`

**乐观锁：** SQL 条件更新必须包含 tenant、id 和 expected version；`rowcount != 1` 返回 `VERSION_CONFLICT`，包含 expected、actual 和当前版本信息。

**审计：** actor、roles、tenant、request ID、jti、幂等键、资源、before/after、结果和错误码完整；业务事务回滚时审计也回滚，成功时一同提交。

**验证：**

```powershell
python -m alembic upgrade head
python -m pytest tests/services/test_optimistic_versioning.py tests/services/test_audit_service.py -v
python -m pytest tests/services/test_idempotency_service.py tests/migrations -v
```

**提交：** `feat: add maintenance concurrency and audit controls`

---

### Unit 10：为现有业务 API 应用角色策略与 metadata

**文件：**

- 修改 `app/api/v1/master_data/*.py`
- 修改 `app/api/v1/demand/*.py`
- 修改 `app/api/v1/ai/*.py`
- 修改 `app/api/v1/router.py`
- 新增 `tests/security/test_api_rbac.py`
- 新增 `tests/integration/test_weknora_proxy_identity.py`

**角色矩阵：**

- GET/list/detail/export/status/SSE：viewer；
- 普通 create/update/deactivate/import/compute/review：contributor；
- 删除、发布、高风险确认、库存调整类能力：admin。

**验收：**

- 伪造 `X-Tenant-ID` 无效；
- 跨租户 ID 返回 404；
- viewer 写入返回稳定 403；
- 所有业务成功响应含 actor tenant/request metadata；
- health/root/system info 保持既有可用性；
- AI SSE 在认证后可持续流式输出。

**验证：**

```powershell
python -m pytest tests/api tests/integration tests/security -v
python -m ruff check app tests
```

**提交：** `feat: protect maintenance business APIs`

---

### Unit 11：部署、运行手册和 Phase 05-1 总门禁

**文件：**

- 新增 `extensions/maintenance-api/Dockerfile`
- 修改 `docker-compose.yml`
- 按需要修改 `docker-compose.dev.yml`
- 修改根 `.env.example`
- 修改 `extensions/maintenance-api/.env.example`
- 修改 `extensions/maintenance-api/README.md`
- 新增 `tests/security/test_security_settings.py`

**Docker 约束：**

- Maintenance API 仅 `expose: 8100` 到内部网络，不映射浏览器可访问的 host port；
- WeKnora app 通过 `http://maintenance-api:8100` 调用；
- 两侧使用同一随机 secret；
- 生产禁止空值、短值和示例密钥；
- healthcheck 可在不带 JWT 时访问；
- 数据库迁移在明确步骤中执行，失败时服务不假装健康。

**最终门禁：**

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05

go test ./internal/config ./internal/maintenanceproxy ./internal/router ./internal/middleware

cd extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m alembic downgrade base
python -m alembic upgrade head
python -m pytest tests/security tests/migrations tests/models tests/repositories tests/services tests/api tests/workers tests/integration -v
python -m ruff check app tests

cd ..\..
docker compose config
```

通过标准：全部命令成功；两租户隔离测试通过；无高风险审查项；不存在未保护的业务路由。

**提交：** `docs: complete maintenance security foundation`

## 四、每个实施单元的双重代码审查

### 规格符合性审查

检查：任务是否完整、是否越界、接口是否与后续单元一致、测试是否真正覆盖红灯原因。

### 代码质量与安全审查

检查：

- secret、token、tenant 是否可能泄漏；
- 所有查询和唯一约束是否 tenant-safe；
- 是否存在仓储 commit、绕过 Service 的直接写入；
- 幂等与乐观锁是否在数据库层真实成立；
- SSE、错误处理和连接资源是否正确；
- migration upgrade/downgrade 是否可重复；
- 测试是否存在无断言、错误 mock 或只验证实现细节。

Critical/Important 问题必须修复并重新审查；Minor 记录到 `.superpowers/sdd/progress.md`，由阶段终审统一裁决。

## 五、交付包约定

每个 Unit 生成一个 ZIP：

```text
plan05-01-unitNN-<name>.zip
├── payload/                  # 按仓库相对路径组织的完整文件
├── patches/unitNN.patch      # git binary-safe patch
├── scripts/apply-unitNN.ps1
├── scripts/verify-unitNN.ps1
├── scripts/rollback-unitNN.ps1
├── reviews/spec-review.md
├── reviews/code-review.md
├── UNIT_REPORT.md
└── SHA256SUMS.txt
```

应用脚本执行前必须验证：

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
```

脚本不会自动 `git commit` 或 `git push`。测试通过并经用户确认后，再提供明确的：

```powershell
git add <本单元文件>
git commit -m "<约定提交信息>"
git push origin feature/maintenance-frontend-plan05
```

## 六、暂停条件

出现以下任一情况立即停止，不继续下一单元：

- 当前 HEAD 与预期基线不一致；
- 工作区存在来源不明的代码修改；
- 红灯测试不是因目标能力缺失而失败；
- migration 需要猜测历史 tenant；
- Go/Python/Node 版本与计划不兼容；
- 聚焦测试通过但受影响回归失败；
- 审查存在未解决的 Critical/Important 问题。

## 七、批准后的第一份代码交付

批准本实施方案后，第一批不直接进入 JWT signer，而是依次交付：

1. **Unit 0：计划与进度台账持久化包**；
2. **Unit 1：Task 1 配置契约校正包**。

Unit 1 在用户本地 Go 1.26 测试通过并完成审查后，才生成 Unit 2 代码。

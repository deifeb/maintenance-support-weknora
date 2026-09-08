# WeKnora Maintenance Frontend Plan 05 Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Plan 05 as five independently testable vertical slices that turn existing maintenance APIs, demand engines, and AI orchestration into a tenant-safe native WeKnora maintenance support module.

**Architecture:** Keep WeKnora as the browser-facing application and identity authority. Add a Go reverse proxy that exchanges the authenticated WeKnora user context for a three-minute internal JWT, then extend the FastAPI maintenance modular monolith with tenant-scoped data, business state machines, and versioned APIs consumed by a Vue 3/TDesign module under `/platform/maintenance`.

**Tech Stack:** Go 1.26, Gin, `github.com/golang-jwt/jwt/v5`, Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite/PostgreSQL-compatible SQL, Vue 3.5, TypeScript 6, Pinia 3, Vue Router 4, TDesign Vue Next, Node test runner through `tsx --test`, pytest, Ruff.

## Global Constraints

- Base all work on commit `baf71615504606331ad4634fb6507843b6df5452` from `feature/demand-calculation-engine`.
- Execute in an isolated worktree on `feature/maintenance-frontend-plan05`; do not implement on `main`.
- The enterprise user interface must be native WeKnora Vue pages; do not create an iframe, a second global sidebar, or an independent Streamlit portal.
- Browser code calls only `/api/maintenance/*`; it must not know the Maintenance API deployment address or internal signing secret.
- The internal JWT lifetime is 180 seconds and includes `sub`, `tenant_id`, `roles`, `aud`, `iss`, `iat`, `exp`, `jti`, and `request_id`.
- Maintenance API derives tenant and actor only from the verified internal JWT; request bodies and query strings are never trusted for tenant selection.
- All maintenance business records, imports, jobs, reports, AI sessions, audit rows, and exported files are tenant-scoped.
- `viewer` is read-only; `contributor` may maintain ordinary data and execute ordinary workflows; `admin` alone may publish rules, confirm high-risk changes, transfer/freeze/adjust stock, and confirm stocktakes.
- LLM output never becomes an authoritative demand quantity, inventory balance, reservation, lifecycle state, or published rule without deterministic service validation and the required confirmation.
- Published scenarios, demand lists, allocation rules, allocation plans, and reports are immutable; changes create derived versions.
- Inventory-changing endpoints require an idempotency key, expected object version, transaction-level revalidation, and an audit row.
- Numeric inventory, reliability, service-level, and demand values use `Decimal`/`Numeric`, not persisted binary floating point.
- Repository methods do not commit; service methods own transaction boundaries.
- Every task follows test-driven development: failing test, observed failure, minimal implementation, passing focused test, passing affected suite, then commit.
- No Plan 05 task may silently refactor unrelated WeKnora knowledge-base, chat, agent, or organization behavior.
- Go verification requires a working Go 1.26 toolchain before Phase 05-1 execution; the previously observed “go not recognized” environment is not considered a code failure.

---

## Approved Scope Coverage

本计划集完整覆盖已通过设计稿中的七个专业页面与横向能力：

| 设计范围 | 实施计划 | 主要交付 |
|---|---|---|
| 工作台 | 05-2 | 租户实时指标、风险分布、最近任务、30秒轮询 |
| 基础数据 | 05-2 | 装备、构型、BOM、器材、仓库、批次、序列号、导入导出 |
| 任务场景 | 05-3 | AI草稿衔接、六步向导、自动保存、版本确认 |
| 需求推算 | 05-3 | 模型推荐、多模型并行、SSE进度、结果比较、逐项决策 |
| 库存缺口 | 05-4 | FEFO、替代建议、保障分配、预留、领退调拨、盘点 |
| 需求审查 | 05-4 | 配套、构型、数量、证据与库存风险审查，派生新版本 |
| 报告中心 | 05-5 | Markdown、JSON、DOCX报告版本与导出 |
| 问答业务卡片 | 05-5 | 场景、计算、比较、缺口、审查与报告业务卡片 |
| 租户、权限与审计 | 05-1 | internal JWT、tenant_id隔离、viewer/contributor/admin、幂等与审计 |
| 优先级规则模拟 | 05-4 | 硬规则、综合评分、新旧规则模拟、管理员发布 |

## Plan Set and Dependency Order

| Order | Plan | Independently testable result | Depends on |
|---:|---|---|---|
| 1 | `2026-07-24-maintenance-plan05-01-integration-security.md` | Authenticated proxy, internal JWT, tenant isolation, RBAC, idempotency and audit foundation | Existing WeKnora auth and Maintenance API |
| 2 | `2026-07-24-maintenance-plan05-02-frontend-master-data.md` | Native menu, shell, dashboard, master-data views, detail pages and Excel import/export | 05-1 |
| 3 | `2026-07-24-maintenance-plan05-03-scenarios-calculations.md` | Six-step scenario wizard, autosave, multi-model execution, comparison and demand-list lifecycle | 05-1, shared UI from 05-2 |
| 4 | `2026-07-24-maintenance-plan05-04-inventory-review-allocation.md` | Lots, serials, stock ledger, reservations, stocktake, deterministic review and allocation | 05-1, 05-2, demand lists from 05-3 |
| 5 | `2026-07-24-maintenance-plan05-05-chat-reports-acceptance.md` | Chat business cards, report center, E2E acceptance, performance and operations documentation | 05-1 through 05-4 |

Do not start a later plan while an earlier plan’s final verification gate is red. A later plan may be drafted or reviewed, but implementation begins only after the prior plan is committed and verified.

## Cross-Plan Contracts

### Authenticated actor contract

```python
from dataclasses import dataclass
from enum import StrEnum


class MaintenanceRole(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str
    tenant_id: str
    roles: frozenset[MaintenanceRole]
    request_id: str
    token_id: str
```

All Maintenance API routers receive `ActorContext` through a FastAPI dependency. Services accept `actor: ActorContext`; repositories accept `tenant_id: str` explicitly or are constructed with a tenant-scoped context.

### Internal JWT contract

```json
{
  "sub": "user-id",
  "tenant_id": "tenant-id",
  "roles": ["contributor"],
  "aud": "maintenance-api",
  "iss": "weknora",
  "iat": 1784894400,
  "exp": 1784894580,
  "jti": "uuid",
  "request_id": "request-id"
}
```

WeKnora strips any browser-supplied internal authorization header. It signs a new token per proxied request or short reuse window, forwards the original request ID, and never exposes the signing key to the frontend.

### Frontend response contract

```ts
export interface ApiMeta {
  request_id: string
  tenant_id: string
  version?: number
}

export interface MaintenanceSuccess<T> {
  success: true
  data: T
  message: string
  meta: ApiMeta
}

export interface MaintenanceErrorDetail {
  code: string
  message: string
  details?: unknown
  request_id?: string
  retryable?: boolean
}
```

The Plan 05 frontend client unwraps `data`, preserves `meta`, and maps 401/403/409/422/503 into stable UI error states. It does not parse free-form exception strings to decide business behavior.

### Versioned write contract

```http
POST /api/maintenance/v1/inventory/reservations/execute
Idempotency-Key: 1e7168a6-1eaa-4e59-b48d-e7b284e56975
Content-Type: application/json

{
  "expected_plan_version": 4,
  "confirmation_token": "signed-confirmation-token"
}
```

A duplicate idempotency key for the same tenant, actor, route and request hash returns the original status and response. Reusing it with a different request hash returns `409 IDEMPOTENCY_KEY_REUSED`.

## File Ownership Boundaries

```text
WeKnora Go
├── internal/config/maintenance.go              # proxy and signer configuration
├── internal/maintenanceproxy/                  # claims, signer, HTTP/SSE proxy
├── internal/router/maintenance_routes.go       # authenticated route registration
└── internal/router/router.go                    # one registration call only

Maintenance API
├── app/security/                               # verified actor and internal JWT
├── app/models/                                 # tenant/version/audit/business tables
├── app/repositories/                           # tenant-scoped persistence
├── app/services/                               # transactions and state machines
├── app/api/v1/                                 # versioned endpoints
└── alembic/versions/                           # reversible migrations

WeKnora frontend
├── src/api/maintenance/                        # typed API and SSE clients
├── src/stores/maintenance/                     # cross-page state only
├── src/components/maintenance/                 # reusable professional UI
├── src/views/maintenance/                      # seven business pages
├── src/router/index.ts                         # child routes
├── src/stores/menu.ts                          # one maintenance menu item
└── src/i18n/locales/{zh-CN,en-US}.json          # labels and errors
```

## Verification Gates

### Gate 1: security foundation

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
go test ./internal/maintenanceproxy ./internal/router ./internal/middleware
cd extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m pytest tests/security tests/migrations tests/repositories -v
python -m ruff check app tests
```

Expected: all tests pass, Alembic reaches head, Ruff prints `All checks passed!`, and a cross-tenant API request returns 404 or 403 without exposing the target record.

### Gate 2: native shell and master data

```powershell
cd frontend
npm run test
npm run type-check
npm run build
cd ..\extensions\maintenance-api
python -m pytest tests/api/test_dashboard_api.py tests/api/test_master_data_api.py tests/imports -v
```

Expected: maintenance routes compile, the menu works for all three roles, dashboard aggregation is tenant-scoped, and import preview does not mutate data.

### Gate 3: scenario and calculation workflow

```powershell
cd extensions\maintenance-api
python -m pytest tests/api/test_scenario_draft_api.py tests/api/test_calculation_groups.py tests/api/test_demand_lists.py tests/integration/test_plan05_scenario_calculation.py -v
cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

Expected: a chat-created draft resumes in the wizard, independent model children complete or fail separately, SSE resumes without duplicate events, and a published demand list is immutable.

### Gate 4: inventory, review and allocation

```powershell
cd extensions\maintenance-api
python -m pytest tests/inventory tests/reviews tests/allocation tests/integration/test_plan05_inventory_workflow.py -v
python -m alembic downgrade -1
python -m alembic upgrade head
python -m ruff check app tests
cd ..\..\frontend
npm run test
npm run type-check
npm run build
```

Expected: no negative or duplicate stock is produced, FEFO is deterministic, partial reservation conflicts are itemized, stocktake conflicts are detected, and rule simulation never changes formal inventory.

### Gate 5: complete acceptance

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
go test ./...
cd frontend
npm run test
npm run type-check
npm run build
npm run test:e2e
cd ..\extensions\maintenance-api
python -m pytest -v
python -m pytest -m performance -v
python -m ruff check app tests
python -m alembic downgrade base
python -m alembic upgrade head
```

Expected: all automated suites pass, two-tenant E2E isolation passes, the report center exports Markdown/JSON/DOCX, AI-disabled structured workflows remain usable, and no high-risk acceptance finding remains open.

## Commit and Review Cadence

- Each task ends with one focused conventional commit.
- Do not combine database migration, backend state machine and frontend page into one unreviewable commit.
- After every plan, run its complete gate and request code review before proceeding.
- The final PR targets `feature/demand-calculation-engine` unless the repository owner explicitly retargets it.
- GitHub write operations previously returned `403 Resource not accessible by integration`; implementation must commit through the local Git worktree until connector write permission is restored.

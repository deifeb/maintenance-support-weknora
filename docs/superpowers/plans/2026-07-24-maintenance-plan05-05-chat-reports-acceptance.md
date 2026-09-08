# Plan 05-5 Chat Cards, Report Center and System Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate maintenance business cards into existing WeKnora chat, deliver a versioned report center, complete mature-software gap documentation, and prove the full tenant-safe maintenance workflow through automated browser, backend, performance, resilience and deployment acceptance.

**Architecture:** Keep the current WeKnora chat renderer and add a narrow card host beneath assistant messages when a validated `maintenance_cards` payload exists. Cards navigate to structured maintenance pages and never perform high-risk mutations inline. Reuse the existing Phase 04 report service and exporters behind a report-center API, then execute full-stack acceptance across WeKnora proxy, Vue frontend, FastAPI, deterministic engines, optional AI degradation and two tenant contexts.

**Tech Stack:** Vue 3.5, TypeScript 6, TDesign, Pinia, Vue Router, existing chat components, Node `tsx --test`, Playwright, Go 1.26, Gin, Python 3.11, FastAPI, SQLAlchemy, Alembic, pytest, Ruff, Markdown/JSON/DOCX exporters.

## Global Constraints

- Phase 05-1 through 05-4 gates must be green.
- Chat remains an auxiliary entry point; all formal edits, confirmations, publications and inventory actions occur in structured pages.
- Card payloads are validated against a versioned schema; unknown card types render a safe fallback link or are ignored without breaking message rendering.
- Chat cards never expose internal JWTs, raw database IDs from another tenant, model secrets, filesystem paths or unrestricted URLs.
- Report generation reads immutable business snapshots and creates new report versions; it does not recalculate or mutate demand, review, inventory or allocation results.
- Markdown, JSON and DOCX outputs must carry report version, tenant-safe citations, source object versions and generated time.
- AI provider unavailability must not break structured scenario, calculation, review, allocation or template-report workflows.
- E2E acceptance uses two tenants and all three maintenance roles.
- Playwright screenshots and traces must not contain secrets or enterprise production data.
- Performance acceptance measures bounded test datasets and documents hardware; it is not a claim of universal production throughput.
- GitHub write permission remains optional for execution; local branch commits are authoritative until connector 403 is resolved.

---

## File Map

**Create:**

```text
extensions/maintenance-api/app/schemas/business_card.py
extensions/maintenance-api/app/services/business_card_service.py
extensions/maintenance-api/app/api/v1/ai/business_cards.py
extensions/maintenance-api/app/api/v1/reports/__init__.py
extensions/maintenance-api/app/api/v1/reports/router.py
extensions/maintenance-api/app/api/v1/reports/jobs.py
extensions/maintenance-api/app/services/report_center_service.py
extensions/maintenance-api/app/schemas/report_center.py
extensions/maintenance-api/tests/services/test_business_card_service.py
extensions/maintenance-api/tests/api/test_business_card_api.py
extensions/maintenance-api/tests/services/test_report_center_service.py
extensions/maintenance-api/tests/api/test_report_center_api.py
extensions/maintenance-api/tests/integration/test_plan05_full_workflow.py
extensions/maintenance-api/tests/integration/test_plan05_ai_disabled.py
extensions/maintenance-api/tests/performance/test_plan05_dashboard_performance.py
extensions/maintenance-api/tests/performance/test_plan05_inventory_performance.py
extensions/maintenance-api/tests/performance/test_plan05_report_performance.py
frontend/src/api/maintenance/reports.ts
frontend/src/api/maintenance/business-cards.ts
frontend/src/components/maintenance/chat/MaintenanceBusinessCardHost.vue
frontend/src/components/maintenance/chat/ScenarioDraftCard.vue
frontend/src/components/maintenance/chat/CalculationCard.vue
frontend/src/components/maintenance/chat/ModelComparisonCard.vue
frontend/src/components/maintenance/chat/InventoryGapCard.vue
frontend/src/components/maintenance/chat/ReviewFindingCard.vue
frontend/src/components/maintenance/chat/ReportCard.vue
frontend/src/components/maintenance/chat/card-registry.ts
frontend/src/components/maintenance/chat/__tests__/card-registry.test.ts
frontend/src/components/maintenance/chat/__tests__/card-navigation.test.ts
frontend/src/views/maintenance/reports/ReportCenter.vue
frontend/src/views/maintenance/reports/ReportDetail.vue
frontend/src/components/maintenance/report/ReportFilterBar.vue
frontend/src/components/maintenance/report/ReportVersionTimeline.vue
frontend/src/components/maintenance/report/ReportGenerationDialog.vue
frontend/src/components/maintenance/report/ReportExportActions.vue
frontend/src/components/maintenance/report/__tests__/report-actions.test.ts
frontend/e2e/maintenance/auth.setup.ts
frontend/e2e/maintenance/navigation.spec.ts
frontend/e2e/maintenance/permissions.spec.ts
frontend/e2e/maintenance/tenant-isolation.spec.ts
frontend/e2e/maintenance/scenario-calculation.spec.ts
frontend/e2e/maintenance/inventory-review-allocation.spec.ts
frontend/e2e/maintenance/reports-chat.spec.ts
frontend/playwright.config.ts
docs/maintenance/plan05-mature-software-gap-matrix.md
docs/maintenance/plan05-deployment-guide.md
docs/maintenance/plan05-permission-matrix.md
docs/maintenance/plan05-user-guide.md
docs/maintenance/plan05-operations-runbook.md
docs/maintenance/plan05-acceptance-report.md
scripts/verify-plan05.ps1
```

**Modify:**

```text
extensions/maintenance-api/app/api/v1/router.py
extensions/maintenance-api/app/services/ai_orchestration_service.py
extensions/maintenance-api/app/services/ai_report_service.py
extensions/maintenance-api/app/services/ai_report_validation_service.py
extensions/maintenance-api/app/exporters/ai_report_markdown.py
extensions/maintenance-api/app/exporters/ai_report_json.py
extensions/maintenance-api/app/exporters/ai_report_docx.py
extensions/maintenance-api/config/report-templates.yaml
extensions/maintenance-api/tests/conftest.py
frontend/src/views/chat/index.vue
frontend/src/views/chat/components/botmsg.vue
frontend/src/router/maintenance.ts
frontend/src/i18n/locales/zh-CN.json
frontend/src/i18n/locales/en-US.json
frontend/package.json
frontend/package-lock.json
README.md
extensions/maintenance-api/README.md
```

---

### Task 1: Define and Validate Maintenance Business Card Schemas

**Files:**
- Create: `app/schemas/business_card.py`
- Create: `app/services/business_card_service.py`
- Test: `tests/services/test_business_card_service.py`

**Interfaces:**
- Produces: discriminated card union `MaintenanceBusinessCard`, schema version `1.0`, tenant-safe navigation validation.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Write failing card schema tests**

```python
import pytest
from pydantic import ValidationError

from app.schemas.business_card import MaintenanceBusinessCard


def test_scenario_card_accepts_internal_navigation():
    card = MaintenanceBusinessCard.model_validate({
        "type": "SCENARIO_DRAFT",
        "schema_version": "1.0",
        "title": "任务场景草稿",
        "summary": "仍有2个字段待确认",
        "status": "CLARIFICATION_REQUIRED",
        "navigation_url": "/platform/maintenance/scenarios/new?session_id=12",
        "payload": {"session_id": 12, "draft_version": 3, "blocking_fields": ["service_level"]},
    })
    assert card.type == "SCENARIO_DRAFT"


@pytest.mark.parametrize("url", [
    "https://example.com/steal", "javascript:alert(1)",
    "/platform/organizations", "//external.example/path",
])
def test_card_rejects_external_or_non_maintenance_navigation(url):
    with pytest.raises(ValidationError):
        MaintenanceBusinessCard.model_validate({
            "type": "REPORT", "schema_version": "1.0", "title": "x", "summary": "x",
            "status": "COMPLETED", "navigation_url": url,
            "payload": {"report_id": 1, "version": 1},
        })


def test_unknown_card_type_is_rejected_without_coercion():
    with pytest.raises(ValidationError):
        MaintenanceBusinessCard.model_validate({
            "type": "EXECUTE_SQL", "schema_version": "1.0", "title": "x",
            "summary": "x", "status": "READY", "navigation_url": "/platform/maintenance/dashboard", "payload": {},
        })
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_business_card_service.py -v
```

Expected: FAIL because the card schema is absent.

- [ ] **Step 3: Implement the discriminated union**

```python
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class CardBase(BaseModel):
    schema_version: Literal["1.0"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    status: str = Field(min_length=1, max_length=64)
    navigation_url: str

    @field_validator("navigation_url")
    @classmethod
    def validate_navigation(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/platform/maintenance/"):
            raise ValueError("business card navigation must stay inside maintenance routes")
        return value


class ScenarioDraftCard(CardBase):
    type: Literal["SCENARIO_DRAFT"]
    payload: ScenarioDraftCardPayload


class CalculationCard(CardBase):
    type: Literal["CALCULATION"]
    payload: CalculationCardPayload


class ModelComparisonCard(CardBase):
    type: Literal["MODEL_COMPARISON"]
    payload: ModelComparisonCardPayload


class InventoryGapCard(CardBase):
    type: Literal["INVENTORY_GAP"]
    payload: InventoryGapCardPayload


class ReviewFindingCard(CardBase):
    type: Literal["REVIEW_FINDING"]
    payload: ReviewFindingCardPayload


class ReportCard(CardBase):
    type: Literal["REPORT"]
    payload: ReportCardPayload


MaintenanceBusinessCard = Annotated[
    Union[ScenarioDraftCard, CalculationCard, ModelComparisonCard, InventoryGapCard, ReviewFindingCard, ReportCard],
    Field(discriminator="type"),
]
```

`BusinessCardService` loads referenced objects with actor tenant scope before constructing cards. It never accepts object titles, statuses or URLs directly from LLM output without reloading the authoritative object.

- [ ] **Step 4: Run tests and lint**

```powershell
python -m pytest tests/services/test_business_card_service.py -v
python -m ruff check app/schemas/business_card.py app/services/business_card_service.py tests/services/test_business_card_service.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/business_card.py extensions/maintenance-api/app/services/business_card_service.py extensions/maintenance-api/tests/services/test_business_card_service.py
git commit -m "feat: define maintenance chat business cards"
```

---

### Task 2: Expose Business Cards Through AI Session Responses

**Files:**
- Create: `app/api/v1/ai/business_cards.py`
- Modify: AI orchestration service and AI router
- Test: `tests/api/test_business_card_api.py`

**Interfaces:**
- Produces: `GET /api/v1/ai/sessions/{session_id}/business-cards` and `maintenance_cards` in completed AI turn payloads.
- Consumed by: Tasks 3–4.

- [ ] **Step 1: Write failing API tests**

```python
def test_session_cards_are_tenant_scoped(client, contributor_headers, session_with_cards):
    response = client.get(f"/api/v1/ai/sessions/{session_with_cards.id}/business-cards", headers=contributor_headers)
    assert response.status_code == 200
    cards = response.json()["data"]["items"]
    assert cards[0]["navigation_url"].startswith("/platform/maintenance/")


def test_other_tenant_card_session_returns_not_found(client, contributor_headers, tenant_two_session_with_cards):
    response = client.get(f"/api/v1/ai/sessions/{tenant_two_session_with_cards.id}/business-cards", headers=contributor_headers)
    assert response.status_code == 404


def test_high_risk_card_contains_navigation_not_execute_action(client, contributor_headers, allocation_card_session):
    cards = client.get(f"/api/v1/ai/sessions/{allocation_card_session.id}/business-cards", headers=contributor_headers).json()["data"]["items"]
    assert all("execute_url" not in card for card in cards)
    assert all("confirmation_token" not in card for card in cards)
```

- [ ] **Step 2: Run and observe failure**

```powershell
python -m pytest tests/api/test_business_card_api.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement card persistence/reference behavior**

Store cards as validated JSON on assistant message structured content or as a normalized `ai_message_business_cards` table. Prefer normalized references when cards must survive title/status changes; the API reconstructs the card from current authorized objects.

Completed AI response adds:

```json
{
  "message_id": 84,
  "content": "已形成需求比较结果。",
  "maintenance_cards": [
    {
      "type": "MODEL_COMPARISON",
      "schema_version": "1.0",
      "title": "模型比较已完成",
      "summary": "3个模型完成，2项差异较大",
      "status": "COMPLETED",
      "navigation_url": "/platform/maintenance/calculations/35/comparison",
      "payload": {"calculation_group_id": 35, "completed_models": 3, "high_difference_items": 2}
    }
  ]
}
```

Do not alter general chat messages without maintenance cards.

- [ ] **Step 4: Run AI and card tests**

```powershell
python -m pytest tests/api/test_business_card_api.py tests/api/test_ai_sessions.py tests/integration/test_ai_full_workflow.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api/v1/ai/business_cards.py extensions/maintenance-api/app/api/v1/ai/router.py extensions/maintenance-api/app/services/ai_orchestration_service.py extensions/maintenance-api/tests/api/test_business_card_api.py
git commit -m "feat: expose maintenance cards in ai sessions"
```

---

### Task 3: Add Frontend Card Registry and Safe Navigation

**Files:**
- Create: card registry, host, card components and tests listed in file map
- Create: `frontend/src/api/maintenance/business-cards.ts`

**Interfaces:**
- Consumes: validated backend card union.
- Produces: `MaintenanceBusinessCardHost` and `cardComponentFor(type)`.
- Consumed by: Task 4.

- [ ] **Step 1: Write failing card registry tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { cardComponentKey, isSafeMaintenanceNavigation } from '../card-registry'


test('all approved card types have renderers', () => {
  for (const type of ['SCENARIO_DRAFT', 'CALCULATION', 'MODEL_COMPARISON', 'INVENTORY_GAP', 'REVIEW_FINDING', 'REPORT'] as const) {
    assert.equal(cardComponentKey(type), type)
  }
})

test('safe navigation stays under platform maintenance', () => {
  assert.equal(isSafeMaintenanceNavigation('/platform/maintenance/scenarios/new?session_id=1'), true)
  assert.equal(isSafeMaintenanceNavigation('/platform/settings'), false)
  assert.equal(isSafeMaintenanceNavigation('https://example.com'), false)
})

test('unknown type returns fallback instead of throwing', () => {
  assert.equal(cardComponentKey('UNKNOWN' as never), 'UNSUPPORTED')
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/components/maintenance/chat/__tests__/card-registry.test.ts src/components/maintenance/chat/__tests__/card-navigation.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement registry and cards**

```ts
export type MaintenanceCardType =
  | 'SCENARIO_DRAFT'
  | 'CALCULATION'
  | 'MODEL_COMPARISON'
  | 'INVENTORY_GAP'
  | 'REVIEW_FINDING'
  | 'REPORT'

export function isSafeMaintenanceNavigation(value: string): boolean {
  try {
    const url = new URL(value, window.location.origin)
    return url.origin === window.location.origin && url.pathname.startsWith('/platform/maintenance/')
  } catch {
    return false
  }
}
```

Each card shows title, status, compact key metrics, risk tag and one navigation button. It does not contain execute, publish, reserve or confirm controls. `MaintenanceBusinessCardHost` catches renderer errors and preserves the normal assistant text.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/chat/__tests__/card-registry.test.ts src/components/maintenance/chat/__tests__/card-navigation.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/business-cards.ts frontend/src/components/maintenance/chat
git commit -m "feat: add maintenance chat card renderers"
```

---

### Task 4: Integrate Card Host into Existing Chat Without Regressions

**Files:**
- Modify: `frontend/src/views/chat/index.vue`
- Modify: `frontend/src/views/chat/components/botmsg.vue`
- Test: `frontend/src/components/maintenance/chat/__tests__/chat-integration.test.ts`

**Interfaces:**
- Consumes: assistant message `maintenance_cards` and card host.
- Produces: cards beneath the corresponding assistant response.

- [ ] **Step 1: Write failing message selection tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { cardsForAssistantMessage } from '../chat-integration'


test('ordinary assistant message returns no card host data', () => {
  assert.deepEqual(cardsForAssistantMessage({ role: 'assistant', content: 'Hello' }), [])
})

test('validated cards are preserved in server order', () => {
  const cards = cardsForAssistantMessage({
    role: 'assistant', content: 'Done',
    maintenance_cards: [scenarioCard(1), reportCard(2)],
  })
  assert.deepEqual(cards.map(card => card.type), ['SCENARIO_DRAFT', 'REPORT'])
})

test('malformed card is dropped but message remains renderable', () => {
  assert.deepEqual(cardsForAssistantMessage({ role: 'assistant', content: 'Done', maintenance_cards: [{ type: 'BAD' }] }), [])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test -- src/components/maintenance/chat/__tests__/chat-integration.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Add minimal chat integration**

In `chat/index.vue`, pass `session.maintenance_cards` to `botmsg`. In `botmsg.vue`, render after normal answer content:

```vue
<MaintenanceBusinessCardHost
  v-if="maintenanceCards.length"
  :cards="maintenanceCards"
  @navigate="path => router.push(path)"
/>
```

Do not change message keys, streaming lifecycle, markdown rendering, citations, follow-up suggestions or scroll-completion signaling. Card rendering completion must be included in the existing answer-render-complete state so the bottom-scroll calculation remains stable.

- [ ] **Step 4: Run chat and frontend suites**

```powershell
npm run test
npm run type-check
npm run build
```

Expected: PASS; ordinary chats render exactly as before and maintenance cards appear only when present.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/views/chat/index.vue frontend/src/views/chat/components/botmsg.vue frontend/src/components/maintenance/chat/__tests__/chat-integration.test.ts
git commit -m "feat: render maintenance cards in weknora chat"
```

---

### Task 5: Add Report Center Service and Versioned API

**Files:**
- Create: report center schema/service/router/API files
- Modify: existing AI report service, validation service, exporters, config
- Test: report center service and API tests

**Interfaces:**
- Produces: report listing/detail/version/generate/export endpoints.
- Consumed by: Task 6 and cards.

- [ ] **Step 1: Write failing report tests**

```python
def test_generate_report_binds_source_versions(session, actor_contributor, published_demand_list, allocation_plan):
    job = ReportCenterService().create_job(session, actor_contributor, {
        "report_type": "INVENTORY_GAP",
        "source_refs": [
            {"type": "demand_list", "id": published_demand_list.id, "version": published_demand_list.version},
            {"type": "allocation_plan", "id": allocation_plan.id, "version": allocation_plan.version},
        ],
        "formats": ["MARKDOWN", "JSON", "DOCX"],
    })
    completed = run_report_job(session, job)
    assert completed.status == "COMPLETED"
    assert {export.format for export in completed.exports} == {"MARKDOWN", "JSON", "DOCX"}
    assert completed.version_number == 1


def test_regenerate_creates_new_version_without_overwrite(session, actor_contributor, completed_report):
    next_job = ReportCenterService().regenerate(session, actor_contributor, completed_report.id)
    run_report_job(session, next_job)
    versions = ReportCenterService().versions(session, actor_contributor, completed_report.lineage_id)
    assert [version.version_number for version in versions] == [2, 1]
    assert versions[1].exports[0].content_hash != ""


def test_report_export_is_tenant_scoped(client, tenant_one_headers, tenant_two_report):
    response = client.get(f"/api/v1/reports/{tenant_two_report.id}/exports/docx", headers=tenant_one_headers)
    assert response.status_code == 404
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd extensions\maintenance-api
python -m pytest tests/services/test_report_center_service.py tests/api/test_report_center_api.py -v
```

Expected: FAIL because the unified report center API is absent.

- [ ] **Step 3: Implement report center contracts**

Report types:

```text
DEMAND_CALCULATION
MODEL_COMPARISON
DEMAND_REVIEW
INVENTORY_GAP
ALLOCATION_PLAN
STOCKTAKE
SPARE_PART_RISK
```

Endpoints:

```text
GET  /api/v1/reports
POST /api/v1/reports/jobs
GET  /api/v1/reports/jobs/{job_id}
GET  /api/v1/reports/{report_id}
GET  /api/v1/reports/{report_id}/versions
POST /api/v1/reports/{report_id}/regenerate
GET  /api/v1/reports/{report_id}/exports/{format}
```

The service reloads and validates all source objects in the actor tenant, stores source IDs and versions, computes an input hash, and sends immutable snapshots to the existing report generator. When AI is unavailable, deterministic templates generate complete structured sections and mark `generation_mode="RULE_FALLBACK"`.

Export metadata includes tenant ID internally but does not print it in end-user report body unless the template explicitly requires an organization identifier. Filenames are sanitized and do not contain database paths.

- [ ] **Step 4: Run tests and existing exporter suites**

```powershell
python -m pytest tests/services/test_report_center_service.py tests/api/test_report_center_api.py tests/exporters/test_ai_report_exports.py tests/services/test_ai_report_service.py tests/services/test_ai_report_validation_service.py -v
python -m ruff check app tests
```

Expected: PASS and Ruff clean.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/schemas/report_center.py extensions/maintenance-api/app/services/report_center_service.py extensions/maintenance-api/app/api/v1/reports extensions/maintenance-api/app/api/v1/router.py extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/app/services/ai_report_validation_service.py extensions/maintenance-api/app/exporters extensions/maintenance-api/config/report-templates.yaml extensions/maintenance-api/tests/services/test_report_center_service.py extensions/maintenance-api/tests/api/test_report_center_api.py
git commit -m "feat: add versioned maintenance report center"
```

---

### Task 6: Build Report Center and Export UI

**Files:**
- Create: report frontend files listed in file map
- Modify: routes and locale files
- Test: report action tests

**Interfaces:**
- Consumes: report center API.
- Produces: report center list/detail/generation/export user flow.

- [ ] **Step 1: Write failing report action tests**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { reportActions } from '../report-actions'


test('completed report exposes available exports and regenerate', () => {
  assert.deepEqual(reportActions({ role: 'contributor', status: 'COMPLETED', formats: ['MARKDOWN', 'JSON', 'DOCX'] }), [
    'view', 'downloadMarkdown', 'downloadJson', 'downloadDocx', 'regenerate',
  ])
})

test('viewer can download but cannot regenerate', () => {
  assert.deepEqual(reportActions({ role: 'viewer', status: 'COMPLETED', formats: ['DOCX'] }), ['view', 'downloadDocx'])
})

test('failed job exposes retry only to contributor or admin', () => {
  assert.deepEqual(reportActions({ role: 'contributor', status: 'FAILED', formats: [] }), ['viewFailure', 'retry'])
})
```

- [ ] **Step 2: Run and observe failure**

```powershell
cd frontend
npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement report center pages**

List filters:

```text
report type, status, scenario, demand-list version, date range, generator, keyword
```

Detail shows source objects and versions, report lineage/version timeline, validation findings, citations, generation mode, job events and exports.

Generation dialog requires report type, source object versions, formats and template. It displays that regeneration creates a new version. Export uses Blob downloads through the existing authenticated request client and uses server-provided sanitized filename.

- [ ] **Step 4: Run tests and build**

```powershell
npm run test -- src/components/maintenance/report/__tests__/report-actions.test.ts
npm run type-check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/maintenance/reports.ts frontend/src/views/maintenance/reports frontend/src/components/maintenance/report frontend/src/router/maintenance.ts frontend/src/i18n/locales
git commit -m "feat: add maintenance report center ui"
```

---

### Task 7: Add Mature Software Gap Matrix

**Files:**
- Create: `docs/maintenance/plan05-mature-software-gap-matrix.md`
- Test: `scripts/test-plan05-gap-matrix.ps1`

**Interfaces:**
- Produces: reviewed mapping of mature EAM capability to project API, page, data model, phase and non-goal.

- [ ] **Step 1: Write the matrix validation script**

```powershell
$path = "docs/maintenance/plan05-mature-software-gap-matrix.md"
$content = Get-Content $path -Raw
$required = @(
  "IBM Maximo", "SAP Asset Management", "Oracle Maintenance",
  "器材主档", "构型适用", "仓库与库位", "批次与有效期", "序列号",
  "预留", "领用", "退回", "调拨", "盘点", "替代件", "配套规则",
  "Plan 05", "后端接口", "数据表", "权限", "验收案例"
)
foreach ($term in $required) {
  if (-not $content.Contains($term)) { throw "Gap matrix missing required term: $term" }
}
$placeholderPattern = '\bT' + 'BD\b|\bTO' + 'DO\b'
if ($content -match $placeholderPattern) { throw "Gap matrix contains placeholder" }
Write-Host "Plan 05 gap matrix validation passed"
```

- [ ] **Step 2: Run and observe failure**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-plan05-gap-matrix.ps1
```

Expected: FAIL because the matrix file is missing.

- [ ] **Step 3: Write the complete matrix**

Use columns:

```text
功能域 | 成熟软件能力 | 本项目必要性 | 现有能力 | Plan 05 实现
前端页面 | 后端接口 | 数据表 | 权限 | 验收案例 | 延后原因
```

At minimum include:

- Maximo-inspired item master, storeroom, balance, reservation, issue/return, transfer, stocktake and repairable asset concepts;
- SAP-inspired maintenance task material linkage, stock/non-stock distinction, availability check and high-priority reassignment;
- Oracle-inspired warehouse/location/lot/serial reservation, pick/issue and return behavior;
- explicit exclusions for procurement, invoice, financial ledger, full WMS and offline mobile scanning.

Do not present the matrix as proof of exact feature parity. Label each row `adopted`, `adapted`, `partial`, or `deferred`.

- [ ] **Step 4: Run matrix validation**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-plan05-gap-matrix.ps1
```

Expected: `Plan 05 gap matrix validation passed`.

- [ ] **Step 5: Commit**

```powershell
git add docs/maintenance/plan05-mature-software-gap-matrix.md scripts/test-plan05-gap-matrix.ps1
git commit -m "docs: add maintenance eam gap matrix"
```

---

### Task 8: Add Full Backend Workflow and AI-Degraded Tests

**Files:**
- Create: full workflow and AI-disabled integration tests
- Modify: test fixtures only as needed

**Interfaces:**
- Produces: automated proof of all structured business boundaries.

- [ ] **Step 1: Write the full workflow test**

```python
def test_plan05_complete_workflow(client, tenant_one_contributor, tenant_one_admin, deterministic_models):
    seed_master_data_and_inventory(client, tenant_one_admin)
    scenario = create_confirmed_scenario_from_ai_draft(client, tenant_one_contributor)
    group = run_multi_model_group(client, tenant_one_contributor, scenario, models=["WEIBULL_RENEWAL", "MONTE_CARLO"])
    demand_list = decide_and_publish_demand_list(client, tenant_one_contributor, tenant_one_admin, group)
    review = review_and_publish_derived_list(client, tenant_one_contributor, tenant_one_admin, demand_list)
    allocation = generate_confirm_and_execute_allocation(client, tenant_one_contributor, review.derived_list)
    report = generate_report(client, tenant_one_contributor, "ALLOCATION_PLAN", allocation.id)
    assert report.status == "COMPLETED"
    assert download_export(client, tenant_one_contributor, report.id, "docx").status_code == 200
    assert ledger_is_balanced(client, tenant_one_contributor, allocation)
```

- [ ] **Step 2: Write the AI-disabled test**

```python
def test_structured_workflow_survives_ai_unavailable(client, contributor_headers, admin_headers, monkeypatch):
    monkeypatch.setenv("AI_REMOTE_ENABLED", "false")
    disable_ollama(monkeypatch)
    scenario = create_scenario_through_structured_api(client, contributor_headers)
    group = run_calculation_group(client, contributor_headers, scenario, ["EXPONENTIAL_POISSON"])
    demand_list = publish_ordinary_demand_list(client, contributor_headers, admin_headers, group)
    review = run_deterministic_review(client, contributor_headers, demand_list)
    report = generate_report(client, contributor_headers, "DEMAND_REVIEW", review.id)
    assert report.generation_mode == "RULE_FALLBACK"
    assert report.status == "COMPLETED"
```

- [ ] **Step 3: Run and repair integration defects**

```powershell
cd extensions\maintenance-api
python -m pytest tests/integration/test_plan05_full_workflow.py tests/integration/test_plan05_ai_disabled.py -v
```

Expected: PASS.

- [ ] **Step 4: Run all backend tests**

```powershell
python -m pytest -v
python -m ruff check app tests
```

Expected: all non-performance and non-external tests pass; Ruff clean.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/tests/integration/test_plan05_full_workflow.py extensions/maintenance-api/tests/integration/test_plan05_ai_disabled.py extensions/maintenance-api/tests/conftest.py
git commit -m "test: cover complete plan05 backend workflow"
```

---

### Task 9: Add Playwright Full-Stack Acceptance Tests

**Files:**
- Create: Playwright config/setup/specs listed in file map
- Modify: frontend package files

**Interfaces:**
- Produces: browser acceptance for navigation, permissions, tenant isolation, workflows, chat cards and reports.

- [ ] **Step 1: Add failing Playwright smoke spec**

```ts
import { test, expect } from '@playwright/test'


test('viewer opens native maintenance dashboard', async ({ page }) => {
  await loginAs(page, 'viewer')
  await page.goto('/platform/maintenance/dashboard')
  await expect(page.getByRole('heading', { name: '维修保障工作台' })).toBeVisible()
  await expect(page.getByRole('link', { name: '基础数据' })).toBeVisible()
  await expect(page.getByRole('button', { name: '新增器材' })).toHaveCount(0)
})
```

- [ ] **Step 2: Install Playwright and run the expected failing smoke test**

```powershell
cd frontend
npm install --save-dev @playwright/test
npx playwright install chromium
npm run test:e2e -- --grep "viewer opens native maintenance dashboard"
```

Expected: FAIL until auth setup, test data and full-stack URLs are configured.

- [ ] **Step 3: Implement deterministic E2E setup and specs**

Add script:

```json
{
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

Test data uses a dedicated E2E database and deterministic users:

```text
tenant-a-viewer
tenant-a-contributor
tenant-a-admin
tenant-b-admin
```

Specs cover:

- native menu and collapsed mode;
- viewer/contributor/admin controls;
- tenant A data invisibility in tenant B;
- AI draft to wizard;
- autosave conflict;
- multi-model partial failure and retry;
- demand-list publish and immutability;
- review and derived version;
- FEFO reservation and partial conflict;
- rule simulation and allocation confirmation;
- report generation/export;
- maintenance card navigation from chat;
- API outage/read-only/error states.

Secrets are loaded from environment and never recorded in screenshots or trace metadata.

- [ ] **Step 4: Run complete E2E suite**

```powershell
npm run test:e2e
```

Expected: all Chromium tests pass; traces are retained only on failure.

- [ ] **Step 5: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/e2e
git commit -m "test: add plan05 browser acceptance"
```

---

### Task 10: Add Performance and Resilience Acceptance

**Files:**
- Create: performance tests listed in file map
- Create: `scripts/verify-plan05.ps1`

**Interfaces:**
- Produces: bounded performance metrics and one-command verification.

- [ ] **Step 1: Write performance assertions**

```python
@pytest.mark.performance
def test_dashboard_summary_p95_under_two_seconds(client, viewer_headers, large_tenant_dataset, benchmark):
    samples = [benchmark(lambda: client.get("/api/v1/dashboard/summary", headers=viewer_headers).elapsed.total_seconds()) for _ in range(30)]
    assert percentile(samples, 95) < 2.0


@pytest.mark.performance
def test_inventory_page_does_not_load_all_rows(client, viewer_headers, hundred_thousand_ledger_rows):
    response = client.get("/api/v1/inventory/ledger?page=1&page_size=50", headers=viewer_headers)
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 50
    assert response.json()["data"]["total"] == 100_000
```

Report test records generation time for a report with 5,000 demand items and asserts it completes within the approved test-environment threshold of 60 seconds.

- [ ] **Step 2: Run performance tests and capture baseline**

```powershell
cd extensions\maintenance-api
python -m pytest -m performance tests/performance/test_plan05_dashboard_performance.py tests/performance/test_plan05_inventory_performance.py tests/performance/test_plan05_report_performance.py -v
```

Expected: tests initially expose any unbounded query or serialization bottleneck; optimize only measured Plan 05 paths.

- [ ] **Step 3: Implement one-command verification script**

```powershell
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot\..
try {
  go test ./...
  Push-Location frontend
  npm ci
  npm run test
  npm run type-check
  npm run build
  npm run test:e2e
  Pop-Location
  Push-Location extensions\maintenance-api
  .\.venv\Scripts\python.exe -m alembic upgrade head
  .\.venv\Scripts\python.exe -m pytest -v
  .\.venv\Scripts\python.exe -m pytest -m performance -v
  .\.venv\Scripts\python.exe -m ruff check app tests
  Pop-Location
} finally {
  Pop-Location
}
```

The script checks for Go, Node, npm and `.venv` first and emits actionable prerequisite errors instead of continuing after a missing tool.

- [ ] **Step 4: Run the script**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-plan05.ps1
```

Expected: exit code 0 and all gates pass.

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/tests/performance scripts/verify-plan05.ps1
git commit -m "test: add plan05 performance verification"
```

---

### Task 11: Write Deployment, Permission, User and Operations Documentation

**Files:**
- Create: documentation files listed in file map
- Modify: root and Maintenance API READMEs
- Test: `scripts/test-plan05-docs.ps1`

**Interfaces:**
- Produces: reproducible deployment and operating procedures.

- [ ] **Step 1: Add documentation completeness test**

```powershell
$files = @(
  "docs/maintenance/plan05-deployment-guide.md",
  "docs/maintenance/plan05-permission-matrix.md",
  "docs/maintenance/plan05-user-guide.md",
  "docs/maintenance/plan05-operations-runbook.md"
)
foreach ($file in $files) {
  if (-not (Test-Path $file)) { throw "Missing documentation: $file" }
  $text = Get-Content $file -Raw
  $placeholderPattern = '\bT' + 'BD\b|\bTO' + 'DO\b'
  if ($text -match $placeholderPattern) { throw "Placeholder found: $file" }
}
Write-Host "Plan 05 documentation validation passed"
```

- [ ] **Step 2: Run and observe failure**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-plan05-docs.ps1
```

Expected: FAIL because documentation is incomplete.

- [ ] **Step 3: Write exact guides**

Deployment guide includes:

- Go 1.26, Node and Python 3.11 prerequisites;
- shared internal secret generation and configuration;
- Maintenance API URL and Docker service network;
- legacy tenant migration procedure and rollback;
- Alembic upgrade/downgrade;
- frontend build and WeKnora deployment;
- health checks and smoke tests.

Permission matrix lists every page and operation for viewer, contributor and admin.

User guide follows scenario → calculation → demand list → review → allocation → inventory → report.

Operations runbook includes:

- proxy 502 and JWT 401 diagnosis;
- SSE reconnect and stuck task recovery;
- idempotency collision investigation;
- inventory conflict and differential regeneration;
- stocktake conflict recovery;
- failed report regeneration;
- AI provider outage and rule fallback;
- tenant isolation incident response;
- backup/restore and audit export.

- [ ] **Step 4: Validate documentation**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-plan05-docs.ps1
```

Expected: `Plan 05 documentation validation passed`.

- [ ] **Step 5: Commit**

```powershell
git add docs/maintenance/plan05-deployment-guide.md docs/maintenance/plan05-permission-matrix.md docs/maintenance/plan05-user-guide.md docs/maintenance/plan05-operations-runbook.md scripts/test-plan05-docs.ps1 README.md extensions/maintenance-api/README.md
git commit -m "docs: add plan05 deployment and operations guides"
```

---

### Task 12: Produce Final Acceptance Report and Release Gate

**Files:**
- Create: `docs/maintenance/plan05-acceptance-report.md`
- Test: all project gates

**Interfaces:**
- Produces: final auditable acceptance decision and release evidence.

- [ ] **Step 1: Create acceptance report structure with explicit evidence fields**

```markdown
# Plan 05 Acceptance Report

## Build Identity
- Branch:
- Commit:
- Date:
- Test environment:

## Automated Verification
| Gate | Command | Result | Evidence |
|---|---|---|---|

## Functional Scenarios
| Scenario | Role | Tenant | Result | Evidence |
|---|---|---|---|---|

## Security and Data Integrity
| Control | Result | Evidence |
|---|---|---|

## Performance
| Measurement | Dataset | Result | Threshold |
|---|---:|---:|---:|

## Open Findings
| Severity | Finding | Owner | Release blocker |
|---|---|---|---|

## Decision
- Release decision: PASS or FAIL
- Approved by:
- Approval time:
```

During execution, replace every blank evidence field with actual command output, screenshot/trace path, count, commit or explicit `None`; do not leave placeholder words.

- [ ] **Step 2: Run the one-command verification**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-plan05.ps1
```

Expected: exit code 0.

- [ ] **Step 3: Run migration and disaster-recovery checks separately**

```powershell
cd extensions\maintenance-api
.\.venv\Scripts\python.exe -m alembic downgrade base
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/migrations -v
```

Expected: reversible migration cycle succeeds on a disposable database and all migration tests pass.

- [ ] **Step 4: Complete the report and enforce release blockers**

Release is `PASS` only when:

- all Go, frontend, backend and E2E tests pass;
- Ruff and type-check pass;
- two-tenant isolation passes;
- no inventory invariant failure occurs;
- published objects remain immutable;
- AI-disabled workflow passes;
- performance thresholds pass in the documented environment;
- no open `BLOCKING` or `HIGH` security/data-integrity finding exists.

- [ ] **Step 5: Commit**

```powershell
git add docs/maintenance/plan05-acceptance-report.md
git commit -m "docs: record plan05 acceptance evidence"
```

## Final Verification Commands

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
powershell -ExecutionPolicy Bypass -File scripts\verify-plan05.ps1
git status --short
git log --oneline --decorate -20
```

Expected:

- verification script exits 0;
- `git status --short` is empty;
- recent log shows focused Plan 05 commits;
- acceptance report decision is `PASS` with no unresolved high-risk blocker.

## Phase Completion Evidence

Attach:

- chat message with each supported business card and navigation target;
- ordinary chat with no visual regression;
- report center list, detail, lineage and exports;
- Markdown, JSON and DOCX sample hashes;
- two-tenant Playwright isolation trace;
- viewer/contributor/admin permission screenshots;
- AI-disabled structured workflow result;
- performance result table;
- mature software gap matrix;
- deployment and operations documents;
- final one-command verification output and clean Git status.

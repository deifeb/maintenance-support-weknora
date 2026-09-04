# Plan 05 C2D-B Report Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make all eight Plan 05 report types creatable and queryable from validated, tenant-scoped durable sources with registry-backed templates.

**Architecture:** A strict create payload is normalized and resolved by ReportSourceService before AIReportService.create() starts its transaction. The resolver returns immutable C2D-A ReportSourceRecord values, while ReportTemplateRegistry is the sole authority for report section definitions and template versions. The list contract filters latest-version AIReportSourceRef records using EXISTS, preserving tenant isolation and paging.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, PyYAML, pytest, Ruff.

## Global Constraints

- Base branch: feature/maintenance-frontend-plan05 at c971ac60e508fc74b65143709350d4ff606f0710. Do not mix unrelated worktrees or untracked bundles into this branch.
- Preserve C2B lineage: one job has one linear version lineage; regeneration reads no current business source and retains the parent snapshot and template version.
- Preserve C2C lifecycle: no automatic supersede, state bypass, or authorization change.
- Resolve every source through tenant-scoped repository reads before inserting a report job, version, or source ref. Missing and foreign-tenant sources return 404 before mutation.
- Creation never mutates a calculation, review, demand list, allocation plan, stocktake, inventory balance, or scenario.
- Snapshot only persisted authority; do not rerun a calculation/review, simulate allocation, or introduce a risk entity.
- Retain legacy session_id, scenario_version_id, calculation_run_id, and review_run_id. Reject incompatible legacy/new inputs rather than choose a source silently.
- Keep the three current 1.0 template titles, versions, section order, and section titles exactly.
- No frontend, new LLM, source-ref backfill, C2D-C source-copy, or export-format/layout work.

---

## File map

| File | Responsibility |
| --- | --- |
| extensions/maintenance-api/app/models/enums.py | Add the five missing report-type values. |
| extensions/maintenance-api/app/schemas/report_center.py | Strict source-ref request and C3-ready source filters. |
| extensions/maintenance-api/app/schemas/ai_report.py | Forward normalized source refs to the report service. |
| extensions/maintenance-api/app/services/report_template_registry.py | Parse, validate, and retrieve immutable versioned template definitions. |
| extensions/maintenance-api/config/report-templates.yaml | Preserve three existing templates and add five explicit 1.0 templates. |
| extensions/maintenance-api/app/services/report_source_policy.py | Define report-type source policy and canonical source records. |
| extensions/maintenance-api/app/services/report_source_service.py | Normalize legacy/new refs, tenant-resolve business sources, enforce versions, and emit persisted evidence. |
| source repositories listed in the approved design | Provide only missing tenant-scoped read helpers used by the resolver. |
| extensions/maintenance-api/app/services/ai_report_service.py | Use resolved records and registry templates for atomic create and skeleton generation. |
| extensions/maintenance-api/app/services/report_center_service.py | Resolve source inputs before creation and forward list filters. |
| extensions/maintenance-api/app/repositories/ai_report_repository.py | Filter report lists through latest-version source refs. |
| extensions/maintenance-api/app/api/v1/reports.py | Bind source filters without accepting tenant overrides. |

## Task 1: Public report type and create/query contract

**Files:**
- Modify: extensions/maintenance-api/app/models/enums.py:347-361
- Modify: extensions/maintenance-api/app/schemas/report_center.py:31-94
- Modify: extensions/maintenance-api/app/schemas/ai_report.py:1-52
- Create: extensions/maintenance-api/tests/services/test_ai_report_type_semantics.py
- Modify: extensions/maintenance-api/tests/api/test_report_center_api.py

**Interfaces:**
- Consumes: existing AIReportSourceType and AIReportType values.
- Produces: ReportSourceRefInput, ReportCenterQuery.source_type/source_id/source_version, and AIReportCreateRequest.source_refs for Tasks 3 and 4.

- [ ] **Step 1: Write failing enum and Pydantic tests**

~~~
@pytest.mark.parametrize("value", [
    "DEMAND_CALCULATION", "MODEL_COMPARISON", "DEMAND_REVIEW",
    "INVENTORY_GAP", "ALLOCATION_PLAN", "STOCKTAKE",
    "SPARE_PART_RISK", "MANAGEMENT_DECISION",
])
def test_all_report_types_are_accepted(value: str) -> None:
    assert AIReportType(value).value == value


def test_report_source_ref_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReportJobCreateRequest(
            title="risk", report_type="SPARE_PART_RISK",
            source_refs=[{"type": "DEMAND_LIST", "id": 1, "extra": True}],
        )


def test_report_center_query_accepts_source_filters() -> None:
    query = ReportCenterQuery(
        source_type="DEMAND_LIST", source_id=7, source_version="3"
    )
    assert query.source_type is AIReportSourceType.DEMAND_LIST
    assert query.source_id == 7
    assert query.source_version == "3"
~~~

- [ ] **Step 2: Run the test and observe the intended failure**

Run from extensions/maintenance-api:

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_ai_report_type_semantics.py -q
~~~

Expected: failure because the five enum values, ReportSourceRefInput, and query fields do not exist.

- [ ] **Step 3: Implement the contract**

Add these enum members without renaming existing ones:

~~~
MODEL_COMPARISON = "MODEL_COMPARISON"
DEMAND_REVIEW = "DEMAND_REVIEW"
ALLOCATION_PLAN = "ALLOCATION_PLAN"
STOCKTAKE = "STOCKTAKE"
SPARE_PART_RISK = "SPARE_PART_RISK"
~~~

In report_center.py add:

~~~
class ReportSourceRefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AIReportSourceType
    id: int = Field(gt=0)
    version: str | None = None
~~~

Add source_refs: list[ReportSourceRefInput] = Field(default_factory=list) to both ReportJobCreateRequest and AIReportCreateRequest. Add source_type: AIReportSourceType | None, source_id: int | None = Field(default=None, gt=0), and source_version: str | None = Field(default=None, min_length=1, max_length=128) to ReportCenterQuery.

- [ ] **Step 4: Prove compatibility**

Run:

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_ai_report_type_semantics.py tests/api/test_report_center_api.py -q
~~~

Expected: PASS; every old create payload still validates.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/models/enums.py extensions/maintenance-api/app/schemas/report_center.py extensions/maintenance-api/app/schemas/ai_report.py extensions/maintenance-api/tests/services/test_ai_report_type_semantics.py extensions/maintenance-api/tests/api/test_report_center_api.py
git commit -m "feat(maintenance): add report source create contracts"
~~~

## Task 2: Versioned template registry and deterministic skeletons

**Files:**
- Create: extensions/maintenance-api/app/services/report_template_registry.py
- Modify: extensions/maintenance-api/config/report-templates.yaml
- Modify: extensions/maintenance-api/app/services/ai_report_service.py:55-71, 158-225, 307-414
- Create: extensions/maintenance-api/tests/services/test_report_template_registry.py
- Modify: extensions/maintenance-api/tests/services/test_ai_report_service.py

**Interfaces:**
- Consumes: Task 1's complete AIReportType enum.
- Produces: ReportTemplateSection, ReportTemplateDefinition, get_template(report_type, version=None), list_templates(), and persisted template versions for Tasks 3 and 4.

- [ ] **Step 1: Write failing registry tests**

~~~
@pytest.mark.parametrize("report_type", list(AIReportType))
def test_each_report_type_resolves_explicit_template(
    report_type: AIReportType,
) -> None:
    template = get_template(report_type)
    assert template.report_type is report_type
    assert template.version == "1.0"
    assert template.sections
    assert len({section.code for section in template.sections}) == len(template.sections)


def test_unknown_template_version_fails_closed() -> None:
    with pytest.raises(BusinessValidationError, match="REPORT_TEMPLATE_NOT_FOUND"):
        get_template(AIReportType.DEMAND_REVIEW, "99.0")
~~~

Add a generation test for STOCKTAKE asserting this exact section order:

~~~
[
    "report_information", "management_summary", "scope_and_snapshot",
    "count_progress", "variance_summary", "conflicts",
    "confirmation_state", "inventory_impact", "citations", "audit",
]
~~~

- [ ] **Step 2: Run and observe the intended failure**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_template_registry.py -q
~~~

Expected: failure because no registry or new templates exist.

- [ ] **Step 3: Implement registry and YAML definitions**

Implement these frozen interfaces:

~~~
@dataclass(frozen=True)
class ReportTemplateSection:
    code: str
    title: str


@dataclass(frozen=True)
class ReportTemplateDefinition:
    report_type: AIReportType
    version: str
    title: str
    sections: tuple[ReportTemplateSection, ...]


def get_template(
    report_type: AIReportType, version: str | None = None
) -> ReportTemplateDefinition:
    resolved_version = version or _latest_versions[report_type]
    try:
        return _templates[(report_type, resolved_version)]
    except KeyError as error:
        raise BusinessValidationError(
            "report template was not found", code="REPORT_TEMPLATE_NOT_FOUND"
        ) from error


def list_templates() -> tuple[ReportTemplateDefinition, ...]:
    return tuple(sorted(_templates.values(), key=lambda item: (item.report_type.value, item.version)))
~~~

Load the YAML relative to the maintenance API package. Reject malformed YAML, unknown report type, missing string version/title, empty sections, duplicate section code, and duplicate (report_type, version) using BusinessValidationError(code="REPORT_TEMPLATE_INVALID"). Use REPORT_TEMPLATE_NOT_FOUND for a valid registry with no requested version.

Keep the existing three templates unchanged. Add the approved 1.0 section orders:

- MODEL_COMPARISON: report_information, management_summary, mission_and_configuration, model_scope, model_assumptions, comparison_results, difference_analysis, uncertainty_and_risk, decision_items, citations, audit.
- DEMAND_REVIEW: report_information, management_summary, source_demand_list, review_rule_set, findings_summary, blocking_findings, decisions, derived_demand_impact, citations, audit.
- ALLOCATION_PLAN: report_information, management_summary, source_demand, allocation_rule, inventory_snapshot, allocation_results, unfulfilled_gap, risk_items, reservation_execution_state, citations, audit.
- STOCKTAKE: report_information, management_summary, scope_and_snapshot, count_progress, variance_summary, conflicts, confirmation_state, inventory_impact, citations, audit.
- SPARE_PART_RISK: report_information, management_summary, demand_exposure, inventory_exposure, repair_reliability_context, shortage_risk, high_priority_parts, mitigation_recommendations, citations, audit.

In AIReportService.create(), call get_template(payload.report_type), persist its version, and remove the literal "1.0". In _generate_version(), use get_template(job.report_type, version.template_version).sections instead of REPORT_SECTION_DEFINITIONS. RULE_FALLBACK remains unchanged.

- [ ] **Step 4: Run focused tests**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_template_registry.py tests/services/test_ai_report_service.py -q
~~~

Expected: PASS; legacy skeletons are unchanged and every type resolves one template.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/services/report_template_registry.py extensions/maintenance-api/config/report-templates.yaml extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/tests/services/test_report_template_registry.py extensions/maintenance-api/tests/services/test_ai_report_service.py
git commit -m "feat(maintenance): register report type templates"
~~~

## Task 3: Authoritative source resolution and policy enforcement

**Files:**
- Create: extensions/maintenance-api/app/services/report_source_service.py
- Modify: extensions/maintenance-api/app/services/report_source_policy.py
- Modify: extensions/maintenance-api/app/services/ai_report_service.py:158-225
- Modify only when a tenant-scoped read is missing: calculation_group_repository.py, demand_calculation_repository.py, demand_list_repository.py, demand_review_repository.py, allocation_repository.py, inventory_stocktake_repository.py, demand_scenario_repository.py
- Create: extensions/maintenance-api/tests/services/test_report_source_service.py
- Modify: extensions/maintenance-api/tests/services/test_report_source_policy.py
- Modify: extensions/maintenance-api/tests/services/test_report_source_snapshot.py

**Interfaces:**
- Consumes: Task 1 source refs, Task 2 template version, C2D-A ReportSourceRecord and build_authoritative_source_snapshot().
- Produces: ResolvedReportSources and ReportSourceService.resolve_for_create(session, actor, payload) for Task 4.

- [ ] **Step 1: Write failing policy and isolation tests**

~~~
@pytest.mark.parametrize("report_type, source_type", [
    (AIReportType.DEMAND_CALCULATION, AIReportSourceType.CALCULATION_RUN),
    (AIReportType.MODEL_COMPARISON, AIReportSourceType.CALCULATION_GROUP),
    (AIReportType.DEMAND_REVIEW, AIReportSourceType.DEMAND_REVIEW),
    (AIReportType.INVENTORY_GAP, AIReportSourceType.DEMAND_LIST),
    (AIReportType.ALLOCATION_PLAN, AIReportSourceType.ALLOCATION_PLAN),
    (AIReportType.STOCKTAKE, AIReportSourceType.INVENTORY_STOCKTAKE),
    (AIReportType.SPARE_PART_RISK, AIReportSourceType.DEMAND_LIST),
])
def test_policy_accepts_required_source(source_factory, report_type, source_type):
    result = report_source_service.resolve_for_create(
        source_factory.session, source_factory.actor,
        source_factory.payload(report_type, source_type),
    )
    assert result.records[0].source_type is source_type


def test_allocation_report_requires_allocation_plan(source_factory):
    with pytest.raises(BusinessValidationError, match="REPORT_SOURCE_REQUIRED"):
        report_source_service.resolve_for_create(
            source_factory.session, source_factory.actor,
            source_factory.empty_payload(AIReportType.ALLOCATION_PLAN),
        )


def test_foreign_tenant_source_is_not_found_before_report_insert(source_factory):
    with pytest.raises(NotFoundError):
        report_source_service.resolve_for_create(
            source_factory.session, source_factory.actor,
            source_factory.foreign_demand_list_payload(),
        )
    assert source_factory.report_job_count() == 0


def test_explicit_version_conflict_is_pre_write(source_factory):
    with pytest.raises(BusinessValidationError, match="REPORT_SOURCE_VERSION_CONFLICT"):
        report_source_service.resolve_for_create(
            source_factory.session, source_factory.actor,
            source_factory.demand_list_payload(version="999"),
        )
~~~

Also test same-type legacy/new disagreement returns REPORT_SOURCE_CONFLICT, allowed optional pairs work, and serialized source records contain only canonical persisted evidence.

- [ ] **Step 2: Run and observe the intended failure**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_source_service.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py -q
~~~

Expected: failure because ReportSourceService and C2D-B policies do not exist.

- [ ] **Step 3: Implement normalization, tenant reads, and canonical records**

Add one repository method only where missing; each method has the signature get(session: Session, tenant_id: str, source_id: int) -> Model | None and confines the query to that tenant. Do not put business-object SQL in report_source_service.py.

Implement:

~~~
@dataclass(frozen=True)
class ResolvedReportSources:
    records: tuple[ReportSourceRecord, ...]
    session_id: int | None
    scenario_version_id: int | None
    calculation_run_id: int | None
    review_run_id: int | None


class ReportSourceService:
    def resolve_for_create(
        self,
        session: Session,
        actor: ActorContext,
        payload: AIReportCreateRequest,
    ) -> ResolvedReportSources:
        normalized = self._normalize(payload)
        rows = self._read_and_validate(session, actor.tenant_id, normalized)
        return self._build_resolved_sources(payload, rows)
~~~

Normalize legacy IDs to the same source input representation before policy checks. The policies are:

| Report type | Required | Optional |
| --- | --- | --- |
| DEMAND_CALCULATION | CALCULATION_RUN | SCENARIO_VERSION when inherited |
| MODEL_COMPARISON | CALCULATION_GROUP | none |
| DEMAND_REVIEW | DEMAND_REVIEW | materialized DEMAND_LIST only |
| INVENTORY_GAP | DEMAND_LIST | ALLOCATION_PLAN |
| ALLOCATION_PLAN | ALLOCATION_PLAN | none |
| STOCKTAKE | INVENTORY_STOCKTAKE | none |
| SPARE_PART_RISK | DEMAND_LIST | DEMAND_REVIEW |
| MANAGEMENT_DECISION | none | every supported source type |

Use BusinessValidationError codes REPORT_SOURCE_REQUIRED for missing required refs, REPORT_SOURCE_CONFLICT for disallowed/contradictory/legacy-conflicting refs, and REPORT_SOURCE_VERSION_CONFLICT when a supplied version differs from the resolved canonical string version. A missing or foreign source raises NotFoundError before a resolved value is returned.

Build ReportSourceRecord with string id/version, source_snapshot_digest(persisted_evidence), no tenant id/path/secret, and the policy's stable source order. Use only the persisted evidence named in the approved design. Preserve build_source_records() for the legacy C2D-A path.

Change AIReportService.create() to accept resolved_sources: ResolvedReportSources | None = None. When supplied, it uses those records and legacy IDs without another source read; when absent, its existing legacy path remains valid. Existing job, version, Snapshot 1.1, and source-ref creation stay in one transaction.

- [ ] **Step 4: Run focused source and migration regressions**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_source_service.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/migrations/test_ai_report_source_ref_migration.py -q
~~~

Expected: PASS; invalid attempts leave no report job/version/source-ref row and valid attempts persist Snapshot 1.1.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/services/report_source_service.py extensions/maintenance-api/app/services/report_source_policy.py extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/app/repositories/calculation_group_repository.py extensions/maintenance-api/app/repositories/demand_calculation_repository.py extensions/maintenance-api/app/repositories/demand_list_repository.py extensions/maintenance-api/app/repositories/demand_review_repository.py extensions/maintenance-api/app/repositories/allocation_repository.py extensions/maintenance-api/app/repositories/inventory_stocktake_repository.py extensions/maintenance-api/app/repositories/demand_scenario_repository.py extensions/maintenance-api/tests/services/test_report_source_service.py extensions/maintenance-api/tests/services/test_report_source_policy.py extensions/maintenance-api/tests/services/test_report_source_snapshot.py extensions/maintenance-api/tests/migrations/test_ai_report_source_ref_migration.py
git commit -m "feat(maintenance): resolve authoritative report sources"
~~~

## Task 4: Create orchestration, latest-source filters, and API wiring

**Files:**
- Modify: extensions/maintenance-api/app/services/report_center_service.py:18-112
- Modify: extensions/maintenance-api/app/repositories/ai_report_repository.py:253-459
- Modify: extensions/maintenance-api/app/api/v1/reports.py:61-111
- Create: extensions/maintenance-api/tests/api/test_report_center_source_refs_api.py
- Modify: extensions/maintenance-api/tests/api/test_report_center_api.py

**Interfaces:**
- Consumes: Task 3 ReportSourceService.resolve_for_create() and Task 1 filter fields.
- Produces: POST /reports/jobs source-specific failures before writes and GET /reports source filters for C3.

- [ ] **Step 1: Write failing façade and API tests**

~~~
def test_legacy_create_contract_still_works(client, contributor_headers, seeded_calculation_run):
    response = client.post("/api/v1/reports/jobs", headers=contributor_headers, json={
        "title": "legacy", "report_type": "DEMAND_CALCULATION",
        "calculation_run_id": seeded_calculation_run.id,
    })
    assert response.status_code == 200


def test_source_version_conflict_is_409(client, contributor_headers, demand_list):
    response = client.post("/api/v1/reports/jobs", headers=contributor_headers, json={
        "title": "risk", "report_type": "SPARE_PART_RISK",
        "source_refs": [{"type": "DEMAND_LIST", "id": demand_list.id, "version": "999"}],
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_SOURCE_VERSION_CONFLICT"


def test_report_list_filters_by_latest_source_ref(client, viewer_headers, report_factory):
    matching, other = report_factory.two_reports_with_distinct_demand_lists()
    response = client.get(
        f"/api/v1/reports?source_type=DEMAND_LIST&source_id={matching.source_id}",
        headers=viewer_headers,
    )
    assert [row["report_id"] for row in response.json()["data"]["items"]] == [matching.report_id]
    assert other.report_id not in [row["report_id"] for row in response.json()["data"]["items"]]
~~~

Add the foreign source test asserting 404 and unchanged AIReportJob count, plus a query test showing source_version further narrows results.

- [ ] **Step 2: Run and observe the intended failure**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_refs_api.py tests/api/test_report_center_api.py -q
~~~

Expected: failure because the façade does not resolve source refs and router/repository filters do not exist.

- [ ] **Step 3: Wire the boundaries and status mapping**

In ReportCenterQueryService.create_job(), construct AIReportCreateRequest with payload.model_dump(mode="json"), call ReportSourceService.resolve_for_create(), then call AIReportService.create(session, actor, request, resolved_sources=resolved). Do not catch NotFoundError or BusinessValidationError. Verify the existing handler maps REPORT_SOURCE_VERSION_CONFLICT to HTTP 409; add that mapping only if absent.

Add source_type, source_id, source_version query parameters to list_reports(), include them in ReportCenterQuery, and pass them through ReportCenterQueryService.list().

Extend AIReportRepository.list_report_center_page() with these optional arguments. When any is supplied, add one correlated EXISTS condition against AIReportSourceRef for the latest-version subquery already used by the list query:

~~~
AIReportSourceRef.tenant_id == tenant_id
AIReportSourceRef.report_version_id == latest_version_id_subquery
AIReportSourceRef.source_type == source_type      # when supplied
AIReportSourceRef.source_id == str(source_id)     # when supplied
AIReportSourceRef.source_version == source_version  # when supplied
~~~

Use EXISTS, not a join, so a report appears once and existing paging/sort behavior is unchanged.

- [ ] **Step 4: Run API and authorization regressions**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_refs_api.py tests/api/test_report_center_api.py tests/api/test_ai_reports.py tests/security/test_ai_report_authority.py -q
~~~

Expected: PASS; foreign references are 404, version drift is 409, policy failures are 422, and old requests/list filters work.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/services/report_center_service.py extensions/maintenance-api/app/repositories/ai_report_repository.py extensions/maintenance-api/app/api/v1/reports.py extensions/maintenance-api/tests/api/test_report_center_source_refs_api.py extensions/maintenance-api/tests/api/test_report_center_api.py
git commit -m "feat(maintenance): filter reports by source references"
~~~

## Task 5: C2D-B regression closure and evidence

**Files:**
- Modify: extensions/maintenance-api/tests/services/test_report_regeneration_lineage.py
- Modify: extensions/maintenance-api/tests/api/test_report_center_regenerate_api.py only if an API assertion must protect C2B compatibility
- Create: docs/superpowers/sdd/c2d-b-closure.md

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: evidence that C2D-B changes only create/query/template behavior and does not begin C2D-C.

- [ ] **Step 1: Add the regeneration isolation regression**

~~~
def test_regeneration_does_not_resolve_current_source_after_c2d_b(
    report_service, session, actor, seeded_report, monkeypatch
):
    monkeypatch.setattr(
        "app.services.report_source_service.ReportSourceService.resolve_for_create",
        lambda *args, **kwargs: pytest.fail("regeneration must not resolve current sources"),
    )
    child = report_service.regenerate(session, actor, seeded_report.id)
    assert child.parent_version_id == seeded_report.latest_version_id
~~~

- [ ] **Step 2: Run the regression**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_lineage.py -q
~~~

Expected: PASS. If it exposes a regression, remove the unintended current-source call while leaving C2D-C source-ref copying unimplemented.

- [ ] **Step 3: Run the complete C2D-B gate**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_ai_report_type_semantics.py tests/services/test_report_template_registry.py tests/services/test_report_source_service.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_source_refs_api.py tests/api/test_report_center_api.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_ai_reports.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py tests/migrations -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
git diff --check
~~~

Expected: all selected tests pass, Ruff reports no violations, and git diff --check prints no whitespace error.

- [ ] **Step 4: Record closure and commit**

Create docs/superpowers/sdd/c2d-b-closure.md recording base/head SHA, exact commands, pass counts, Alembic head, accepted warnings, and confirmation that no frontend/export/regeneration-source-copy code changed. Then run:

~~~
git add extensions/maintenance-api/tests/services/test_report_regeneration_lineage.py extensions/maintenance-api/tests/api/test_report_center_regenerate_api.py docs/superpowers/sdd/c2d-b-closure.md
git commit -m "docs(maintenance): close c2d-b execution"
~~~

## Plan self-review

- Spec coverage: Tasks 1-4 cover eight types, strict source input, legacy compatibility, policies, tenant visibility, version drift, templates, atomic creation, safe query filters, and API status contracts. Task 5 proves C2B/C2C preservation and records closure evidence.
- Scope guard: no task changes frontend files, exports, regeneration source copying, lifecycle behavior, source backfill, or LLM behavior. C2D-C remains separate.
- Interface consistency: ReportSourceRefInput becomes AIReportCreateRequest.source_refs; ReportSourceService.resolve_for_create() returns ResolvedReportSources; AIReportService.create(session, actor, request, resolved_sources=resolved) persists its ReportSourceRecord values; list filtering uses AIReportSourceRef only.
- Placeholder scan: every task identifies files, interfaces, concrete tests, expected failure/pass behavior, commands, and commit boundary.

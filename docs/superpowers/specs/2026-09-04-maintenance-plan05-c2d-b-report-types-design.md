# Plan 05 C2D-B: Report Types, Authoritative Sources, and Templates

**Status:** Approved design; implementation has not started.

**Base:** `feature/maintenance-frontend-plan05` at `c971ac60e508fc74b65143709350d4ff606f0710`.

## Goal

Complete the backend contract needed to create and query every original Plan 05 report type from tenant-scoped, durable business sources. C2D-B extends the C2D-A source-reference foundation without changing frontend behavior, report lifecycle authority, regeneration behavior, or export formats.

## Scope and non-goals

Included:

- eight supported `AIReportType` values: the original seven report types plus the existing `MANAGEMENT_DECISION` compatibility type;
- a source resolver that validates each requested source before a report job is inserted;
- fixed, type-specific source policies and immutable Snapshot 1.1 input;
- a versioned YAML-backed template registry and five new explicit templates;
- create and list contracts that accept and filter by safe source references;
- regression coverage for report creation, source isolation, template selection, and C2B/C2C compatibility.

Excluded:

- frontend/C3 changes;
- new LLM workflows or source recomputation;
- regeneration source-reference copying and export layout changes (C2D-C);
- migration/backfill of historic report rows;
- automatic lifecycle transitions, superseding, or source-object mutation.

## Architecture

`ReportCenterQueryService.create_job()` remains the public orchestration entry point. It will translate the strict public payload into a report creation request only after `ReportSourceService` has resolved all explicit and compatible legacy references against the actor's tenant.

```text
POST /reports/jobs
  -> ReportCenterQueryService
  -> ReportSourceService.resolve_for_create()
  -> policy validation + repository-backed tenant reads + version checks
  -> immutable ReportSourceRecord[]
  -> AIReportService.create()
  -> C2D-A source snapshot + AIReportSourceRef rows, in the same transaction
```

The resolver is the only new component permitted to read current business source objects for a create operation. It never changes those objects, runs a calculation/review/simulation, or changes a stocktake state. `AIReportService` receives already-resolved records and must not independently re-query them.

`ReportTemplateRegistry` is the only authority for section definitions. `AIReportService` selects the definition by `(report_type, template_version)` when it creates a version and when it generates its deterministic skeleton. Regeneration continues to use the stored parent template version; C2D-C owns copying source-reference rows for regenerated versions.

## Public contracts

### Report type values

`AIReportType` gains, without renaming existing values:

```text
DEMAND_CALCULATION
MODEL_COMPARISON
DEMAND_REVIEW
INVENTORY_GAP
ALLOCATION_PLAN
STOCKTAKE
SPARE_PART_RISK
MANAGEMENT_DECISION
```

`MANAGEMENT_DECISION` remains the default and retains its legacy create behavior.

### Create input

`ReportSourceRefInput` is a `BaseModel` with `extra="forbid"`:

```python
class ReportSourceRefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AIReportSourceType
    id: int = Field(gt=0)
    version: str | None = None
```

`ReportJobCreateRequest.source_refs` is `list[ReportSourceRefInput]` with an empty-list default. The compatibility fields `session_id`, `scenario_version_id`, `calculation_run_id`, and `review_run_id` remain accepted.

The resolver converts legacy fields to the same canonical source-reference representation. A legacy source and an explicit source of the same type must identify the same object; otherwise creation fails with `REPORT_SOURCE_CONFLICT`. It may deduplicate identical references but must preserve the policy-defined stable order in the resulting snapshot.

### List input

`ReportCenterQuery` and `GET /reports` add optional `source_type`, `source_id`, and `source_version` fields. Source filtering uses a tenant-scoped `EXISTS` predicate against the latest report version's `AIReportSourceRef` rows, rather than joining arbitrary source rows or exposing snapshot JSON. The predicate returns each matching report once and preserves the existing paging and sorting behavior.

The detail response continues to expose only C2D-A's fail-closed `source_versions` projection. It contains the safe source type, id, version, lineage id, and digest fields when a Snapshot 1.1 projection is valid; raw source snapshots and internal evidence never become API fields.

## Source policies and resolution

The policy registry is explicit data keyed by `AIReportType`. It declares supported source types, required types, optional types, stable snapshot order, and compatibility mappings. `ReportSourceService` uses existing repositories/services for tenant-scoped reads; it does not duplicate business SQL in the report domain.

| Report type | Required source | Optional source | Snapshot rule |
| --- | --- | --- | --- |
| `DEMAND_CALCULATION` | `CALCULATION_RUN` | inherited `SCENARIO_VERSION` | retain run attempt, engine, input hash, and available inventory timestamp |
| `MODEL_COMPARISON` | `CALCULATION_GROUP` | none | retain group state, scenario, candidate identities, model/version identities, and persisted comparison decision outputs |
| `DEMAND_REVIEW` | `DEMAND_REVIEW` | derived demand-list reference only when materialized | retain review state, rule set, demand-list lineage, findings, and decisions |
| `INVENTORY_GAP` | `DEMAND_LIST` | `ALLOCATION_PLAN` | retain published quantities, approved gap/risk evidence, and inventory fingerprint |
| `ALLOCATION_PLAN` | `ALLOCATION_PLAN` | none | retain plan/rule versions, source demand-list version, inventory fingerprint, lines, and persisted gaps/risks |
| `STOCKTAKE` | `INVENTORY_STOCKTAKE` | none | retain status, scope, snapshot time, balance versions, counted quantities, and variance/conflict state |
| `SPARE_PART_RISK` | `DEMAND_LIST` | `DEMAND_REVIEW` | retain already-persisted shortage risk, inventory state, repair/reliability context, and linked review findings |
| `MANAGEMENT_DECISION` | none | any supported type | preserve compatibility behavior and resolve any supplied source safely |

For every source, a missing object or object belonging to another tenant is a `404` before `AIReportJob` or `AIReportVersion` insertion. If `version` is present and does not equal the current authoritative version, create returns `409 REPORT_SOURCE_VERSION_CONFLICT` before mutation. A missing required type returns `422 REPORT_SOURCE_REQUIRED`; disallowed, duplicated-conflicting, or legacy/explicit mismatches return `422 REPORT_SOURCE_CONFLICT`.

The source-specific evidence is converted to `ReportSourceRecord` and passed to the C2D-A Snapshot 1.1 builder. Its digest is derived only from canonical persisted evidence. No transient `InventoryGap` calculation, new demand review, calculation execution, allocation simulation, or stocktake transition is a legal source of evidence.

## Templates

`config/report-templates.yaml` remains the editable configuration source. A new `ReportTemplateRegistry` parses and validates it at load time and exposes:

```python
@dataclass(frozen=True)
class ReportTemplateDefinition:
    report_type: AIReportType
    version: str
    title: str
    sections: tuple[ReportTemplateSection, ...]

def get_template(report_type: AIReportType, version: str | None = None) -> ReportTemplateDefinition: ...
def list_templates() -> tuple[ReportTemplateDefinition, ...]: ...
```

The existing three 1.0 templates keep their current title, version, section order, and section titles. The registry rejects an unknown type, missing/non-string version or title, empty sections, duplicate section codes, and duplicate `(type, version)` definitions before they can be used to create a report.

Five new templates use version `1.0` and these exact section-code orders:

- `MODEL_COMPARISON`: `report_information`, `management_summary`, `mission_and_configuration`, `model_scope`, `model_assumptions`, `comparison_results`, `difference_analysis`, `uncertainty_and_risk`, `decision_items`, `citations`, `audit`.
- `DEMAND_REVIEW`: `report_information`, `management_summary`, `source_demand_list`, `review_rule_set`, `findings_summary`, `blocking_findings`, `decisions`, `derived_demand_impact`, `citations`, `audit`.
- `ALLOCATION_PLAN`: `report_information`, `management_summary`, `source_demand`, `allocation_rule`, `inventory_snapshot`, `allocation_results`, `unfulfilled_gap`, `risk_items`, `reservation_execution_state`, `citations`, `audit`.
- `STOCKTAKE`: `report_information`, `management_summary`, `scope_and_snapshot`, `count_progress`, `variance_summary`, `conflicts`, `confirmation_state`, `inventory_impact`, `citations`, `audit`.
- `SPARE_PART_RISK`: `report_information`, `management_summary`, `demand_exposure`, `inventory_exposure`, `repair_reliability_context`, `shortage_risk`, `high_priority_parts`, `mitigation_recommendations`, `citations`, `audit`.

`AIReportVersion.template_version` stores the definition version selected during create. Deterministic generation continues to record `RULE_FALLBACK`; it renders registered sections rather than the current global hard-coded list.

## Transaction and compatibility rules

The complete create operation is atomic: validate sources, create the report job/version, create C2D-A source references, and persist Snapshot 1.1 or roll back all report writes. No source object can be changed by this transaction.

Existing calls with legacy source fields continue to use the C2D-A-compatible records for `DEMAND_CALCULATION` and `MANAGEMENT_DECISION`. A legacy request for a newly strict type must satisfy that type's policy after normalization; unsupported legacy combinations fail rather than silently choosing a different source.

C2B parent-chain and input-digest rules and C2C lifecycle guards are unchanged. In particular, this phase does not change the existing regeneration source-snapshot copy behavior, export document contents, report statuses, or authorization dependencies.

## Tests and acceptance criteria

New focused tests cover:

- all eight accepted report types and each required/optional-source policy;
- source resolver tenant isolation, not-found-before-write behavior, version mismatch, conflict normalization, and no source mutation;
- strict source-ref request validation and legacy request compatibility;
- every explicit template, registry validation failures, persisted template version, and deterministic section order;
- source type/id/version list filters, latest-version semantics, tenant isolation, paging, and no duplicate jobs;
- safe detail provenance without raw snapshot/evidence exposure.

The regression gate includes C2D-A source/migration tests, C2B regeneration lineage and API tests, C2C lifecycle facade/API tests, existing Report Center and AI report authority tests, migration tests, exporter tests, Ruff, and `git diff --check`.

C2D-B is complete only when all eight values are supported, the seven original types have their documented authoritative source policies, `MANAGEMENT_DECISION` is compatible, source-version drift is rejected, C3 source filters are available, template lookup is registry-backed, and no frontend files change.

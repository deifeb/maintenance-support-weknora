from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.core.exceptions import BusinessValidationError, NotFoundError
from app.models.enums import AIReportSourceType, AIReportType
from app.schemas.ai_report import AIReportCreateRequest, ReportSourceRefInput
from app.services.report_source_service import ReportSourceService


class _Repo:
    def __init__(self, rows=None) -> None:
        self.rows = dict(rows or {})
        self.calls: list[tuple[str, int]] = []

    def get(self, session, tenant_id: str, source_id: int):
        del session
        self.calls.append((tenant_id, source_id))
        return self.rows.get((tenant_id, source_id))


class _CalculationRunRepo(_Repo):
    pass


class _AllocationRepo(_Repo):
    def list_plan_lines(self, session, tenant_id: str, plan_id: int):
        del session
        return self.rows.get((tenant_id, plan_id, "lines"), [])


class _ReviewRepo(_Repo):
    def list_findings(self, session, tenant_id: str, review_id: int):
        del session
        return self.rows.get((tenant_id, review_id, "findings"), [])

    def list_decisions(self, session, tenant_id: str, review_id: int):
        del session
        return self.rows.get((tenant_id, review_id, "decisions"), [])


class _StocktakeRepo(_Repo):
    def list_lines(self, session, tenant_id: str, stocktake_id: int):
        del session
        return self.rows.get((tenant_id, stocktake_id, "lines"), [])


class _LegacyReviewRepo:
    def __init__(self, rows=None) -> None:
        self.rows = dict(rows or {})

    def get_run(self, session, tenant_id: str, source_id: int):
        del session
        return self.rows.get((tenant_id, source_id))


@pytest.fixture
def source_service():
    tenant = "tenant-a"
    calculation = SimpleNamespace(
        id=51,
        version=4,
        scenario_version_id=2,
        input_snapshot_hash="a" * 64,
        inventory_snapshot_at="2026-09-04T00:00:00+00:00",
    )
    run = SimpleNamespace(
        id=1,
        attempt_number=3,
        calculation_id=51,
        run_mode="ANALYTICAL",
        engine_version="engine-1",
        formula_version="formula-1",
        calculation=calculation,
    )
    group = SimpleNamespace(
        id=1,
        version=2,
        status="COMPLETED",
        scenario_version_id=2,
        primary_candidate_key="primary",
        recommendation_snapshot_json={"winner": "primary"},
        parameter_snapshot_json={"alpha": 1},
        current_children=[],
        decisions=[],
    )
    demand_list = SimpleNamespace(
        id=1,
        version_number=5,
        lineage_id="demand-lineage",
        status="PUBLISHED",
        scenario_version_id=2,
        calculation_group_id=1,
        items=[],
    )
    review = SimpleNamespace(
        id=1,
        version=6,
        status="DERIVED",
        rule_set_version="review-1",
        input_hash="b" * 64,
        source_demand_list_id=1,
        source_demand_list_version=5,
        source_lineage_id="demand-lineage",
        source_version_number=5,
        derived_demand_list_id=1,
        total_finding_count=0,
        blocking_finding_count=0,
        pending_finding_count=0,
        pending_blocking_finding_count=0,
    )
    allocation = SimpleNamespace(
        id=1,
        version=7,
        status="READY",
        source_demand_list_id=1,
        source_demand_list_version=5,
        rule_id=21,
        inventory_fingerprint="c" * 64,
    )
    stocktake = SimpleNamespace(
        id=1,
        version=8,
        status="CONFIRMED",
        warehouse_id=31,
        location_id=41,
        snapshot_at="2026-09-04T01:00:00+00:00",
        confirmed_at="2026-09-04T02:00:00+00:00",
    )
    scenario = SimpleNamespace(
        id=2,
        version=9,
        version_code="SCN-9",
        formula_version="formula-1",
    )
    session_row = SimpleNamespace(id=1, version=2, session_code="AI-1")
    legacy_review = SimpleNamespace(
        id=1,
        version=3,
        status="COMPLETED",
        rule_set_version="legacy-review-1",
        session_id=None,
        scenario_version_id=2,
        calculation_run_id=1,
    )
    return ReportSourceService(
        ai_session_repository=_Repo({(tenant, 1): session_row}),
        scenario_repository=_Repo({(tenant, 2): scenario}),
        calculation_run_repository=_CalculationRunRepo({(tenant, 1): run}),
        calculation_group_repository=_Repo({(tenant, 1): group}),
        demand_list_repository=_Repo({(tenant, 1): demand_list}),
        demand_review_repository=_ReviewRepo({(tenant, 1): review}),
        allocation_repository=_AllocationRepo({(tenant, 1): allocation}),
        stocktake_repository=_StocktakeRepo({(tenant, 1): stocktake}),
        legacy_review_repository=_LegacyReviewRepo({(tenant, 1): legacy_review}),
    )


def _payload(report_type: AIReportType, *refs: tuple[AIReportSourceType, int, str | None]):
    return AIReportCreateRequest(
        title="Report",
        report_type=report_type,
        source_refs=[
            ReportSourceRefInput(type=source_type, id=source_id, version=version)
            for source_type, source_id, version in refs
        ],
    )


@pytest.mark.parametrize(
    ("report_type", "source_type"),
    [
        (AIReportType.DEMAND_CALCULATION, AIReportSourceType.CALCULATION_RUN),
        (AIReportType.MODEL_COMPARISON, AIReportSourceType.CALCULATION_GROUP),
        (AIReportType.DEMAND_REVIEW, AIReportSourceType.DEMAND_REVIEW),
        (AIReportType.INVENTORY_GAP, AIReportSourceType.DEMAND_LIST),
        (AIReportType.ALLOCATION_PLAN, AIReportSourceType.ALLOCATION_PLAN),
        (AIReportType.STOCKTAKE, AIReportSourceType.INVENTORY_STOCKTAKE),
        (AIReportType.SPARE_PART_RISK, AIReportSourceType.DEMAND_LIST),
    ],
)
def test_policy_accepts_required_source(source_service, report_type, source_type):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(report_type, (source_type, 1, None)),
    )

    assert result.records[0].source_type is source_type


def test_allocation_report_requires_allocation_plan(source_service):
    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(),
            SimpleNamespace(tenant_id="tenant-a"),
            _payload(AIReportType.ALLOCATION_PLAN),
        )

    assert error.value.code == "REPORT_SOURCE_REQUIRED"
    assert error.value.status_code == 422


def test_foreign_tenant_source_is_not_found(source_service):
    with pytest.raises(NotFoundError) as error:
        source_service.resolve_for_create(
            object(),
            SimpleNamespace(tenant_id="tenant-b"),
            _payload(
                AIReportType.INVENTORY_GAP,
                (AIReportSourceType.DEMAND_LIST, 1, None),
            ),
        )

    assert error.value.status_code == 404


def test_explicit_version_conflict_is_409(source_service):
    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(),
            SimpleNamespace(tenant_id="tenant-a"),
            _payload(
                AIReportType.INVENTORY_GAP,
                (AIReportSourceType.DEMAND_LIST, 1, "999"),
            ),
        )

    assert error.value.code == "REPORT_SOURCE_VERSION_CONFLICT"
    assert error.value.status_code == 409


def test_legacy_and_explicit_same_type_disagreement_is_conflict(source_service):
    payload = _payload(
        AIReportType.DEMAND_CALCULATION,
        (AIReportSourceType.CALCULATION_RUN, 2, None),
    )
    payload.calculation_run_id = 1

    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(), SimpleNamespace(tenant_id="tenant-a"), payload
        )

    assert error.value.code == "REPORT_SOURCE_CONFLICT"


def test_explicit_demand_review_always_conflicts_with_legacy_review_run(source_service):
    payload = _payload(
        AIReportType.DEMAND_REVIEW,
        (AIReportSourceType.DEMAND_REVIEW, 1, None),
    )
    payload.review_run_id = 1

    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(), SimpleNamespace(tenant_id="tenant-a"), payload
        )

    assert error.value.code == "REPORT_SOURCE_CONFLICT"


def test_optional_sources_are_in_policy_order(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.INVENTORY_GAP,
            (AIReportSourceType.ALLOCATION_PLAN, 1, None),
            (AIReportSourceType.DEMAND_LIST, 1, None),
        ),
    )

    assert [record.source_type for record in result.records] == [
        AIReportSourceType.DEMAND_LIST,
        AIReportSourceType.ALLOCATION_PLAN,
    ]


def test_calculation_run_inherits_its_persisted_scenario(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.DEMAND_CALCULATION,
            (AIReportSourceType.CALCULATION_RUN, 1, None),
        ),
    )

    assert [record.source_type for record in result.records] == [
        AIReportSourceType.CALCULATION_RUN,
        AIReportSourceType.SCENARIO_VERSION,
    ]
    assert result.scenario_version_id == 2


def test_records_contain_only_canonical_persisted_evidence(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.ALLOCATION_PLAN,
            (AIReportSourceType.ALLOCATION_PLAN, 1, None),
        ),
    )

    record = result.records[0]
    assert record.source_id == "1"
    assert record.source_version == "7"
    assert record.source_digest
    assert record.evidence == {
        "id": 1,
        "version": 7,
        "status": "READY",
        "source_demand_list_id": 1,
        "source_demand_list_version": 5,
        "rule_id": 21,
        "inventory_fingerprint": "c" * 64,
        "lines": [],
    }
    assert "tenant_id" not in repr(record.evidence)


def test_demand_review_materializes_only_its_derived_list(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.DEMAND_REVIEW,
            (AIReportSourceType.DEMAND_REVIEW, 1, None),
        ),
    )

    assert [record.source_type for record in result.records] == [
        AIReportSourceType.DEMAND_REVIEW,
        AIReportSourceType.DEMAND_LIST,
    ]
    assert result.records[0].source_lineage_id == "demand-lineage"


def test_disallowed_source_is_conflict_before_read(source_service):
    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(),
            SimpleNamespace(tenant_id="tenant-a"),
            _payload(
                AIReportType.STOCKTAKE,
                (AIReportSourceType.DEMAND_LIST, 1, None),
                (AIReportSourceType.INVENTORY_STOCKTAKE, 1, None),
            ),
        )

    assert error.value.code == "REPORT_SOURCE_CONFLICT"


def test_identical_duplicate_ref_is_deduplicated(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.INVENTORY_GAP,
            (AIReportSourceType.DEMAND_LIST, 1, None),
            (AIReportSourceType.DEMAND_LIST, 1, None),
        ),
    )

    assert len(result.records) == 1


def test_duplicate_ref_versions_conflict(source_service):
    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(),
            SimpleNamespace(tenant_id="tenant-a"),
            _payload(
                AIReportType.INVENTORY_GAP,
                (AIReportSourceType.DEMAND_LIST, 1, "5"),
                (AIReportSourceType.DEMAND_LIST, 1, "6"),
            ),
        )

    assert error.value.code == "REPORT_SOURCE_CONFLICT"


def test_explicit_ai_session_populates_legacy_session_link(source_service):
    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.MANAGEMENT_DECISION,
            (AIReportSourceType.AI_SESSION, 1, None),
        ),
    )

    assert result.session_id == 1


def test_legacy_review_cannot_authorize_materialized_demand_list(source_service):
    payload = _payload(
        AIReportType.DEMAND_REVIEW,
        (AIReportSourceType.DEMAND_LIST, 1, None),
    )
    payload.review_run_id = 1

    with pytest.raises(BusinessValidationError) as error:
        source_service.resolve_for_create(
            object(), SimpleNamespace(tenant_id="tenant-a"), payload
        )

    assert error.value.code == "REPORT_SOURCE_CONFLICT"


def test_nested_persisted_evidence_omits_sensitive_keys(source_service):
    demand_list = source_service.demand_list_repository.rows[("tenant-a", 1)]
    demand_list.items = [
        SimpleNamespace(
            id=10,
            version=1,
            spare_part_id=20,
            spare_part_code_snapshot="SP-20",
            spare_part_name_snapshot="Part 20",
            spare_part_unit_snapshot="EA",
            criticality_level_snapshot="HIGH",
            original_quantity=2,
            final_quantity=3,
            decision_type="MANUAL_QUANTITY",
            decision_risk="HIGH",
            risk_rule_version="risk-1",
            decision_snapshot_json={
                "approved": True,
                "tenant_id": "tenant-a",
                "provider_token": "secret-token",
                "file_path": "C:/private/source.json",
            },
            inventory_snapshot_json={"fingerprint": "safe"},
        )
    ]

    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.INVENTORY_GAP,
            (AIReportSourceType.DEMAND_LIST, 1, None),
        ),
    )

    serialized = repr(result.records[0].evidence)
    assert "tenant_id" not in serialized
    assert "provider_token" not in serialized
    assert "file_path" not in serialized
    assert "approved" in serialized


def test_spare_part_risk_keeps_persisted_source_context_without_sensitive_keys(
    source_service,
):
    demand_list = source_service.demand_list_repository.rows[("tenant-a", 1)]
    demand_list.items = [
        SimpleNamespace(
            id=10,
            version=1,
            spare_part_id=20,
            spare_part_code_snapshot="SP-20",
            spare_part_name_snapshot="Part 20",
            spare_part_unit_snapshot="EA",
            criticality_level_snapshot="HIGH",
            source_calculation_group_id=30,
            source_group_child_id=31,
            source_calculation_id=32,
            source_calculation_run_id=33,
            source_result_id=34,
            reliability_model="WEIBULL",
            execution_mode="SIMULATION",
            original_quantity=2,
            final_quantity=3,
            decision_type="MANUAL_QUANTITY",
            decision_reason="shortage mitigation",
            decision_risk="HIGH",
            requires_admin_confirmation=True,
            confirmed_by_admin=True,
            risk_rule_version="risk-1",
            source_snapshot_json={
                "shortage_risk_level": "HIGH",
                "available_quantity": "2",
                "repair_pipeline_demand": "4",
                "selected_reliability_profile_id": 40,
                "selected_repair_profile_id": 41,
                "provider_token": "secret-token",
            },
            decision_snapshot_json={"approved": True},
            interval_snapshot_json={"selected_child_id": 31},
            parameter_snapshot_json={"weibull_shape": "1.8"},
            warning_snapshot_json=["INV-003"],
            inventory_snapshot_json={"usable_inventory": "2", "net_demand_gap": "1"},
        )
    ]

    result = source_service.resolve_for_create(
        object(),
        SimpleNamespace(tenant_id="tenant-a"),
        _payload(
            AIReportType.SPARE_PART_RISK,
            (AIReportSourceType.DEMAND_LIST, 1, None),
        ),
    )

    item = result.records[0].evidence["items"][0]
    assert item["source_snapshot_json"] == {
        "shortage_risk_level": "HIGH",
        "available_quantity": "2",
        "repair_pipeline_demand": "4",
        "selected_reliability_profile_id": 40,
        "selected_repair_profile_id": 41,
    }
    assert item["inventory_snapshot_json"] == {
        "usable_inventory": "2",
        "net_demand_gap": "1",
    }
    assert item["reliability_model"] == "WEIBULL"
    assert item["parameter_snapshot_json"] == {"weibull_shape": "1.8"}


def test_group_decisions_and_demand_list_items_have_stable_evidence_order(
    source_service,
):
    group = source_service.calculation_group_repository.rows[("tenant-a", 1)]
    demand_list = source_service.demand_list_repository.rows[("tenant-a", 1)]
    group.decisions = [
        SimpleNamespace(id=20, spare_part_id=200),
        SimpleNamespace(id=10, spare_part_id=100),
    ]
    demand_list.items = [
        SimpleNamespace(id=20, spare_part_id=200),
        SimpleNamespace(id=10, spare_part_id=100),
    ]
    payload = _payload(
        AIReportType.MANAGEMENT_DECISION,
        (AIReportSourceType.DEMAND_LIST, 1, None),
        (AIReportSourceType.CALCULATION_GROUP, 1, None),
    )

    first = source_service.resolve_for_create(
        object(), SimpleNamespace(tenant_id="tenant-a"), payload
    )
    group.decisions.reverse()
    demand_list.items.reverse()
    second = source_service.resolve_for_create(
        object(), SimpleNamespace(tenant_id="tenant-a"), payload
    )

    first_group, first_list = first.records
    second_group, second_list = second.records
    assert [row["id"] for row in first_group.evidence["decisions"]] == [10, 20]
    assert [row["id"] for row in first_list.evidence["items"]] == [10, 20]
    assert first_group.source_digest == second_group.source_digest
    assert first_list.source_digest == second_list.source_digest

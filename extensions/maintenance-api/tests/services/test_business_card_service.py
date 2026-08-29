from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.schemas.business_card import (
    MAX_CARD_PROJECTION_BYTES,
    BusinessCardBatch,
    CalculationCard,
    CalculationPayload,
    InventoryGapCard,
    InventoryGapPayload,
    MaintenanceCardTarget,
    ModelComparisonCard,
    ModelComparisonPayload,
    ReportCard,
    ReportPayload,
    ReviewFindingCard,
    ReviewFindingPayload,
    ScenarioDraftCard,
    ScenarioDraftPayload,
    canonical_card_json,
    canonicalize_cards,
    parse_business_card,
    projection_size_bytes,
    require_projection_size,
)
from app.services.business_card_service import BusinessCardService
from pydantic import ValidationError

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def target(object_type: str, object_id: int, version: int, path: str):
    return MaintenanceCardTarget(
        object_type=object_type,
        object_id=object_id,
        observed_version=version,
        navigation_path=path,
    )


def cards():
    return [
        ScenarioDraftCard(
            title="场景草稿待完善",
            summary="可继续补充场景信息。",
            status="PLANNED",
            target=target(
                "AI_SESSION_SNAPSHOT",
                7,
                3,
                "/platform/maintenance/scenarios/new?session_id=7",
            ),
            observed_at=NOW,
            payload=ScenarioDraftPayload(),
        ),
        CalculationCard(
            title="计算已创建",
            summary="可进入计算进度页查看结果。",
            status="PENDING",
            target=target(
                "CALCULATION_GROUP",
                35,
                1,
                "/platform/maintenance/calculations/35/progress",
            ),
            observed_at=NOW,
            payload=CalculationPayload(
                group_id=35,
                scenario_version_id=8,
                status="PENDING",
                primary_candidate_key="base",
                current_candidate_count=2,
                observed_version=1,
            ),
        ),
        ModelComparisonCard(
            title="模型比较可用",
            summary="已有多个可比较计算结果。",
            status="COMPLETED",
            target=target(
                "CALCULATION_GROUP",
                35,
                1,
                "/platform/maintenance/calculations/35/comparison",
            ),
            observed_at=NOW,
            payload=ModelComparisonPayload(
                group_id=35,
                scenario_version_id=8,
                comparable_candidate_count=2,
                primary_candidate_key="base",
                observed_version=1,
            ),
        ),
        InventoryGapCard(
            title="存在库存缺口",
            summary="部分需求尚未满足。",
            status="PREVIEWED",
            target=target(
                "ALLOCATION_PLAN",
                41,
                2,
                "/platform/maintenance/inventory-gap/allocations/41",
            ),
            observed_at=NOW,
            payload=InventoryGapPayload(
                gap_item_count=2,
                total_gap_quantity="14.5",
                risk_item_count=1,
                source_demand_list_id=11,
                plan_status="PREVIEWED",
                observed_version=2,
            ),
        ),
        ReviewFindingCard(
            title="复核发现待处理",
            summary="存在待决策复核发现。",
            status="PENDING",
            target=target(
                "DEMAND_REVIEW_FINDING",
                51,
                4,
                "/platform/maintenance/reviews/50",
            ),
            observed_at=NOW,
            payload=ReviewFindingPayload(
                finding_id=51,
                review_id=50,
                severity="HIGH",
                blocking=True,
                remaining_pending_count=2,
                observed_version=4,
            ),
        ),
        ReportCard(
            title="报告待复核",
            summary="报告已生成，可进入报告中心查看。",
            status="READY_FOR_REVIEW",
            target=target(
                "AI_REPORT_JOB",
                61,
                3,
                "/platform/maintenance/reports?report_id=61",
            ),
            observed_at=NOW,
            payload=ReportPayload(
                report_id=61,
                report_code="RPT-061",
                report_type="MANAGEMENT_DECISION",
                job_status="READY_FOR_REVIEW",
                version_id=62,
                version_number=3,
                version_status="REVIEWED",
            ),
        ),
    ]


def test_all_six_v1_types_parse():
    for card in cards():
        parsed = parse_business_card(card.model_dump(mode="json"))
        assert parsed.type == card.type
        assert parsed.schema_version == "1.0"


def test_unknown_type_rejected():
    raw = cards()[1].model_dump(mode="json")
    raw["type"] = "EXECUTE_SQL"
    with pytest.raises(ValidationError):
        parse_business_card(raw)


def test_unknown_schema_rejected():
    raw = cards()[1].model_dump(mode="json")
    raw["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        parse_business_card(raw)


@pytest.mark.parametrize("path", [
    "https://example.com/platform/maintenance/calculations/35/progress",
    "//example.com/platform/maintenance/calculations/35/progress",
    "/platform/settings",
    "/platform/maintenance/reports?report_id=35",
])
def test_calculation_rejects_non_allowlisted_navigation(path):
    raw = cards()[1].model_dump(mode="json")
    raw["target"]["navigation_path"] = path
    with pytest.raises(ValidationError):
        parse_business_card(raw)


@pytest.mark.parametrize("forbidden", [
    "confirmation_token",
    "execute_url",
    "tenant_id",
    "internal_jwt",
    "file_path",
    "provider_secret",
    "structured_content_json",
])
def test_payload_rejects_forbidden_or_unknown_fields(forbidden):
    raw = cards()[1].model_dump(mode="json")
    raw["payload"][forbidden] = "secret-or-unbounded"
    with pytest.raises(ValidationError):
        parse_business_card(raw)


def test_text_bounds_are_enforced():
    raw = cards()[1].model_dump(mode="json")
    raw["title"] = "x" * 201
    with pytest.raises(ValidationError):
        parse_business_card(raw)
    raw = cards()[1].model_dump(mode="json")
    raw["summary"] = "x" * 1001
    with pytest.raises(ValidationError):
        parse_business_card(raw)
    raw = cards()[1].model_dump(mode="json")
    raw["status"] = "x" * 65
    with pytest.raises(ValidationError):
        parse_business_card(raw)


def test_batch_caps_three_and_one_per_type():
    valid = cards()
    BusinessCardBatch(cards=valid[:3])
    with pytest.raises(ValidationError):
        BusinessCardBatch(cards=valid[:4])

    exact_duplicate = BusinessCardBatch(cards=[valid[1], valid[1]])
    assert len(exact_duplicate.cards) == 1

    second_calculation = valid[1].model_copy(deep=True)
    second_calculation.target.object_id = 36
    second_calculation.target.navigation_path = (
        "/platform/maintenance/calculations/36/progress"
    )
    second_calculation.payload.group_id = 36
    with pytest.raises(ValidationError):
        BusinessCardBatch(cards=[valid[1], second_calculation])


def test_projection_ceiling_is_exactly_32kib_and_enforced():
    assert MAX_CARD_PROJECTION_BYTES == 32 * 1024
    chosen = cards()[:3]
    assert projection_size_bytes(chosen) < MAX_CARD_PROJECTION_BYTES

    with pytest.raises(ValueError, match="projection exceeds"):
        require_projection_size(chosen, max_bytes=128)


def test_canonicalization_is_stable_and_priority_sorted():
    chosen = [cards()[5], cards()[1], cards()[4]]
    a = canonicalize_cards(chosen)
    b = canonicalize_cards(list(reversed(chosen)))
    assert [item.type for item in a] == ["REVIEW_FINDING", "CALCULATION", "REPORT"]
    assert canonical_card_json(a) == canonical_card_json(b)


def test_observed_at_requires_timezone():
    raw = cards()[1].model_dump(mode="json")
    raw["observed_at"] = "2026-08-29T10:00:00"
    with pytest.raises(ValidationError):
        parse_business_card(raw)


# 05-5A2 authoritative builder tests


def ns(**values):
    return SimpleNamespace(**values)


class AIRepo:
    def __init__(self, session_row=None, snapshot=None):
        self.session_row = session_row
        self.snapshot = snapshot
        self.last_tenant = None

    def get(self, session, tenant_id, session_id):
        self.last_tenant = tenant_id
        return self.session_row if self.session_row and self.session_row.id == session_id else None

    def latest_snapshot(self, session, tenant_id, session_id):
        self.last_tenant = tenant_id
        return self.snapshot


class CalcRepo:
    def __init__(self, group=None):
        self.group = group
        self.last_tenant = None

    def get(self, session, tenant_id, group_id):
        self.last_tenant = tenant_id
        return self.group if self.group and self.group.id == group_id else None


class AllocationRepo:
    def __init__(self, plan=None, lines=None):
        self.plan = plan
        self.lines = lines or []
        self.last_tenant = None

    def get_plan(self, session, tenant_id, plan_id):
        self.last_tenant = tenant_id
        return self.plan if self.plan and self.plan.id == plan_id else None

    def list_plan_lines(self, session, tenant_id, plan_id):
        self.last_tenant = tenant_id
        return list(self.lines)


class ReviewRepo:
    def __init__(self, review=None, findings=None):
        self.review = review
        self.findings = findings or []
        self.last_tenant = None

    def get(self, session, tenant_id, review_id):
        self.last_tenant = tenant_id
        return self.review if self.review and self.review.id == review_id else None

    def list_findings(self, session, tenant_id, review_id):
        self.last_tenant = tenant_id
        return list(self.findings)


class ReportRepo:
    def __init__(self, job=None, version=None):
        self.job = job
        self.version = version
        self.last_tenant = None

    def get_job(self, session, tenant_id, report_job_id):
        self.last_tenant = tenant_id
        return self.job if self.job and self.job.id == report_job_id else None

    def latest_version(self, session, tenant_id, report_job_id):
        self.last_tenant = tenant_id
        return self.version


def service(**overrides):
    return BusinessCardService(
        ai_session_repository=overrides.get("ai", AIRepo()),
        calculation_group_repository=overrides.get("calc", CalcRepo()),
        allocation_repository=overrides.get("allocation", AllocationRepo()),
        demand_review_repository=overrides.get("review", ReviewRepo()),
        ai_report_repository=overrides.get("report", ReportRepo()),
    )


def test_scenario_builder_uses_latest_authoritative_snapshot_and_tenant(actor_viewer):
    actor = actor_viewer
    ai = AIRepo(
        ns(
            id=7,
            title="Engine fleet",
            status="PLANNED",
            active_scenario_version_id=None,
            updated_at=NOW,
        ),
        ns(
            session_id=7,
            snapshot_version=3,
            scenario_draft_json={"mission": "x"},
            updated_at=NOW,
        ),
    )
    card = service(ai=ai).build_scenario_draft(object(), actor, 7)
    assert ai.last_tenant == "tenant-a"
    assert card.type == "SCENARIO_DRAFT"
    assert card.target.object_id == 7
    assert card.target.observed_version == 3
    assert card.target.navigation_path == "/platform/maintenance/scenarios/new?session_id=7"


def test_scenario_builder_suppresses_materialized_or_empty_draft(actor_viewer):
    actor = actor_viewer
    materialized = AIRepo(
        ns(
            id=7,
            title="x",
            status="PLANNED",
            active_scenario_version_id=99,
            updated_at=NOW,
        ),
        ns(
            session_id=7,
            snapshot_version=3,
            scenario_draft_json={"x": 1},
            updated_at=NOW,
        ),
    )
    assert service(ai=materialized).build_scenario_draft(object(), actor, 7) is None
    empty = AIRepo(
        ns(
            id=7,
            title="x",
            status="PLANNED",
            active_scenario_version_id=None,
            updated_at=NOW,
        ),
        ns(
            session_id=7,
            snapshot_version=3,
            scenario_draft_json={},
            updated_at=NOW,
        ),
    )
    assert service(ai=empty).build_scenario_draft(object(), actor, 7) is None


def test_cross_tenant_or_missing_object_is_non_enumerating_not_found(actor_viewer):
    with pytest.raises(NotFoundError):
        service(calc=CalcRepo()).build_calculation(object(), actor_viewer, 35)


def test_calculation_builder_uses_group_authority(actor_viewer):
    group = ns(
        id=35,
        scenario_version_id=8,
        status="COMPLETED",
        primary_candidate_key="base",
        current_children=[ns(candidate_key="base"), ns(candidate_key="alt")],
        version=4,
        updated_at=NOW,
    )
    calc = CalcRepo(group)
    card = service(calc=calc).build_calculation(object(), actor_viewer, 35)
    assert calc.last_tenant == "tenant-a"
    assert card.payload.group_id == 35
    assert card.payload.current_candidate_count == 2
    assert card.payload.observed_version == 4
    assert card.target.navigation_path == "/platform/maintenance/calculations/35/progress"


def test_model_comparison_requires_two_meaningful_current_children(actor_viewer):
    def meaningful(status="SUCCEEDED"):
        return ns(calculation=ns(status=status, result_summary_json={"items": 2}))

    group = ns(
        id=35,
        scenario_version_id=8,
        status="COMPLETED",
        primary_candidate_key="base",
        current_children=[meaningful(), meaningful("PARTIAL_SUCCESS")],
        version=4,
        updated_at=NOW,
    )
    card = service(calc=CalcRepo(group)).build_model_comparison(object(), actor_viewer, 35)
    assert card.payload.comparable_candidate_count == 2
    assert card.target.navigation_path == "/platform/maintenance/calculations/35/comparison"

    group.current_children = [
        meaningful(),
        ns(calculation=ns(status="RUNNING", result_summary_json=None)),
    ]
    assert service(calc=CalcRepo(group)).build_model_comparison(object(), actor_viewer, 35) is None


def test_inventory_gap_builder_aggregates_authoritative_lines(actor_viewer):
    plan = ns(
        id=41,
        status="PREVIEWED",
        source_demand_list_id=11,
        version=2,
        updated_at=NOW,
    )
    lines = [
        ns(gap_quantity=Decimal("10"), risks_json=[], updated_at=NOW),
        ns(gap_quantity=Decimal("4.5"), risks_json=[{"code": "R1"}], updated_at=NOW),
        ns(gap_quantity=Decimal("0"), risks_json=[], updated_at=NOW),
    ]
    card = service(allocation=AllocationRepo(plan, lines)).build_inventory_gap(
        object(), actor_viewer, 41
    )
    assert card.payload.gap_item_count == 2
    assert card.payload.total_gap_quantity == Decimal("14.5")
    assert card.payload.risk_item_count == 1
    assert card.target.navigation_path == "/platform/maintenance/inventory-gap/allocations/41"


def test_inventory_gap_draft_or_no_gap_is_not_applicable(actor_viewer):
    plan = ns(
        id=41,
        status="DRAFT",
        source_demand_list_id=11,
        version=1,
        updated_at=NOW,
    )
    lines = [ns(gap_quantity=Decimal("1"), risks_json=[], updated_at=NOW)]
    assert service(allocation=AllocationRepo(plan, lines)).build_inventory_gap(
        object(), actor_viewer, 41
    ) is None
    plan.status = "PREVIEWED"
    lines = [ns(gap_quantity=Decimal("0"), risks_json=[], updated_at=NOW)]
    assert service(allocation=AllocationRepo(plan, lines)).build_inventory_gap(
        object(), actor_viewer, 41
    ) is None


def test_review_builder_selects_one_finding_by_approved_priority(actor_viewer):
    review = ns(id=50, pending_finding_count=3, updated_at=NOW)
    findings = [
        ns(
            id=1,
            review_id=50,
            decision_status="ACCEPTED",
            blocking=True,
            severity="CRITICAL",
            requires_admin_acceptance=True,
            version=2,
            updated_at=NOW,
        ),
        ns(
            id=2,
            review_id=50,
            decision_status="PENDING",
            blocking=False,
            severity="CRITICAL",
            requires_admin_acceptance=False,
            version=1,
            updated_at=NOW,
        ),
        ns(
            id=3,
            review_id=50,
            decision_status="PENDING",
            blocking=True,
            severity="HIGH",
            requires_admin_acceptance=True,
            version=4,
            updated_at=NOW,
        ),
    ]
    card = service(review=ReviewRepo(review, findings)).build_review_finding(
        object(), actor_viewer, 50
    )
    assert card.target.object_id == 3
    assert card.payload.review_id == 50
    assert card.payload.remaining_pending_count == 3
    assert card.target.navigation_path == "/platform/maintenance/reviews/50"


def test_report_builder_uses_latest_version_and_meaningful_job_states(actor_viewer):
    job = ns(
        id=61,
        report_code="AIR-61",
        report_type="MANAGEMENT_DECISION",
        status="READY_FOR_REVIEW",
        title="Management decision report",
        updated_at=NOW,
    )
    version = ns(id=62, version_number=3, status="REVIEWED", updated_at=NOW)
    card = service(report=ReportRepo(job, version)).build_report(object(), actor_viewer, 61)
    assert card.title == "Management decision report"
    assert card.payload.version_id == 62
    assert card.target.observed_version == 3
    assert card.target.navigation_path == "/platform/maintenance/reports?report_id=61"

    job.status = "GENERATING_SECTIONS"
    assert service(report=ReportRepo(job, version)).build_report(object(), actor_viewer, 61) is None


def test_build_cards_applies_stable_priority_dedup_and_limit(actor_viewer):
    ai = AIRepo(
        ns(
            id=7,
            title="x",
            status="PLANNED",
            active_scenario_version_id=None,
            updated_at=NOW,
        ),
        ns(
            session_id=7,
            snapshot_version=1,
            scenario_draft_json={"x": 1},
            updated_at=NOW,
        ),
    )
    group = ns(
        id=35,
        scenario_version_id=8,
        status="COMPLETED",
        primary_candidate_key="base",
        current_children=[],
        version=1,
        updated_at=NOW,
    )
    plan = ns(
        id=41,
        status="PREVIEWED",
        source_demand_list_id=11,
        version=1,
        updated_at=NOW,
    )
    allocation = AllocationRepo(
        plan,
        [ns(gap_quantity=Decimal("1"), risks_json=[], updated_at=NOW)],
    )
    result = service(ai=ai, calc=CalcRepo(group), allocation=allocation).build_cards(
        object(),
        actor_viewer,
        [
            ("CALCULATION", 35),
            ("SCENARIO_DRAFT", 7),
            ("INVENTORY_GAP", 41),
            ("CALCULATION", 35),
        ],
    )
    assert [card.type for card in result] == [
        "INVENTORY_GAP",
        "SCENARIO_DRAFT",
        "CALCULATION",
    ]

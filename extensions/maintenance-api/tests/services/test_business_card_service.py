from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.business_card import (
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
    MAX_CARD_PROJECTION_BYTES,
    projection_size_bytes,
    require_projection_size,
    canonical_card_json,
    canonicalize_cards,
    parse_business_card,
)

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

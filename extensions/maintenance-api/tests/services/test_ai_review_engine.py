from decimal import Decimal

from app.services.ai_review_engine import AIReviewEngine, ReviewContext


def test_inventory_shortage_rule_is_deterministic() -> None:
    findings = AIReviewEngine().run(
        ReviewContext(
            scenario_snapshot={"scenario_version_id": 1, "stages": [{"code": "S1"}]},
            calculation_items=[
                {
                    "spare_part_id": 10,
                    "recommended_spare_quantity": Decimal("8"),
                    "usable_inventory": Decimal("3"),
                    "net_demand_gap": Decimal("5"),
                    "inventory_coverage_rate": Decimal("0.375"),
                    "selected_reliability_profile_id": 2,
                    "warning_codes": [],
                }
            ],
            evidence_items=[],
        )
    )
    finding = next(item for item in findings if item.rule_code == "INV-001")
    assert finding.severity == "ERROR"
    assert finding.blocking_level == "BLOCK_REPORT_FINALIZATION"
    assert finding.observed_value == "3"

import time

import pytest
from app.services.ai_review_engine import AIReviewEngine, ReviewContext


@pytest.mark.performance
def test_review_1000_items_under_five_seconds() -> None:
    context = ReviewContext(
        scenario_snapshot={"scenario_version_id": 1, "stages": [{"code": "S1"}]},
        calculation_items=[
            {
                "spare_part_id": index,
                "recommended_spare_quantity": 8,
                "usable_inventory": 3,
                "net_demand_gap": 5,
                "inventory_coverage_rate": 0.375,
                "selected_reliability_profile_id": 2,
            }
            for index in range(1000)
        ],
        evidence_items=[],
    )
    started = time.perf_counter()
    findings = AIReviewEngine().run(context)
    elapsed = time.perf_counter() - started
    assert len(findings) >= 1000
    assert elapsed < 5.0

import pytest
from app.services.ai_review_engine import (
    ReviewContext,
    ReviewFindingDraft,
)
from app.services.ai_review_service import (
    AIReviewService,
)


class FakeReviewEngine:
    def run(
        self,
        context: ReviewContext,
    ) -> list[ReviewFindingDraft]:
        del context
        return [
            ReviewFindingDraft(
                rule_code="INV-001",
                rule_version="1.0",
                category="INVENTORY",
                severity="ERROR",
                blocking_level=(
                    "BLOCK_REPORT_FINALIZATION"
                ),
                affected_entity_type=(
                    "SPARE_PART"
                ),
                affected_entity_id=10,
                affected_spare_part_id=None,
                finding_title="库存不足",
                deterministic_message=(
                    "可用库存低于需求"
                ),
                observed_value="3",
                expected_range=">=8",
                evidence_references=[],
                calculation_reference="run:1",
                suggested_actions=["补充库存"],
            )
        ]


class FakeExplanation:
    def model_dump(self, mode="json"):
        del mode
        return {
            "summary": "风险很低",
            "severity": "INFO",
            "blocking_level": "NONE",
        }


class FakeExplainer:
    async def explain(self, finding):
        del finding
        return FakeExplanation()


@pytest.mark.asyncio
async def test_review_service_preserves_rule_severity(
    session,
    actor_contributor,
) -> None:
    service = AIReviewService(
        engine=FakeReviewEngine(),
        explainer=FakeExplainer(),
        context_loader=(
            lambda _db, _actor, _run_id: (
                ReviewContext(
                    scenario_snapshot={},
                    calculation_items=[],
                    evidence_items=[],
                )
            )
        ),
    )
    review = (
        await service
        .create_demand_list_review(
            session,
            actor_contributor,
            calculation_run_id=None,
            context=ReviewContext(
                scenario_snapshot={},
                calculation_items=[],
                evidence_items=[],
            ),
        )
    )
    finding = next(
        row
        for row in review.findings
        if row.rule_code == "INV-001"
    )
    assert finding.severity.value == "ERROR"
    assert (
        finding.blocking_level.value
        == "BLOCK_REPORT_FINALIZATION"
    )

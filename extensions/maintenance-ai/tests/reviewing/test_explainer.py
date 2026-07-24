import pytest

from maintenance_ai.enums import ReviewBlockingLevel, ReviewSeverity
from maintenance_ai.providers import DeterministicTestProvider
from maintenance_ai.reviewing import ReviewExplainer, ReviewFindingInput


@pytest.mark.asyncio
async def test_explainer_cannot_change_deterministic_severity():
    finding = ReviewFindingInput(
        rule_code="CFG-001",
        title="不适配",
        deterministic_message="器材不属于构型",
        severity=ReviewSeverity.ERROR,
        blocking_level=ReviewBlockingLevel.BLOCK_FORMAL_CALCULATION,
        evidence_ids=("E1",),
    )
    provider = DeterministicTestProvider(
        fixtures={
            "review_explanation": {
                "summary": "说明",
                "cause": "原因",
                "impact": "影响",
                "suggested_actions": ["修正构型"],
                "evidence_ids": ["E1"],
                "severity": "INFO",
            }
        }
    )
    result = await ReviewExplainer(provider).explain(finding)
    assert result.severity is ReviewSeverity.ERROR
    assert result.blocking_level is ReviewBlockingLevel.BLOCK_FORMAL_CALCULATION

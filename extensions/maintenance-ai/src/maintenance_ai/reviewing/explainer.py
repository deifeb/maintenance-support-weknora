from maintenance_ai.providers import LLMProvider, StructuredCompletionRequest, TextMessage
from maintenance_ai.reviewing.models import (
    ReviewExplanation,
    ReviewExplanationPayload,
    ReviewFindingInput,
)


class ReviewExplainer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def explain(self, finding: ReviewFindingInput) -> ReviewExplanation:
        request = StructuredCompletionRequest(
            messages=(TextMessage(role="user", content=finding.model_dump_json()),),
            function_name="review_explanation",
            prompt_name="review-explainer",
            prompt_version="1.0",
            schema_version="1.0",
        )
        result = await self.provider.complete_structured(request, ReviewExplanationPayload)
        payload = ReviewExplanationPayload.model_validate(result.data)
        invalid = set(payload.evidence_ids) - set(finding.evidence_ids)
        if invalid:
            payload = payload.model_copy(
                update={
                    "evidence_ids": [
                        eid for eid in payload.evidence_ids if eid in finding.evidence_ids
                    ]
                }
            )
        return ReviewExplanation(
            rule_code=finding.rule_code,
            summary=payload.summary,
            cause=payload.cause,
            impact=payload.impact,
            suggested_actions=tuple(payload.suggested_actions),
            evidence_ids=tuple(payload.evidence_ids),
            severity=finding.severity,
            blocking_level=finding.blocking_level,
        )

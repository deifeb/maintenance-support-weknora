import pytest
from pydantic import BaseModel

from maintenance_ai.enums import ExecutionMode, ProviderHealthStatus
from maintenance_ai.providers import (
    DeterministicTestProvider,
    RuleFallbackProvider,
    StructuredCompletionRequest,
    TextCompletionRequest,
    TextMessage,
)


class Answer(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_deterministic_provider_returns_fixture_and_simulates_failures():
    provider = DeterministicTestProvider(fixtures={"scenario_parsing": {"value": "ok"}})
    req = StructuredCompletionRequest(
        messages=(TextMessage(role="user", content="x"),),
        function_name="scenario_parsing",
        prompt_name="p",
        prompt_version="1",
        schema_version="1",
    )
    result = await provider.complete_structured(req, Answer)
    assert result.data["value"] == "ok"
    assert (await provider.health_check()).status is ProviderHealthStatus.HEALTHY
    provider.failures["scenario_parsing"] = "timeout"
    with pytest.raises(Exception):
        await provider.complete_structured(req, Answer)


@pytest.mark.asyncio
async def test_rule_fallback_is_explicitly_non_llm():
    provider = RuleFallbackProvider()
    req = TextCompletionRequest(
        messages=(TextMessage(role="user", content="解释结果"),),
        function_name="review_explanation",
        prompt_name="p",
        prompt_version="1",
    )
    result = await provider.complete_text(req)
    assert result.execution_mode is ExecutionMode.RULE_FALLBACK
    assert result.llm_generated is False
    assert result.fallback_reason

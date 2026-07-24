import os

import pytest
from maintenance_ai.enums import ProviderHealthStatus
from maintenance_ai.providers import OpenAICompatibleProvider, TextCompletionRequest, TextMessage


@pytest.mark.external
@pytest.mark.openai_compatible
@pytest.mark.asyncio
async def test_configured_openai_compatible_smoke() -> None:
    enabled = os.getenv("AI_REMOTE_ENABLED", "false").lower() == "true"
    base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL")
    api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY")
    model = os.getenv("OPENAI_COMPATIBLE_MODEL")
    if not (enabled and base_url and api_key and model):
        pytest.skip("OpenAI-compatible provider is not fully configured")

    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=30,
    )
    health = await provider.health_check()
    if health.status is not ProviderHealthStatus.HEALTHY:
        pytest.fail(f"remote provider unhealthy: {health.status.value}")
    result = await provider.complete_text(
        TextCompletionRequest(
            messages=(TextMessage(role="user", content="Reply with OK."),),
            function_name="general_qa",
            prompt_name="general-qa",
            prompt_version="1.0",
            max_output_tokens=16,
            temperature=0,
        )
    )
    assert result.text.strip()
    assert api_key not in repr(provider)

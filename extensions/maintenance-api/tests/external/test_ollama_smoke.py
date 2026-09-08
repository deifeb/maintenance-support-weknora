import os

import pytest
from maintenance_ai.enums import ProviderHealthStatus
from maintenance_ai.providers import OllamaProvider, StructuredCompletionRequest, TextMessage
from maintenance_ai.scenarios import ScenarioDraft


@pytest.mark.external
@pytest.mark.ollama
@pytest.mark.asyncio
async def test_real_ollama_structured_scenario_smoke() -> None:
    provider = OllamaProvider(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
        timeout=30,
    )
    health = await provider.health_check()
    if health.status is ProviderHealthStatus.UNAVAILABLE:
        pytest.skip(f"Ollama service unreachable: {health.detail}")
    if health.status is ProviderHealthStatus.CONFIGURED_BUT_MODEL_MISSING:
        pytest.fail("CONFIGURED_BUT_MODEL_MISSING: configured Ollama model is not installed")

    result = await provider.complete_structured(
        StructuredCompletionRequest(
            messages=(
                TextMessage(
                    role="user",
                    content=(
                        "Return a valid ScenarioDraft JSON for 10 units, 30 days, "
                        "95 percent service level, equipment EQ-001, configuration V1."
                    ),
                ),
            ),
            function_name="scenario_parsing",
            prompt_name="scenario-parser",
            prompt_version="1.0",
            schema_version="1.0",
            temperature=0,
        ),
        ScenarioDraft,
    )
    assert ScenarioDraft.model_validate(result.data).equipment_quantity is not None

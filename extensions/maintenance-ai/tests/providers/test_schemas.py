from maintenance_ai.enums import ExecutionMode, ProviderKind, SensitivityLevel
from maintenance_ai.providers import StructuredCompletionRequest, TextMessage


def test_structured_request_preserves_security_metadata():
    request = StructuredCompletionRequest(
        messages=(TextMessage(role="user", content="生成场景"),),
        function_name="scenario_parsing",
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        prompt_name="scenario-parser",
        prompt_version="1.0",
        schema_version="1.0",
    )
    assert request.sensitivity is SensitivityLevel.CONFIDENTIAL
    assert request.temperature == 0.0
    assert ProviderKind.OLLAMA.value == "OLLAMA"
    assert ExecutionMode.RULE_FALLBACK.value == "RULE_FALLBACK"

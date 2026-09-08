from maintenance_ai.providers import LLMProvider


def test_provider_protocol_is_runtime_checkable():
    assert getattr(LLMProvider, "_is_runtime_protocol", False) is True

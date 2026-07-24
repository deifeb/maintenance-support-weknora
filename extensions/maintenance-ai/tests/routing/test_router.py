import pytest

from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel
from maintenance_ai.exceptions import SensitiveRemoteCallBlockedError
from maintenance_ai.routing import ModelDefinition, ModelRegistry, ModelRouter, RouteDefinition


def build_router():
    registry = ModelRegistry(
        models={
            "local": ModelDefinition(
                name="local",
                provider=ProviderKind.OLLAMA,
                model="qwen",
                capabilities={ModelCapability.STRUCTURED_OUTPUT},
                sensitivity_allowed=set(SensitivityLevel),
            ),
            "remote": ModelDefinition(
                name="remote",
                provider=ProviderKind.OPENAI_COMPATIBLE,
                model="r",
                capabilities={ModelCapability.STRUCTURED_OUTPUT},
                sensitivity_allowed={SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL},
            ),
        },
        routes={
            "report_generation": RouteDefinition(
                primary="remote", fallbacks=("local", "rule-fallback")
            )
        },
    )
    return ModelRouter(registry)


def test_confidential_never_routes_remote():
    decision = build_router().route(
        "report_generation", SensitivityLevel.CONFIDENTIAL, {ModelCapability.STRUCTURED_OUTPUT}
    )
    assert decision.selected == "local"
    assert "remote" in decision.filtered


def test_explicit_remote_override_is_blocked_for_confidential():
    with pytest.raises(SensitiveRemoteCallBlockedError):
        build_router().route(
            "report_generation",
            SensitivityLevel.CONFIDENTIAL,
            {ModelCapability.STRUCTURED_OUTPUT},
            override="remote",
        )


def test_registry_accepts_config_aliases_and_route_capabilities():
    registry = ModelRegistry.from_dicts(
        {
            "models": {
                "local": {
                    "provider": "OLLAMA",
                    "model": "qwen",
                    "allowed_sensitivity": ["PUBLIC", "INTERNAL"],
                    "capabilities": ["STRUCTURED_OUTPUT"],
                    "context_window": 32768,
                }
            }
        },
        {
            "routes": {
                "scenario_parsing": {
                    "primary": "local",
                    "fallbacks": ["RULE_FALLBACK"],
                    "required_capabilities": ["STRUCTURED_OUTPUT"],
                }
            }
        },
    )
    assert registry.models["local"].context_window == 32768
    assert SensitivityLevel.INTERNAL in registry.models["local"].sensitivity_allowed
    assert (
        ModelCapability.STRUCTURED_OUTPUT
        in registry.routes["scenario_parsing"].required_capabilities
    )


def test_router_keeps_provider_mapping_for_runtime():
    registry = ModelRegistry(models={}, routes={})
    provider = object()
    router = ModelRouter(registry, providers={"local": provider}, rule_fallback=provider)
    assert router.providers["local"] is provider
    assert router.rule_fallback is provider

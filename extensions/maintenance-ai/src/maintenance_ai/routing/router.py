from typing import Any

from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel
from maintenance_ai.exceptions import ProviderUnavailableError, SensitiveRemoteCallBlockedError
from maintenance_ai.routing.models import RouteDecision
from maintenance_ai.routing.registry import ModelRegistry


class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        providers: dict[str, Any] | None = None,
        rule_fallback: Any | None = None,
    ) -> None:
        self.registry = registry
        self.providers = providers or {}
        self.rule_fallback = rule_fallback

    def route(
        self,
        function_name: str,
        sensitivity: SensitivityLevel,
        required_capabilities: set[ModelCapability] | None = None,
        *,
        override: str | None = None,
    ) -> RouteDecision:
        route = self.registry.routes.get(function_name)
        if route is None:
            raise ProviderUnavailableError(f"no model route for {function_name}")
        capabilities = required_capabilities or route.required_capabilities
        names = (override,) if override else (route.primary, *route.fallbacks)
        filtered: list[str] = []
        for name in names:
            if name.upper().replace("-", "_") == "RULE_FALLBACK":
                return RouteDecision(
                    function_name=function_name,
                    selected="RULE_FALLBACK",
                    candidates=tuple(names),
                    filtered=tuple(filtered),
                    reason="deterministic fallback",
                )
            definition = self.registry.models.get(name)
            if definition is None:
                filtered.append(name)
                continue
            if sensitivity not in definition.sensitivity_allowed:
                filtered.append(name)
                if override and definition.provider is ProviderKind.OPENAI_COMPATIBLE:
                    raise SensitiveRemoteCallBlockedError(
                        f"{sensitivity.value} data cannot be sent to remote model {name}"
                    )
                continue
            if not definition.enabled:
                filtered.append(name)
                continue
            if not capabilities.issubset(definition.capabilities):
                filtered.append(name)
                continue
            return RouteDecision(
                function_name=function_name,
                selected=name,
                candidates=tuple(names),
                filtered=tuple(filtered),
                reason="first allowed capable model",
            )
        if override:
            raise ProviderUnavailableError(f"model override {override} is unavailable or incapable")
        raise ProviderUnavailableError(f"no eligible model for {function_name}")

    def provider_for(self, decision: RouteDecision):
        if decision.selected == "RULE_FALLBACK":
            if self.rule_fallback is None:
                raise ProviderUnavailableError("rule fallback provider is unavailable")
            return self.rule_fallback
        provider = self.providers.get(decision.selected)
        if provider is None:
            raise ProviderUnavailableError(f"provider for {decision.selected} is unavailable")
        return provider

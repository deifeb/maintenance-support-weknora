from fastapi import APIRouter
from maintenance_ai.enums import ModelCapability, SensitivityLevel
from maintenance_ai.exceptions import (
    ProviderUnavailableError,
    SensitiveRemoteCallBlockedError,
)
from maintenance_ai.routing import ModelRegistry, ModelRouter

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError
from app.core.responses import success_response
from app.services.ai_model_runtime import AIModelRuntime

router = APIRouter()


def _load_registry() -> ModelRegistry:
    settings = get_settings()
    try:
        return ModelRegistry.from_yaml(
            settings.ai_models_config_path,
            settings.ai_routes_config_path,
        )
    except Exception as exc:
        raise BusinessValidationError(
            "AI model configuration is invalid",
            code="AI_MODEL_CONFIG_INVALID",
            details={"reason": str(exc)},
        ) from exc


@router.get("/providers/health")
async def provider_health():
    runtime = AIModelRuntime.from_settings()
    runtime_results = await runtime.health()
    registry = runtime.router.registry
    results = []
    for name, definition in registry.models.items():
        health = runtime_results.get(name)
        if health is None:
            health = {
                "provider": definition.provider.value,
                "model": definition.model,
                "status": "DISABLED" if not definition.enabled else "UNAVAILABLE",
                "detail": "provider is not enabled or credentials are incomplete",
                "latency_ms": 0,
            }
        results.append({"name": name, **health})
    results.append({"name": "RULE_FALLBACK", **runtime_results["RULE_FALLBACK"]})
    return success_response(results)


@router.get("/model-routes")
def model_routes():
    registry = _load_registry()
    return success_response(
        {
            name: {
                "primary": route.primary,
                "fallbacks": list(route.fallbacks),
                "required_capabilities": sorted(
                    capability.value for capability in route.required_capabilities
                ),
            }
            for name, route in registry.routes.items()
        }
    )


@router.post("/model-routes/preview")
def model_route_preview(payload: dict):
    registry = _load_registry()
    function_name = str(payload.get("function_name", "scenario_parsing"))
    sensitivity = SensitivityLevel(str(payload.get("sensitivity_level", "INTERNAL")))
    override = payload.get("model_override")
    required = {ModelCapability(str(value)) for value in payload.get("required_capabilities", [])}
    try:
        decision = ModelRouter(registry).route(
            function_name,
            sensitivity,
            required or None,
            override=str(override) if override else None,
        )
    except SensitiveRemoteCallBlockedError as exc:
        raise BusinessValidationError(
            "sensitive data cannot be sent to the requested remote model",
            code="SENSITIVE_REMOTE_CALL_BLOCKED",
            details={"model_override": override},
        ) from exc
    except ProviderUnavailableError as exc:
        raise BusinessValidationError(
            "no eligible model is available for this request",
            code="PROVIDER_UNAVAILABLE",
            details={"reason": str(exc)},
        ) from exc

    selected_definition = registry.models.get(decision.selected)
    return success_response(
        {
            "function_name": function_name,
            "sensitivity_level": sensitivity.value,
            "selected": decision.selected,
            "provider": (
                "RULE_FALLBACK"
                if selected_definition is None
                else selected_definition.provider.value
            ),
            "candidates": list(decision.candidates),
            "filtered": list(decision.filtered),
            "reason": decision.reason,
        }
    )

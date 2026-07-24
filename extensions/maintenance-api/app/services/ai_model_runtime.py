from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable
from typing import TypeVar

from maintenance_ai.enums import ModelCapability, ProviderKind
from maintenance_ai.exceptions import SensitiveRemoteCallBlockedError
from maintenance_ai.providers import (
    OllamaProvider,
    OpenAICompatibleProvider,
    RuleFallbackProvider,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)
from maintenance_ai.routing import ModelRegistry, ModelRouter, RouteDecision
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import BusinessValidationError
from app.models import AIModelCall
from app.models.enums import AIModelCallStatus
from app.repositories.ai_execution_repository import AIExecutionRepository

T = TypeVar("T", bound=BaseModel)

_BEARER_RE = re.compile(r"(Authorization:\s*Bearer\s+)[^\s,;]+", re.IGNORECASE)
_KEY_RE = re.compile(r"(api_key\s*=\s*)[^\s,;]+", re.IGNORECASE)
_ENV_KEY_RE = re.compile(
    r"((?:OPENAI_COMPATIBLE_API_KEY|WEKNORA_API_KEY)\s*=\s*)[^\s,;]+",
    re.IGNORECASE,
)


def redact_secrets(text: str, *, configured_secrets: Iterable[str] = ()) -> str:
    result = _BEARER_RE.sub(r"\1***", text)
    result = _KEY_RE.sub(r"\1***", result)
    result = _ENV_KEY_RE.sub(r"\1***", result)
    for secret in configured_secrets:
        if secret:
            result = result.replace(secret, "***")
    return result


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AIModelRuntime:
    def __init__(
        self,
        *,
        router: ModelRouter,
        repository: AIExecutionRepository | None = None,
        configured_secrets: tuple[str, ...] = (),
    ) -> None:
        self.router = router
        self.repository = repository or AIExecutionRepository()
        self.configured_secrets = tuple(secret for secret in configured_secrets if secret)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AIModelRuntime":
        settings = settings or get_settings()
        try:
            registry = ModelRegistry.from_yaml(
                settings.ai_models_config_path,
                settings.ai_routes_config_path,
            )
        except Exception as exc:
            raise BusinessValidationError(
                "AI model configuration is invalid",
                details={"reason": str(exc)},
                code="AI_MODEL_CONFIG_INVALID",
            ) from exc

        providers: dict[str, object] = {}
        for name, definition in registry.models.items():
            if not definition.enabled:
                continue
            if definition.provider is ProviderKind.OLLAMA:
                providers[name] = OllamaProvider(
                    base_url=definition.base_url or settings.ollama_base_url,
                    model=definition.model or settings.ollama_model,
                    timeout=settings.ai_model_timeout_seconds,
                )
            elif definition.provider is ProviderKind.OPENAI_COMPATIBLE:
                if not (
                    settings.ai_remote_enabled
                    and settings.openai_compatible_base_url
                    and settings.openai_compatible_api_key
                    and settings.openai_compatible_model
                ):
                    continue
                providers[name] = OpenAICompatibleProvider(
                    base_url=settings.openai_compatible_base_url,
                    api_key=settings.openai_compatible_api_key,
                    model=settings.openai_compatible_model,
                    timeout=settings.ai_model_timeout_seconds,
                )
        return cls(
            router=ModelRouter(
                registry,
                providers=providers,
                rule_fallback=RuleFallbackProvider(),
            ),
            configured_secrets=(
                settings.openai_compatible_api_key or "",
                settings.weknora_api_key or "",
            ),
        )

    def _candidate_decisions(
        self,
        request: TextCompletionRequest,
        required_capability: ModelCapability,
    ) -> list[RouteDecision]:
        route = self.router.registry.routes.get(request.function_name)
        if route is None:
            return []
        override = request.metadata.get("model_override")
        names: list[str] = []
        if override:
            names.append(str(override))
        names.extend([route.primary, *route.fallbacks])
        decisions: list[RouteDecision] = []
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            try:
                decisions.append(
                    self.router.route(
                        request.function_name,
                        request.sensitivity,
                        {required_capability},
                        override=name,
                    )
                )
            except SensitiveRemoteCallBlockedError:
                if override and name == str(override):
                    raise
            except Exception:
                continue
        return decisions

    def _start_call(
        self,
        session: Session,
        *,
        session_id: int | None,
        request: TextCompletionRequest,
        schema_version: str | None,
        decision: RouteDecision,
    ) -> AIModelCall:
        definition = self.router.registry.models.get(decision.selected)
        provider_name = (
            ProviderKind.RULE_FALLBACK.value
            if decision.selected == "RULE_FALLBACK"
            else definition.provider.value
        )
        model_name = (
            "rule-fallback-v1" if decision.selected == "RULE_FALLBACK" else definition.model
        )
        row = AIModelCall(
            session_id=session_id,
            request_id=f"AI-MODEL-{uuid.uuid4().hex}",
            function_name=request.function_name,
            provider=provider_name,
            model=model_name,
            status=AIModelCallStatus.PENDING,
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            schema_version=schema_version,
            sensitivity_level=request.sensitivity.value,
            input_digest=_digest(request.model_dump(mode="json")),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    @staticmethod
    def _finish_success(
        session: Session,
        row: AIModelCall,
        result: StructuredCompletionResult | TextCompletionResult,
    ) -> None:
        metadata = result.metadata
        row.status = AIModelCallStatus.SUCCEEDED
        row.provider = metadata.provider.value
        row.model = metadata.model
        row.output_digest = metadata.raw_response_digest
        row.raw_response_digest = metadata.raw_response_digest
        row.finish_reason = metadata.finish_reason
        row.latency_ms = metadata.latency_ms
        row.input_tokens = metadata.usage.input_tokens
        row.output_tokens = metadata.usage.output_tokens
        row.retry_count = metadata.retry_count
        row.structured_validation_attempts = metadata.structured_validation_attempts
        row.fallback_used = metadata.fallback_used
        session.commit()

    def _finish_failure(self, session: Session, row: AIModelCall, exc: Exception) -> None:
        row.status = AIModelCallStatus.FAILED
        row.error_code = getattr(exc, "code", type(exc).__name__.upper())
        row.error_message = redact_secrets(
            str(exc)[:2000],
            configured_secrets=self.configured_secrets,
        )
        session.commit()

    async def complete_structured(
        self,
        session: Session,
        *,
        session_id: int | None,
        request: StructuredCompletionRequest,
        response_model: type[T],
    ) -> StructuredCompletionResult:
        decisions = self._candidate_decisions(
            request,
            ModelCapability.STRUCTURED_OUTPUT,
        )
        last_error: Exception | None = None
        for decision in decisions:
            row = self._start_call(
                session,
                session_id=session_id,
                request=request,
                schema_version=request.schema_version,
                decision=decision,
            )
            try:
                provider = self.router.provider_for(decision)
                result = await provider.complete_structured(request, response_model)
                self._finish_success(session, row, result)
                return result
            except Exception as exc:
                last_error = exc
                self._finish_failure(session, row, exc)
        if last_error is not None:
            raise last_error
        raise BusinessValidationError(
            "no eligible provider for structured completion",
            code="PROVIDER_UNAVAILABLE",
        )

    async def complete_text(
        self,
        session: Session,
        *,
        session_id: int | None,
        request: TextCompletionRequest,
    ) -> TextCompletionResult:
        decisions = self._candidate_decisions(request, ModelCapability.TEXT)
        last_error: Exception | None = None
        for decision in decisions:
            row = self._start_call(
                session,
                session_id=session_id,
                request=request,
                schema_version=None,
                decision=decision,
            )
            try:
                provider = self.router.provider_for(decision)
                result = await provider.complete_text(request)
                self._finish_success(session, row, result)
                return result
            except Exception as exc:
                last_error = exc
                self._finish_failure(session, row, exc)
        if last_error is not None:
            raise last_error
        raise BusinessValidationError(
            "no eligible provider for text completion",
            code="PROVIDER_UNAVAILABLE",
        )

    async def health(self) -> dict[str, object]:
        results: dict[str, object] = {}
        for name, provider in self.router.providers.items():
            results[name] = (await provider.health_check()).model_dump(mode="json")
        if self.router.rule_fallback is not None:
            results["RULE_FALLBACK"] = (await self.router.rule_fallback.health_check()).model_dump(
                mode="json"
            )
        return results

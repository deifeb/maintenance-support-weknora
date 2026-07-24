import time
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

from maintenance_ai.enums import (
    ExecutionMode,
    ProviderHealthStatus,
    ProviderKind,
    StreamEventType,
)
from maintenance_ai.providers._utils import metadata
from maintenance_ai.providers.schemas import (
    ProviderHealth,
    StreamEvent,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)

T = TypeVar("T", bound=BaseModel)


class RuleFallbackProvider:
    model = "rule-fallback-v1"

    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        started = time.perf_counter()
        text = "模型不可用，已使用确定性规则和固定模板完成处理。"
        return TextCompletionResult(
            text=text,
            metadata=metadata(
                ProviderKind.RULE_FALLBACK, self.model, text, started, fallback_used=True
            ),
            execution_mode=ExecutionMode.RULE_FALLBACK,
            llm_generated=False,
            fallback_reason="all configured LLM providers unavailable or disallowed",
        )

    async def complete_structured(
        self, request: StructuredCompletionRequest, response_model: type[T]
    ) -> StructuredCompletionResult:
        started = time.perf_counter()
        defaults = request.metadata.get("rule_fallback_data", {})
        validated = response_model.model_validate(defaults)
        data = validated.model_dump(mode="json")
        return StructuredCompletionResult(
            data=data,
            metadata=metadata(
                ProviderKind.RULE_FALLBACK, self.model, data, started, fallback_used=True
            ),
            execution_mode=ExecutionMode.RULE_FALLBACK,
            llm_generated=False,
            fallback_reason="all configured LLM providers unavailable or disallowed",
        )

    async def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]:
        result = await self.complete_text(request)
        yield StreamEvent(event_type=StreamEventType.TOKEN, text=result.text, sequence=1)
        yield StreamEvent(event_type=StreamEventType.COMPLETED, sequence=2)

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=ProviderKind.RULE_FALLBACK,
            model=self.model,
            status=ProviderHealthStatus.HEALTHY,
            detail="deterministic fallback ready",
            latency_ms=0,
        )

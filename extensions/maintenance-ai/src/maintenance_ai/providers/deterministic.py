import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from pydantic import BaseModel

from maintenance_ai.enums import ProviderHealthStatus, ProviderKind, StreamEventType
from maintenance_ai.exceptions import ProviderTimeoutError, ProviderUnavailableError
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


class DeterministicTestProvider:
    def __init__(self, fixtures: dict[str, Any] | None = None, model: str = "deterministic-v1"):
        self.fixtures = fixtures or {}
        self.failures: dict[str, str] = {}
        self.model = model

    def _raise_failure(self, function_name: str) -> None:
        failure = self.failures.get(function_name)
        if failure == "timeout":
            raise ProviderTimeoutError("deterministic timeout")
        if failure == "unavailable":
            raise ProviderUnavailableError("deterministic unavailable")

    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        started = time.perf_counter()
        self._raise_failure(request.function_name)
        fixture = self.fixtures.get(request.function_name, "确定性测试响应")
        text = fixture if isinstance(fixture, str) else str(fixture.get("text", fixture))
        return TextCompletionResult(
            text=text,
            metadata=metadata(ProviderKind.DETERMINISTIC_TEST, self.model, text, started),
        )

    async def complete_structured(
        self, request: StructuredCompletionRequest, response_model: type[T]
    ) -> StructuredCompletionResult:
        started = time.perf_counter()
        self._raise_failure(request.function_name)
        fixture = self.fixtures.get(
            request.function_name,
            request.metadata.get("rule_fallback_data", {}),
        )
        if isinstance(fixture, BaseModel):
            fixture = fixture.model_dump(mode="json")
        validated = response_model.model_validate(fixture)
        data = validated.model_dump(mode="json")
        return StructuredCompletionResult(
            data=data,
            metadata=metadata(ProviderKind.DETERMINISTIC_TEST, self.model, data, started),
        )

    async def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]:
        result = await self.complete_text(request)
        for sequence, token in enumerate(result.text.split(), 1):
            await asyncio.sleep(0)
            yield StreamEvent(event_type=StreamEventType.TOKEN, text=token, sequence=sequence)
        yield StreamEvent(
            event_type=StreamEventType.COMPLETED, sequence=max(1, len(result.text.split()) + 1)
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=ProviderKind.DETERMINISTIC_TEST,
            model=self.model,
            status=ProviderHealthStatus.HEALTHY,
            detail="deterministic provider ready",
            latency_ms=0,
        )

from collections.abc import AsyncIterator
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from maintenance_ai.providers.schemas import (
    ProviderHealth,
    StreamEvent,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult: ...

    async def complete_structured(
        self, request: StructuredCompletionRequest, response_model: type[ResponseT]
    ) -> StructuredCompletionResult: ...

    def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]: ...

    async def health_check(self) -> ProviderHealth: ...

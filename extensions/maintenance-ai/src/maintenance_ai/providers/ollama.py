import json
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from maintenance_ai.enums import ProviderHealthStatus, ProviderKind, StreamEventType
from maintenance_ai.exceptions import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from maintenance_ai.providers._utils import metadata
from maintenance_ai.providers.schemas import (
    CompletionUsage,
    ProviderHealth,
    StreamEvent,
    StructuredCompletionRequest,
    StructuredCompletionResult,
    TextCompletionRequest,
    TextCompletionResult,
)
from maintenance_ai.structured import validate_structured_output

T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        keep_alive: str = "5m",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _prompt(request: TextCompletionRequest) -> str:
        return "\n".join(f"{message.role}: {message.content}" for message in request.messages)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        started = time.perf_counter()
        raw = await self._post(
            {
                "model": self.model,
                "prompt": self._prompt(request),
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_output_tokens,
                },
            }
        )
        text = str(raw.get("response", ""))
        if not text:
            raise ProviderError("Ollama returned empty response")
        usage = CompletionUsage(
            input_tokens=raw.get("prompt_eval_count"), output_tokens=raw.get("eval_count")
        )
        return TextCompletionResult(
            text=text,
            metadata=metadata(
                ProviderKind.OLLAMA,
                self.model,
                raw,
                started,
                finish_reason="stop" if raw.get("done") else None,
                usage=usage,
            ),
        )

    async def complete_structured(
        self, request: StructuredCompletionRequest, response_model: type[T]
    ) -> StructuredCompletionResult:
        started = time.perf_counter()
        raw = await self._post(
            {
                "model": self.model,
                "prompt": self._prompt(request),
                "stream": False,
                "keep_alive": self.keep_alive,
                "format": response_model.model_json_schema(),
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_output_tokens,
                },
            }
        )
        validated = validate_structured_output(str(raw.get("response", "")), response_model)
        data = validated.model_dump(mode="json")
        usage = CompletionUsage(
            input_tokens=raw.get("prompt_eval_count"), output_tokens=raw.get("eval_count")
        )
        return StructuredCompletionResult(
            data=data,
            metadata=metadata(
                ProviderKind.OLLAMA,
                self.model,
                raw,
                started,
                finish_reason="stop" if raw.get("done") else None,
                structured_validation_attempts=1,
                usage=usage,
            ),
        )

    async def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]:
        payload = {
            "model": self.model,
            "prompt": self._prompt(request),
            "stream": True,
            "keep_alive": self.keep_alive,
        }
        sequence = 0
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    row = json.loads(line)
                    if row.get("response"):
                        sequence += 1
                        yield StreamEvent(
                            event_type=StreamEventType.TOKEN,
                            text=row["response"],
                            sequence=sequence,
                        )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        yield StreamEvent(event_type=StreamEventType.COMPLETED, sequence=sequence + 1)

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = {row.get("name") for row in response.json().get("models", [])}
            status = (
                ProviderHealthStatus.HEALTHY
                if self.model in models
                else ProviderHealthStatus.CONFIGURED_BUT_MODEL_MISSING
            )
            detail = "model ready" if self.model in models else "configured model is not installed"
        except httpx.HTTPError as exc:
            status = ProviderHealthStatus.UNAVAILABLE
            detail = str(exc)
        return ProviderHealth(
            provider=ProviderKind.OLLAMA,
            model=self.model,
            status=status,
            detail=detail,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

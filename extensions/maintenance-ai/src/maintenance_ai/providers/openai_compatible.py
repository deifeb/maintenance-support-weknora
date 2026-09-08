import json
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from maintenance_ai.enums import ProviderHealthStatus, ProviderKind, StreamEventType
from maintenance_ai.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
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


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
        supports_json_schema: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.supports_json_schema = supports_json_schema
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions", headers=self.headers, json=payload
            )
            if response.status_code == 429:
                raise ProviderRateLimitError("remote provider rate limited")
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

    def _base_payload(self, request: TextCompletionRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }

    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult:
        started = time.perf_counter()
        raw = await self._post(self._base_payload(request))
        choice = raw.get("choices", [{}])[0]
        text = str(choice.get("message", {}).get("content", ""))
        if not text:
            raise ProviderError("OpenAI-compatible provider returned empty response")
        usage_raw = raw.get("usage", {})
        return TextCompletionResult(
            text=text,
            metadata=metadata(
                ProviderKind.OPENAI_COMPATIBLE,
                self.model,
                raw,
                started,
                request_id=raw.get("id", "remote"),
                finish_reason=choice.get("finish_reason"),
                usage=CompletionUsage(
                    input_tokens=usage_raw.get("prompt_tokens"),
                    output_tokens=usage_raw.get("completion_tokens"),
                ),
            ),
        )

    async def complete_structured(
        self, request: StructuredCompletionRequest, response_model: type[T]
    ) -> StructuredCompletionResult:
        started = time.perf_counter()
        payload = self._base_payload(request)
        if self.supports_json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.function_name.replace("-", "_"),
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        raw = await self._post(payload)
        choice = raw.get("choices", [{}])[0]
        content = str(choice.get("message", {}).get("content", ""))
        validated = validate_structured_output(content, response_model)
        data = validated.model_dump(mode="json")
        usage_raw = raw.get("usage", {})
        return StructuredCompletionResult(
            data=data,
            metadata=metadata(
                ProviderKind.OPENAI_COMPATIBLE,
                self.model,
                raw,
                started,
                request_id=raw.get("id", "remote"),
                finish_reason=choice.get("finish_reason"),
                structured_validation_attempts=1,
                usage=CompletionUsage(
                    input_tokens=usage_raw.get("prompt_tokens"),
                    output_tokens=usage_raw.get("completion_tokens"),
                ),
            ),
        )

    async def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]:
        payload = self._base_payload(request)
        payload["stream"] = True
        sequence = 0
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self.headers, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    row = json.loads(data)
                    token = row.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if token:
                        sequence += 1
                        yield StreamEvent(
                            event_type=StreamEventType.TOKEN, text=token, sequence=sequence
                        )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        yield StreamEvent(event_type=StreamEventType.COMPLETED, sequence=sequence + 1)

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self._client.get(f"{self.base_url}/models", headers=self.headers)
            response.raise_for_status()
            status = ProviderHealthStatus.HEALTHY
            detail = "remote provider ready"
        except httpx.HTTPError as exc:
            status = ProviderHealthStatus.UNAVAILABLE
            detail = str(exc)
        return ProviderHealth(
            provider=ProviderKind.OPENAI_COMPATIBLE,
            model=self.model,
            status=status,
            detail=detail,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(base_url={self.base_url!r}, model={self.model!r}, api_key='***')"

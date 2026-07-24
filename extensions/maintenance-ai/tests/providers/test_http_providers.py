import json

import httpx
import pytest
from pydantic import BaseModel

from maintenance_ai.providers import (
    OllamaProvider,
    OpenAICompatibleProvider,
    StructuredCompletionRequest,
    TextMessage,
)


class Result(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_ollama_structured_request_uses_format_schema():
    seen = {}

    async def handler(request: httpx.Request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "response": '{"answer":"ok"}',
                "done": True,
                "eval_count": 2,
                "prompt_eval_count": 3,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(base_url="http://ollama", model="qwen", client=client)
    req = StructuredCompletionRequest(
        messages=(TextMessage(role="user", content="x"),),
        function_name="f",
        prompt_name="p",
        prompt_version="1",
        schema_version="1",
    )
    result = await provider.complete_structured(req, Result)
    assert result.data == {"answer": "ok"}
    assert seen["format"]["type"] == "object"
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_does_not_leak_key_and_parses_json():
    seen = {}

    async def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "id": "r1",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="http://remote/v1", api_key="secret", model="m", client=client
    )
    req = StructuredCompletionRequest(
        messages=(TextMessage(role="user", content="x"),),
        function_name="f",
        prompt_name="p",
        prompt_version="1",
        schema_version="1",
    )
    result = await provider.complete_structured(req, Result)
    assert result.data["answer"] == "ok"
    assert seen["auth"] == "Bearer secret"
    assert "secret" not in repr(result)
    await client.aclose()

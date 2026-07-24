import pytest
from app.services.ai_model_runtime import AIModelRuntime
from maintenance_ai.providers import StructuredCompletionRequest, TextMessage
from pydantic import BaseModel
from tests.ai.factories import create_ai_session, latest_model_call, make_router


class Result(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_runtime_persists_model_call_without_raw_secret(session) -> None:
    runtime = AIModelRuntime(
        router=make_router(
            function_name="scenario_parsing",
            structured_payload={"value": "ok"},
        )
    )
    result = await runtime.complete_structured(
        session,
        session_id=create_ai_session(session).id,
        request=StructuredCompletionRequest(
            messages=(TextMessage(role="user", content="secret user content"),),
            function_name="scenario_parsing",
            prompt_name="scenario-parser",
            prompt_version="1.0",
            schema_version="1.0",
        ),
        response_model=Result,
    )
    session.commit()
    row = latest_model_call(session)
    assert result.data["value"] == "ok"
    assert row.status.value == "SUCCEEDED"
    assert row.raw_response_digest
    assert "secret user content" not in (row.error_message or "")

import httpx
import pytest
from app.services.ai_evidence_service import WeknoraEvidenceRetriever
from maintenance_ai.enums import SensitivityLevel
from maintenance_ai.evidence import EvidenceQuery


@pytest.mark.asyncio
async def test_weknora_adapter_converts_response_to_evidence_package() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "chunk-1",
                        "type": "PARAMETER",
                        "statement": "失效率为0.0001",
                        "parameter_name": "failure_rate",
                        "value": "0.0001",
                        "unit": "1/hour",
                        "document": "manual.pdf",
                        "page": 12,
                        "chunk_reference": "chunk-1",
                        "score": 0.91,
                        "rerank_score": 0.95,
                        "sensitivity": "INTERNAL",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    retriever = WeknoraEvidenceRetriever(
        endpoint_url="http://weknora.test/evidence",
        api_key=None,
        timeout_seconds=5,
        client=client,
    )
    package = await retriever.retrieve(
        EvidenceQuery(
            query_text="EQ-A 失效率",
            sensitivity=SensitivityLevel.INTERNAL,
            max_items=10,
        )
    )
    await client.aclose()
    assert package.items[0].source_document == "manual.pdf"
    assert seen["max_items"] == 10

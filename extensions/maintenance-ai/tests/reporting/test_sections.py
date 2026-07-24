import pytest

from maintenance_ai.providers import DeterministicTestProvider
from maintenance_ai.reporting import ReportSectionGenerator, ReportSectionRequest


@pytest.mark.asyncio
async def test_report_section_rejects_unknown_numbers_and_citations():
    provider = DeterministicTestProvider(
        fixtures={
            "report_generation": {
                "title": "摘要",
                "content": "共有10项，引用E1",
                "citation_ids": ["E1"],
            }
        }
    )
    gen = ReportSectionGenerator(provider)
    result = await gen.generate(
        ReportSectionRequest(
            section_code="summary",
            title="摘要",
            facts={"item_count": 10},
            allowed_numbers=("10",),
            allowed_citation_ids=("E1",),
        )
    )
    assert result.content.startswith("共有10")
    provider.fixtures["report_generation"] = {
        "title": "摘要",
        "content": "共有99项，引用E9",
        "citation_ids": ["E9"],
    }
    with pytest.raises(Exception):
        await gen.generate(
            ReportSectionRequest(
                section_code="summary",
                title="摘要",
                facts={},
                allowed_numbers=("10",),
                allowed_citation_ids=("E1",),
            )
        )

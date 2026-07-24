import re

from maintenance_ai.exceptions import ReportValidationError
from maintenance_ai.providers import LLMProvider, StructuredCompletionRequest, TextMessage
from maintenance_ai.reporting.models import (
    ReportSection,
    ReportSectionPayload,
    ReportSectionRequest,
)

_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")


class ReportSectionGenerator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(self, request_data: ReportSectionRequest) -> ReportSection:
        request = StructuredCompletionRequest(
            messages=(TextMessage(role="user", content=request_data.model_dump_json()),),
            function_name="report_generation",
            prompt_name="report-section",
            prompt_version="1.0",
            schema_version="1.0",
        )
        result = await self.provider.complete_structured(request, ReportSectionPayload)
        payload = ReportSectionPayload.model_validate(result.data)
        numbers = set(_NUMBER_RE.findall(payload.content))
        allowed = set(request_data.allowed_numbers)
        unsupported = {number for number in numbers if number not in allowed}
        if unsupported:
            raise ReportValidationError(f"unsupported report numbers: {sorted(unsupported)}")
        invalid_citations = set(payload.citation_ids) - set(request_data.allowed_citation_ids)
        if invalid_citations:
            raise ReportValidationError(f"invalid citations: {sorted(invalid_citations)}")
        return ReportSection(
            section_code=request_data.section_code,
            title=payload.title,
            content=payload.content,
            citation_ids=tuple(payload.citation_ids),
        )

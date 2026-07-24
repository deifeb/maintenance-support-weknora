import re
from typing import Any

from maintenance_ai.enums import FieldRiskLevel, FieldSourceType
from maintenance_ai.providers import LLMProvider, StructuredCompletionRequest, TextMessage
from maintenance_ai.scenarios.models import FieldValue, ScenarioDraft


def _field(
    value: Any, risk: FieldRiskLevel, source: FieldSourceType = FieldSourceType.USER_PROVIDED
) -> FieldValue:
    return FieldValue(value=value, source_type=source, confidence=1.0, risk_level=risk)


class RuleScenarioParser:
    def parse(self, text: str) -> ScenarioDraft:
        quantity = re.search(r"(\d+)\s*(?:台|套|艘|架)", text)
        equipment = re.search(r"(EQ-\d+|示例装备\d+)", text, re.IGNORECASE)
        configuration = re.search(r"(?:构型(?:版本)?\s*)?(V\d+|示例构型\d+)", text, re.IGNORECASE)
        duration = re.search(r"(\d+(?:\.\d+)?)\s*天", text)
        service = re.search(r"(?:保障率|服务水平)\s*(\d+(?:\.\d+)?)\s*%", text)
        intensity = 1.0
        if "高强度" in text:
            intensity = 1.5
        elif "低强度" in text:
            intensity = 0.7
        days = float(duration.group(1)) if duration else None
        return ScenarioDraft(
            scenario_name=_field("自然语言任务场景", FieldRiskLevel.LOW),
            equipment_model=(
                _field(equipment.group(1), FieldRiskLevel.HIGH)
                if equipment
                else _field(
                    "待主数据匹配",
                    FieldRiskLevel.HIGH,
                    FieldSourceType.LLM_INFERRED,
                )
            ),
            configuration_version=(
                _field(configuration.group(1), FieldRiskLevel.HIGH) if configuration else None
            ),
            equipment_quantity=_field(int(quantity.group(1)), FieldRiskLevel.HIGH)
            if quantity
            else None,
            duration_days=_field(days, FieldRiskLevel.HIGH) if days is not None else None,
            stages=_field(
                [
                    {
                        "code": "MISSION",
                        "name": "任务阶段",
                        "duration_hours": days * 24,
                        "usage_intensity": intensity,
                    }
                ],
                FieldRiskLevel.HIGH,
            )
            if days is not None
            else None,
            usage_intensity=_field(intensity, FieldRiskLevel.MEDIUM),
            service_level=_field(float(service.group(1)) / 100, FieldRiskLevel.HIGH)
            if service
            else None,
            repair_policy=_field("ENABLED", FieldRiskLevel.HIGH, FieldSourceType.SYSTEM_DEFAULT),
            common_shock_policy=_field(
                "DISABLED", FieldRiskLevel.HIGH, FieldSourceType.SYSTEM_DEFAULT
            ),
        )


class NaturalLanguageScenarioParser:
    def __init__(self, provider: LLMProvider, rule_parser: RuleScenarioParser | None = None):
        self.provider = provider
        self.rule_parser = rule_parser or RuleScenarioParser()

    async def parse(self, text: str, *, sensitivity="INTERNAL") -> ScenarioDraft:
        request = StructuredCompletionRequest(
            messages=(TextMessage(role="user", content=text),),
            function_name="scenario_parsing",
            sensitivity=sensitivity,
            prompt_name="scenario-parser",
            prompt_version="1.0",
            schema_version="1.0",
            metadata={"rule_fallback_data": self.rule_parser.parse(text).model_dump(mode="json")},
        )
        try:
            result = await self.provider.complete_structured(request, ScenarioDraft)
            return ScenarioDraft.model_validate(result.data)
        except Exception:
            return self.rule_parser.parse(text)

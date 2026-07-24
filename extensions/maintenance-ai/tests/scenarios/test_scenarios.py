import pytest

from maintenance_ai.enums import FieldRiskLevel, FieldSourceType, ScenarioReadiness
from maintenance_ai.scenarios import (
    FieldValue,
    RuleScenarioParser,
    ScenarioDraft,
    assess_clarifications,
    merge_field_values,
)


def test_source_priority_cannot_be_overwritten_by_inference():
    current = FieldValue(
        value="V1",
        source_type=FieldSourceType.USER_CONFIRMED,
        confidence=1,
        confirmed=True,
        risk_level=FieldRiskLevel.HIGH,
    )
    inferred = FieldValue(
        value="V2",
        source_type=FieldSourceType.LLM_INFERRED,
        confidence=0.9,
        risk_level=FieldRiskLevel.HIGH,
    )
    assert merge_field_values(current, inferred).value == "V1"


def test_high_risk_missing_blocks_readiness():
    draft = ScenarioDraft(
        scenario_name=FieldValue(
            value="test",
            source_type=FieldSourceType.USER_PROVIDED,
            confidence=1,
            risk_level=FieldRiskLevel.LOW,
        )
    )
    result = assess_clarifications(draft)
    assert result.readiness is ScenarioReadiness.CLARIFICATION_REQUIRED
    assert "equipment_model" in result.missing_fields


def test_rule_parser_extracts_duration_quantity_and_service_level():
    draft = RuleScenarioParser().parse("10台某型装备执行30天高强度任务，保障率95%")
    assert draft.equipment_quantity.value == 10
    assert draft.duration_days.value == 30
    assert draft.service_level.value == pytest.approx(0.95)

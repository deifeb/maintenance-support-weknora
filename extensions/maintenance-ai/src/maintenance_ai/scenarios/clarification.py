from maintenance_ai.enums import ScenarioReadiness
from maintenance_ai.scenarios.models import ClarificationResult, ScenarioDraft

_HIGH_RISK_FIELDS = (
    "equipment_model",
    "configuration_version",
    "equipment_quantity",
    "duration_days",
    "stages",
    "service_level",
    "repair_policy",
    "common_shock_policy",
)


def assess_clarifications(draft: ScenarioDraft) -> ClarificationResult:
    missing = tuple(
        name
        for name in _HIGH_RISK_FIELDS
        if getattr(draft, name) is None or getattr(draft, name).value in (None, "", [], ())
    )
    if draft.blocking_issues:
        return ClarificationResult(
            readiness=ScenarioReadiness.BLOCKED,
            missing_fields=missing,
            questions=tuple(draft.blocking_issues),
        )
    if missing:
        return ClarificationResult(
            readiness=ScenarioReadiness.CLARIFICATION_REQUIRED,
            missing_fields=missing,
            questions=tuple(f"请确认字段：{name}" for name in missing),
        )
    return ClarificationResult(readiness=ScenarioReadiness.READY_FOR_PREVIEW)

import pytest

from maintenance_ai.enums import ConfirmationLevel, UserIntent
from maintenance_ai.exceptions import PlanValidationError
from maintenance_ai.planning import ExecutionPlan, PlanStep, PlanValidator, ToolPolicy


def validator():
    return PlanValidator(
        {
            "query": ToolPolicy(
                name="query",
                allowed_intents={UserIntent.DEMAND_CALCULATE},
                confirmation_level=ConfirmationLevel.NONE,
            ),
            "start": ToolPolicy(
                name="start",
                allowed_intents={UserIntent.DEMAND_CALCULATE},
                confirmation_level=ConfirmationLevel.EXPLICIT,
            ),
        }
    )


def test_validator_enforces_fixed_confirmation_and_dependencies():
    plan = ExecutionPlan(
        goal="g",
        intent=UserIntent.DEMAND_CALCULATE,
        steps=(
            PlanStep(step_code="a", tool_name="query"),
            PlanStep(
                step_code="b",
                tool_name="start",
                depends_on=("a",),
                requires_confirmation=ConfirmationLevel.NONE,
            ),
        ),
    )
    validated = validator().validate(plan)
    assert validated.steps[1].requires_confirmation is ConfirmationLevel.EXPLICIT


def test_unregistered_tool_and_cycle_are_rejected():
    bad = ExecutionPlan(
        goal="g",
        intent=UserIntent.DEMAND_CALCULATE,
        steps=(PlanStep(step_code="a", tool_name="shell"),),
    )
    with pytest.raises(PlanValidationError):
        validator().validate(bad)

    cycle = ExecutionPlan(
        goal="g",
        intent=UserIntent.DEMAND_CALCULATE,
        steps=(
            PlanStep(step_code="a", tool_name="query", depends_on=("b",)),
            PlanStep(step_code="b", tool_name="query", depends_on=("a",)),
        ),
    )
    with pytest.raises(PlanValidationError):
        validator().validate(cycle)

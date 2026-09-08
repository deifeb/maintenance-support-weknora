from maintenance_ai.enums import ConfirmationLevel, UserIntent
from maintenance_ai.planning.intents import classify_intent
from maintenance_ai.planning.models import ExecutionPlan, PlanStep


class RestrictedPlanner:
    def plan(self, goal: str, intent: UserIntent | None = None) -> ExecutionPlan:
        intent = intent or classify_intent(goal)
        if intent is UserIntent.DEMAND_CALCULATE:
            steps = (
                PlanStep(step_code="prepare", tool_name="prepare_demand_scenario"),
                PlanStep(
                    step_code="preview",
                    tool_name="preview_demand_calculation",
                    depends_on=("prepare",),
                ),
                PlanStep(
                    step_code="calculate",
                    tool_name="start_demand_calculation",
                    depends_on=("preview",),
                    requires_confirmation=ConfirmationLevel.EXPLICIT,
                ),
                PlanStep(
                    step_code="assess", tool_name="run_demand_assessment", depends_on=("calculate",)
                ),
            )
        elif intent is UserIntent.REPORT_GENERATE:
            steps = (
                PlanStep(
                    step_code="report",
                    tool_name="prepare_management_report",
                    requires_confirmation=ConfirmationLevel.EXPLICIT,
                ),
            )
        else:
            steps = (PlanStep(step_code="respond", tool_name="general_qa"),)
        return ExecutionPlan(goal=goal, intent=intent, steps=steps)

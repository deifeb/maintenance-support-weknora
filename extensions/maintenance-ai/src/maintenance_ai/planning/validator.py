from maintenance_ai.enums import ConfirmationLevel
from maintenance_ai.exceptions import PlanValidationError
from maintenance_ai.planning.models import ExecutionPlan, PlanStep, ToolPolicy

_CONFIRM_ORDER = {
    ConfirmationLevel.NONE: 0,
    ConfirmationLevel.IMPLICIT: 1,
    ConfirmationLevel.EXPLICIT: 2,
    ConfirmationLevel.SECONDARY: 3,
}


class PlanValidator:
    def __init__(self, policies: dict[str, ToolPolicy]):
        self.policies = policies

    def validate(self, plan: ExecutionPlan) -> ExecutionPlan:
        codes = [step.step_code for step in plan.steps]
        if len(codes) != len(set(codes)):
            raise PlanValidationError("duplicate plan step code")
        known = set(codes)
        normalized = []
        for step in plan.steps:
            if step.tool_name is None:
                normalized.append(step)
                continue
            policy = self.policies.get(step.tool_name)
            if policy is None:
                raise PlanValidationError(f"tool not registered: {step.tool_name}")
            if plan.intent not in policy.allowed_intents:
                raise PlanValidationError(
                    f"tool {step.tool_name} is not allowed for {plan.intent.value}"
                )
            if not set(step.depends_on).issubset(known):
                raise PlanValidationError(f"unknown dependency in {step.step_code}")
            required = step.requires_confirmation
            if _CONFIRM_ORDER[policy.confirmation_level] > _CONFIRM_ORDER[required]:
                required = policy.confirmation_level
            normalized.append(step.model_copy(update={"requires_confirmation": required}))
        self._reject_cycles(tuple(normalized))
        return plan.model_copy(update={"steps": tuple(normalized)})

    @staticmethod
    def _reject_cycles(steps: tuple[PlanStep, ...]) -> None:
        graph = {step.step_code: set(step.depends_on) for step in steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise PlanValidationError("plan dependency cycle")
            if node in visited:
                return
            visiting.add(node)
            for dep in graph[node]:
                visit(dep)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

from __future__ import annotations

from maintenance_ai.enums import (
    ConfirmationLevel,
    UserIntent,
)
from maintenance_ai.exceptions import PlanValidationError
from maintenance_ai.planning import (
    PlanValidator,
    RestrictedPlanner,
    ToolPolicy,
)
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError
from app.models import AIExecutionPlan
from app.models.enums import (
    AIPlanStatus,
    AISessionStatus,
)
from app.repositories.ai_execution_repository import (
    AIExecutionRepository,
    ai_execution_repository,
)
from app.security.actor import ActorContext
from app.services.ai_session_service import (
    AISessionService,
    ai_session_service,
)
from app.services.ai_tool_registry import (
    ToolRegistry,
    ai_tool_registry,
)


class AIPlanService:
    def __init__(
        self,
        *,
        planner: RestrictedPlanner | None = None,
        tool_registry: ToolRegistry | None = None,
        repository: AIExecutionRepository | None = None,
        session_service: AISessionService | None = None,
    ) -> None:
        self.planner = planner or RestrictedPlanner()
        self.tool_registry = (
            tool_registry or ai_tool_registry
        )
        self.repository = (
            repository or ai_execution_repository
        )
        self.session_service = (
            session_service or ai_session_service
        )

    def _validator(self) -> PlanValidator:
        policies = {}
        for definition in (
            self.tool_registry.list_definitions()
        ):
            allowed = (
                {
                    UserIntent(value)
                    for value
                    in definition.allowed_intents
                }
                if definition.allowed_intents
                else set(UserIntent)
            )
            policies[definition.name] = ToolPolicy(
                name=definition.name,
                allowed_intents=allowed,
                confirmation_level=(
                    ConfirmationLevel(
                        definition
                        .confirmation_level
                        .value
                    )
                ),
            )
        return PlanValidator(policies)

    def create_and_validate(
        self,
        session: Session,
        actor: ActorContext,
        session_id: int,
        goal: str,
    ) -> AIExecutionPlan:
        ai_session = self.session_service.get(
            session,
            actor,
            session_id,
        )
        try:
            plan = self._validator().validate(
                self.planner.plan(goal)
            )
        except PlanValidationError as exc:
            row = self.repository.create_plan(
                session,
                actor.tenant_id,
                session_id=session_id,
                goal=goal,
                intent="UNKNOWN",
            )
            row.validation_status = "FAILED"
            row.validation_errors_json = [
                {
                    "code": "PLAN_VALIDATION_FAILED",
                    "message": str(exc),
                }
            ]
            row.status = AIPlanStatus.FAILED
            ai_session.status = AISessionStatus.FAILED
            session.commit()
            self.session_service.append_event(
                session,
                actor,
                session_id,
                "FAILED",
                {
                    "code": (
                        "PLAN_VALIDATION_FAILED"
                    )
                },
            )
            raise BusinessValidationError(
                "PLAN_VALIDATION_FAILED",
                details={"reason": str(exc)},
                code="PLAN_VALIDATION_FAILED",
            ) from exc

        row = self.repository.create_plan(
            session,
            actor.tenant_id,
            session_id=session_id,
            goal=plan.goal,
            intent=plan.intent.value,
            plan_version=plan.plan_version,
        )
        row.validation_status = "VALID"
        row.validation_errors_json = []
        row.status = AIPlanStatus.VALIDATED
        session.flush()
        for index, step in enumerate(
            plan.steps,
            1,
        ):
            self.repository.add_step(
                session,
                actor.tenant_id,
                plan_id=row.id,
                step_index=index,
                step_code=step.step_code,
                action_type=step.action_type.value,
                tool_name=step.tool_name,
                input_template=step.input_template,
                depends_on=list(step.depends_on),
                confirmation_level=(
                    step.requires_confirmation.value
                ),
                risk_level=step.risk_level,
            )

        ai_session.status = AISessionStatus.PLANNED
        ai_session.current_intent = plan.intent.value
        session.commit()

        self.session_service.append_event(
            session,
            actor,
            session_id,
            "PLAN_CREATED",
            {
                "plan_id": row.id,
                "intent": plan.intent.value,
            },
        )
        self.session_service.append_event(
            session,
            actor,
            session_id,
            "PLAN_VALIDATED",
            {"plan_id": row.id},
        )
        self.session_service.create_snapshot(
            session,
            actor,
            session_id,
            execution_context={"plan_id": row.id},
        )
        session.refresh(row)
        return row


ai_plan_service = AIPlanService()

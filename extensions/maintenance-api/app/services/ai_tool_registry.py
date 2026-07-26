from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessValidationError
from app.models.enums import AIConfirmationLevel
from app.security.actor import ActorContext


class FlexiblePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class FlexibleOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    actor: ActorContext
    workspace_id: str = "default"
    permissions: set[str] = Field(
        default_factory=set
    )
    intent: str
    sensitivity_level: str = "INTERNAL"
    session_id: int | None = None
    plan_step_id: int | None = None
    confirmation_approved: bool = False
    business_idempotency_key: str | None = None

    @property
    def tenant_id(self) -> str:
        return self.actor.tenant_id

    @property
    def user_id(self) -> str:
        return self.actor.user_id


class ToolDefinition(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    name: str
    version: str = "1.0"
    description: str
    input_model: type[BaseModel] = FlexiblePayload
    output_model: type[BaseModel] = FlexibleOutput
    permission_level: str = "READ"
    confirmation_level: AIConfirmationLevel = (
        AIConfirmationLevel.NONE
    )
    idempotent: bool = True
    timeout_seconds: int = 30
    retryable: bool = True
    allowed_intents: set[str] = Field(
        default_factory=set
    )
    allowed_sensitivity: set[str] = Field(
        default_factory=lambda: {
            "PUBLIC",
            "INTERNAL",
            "CONFIDENTIAL",
            "RESTRICTED",
        }
    )
    handler: (
        Callable[
            [
                Session,
                BaseModel,
                ToolExecutionContext,
            ],
            Any,
        ]
        | None
    ) = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[
            str,
            ToolDefinition,
        ] = {}

    def register(
        self,
        definition: ToolDefinition,
    ) -> None:
        if definition.name in self._tools:
            raise BusinessValidationError(
                "TOOL_ALREADY_REGISTERED",
                details={
                    "tool_name": definition.name
                },
                code="TOOL_ALREADY_REGISTERED",
            )
        self._tools[definition.name] = definition

    def get(
        self,
        name: str,
    ) -> ToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise BusinessValidationError(
                "TOOL_NOT_REGISTERED",
                details={"tool_name": name},
                code="TOOL_NOT_REGISTERED",
            )
        return tool

    def list_definitions(
        self,
    ) -> list[ToolDefinition]:
        return sorted(
            self._tools.values(),
            key=lambda row: row.name,
        )

    def execute(
        self,
        session: Session,
        name: str,
        payload: dict[str, Any],
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        tool = self.get(name)

        if (
            tool.allowed_intents
            and context.intent
            not in tool.allowed_intents
        ):
            raise BusinessValidationError(
                "PLAN_TOOL_NOT_ALLOWED",
                details={
                    "tool_name": name,
                    "intent": context.intent,
                },
                code="PLAN_TOOL_NOT_ALLOWED",
            )

        if (
            context.sensitivity_level
            not in tool.allowed_sensitivity
        ):
            raise BusinessValidationError(
                "TOOL_SENSITIVITY_DENIED",
                details={"tool_name": name},
                code="TOOL_SENSITIVITY_DENIED",
            )

        if (
            tool.permission_level
            not in {"NONE", "READ"}
            and tool.permission_level
            not in context.permissions
        ):
            raise BusinessValidationError(
                "TOOL_PERMISSION_DENIED",
                details={
                    "tool_name": name,
                    "permission": (
                        tool.permission_level
                    ),
                },
                code="TOOL_PERMISSION_DENIED",
            )

        if (
            tool.confirmation_level
            in {
                AIConfirmationLevel.EXPLICIT,
                AIConfirmationLevel.SECONDARY,
            }
            and not context.confirmation_approved
        ):
            raise BusinessValidationError(
                "TOOL_CONFIRMATION_REQUIRED",
                details={
                    "tool_name": name,
                    "confirmation_level": (
                        tool
                        .confirmation_level
                        .value
                    ),
                },
                code="TOOL_CONFIRMATION_REQUIRED",
            )

        if tool.handler is None:
            raise BusinessValidationError(
                "TOOL_HANDLER_UNAVAILABLE",
                details={"tool_name": name},
                code="TOOL_HANDLER_UNAVAILABLE",
            )

        validated_input = (
            tool.input_model.model_validate(
                payload
            )
        )
        result = tool.handler(
            session,
            validated_input,
            context,
        )
        if isinstance(result, BaseModel):
            result = result.model_dump(
                mode="json"
            )
        validated_output = (
            tool.output_model.model_validate(
                result
            )
        )
        return validated_output.model_dump(
            mode="json"
        )


_DEFAULT_TOOLS = {
    "search_equipment_models": (
        "Search equipment models",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_equipment_model": (
        "Read equipment model",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "search_configuration_versions": (
        "Search configuration versions",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_configuration_snapshot": (
        "Read configuration snapshot",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "resolve_equipment_context": (
        "Resolve equipment context",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "list_spare_parts": (
        "List spare parts",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_spare_part": (
        "Read spare part",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_reliability_profiles": (
        "Read reliability profiles",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "create_scenario_draft": (
        "Create scenario draft",
        "SCENARIO_DRAFT",
        AIConfirmationLevel.IMPLICIT,
    ),
    "update_scenario_draft": (
        "Update scenario draft",
        "SCENARIO_DRAFT",
        AIConfirmationLevel.IMPLICIT,
    ),
    "validate_scenario_draft": (
        "Validate scenario draft",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_scenario_preview": (
        "Preview scenario",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "publish_scenario_version": (
        "Publish scenario version",
        "SCENARIO_PUBLISH",
        AIConfirmationLevel.SECONDARY,
    ),
    "recommend_calculation_method": (
        "Recommend calculation method",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "preview_demand_calculation": (
        "Preview demand calculation",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "start_demand_calculation": (
        "Start demand calculation",
        "CALCULATION_EXECUTE",
        AIConfirmationLevel.EXPLICIT,
    ),
    "get_calculation_status": (
        "Read calculation status",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_calculation_result": (
        "Read calculation result",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "cancel_demand_calculation": (
        "Cancel calculation",
        "CALCULATION_CANCEL",
        AIConfirmationLevel.SECONDARY,
    ),
    "compare_calculation_runs": (
        "Compare calculation runs",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "calculate_inventory_gap": (
        "Calculate inventory gap",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_inventory_snapshot": (
        "Read inventory snapshot",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "get_repair_pipeline": (
        "Read repair pipeline",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "run_demand_list_review": (
        "Review demand list",
        "REVIEW_EXECUTE",
        AIConfirmationLevel.NONE,
    ),
    "get_review_findings": (
        "Read review findings",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "create_report_draft": (
        "Create report draft",
        "REPORT_CREATE",
        AIConfirmationLevel.IMPLICIT,
    ),
    "get_report_status": (
        "Read report status",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "build_evidence_package": (
        "Build evidence package",
        "READ",
        AIConfirmationLevel.NONE,
    ),
    "prepare_demand_scenario": (
        "Prepare demand scenario",
        "SCENARIO_DRAFT",
        AIConfirmationLevel.IMPLICIT,
    ),
    "run_demand_assessment": (
        "Run demand assessment",
        "CALCULATION_EXECUTE",
        AIConfirmationLevel.EXPLICIT,
    ),
    "prepare_management_report": (
        "Prepare management report",
        "REPORT_CREATE",
        AIConfirmationLevel.EXPLICIT,
    ),
    "general_qa": (
        "General question answering",
        "READ",
        AIConfirmationLevel.NONE,
    ),
}


def build_default_tool_registry() -> ToolRegistry:
    from app.services.ai_tool_adapters import (
        HANDLERS,
        echo_payload,
    )

    registry = ToolRegistry()
    for (
        name,
        (
            description,
            permission,
            confirmation,
        ),
    ) in _DEFAULT_TOOLS.items():
        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                permission_level=permission,
                confirmation_level=confirmation,
                idempotent=(
                    confirmation
                    in {
                        AIConfirmationLevel.NONE,
                        AIConfirmationLevel.IMPLICIT,
                    }
                ),
                retryable=(
                    confirmation
                    is AIConfirmationLevel.NONE
                ),
                handler=HANDLERS.get(
                    name,
                    echo_payload,
                ),
            )
        )
    return registry


ai_tool_registry = build_default_tool_registry()

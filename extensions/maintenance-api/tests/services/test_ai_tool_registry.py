import pytest
from app.core.exceptions import BusinessValidationError
from app.models.enums import AIConfirmationLevel
from app.services.ai_tool_registry import (
    ToolDefinition,
    ToolExecutionContext,
    ToolRegistry,
    build_default_tool_registry,
)
from pydantic import BaseModel


class StartInput(BaseModel):
    calculation_name: str
    scenario_version_id: int


class StartOutput(BaseModel):
    calculation_id: int


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="start_demand_calculation",
            version="1.0",
            description="启动正式需求计算",
            input_model=StartInput,
            output_model=StartOutput,
            permission_level="CALCULATION_EXECUTE",
            confirmation_level=AIConfirmationLevel.EXPLICIT,
            idempotent=False,
            timeout_seconds=30,
            retryable=False,
            allowed_intents={"DEMAND_CALCULATE"},
            allowed_sensitivity={"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"},
            handler=lambda session, payload, context: {"calculation_id": 1},
        )
    )
    return registry


def test_registry_rejects_unknown_tool(session) -> None:
    registry = ToolRegistry()
    with pytest.raises(BusinessValidationError, match="TOOL_NOT_REGISTERED"):
        registry.execute(
            session,
            "execute_sql",
            {},
            ToolExecutionContext(
                user_id="u1",
                workspace_id="default",
                permissions=set(),
                intent="GENERAL_QA",
            ),
        )


def test_registry_requires_fixed_permission(session) -> None:
    registry = build_registry()
    with pytest.raises(BusinessValidationError, match="TOOL_PERMISSION_DENIED"):
        registry.execute(
            session,
            "start_demand_calculation",
            {"calculation_name": "test", "scenario_version_id": 1},
            ToolExecutionContext(
                user_id="u1",
                workspace_id="default",
                permissions=set(),
                intent="DEMAND_CALCULATE",
            ),
        )


def test_default_registry_has_whitelist_and_fixed_confirmation():
    registry = build_default_tool_registry()
    assert len(registry.list_definitions()) >= 20
    assert (
        registry.get("start_demand_calculation").confirmation_level is AIConfirmationLevel.EXPLICIT
    )
    assert (
        registry.get("cancel_demand_calculation").confirmation_level
        is AIConfirmationLevel.SECONDARY
    )

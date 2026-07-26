from __future__ import annotations

from collections.abc import Callable

import pytest
from app.core.exceptions import BusinessValidationError
from app.models.enums import AIConfirmationLevel
from app.security.actor import ActorContext
from app.services.ai_tool_registry import (
    ToolDefinition,
    ToolExecutionContext,
    ToolRegistry,
    build_default_tool_registry,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session


class StartInput(BaseModel):
    calculation_name: str
    scenario_version_id: int


class StartOutput(BaseModel):
    calculation_id: int


def context(
    actor: ActorContext,
    *,
    permissions: set[str] | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        actor=actor,
        workspace_id="default",
        permissions=permissions or set(),
        intent="DEMAND_CALCULATE",
    )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="start_demand_calculation",
            version="1.0",
            description=(
                "Start formal demand calculation"
            ),
            input_model=StartInput,
            output_model=StartOutput,
            permission_level=(
                "CALCULATION_EXECUTE"
            ),
            confirmation_level=(
                AIConfirmationLevel.EXPLICIT
            ),
            idempotent=False,
            timeout_seconds=30,
            retryable=False,
            allowed_intents={
                "DEMAND_CALCULATE"
            },
            allowed_sensitivity={
                "PUBLIC",
                "INTERNAL",
                "CONFIDENTIAL",
                "RESTRICTED",
            },
            handler=lambda session, payload, ctx: {
                "calculation_id": 1
            },
        )
    )
    return registry


def test_registry_rejects_unknown_tool(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    registry = ToolRegistry()
    actor = actor_context()

    with pytest.raises(
        BusinessValidationError,
        match="TOOL_NOT_REGISTERED",
    ):
        registry.execute(
            session,
            "execute_sql",
            {},
            ToolExecutionContext(
                actor=actor,
                intent="GENERAL_QA",
            ),
        )


def test_registry_requires_fixed_permission(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    registry = build_registry()
    actor = actor_context()

    with pytest.raises(
        BusinessValidationError,
        match="TOOL_PERMISSION_DENIED",
    ):
        registry.execute(
            session,
            "start_demand_calculation",
            {
                "calculation_name": "test",
                "scenario_version_id": 1,
            },
            context(actor),
        )


def test_default_registry_has_whitelist_and_fixed_confirmation(
) -> None:
    registry = build_default_tool_registry()

    assert len(
        registry.list_definitions()
    ) >= 20
    assert (
        registry.get(
            "start_demand_calculation"
        ).confirmation_level
        is AIConfirmationLevel.EXPLICIT
    )
    assert (
        registry.get(
            "cancel_demand_calculation"
        ).confirmation_level
        is AIConfirmationLevel.SECONDARY
    )


def test_tool_context_derives_identity_from_actor(
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    tool_context = context(
        actor,
        permissions={
            "CALCULATION_EXECUTE"
        },
    )

    assert tool_context.actor is actor
    assert tool_context.tenant_id == "tenant-a"
    assert tool_context.user_id == "alice"
    assert (
        "user_id"
        not in ToolExecutionContext.model_fields
    )
    assert (
        "tenant_id"
        not in ToolExecutionContext.model_fields
    )

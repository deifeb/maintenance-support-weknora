from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    DemandCalculation,
    EquipmentModel,
)
from app.models.enums import (
    CalculationExecutionType,
    DemandExecutionMode,
)
from app.security.actor import ActorContext
from app.services.ai_tool_adapters import (
    compute_tool_idempotency_key,
    get_calculation_status,
    search_equipment_models,
    start_demand_calculation,
)
from app.services.ai_tool_registry import (
    FlexiblePayload,
    ToolExecutionContext,
)
from app.services.demand_calculation_service import (
    calculation_service,
)
from sqlalchemy.orm import Session


def context(
    actor: ActorContext,
    *,
    key: str | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        actor=actor,
        permissions={
            "CALCULATION_EXECUTE"
        },
        intent="DEMAND_CALCULATE",
        confirmation_approved=True,
        business_idempotency_key=key,
    )


def test_tool_idempotency_key_is_canonical() -> None:
    first = compute_tool_idempotency_key(
        session_id=1,
        plan_step_id=2,
        tool_version="1.0",
        payload={"b": 2, "a": 1},
    )
    second = compute_tool_idempotency_key(
        session_id=1,
        plan_step_id=2,
        tool_version="1.0",
        payload={"a": 1, "b": 2},
    )

    assert first == second
    assert len(first) == 64


def test_equipment_search_is_tenant_scoped(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    session.add_all(
        [
            EquipmentModel(
                tenant_id="tenant-a",
                code="A",
                name="Visible",
            ),
            EquipmentModel(
                tenant_id="tenant-b",
                code="B",
                name="Foreign",
            ),
        ]
    )
    session.commit()

    result = search_equipment_models(
        session,
        FlexiblePayload(),
        context(actor),
    )

    assert [
        item["code"]
        for item in result["items"]
    ] == ["A"]


def test_calculation_status_rejects_foreign_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a"
    )
    now = datetime.now(timezone.utc)
    foreign = DemandCalculation(
        tenant_id="tenant-b",
        calculation_code="FOREIGN",
        calculation_name="Foreign",
        execution_type=(
            CalculationExecutionType
            .SYNCHRONOUS
        ),
        requested_mode=(
            DemandExecutionMode.ANALYTICAL
        ),
        input_snapshot_json={},
        input_snapshot_hash="f" * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(foreign)
    session.commit()

    with pytest.raises(NotFoundError):
        get_calculation_status(
            session,
            FlexiblePayload(
                calculation_id=foreign.id
            ),
            context(actor),
        )


def test_start_calculation_passes_actor_and_tenant_to_worker(
    session: Session,
    actor_context: Callable[..., ActorContext],
    monkeypatch,
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        user_id="alice",
    )
    seen = {}
    row = SimpleNamespace(
        id=42,
        calculation_code="CALC-42",
        status=SimpleNamespace(
            value="PENDING"
        ),
    )

    def fake_submit(
        db,
        seen_actor,
        request,
        *,
        idempotency_key=None,
        force_async=None,
    ):
        seen["db"] = db
        seen["actor"] = seen_actor
        seen["request"] = request
        seen["key"] = idempotency_key
        seen["force_async"] = force_async
        return row

    from app.workers.executor import (
        demand_task_executor,
    )

    def fake_worker_submit(
        tenant_id,
        calculation_id,
    ):
        seen["worker"] = (
            tenant_id,
            calculation_id,
        )
        return True

    monkeypatch.setattr(
        calculation_service,
        "submit",
        fake_submit,
    )
    monkeypatch.setattr(
        demand_task_executor,
        "submit",
        fake_worker_submit,
    )

    result = start_demand_calculation(
        session,
        FlexiblePayload(
            calculation_name="Test",
            scenario_version_id=1,
            requested_mode="AUTO",
            execution_preference="ASYNC",
            random_seed=1,
        ),
        context(actor, key="same-key"),
    )

    assert seen["actor"] is actor
    assert seen["key"] == "same-key"
    assert seen["force_async"] is True
    assert seen["worker"] == (
        actor.tenant_id,
        row.id,
    )
    assert result["calculation_id"] == row.id

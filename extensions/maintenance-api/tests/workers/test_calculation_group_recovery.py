from __future__ import annotations

import pytest
from app.models.enums import CalculationStatus
from app.services.calculation_group_service import (
    CalculationGroupService,
)
from app.workers.calculation_group_executor import (
    CalculationGroupObserver,
)
from app.workers.recovery import recover_interrupted_calculations
from app.workers.task_registry import group_registry, registry
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.services.test_calculation_group_service import (
    add_version,
    service_with_snapshot,
)


def test_recovery_requeues_pending_and_interrupts_running_children(
    session: Session,
    actor_contributor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service: CalculationGroupService = service_with_snapshot(
        monkeypatch
    )
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "WEIBULL:MONTE_CARLO",
        ],
        idempotency_key="recovery-group",
    )
    running = group.child("WEIBULL:ANALYTICAL")
    pending = group.child("WEIBULL:MONTE_CARLO")
    running.calculation.status = CalculationStatus.RUNNING
    session.commit()
    queued: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "app.workers.recovery.calculation_group_executor.submit",
        lambda tenant_id, child_id: (
            queued.append((tenant_id, child_id)) or True
        ),
    )

    recovered = recover_interrupted_calculations(session)

    assert recovered == 1
    session.expire_all()
    assert running.calculation.status is CalculationStatus.INTERRUPTED
    assert queued == [
        (actor_contributor.tenant_id, pending.id)
    ]


def test_group_observer_persists_status_with_lifecycle_event(
    session: Session,
    actor_contributor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    service: CalculationGroupService = service_with_snapshot(
        monkeypatch
    )
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
        ],
        idempotency_key="observer-group",
    )
    child = group.current_children[0]
    observer = CalculationGroupObserver(
        actor_contributor.tenant_id,
        group.id,
        child.id,
    )
    child.calculation.status = CalculationStatus.RUNNING
    session.flush()
    observer.started(session, child.calculation)
    session.commit()

    child.calculation.status = CalculationStatus.SUCCEEDED
    session.flush()
    observer.completed(session, child.calculation)
    session.commit()

    refreshed = service.get(
        session,
        actor_contributor,
        group.id,
    )
    events = service.events(
        session,
        actor_contributor,
        group.id,
    )
    assert refreshed.status.value == "COMPLETED"
    assert "child.started" in {
        event.event_type for event in events
    }
    assert "child.completed" in {
        event.event_type for event in events
    }


def test_application_shutdown_closes_group_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import create_app

    calls: list[bool] = []
    monkeypatch.setattr(
        "app.main.calculation_group_executor.shutdown",
        lambda wait=False: calls.append(wait),
    )

    with TestClient(create_app()):
        pass

    assert calls == [False]


def test_group_and_single_calculation_registries_are_isolated(
) -> None:
    key = ("tenant-a", 73)
    try:
        assert registry.register(key) is True
        assert group_registry.register(key) is True
        assert registry.register(key) is False
        assert group_registry.register(key) is False
    finally:
        registry.unregister(key)
        group_registry.unregister(key)

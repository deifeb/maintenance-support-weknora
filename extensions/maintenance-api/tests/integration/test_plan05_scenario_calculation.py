from __future__ import annotations

from collections.abc import Callable

import pytest
from app.models import SparePart
from app.models.enums import CalculationStatus
from app.security.actor import ActorContext, MaintenanceRole
from app.services.calculation_group_service import (
    CalculationGroupService,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.services.test_calculation_group_service import (
    add_item_result,
    add_version,
    service_with_snapshot,
)


def test_mixed_candidate_workflow_resumes_retries_and_persists_decisions(
    client: TestClient,
    session: Session,
    actor_contributor: ActorContext,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service: CalculationGroupService = service_with_snapshot(
        monkeypatch
    )
    version = add_version(
        session,
        actor_contributor.tenant_id,
    )
    group = service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
            "BINOMIAL:ANALYTICAL",
            "EXPONENTIAL:ANALYTICAL",
        ],
        idempotency_key="integration-mixed-group",
    )
    spare_a = SparePart(
        tenant_id=actor_contributor.tenant_id,
        code="SP-INTEGRATION-A",
        name="Integration spare A",
        unit="piece",
    )
    spare_b = SparePart(
        tenant_id=actor_contributor.tenant_id,
        code="SP-INTEGRATION-B",
        name="Integration spare B",
        unit="piece",
    )
    session.add_all([spare_a, spare_b])
    session.flush()

    primary = group.child("WEIBULL:ANALYTICAL")
    secondary = group.child("BINOMIAL:ANALYTICAL")
    failed = group.child("EXPONENTIAL:ANALYTICAL")
    add_item_result(
        session,
        primary,
        spare_a,
        quantity="40",
    )
    add_item_result(
        session,
        secondary,
        spare_b,
        quantity="22",
    )
    failed.calculation.status = CalculationStatus.FAILED
    for child in (primary, secondary, failed):
        service.group_repository.append_event(
            session,
            actor_contributor.tenant_id,
            group.id,
            child_id=child.id,
            event_type=(
                "child.failed"
                if child is failed
                else "child.completed"
            ),
            payload={
                "calculation_id": child.calculation_id,
                "status": child.calculation.status.value,
            },
        )
    session.commit()
    group = service.refresh_status(
        session,
        actor_contributor,
        group.id,
    )
    assert group.status.value == "PARTIALLY_COMPLETED"

    resume_cursor = group.last_event_sequence - 2
    streamed = client.get(
        (
            "/api/v1/demand/calculation-groups/"
            f"{group.id}/events/stream"
        ),
        params={"last_event_sequence": resume_cursor},
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
    )
    assert streamed.status_code == 200
    assert f"id: {resume_cursor + 1}" in streamed.text
    assert ": heartbeat" not in streamed.text

    successful_ids = {
        primary.candidate_key: primary.id,
        secondary.candidate_key: secondary.id,
    }
    retried = service.retry_failed(
        session,
        actor_contributor,
        group.id,
        idempotency_key="integration-retry-failed",
    )
    assert {
        retried.child(key).id
        for key in successful_ids
    } == set(successful_ids.values())
    retried_child = retried.child(
        "EXPONENTIAL:ANALYTICAL"
    )
    assert retried_child.id != failed.id
    assert retried_child.attempt_number == 2

    add_item_result(
        session,
        retried_child,
        spare_a,
        quantity="38",
    )
    service.group_repository.append_event(
        session,
        actor_contributor.tenant_id,
        group.id,
        child_id=retried_child.id,
        event_type="child.completed",
        payload={
            "calculation_id": retried_child.calculation_id,
            "status": "SUCCEEDED",
        },
    )
    session.commit()
    group = service.refresh_status(
        session,
        actor_contributor,
        group.id,
    )
    assert group.status.value == "COMPLETED"

    comparison = service.comparison(
        session,
        actor_contributor,
        group.id,
    )
    assert {
        row.spare_part_id
        for row in comparison.rows
    } == {spare_a.id, spare_b.id}
    row_b = next(
        row
        for row in comparison.rows
        if row.spare_part_id == spare_b.id
    )
    assert (
        row_b.candidates[
            "EXPONENTIAL:ANALYTICAL"
        ].status
        == "NO_RESULT"
    )

    for row in comparison.rows:
        selected = next(
            cell
            for cell in row.candidates.values()
            if cell.child_id == row.system_child_id
        )
        assert selected.recommended_quantity is not None
        service.save_decision(
            session,
            actor_contributor,
            group.id,
            spare_part_id=row.spare_part_id,
            expected_version=0,
            selected_child_id=row.system_child_id,
            final_quantity=selected.recommended_quantity,
            reason=None,
        )

    persisted = service.comparison(
        session,
        actor_contributor,
        group.id,
    )
    assert all(
        row.decision is not None
        and row.decision.version == 1
        for row in persisted.rows
    )

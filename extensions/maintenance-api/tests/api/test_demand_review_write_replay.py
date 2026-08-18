from __future__ import annotations

from typing import Any

from app.models import (
    CalculationGroup,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.models.enums import CalculationGroupStatus, DemandListStatus
from app.repositories.demand_list_repository import DemandListRepository
from app.security.dependencies import get_actor
from sqlalchemy.orm import Session

PREFIX = "/api/v1/reviews/demand-lists"
RUN_MARKER = "I2_HTTP_RUN_EXACT_REPLAY_MISSING"
DECIDE_MARKER = "I2_HTTP_DECIDE_EXACT_REPLAY_MISSING"
BATCH_MARKER = "I2_HTTP_BATCH_EXACT_REPLAY_MISSING"


def _source(session: Session, tenant_id: str, suffix: str):
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-HTTP-REPLAY-{suffix}",
        name=f"HTTP replay scenario {suffix}",
    )
    session.add(template)
    session.flush()

    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-HTTP-REPLAY-{suffix}",
        version_name=f"HTTP replay version {suffix}",
    )
    session.add(version)
    session.flush()

    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=version.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id=f"user-{suffix}",
        created_by_request_id=f"request-{suffix}",
    )
    session.add(group)
    session.flush()

    source = DemandListRepository().create_version(
        session,
        tenant_id,
        {
            "name": f"HTTP replay source {suffix}",
            "scenario_version_id": version.id,
            "calculation_group_id": group.id,
            "status": DemandListStatus.PUBLISHED,
            "is_current": True,
            "created_by_user_id": f"user-{suffix}",
            "created_by_request_id": f"request-{suffix}",
        },
    )
    source.status = DemandListStatus.PUBLISHED
    source.is_current = True
    session.commit()
    session.refresh(source)
    return source


def _use_actor(client, actor) -> None:
    client.app.dependency_overrides[get_actor] = lambda: actor


def _command_view(response) -> dict[str, Any]:
    assert response.status_code in {200, 201}
    body = response.json()
    assert body["success"] is True
    return {"data": body["data"], "version": body["meta"]["version"]}


def _run_review(client, source, *, key: str):
    payload = {"expected_source_version": source.version}
    response = client.post(
        f"{PREFIX}/{source.id}/run",
        headers={"Idempotency-Key": key},
        json=payload,
    )
    return payload, _command_view(response)


def _pending_finding(review_data: dict[str, Any]) -> dict[str, Any]:
    return next(
        finding
        for finding in review_data["findings"]
        if finding["decision_status"] == "PENDING"
    )


def _single_decision(
    client,
    review_data: dict[str, Any],
    finding: dict[str, Any],
    *,
    key: str,
    action: str,
):
    payload = {
        "expected_review_version": review_data["version"],
        "expected_finding_version": finding["version"],
        "action": action,
    }
    response = client.put(
        f"{PREFIX}/{review_data['id']}/findings/{finding['id']}/decision",
        headers={"Idempotency-Key": key},
        json=payload,
    )
    return payload, _command_view(response)


def _batch_decision(
    client,
    review_data: dict[str, Any],
    finding: dict[str, Any],
    *,
    key: str,
    action: str,
):
    payload = {
        "expected_review_version": review_data["version"],
        "decisions": [
            {
                "finding_id": finding["id"],
                "expected_finding_version": finding["version"],
                "action": action,
            }
        ],
    }
    response = client.post(
        f"{PREFIX}/{review_data['id']}/batch-decisions",
        headers={"Idempotency-Key": key},
        json=payload,
    )
    return payload, _command_view(response)


def _finding_by_id(
    review_data: dict[str, Any],
    finding_id: int,
) -> dict[str, Any]:
    return next(
        finding
        for finding in review_data["findings"]
        if finding["id"] == finding_id
    )


def test_run_http_replay_returns_original_public_response_after_later_decision(
    client,
    session: Session,
    actor_admin,
) -> None:
    _use_actor(client, actor_admin)
    source = _source(session, actor_admin.tenant_id, "RUN")

    run_payload, first_run = _run_review(
        client,
        source,
        key="readiness-red-http-run",
    )
    finding = _pending_finding(first_run["data"])

    _single_decision(
        client,
        first_run["data"],
        finding,
        key="readiness-red-http-run-later-decision",
        action="REJECTED",
    )

    replay = _command_view(
        client.post(
            f"{PREFIX}/{source.id}/run",
            headers={"Idempotency-Key": "readiness-red-http-run"},
            json=run_payload,
        )
    )

    assert replay == first_run, (
        f"{RUN_MARKER}: replaying the RUN command after a later "
        "review mutation must return the original public response"
    )


def test_single_decision_http_replay_returns_original_public_response(
    client,
    session: Session,
    actor_admin,
) -> None:
    _use_actor(client, actor_admin)
    source = _source(session, actor_admin.tenant_id, "DECIDE")

    _, initial = _run_review(
        client,
        source,
        key="readiness-red-http-decide-run",
    )
    finding = _pending_finding(initial["data"])

    first_payload, first_decision = _single_decision(
        client,
        initial["data"],
        finding,
        key="readiness-red-http-decide",
        action="REJECTED",
    )

    current_finding = _finding_by_id(
        first_decision["data"],
        finding["id"],
    )
    _single_decision(
        client,
        first_decision["data"],
        current_finding,
        key="readiness-red-http-decide-later",
        action="ACCEPTED",
    )

    replay = _command_view(
        client.put(
            f"{PREFIX}/{initial['data']['id']}/findings/"
            f"{finding['id']}/decision",
            headers={"Idempotency-Key": "readiness-red-http-decide"},
            json=first_payload,
        )
    )

    assert replay == first_decision, (
        f"{DECIDE_MARKER}: replaying DECIDE_FINDING after a later "
        "redecision must return the original public response"
    )


def test_batch_decision_http_replay_returns_original_public_response(
    client,
    session: Session,
    actor_admin,
) -> None:
    _use_actor(client, actor_admin)
    source = _source(session, actor_admin.tenant_id, "BATCH")

    _, initial = _run_review(
        client,
        source,
        key="readiness-red-http-batch-run",
    )
    finding = _pending_finding(initial["data"])

    batch_payload, first_batch = _batch_decision(
        client,
        initial["data"],
        finding,
        key="readiness-red-http-batch",
        action="REJECTED",
    )

    current_finding = _finding_by_id(
        first_batch["data"],
        finding["id"],
    )
    _single_decision(
        client,
        first_batch["data"],
        current_finding,
        key="readiness-red-http-batch-later",
        action="ACCEPTED",
    )

    replay = _command_view(
        client.post(
            f"{PREFIX}/{initial['data']['id']}/batch-decisions",
            headers={"Idempotency-Key": "readiness-red-http-batch"},
            json=batch_payload,
        )
    )

    assert replay == first_batch, (
        f"{BATCH_MARKER}: replaying BATCH_DECIDE after a later "
        "review mutation must return the original public response"
    )
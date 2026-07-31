from __future__ import annotations

from collections.abc import Callable

from app.models import DemandScenarioTemplate, DemandScenarioVersion
from app.models.enums import (
    CalculationStatus,
    DemandExecutionMode,
    ReliabilityModelType,
    ScenarioVersionStatus,
)
from app.schemas.model_recommendation import (
    CandidateRecommendation,
    ModelRecommendationSet,
)
from app.security.actor import MaintenanceRole
from app.services.calculation_group_service import (
    calculation_group_service,
)
from app.services.model_recommendation_service import (
    model_recommendation_service,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.services.test_calculation_group_service import (
    compatible_snapshot,
)


def recommendation_result() -> ModelRecommendationSet:
    primary = CandidateRecommendation(
        candidate_key="WEIBULL:ANALYTICAL",
        reliability_model=ReliabilityModelType.WEIBULL,
        execution_mode=DemandExecutionMode.ANALYTICAL,
        applicable=True,
        score=95,
        reasons=["weibull_parameters_available"],
        missing_requirements=[],
        parameter_sources={
            "weibull_shape": "scenario_snapshot",
        },
        risk="LOW",
        rule_version="MODEL-RECOMMENDATION-1",
    )
    return ModelRecommendationSet(
        scenario_version_id=7,
        primary=primary,
        items=[primary],
        rule_version="MODEL-RECOMMENDATION-1",
    )


def test_contributor_gets_stable_model_recommendation_response(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        model_recommendation_service,
        "recommend",
        lambda *args, **kwargs: recommendation_result(),
    )

    response = client.post(
        "/api/v1/demand/model-recommendations",
        headers=internal_auth_headers(),
        json={"scenario_version_id": 7},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["primary"]["candidate_key"] == (
        "WEIBULL:ANALYTICAL"
    )
    assert data["primary"]["reliability_model"] == "WEIBULL"
    assert data["primary"]["execution_mode"] == "ANALYTICAL"
    assert data["rule_version"] == "MODEL-RECOMMENDATION-1"
    assert "tenant_id" not in data


def test_viewer_cannot_request_model_recommendations(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    response = client.post(
        "/api/v1/demand/model-recommendations",
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
        json={"scenario_version_id": 7},
    )

    assert response.status_code == 403


def test_model_recommendation_request_rejects_tenant_fields(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    response = client.post(
        "/api/v1/demand/model-recommendations",
        headers=internal_auth_headers(),
        json={
            "scenario_version_id": 7,
            "tenant_id": "tenant-b",
        },
    )

    assert response.status_code == 422


def test_create_list_and_get_calculation_group(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
) -> None:
    template = DemandScenarioTemplate(
        tenant_id="tenant-a",
        code="GROUP-API",
        name="Group API",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id="tenant-a",
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=ScenarioVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.commit()
    monkeypatch.setattr(
        calculation_group_service.calculation_service,
        "build_snapshot",
        lambda *args, **kwargs: (compatible_snapshot(), []),
    )
    monkeypatch.setattr(
        (
            "app.api.v1.demand.calculation_groups."
            "calculation_group_executor.submit"
        ),
        lambda *args, **kwargs: True,
    )
    headers = {
        **internal_auth_headers(),
        "Idempotency-Key": "api-group-create",
    }

    created = client.post(
        "/api/v1/demand/calculation-groups",
        headers=headers,
        json={
            "scenario_version_id": version.id,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "selected_candidate_keys": [
                "WEIBULL:ANALYTICAL",
                "WEIBULL:MONTE_CARLO",
            ],
        },
    )

    assert created.status_code == 201
    created_data = created.json()["data"]
    assert len(created_data["current_children"]) == 2
    assert {
        item["calculation_status"]
        for item in created_data["current_children"]
    } == {"PENDING"}

    listed = client.get(
        "/api/v1/demand/calculation-groups",
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    detail = client.get(
        (
            "/api/v1/demand/calculation-groups/"
            f"{created_data['id']}"
        ),
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == created_data["id"]


def test_group_create_requires_idempotency_key(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    response = client.post(
        "/api/v1/demand/calculation-groups",
        headers=internal_auth_headers(),
        json={
            "scenario_version_id": 1,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "selected_candidate_keys": [
                "WEIBULL:ANALYTICAL",
            ],
        },
    )

    assert response.status_code == 422


def test_events_resume_after_sequence(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
) -> None:
    template = DemandScenarioTemplate(
        tenant_id="tenant-a",
        code="GROUP-EVENT-API",
        name="Group event API",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id="tenant-a",
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=ScenarioVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.commit()
    monkeypatch.setattr(
        calculation_group_service.calculation_service,
        "build_snapshot",
        lambda *args, **kwargs: (compatible_snapshot(), []),
    )
    monkeypatch.setattr(
        (
            "app.api.v1.demand.calculation_groups."
            "calculation_group_executor.submit"
        ),
        lambda *args, **kwargs: True,
    )
    headers = {
        **internal_auth_headers(),
        "Idempotency-Key": "api-event-create",
    }
    created = client.post(
        "/api/v1/demand/calculation-groups",
        headers=headers,
        json={
            "scenario_version_id": version.id,
            "primary_candidate_key": "WEIBULL:ANALYTICAL",
            "selected_candidate_keys": [
                "WEIBULL:ANALYTICAL",
                "WEIBULL:MONTE_CARLO",
            ],
        },
    ).json()["data"]

    response = client.get(
        (
            "/api/v1/demand/calculation-groups/"
            f"{created['id']}/events"
        ),
        params={"after_sequence": 1},
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
    )

    assert response.status_code == 200
    events = response.json()["data"]
    assert events
    assert all(item["sequence"] > 1 for item in events)
    assert [item["sequence"] for item in events] == sorted(
        item["sequence"] for item in events
    )


def test_terminal_event_stream_replays_and_closes(
    client: TestClient,
    session: Session,
    actor_contributor,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
) -> None:
    template = DemandScenarioTemplate(
        tenant_id="tenant-a",
        code="GROUP-SSE-API",
        name="Group SSE API",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id="tenant-a",
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=ScenarioVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.flush()
    monkeypatch.setattr(
        calculation_group_service.calculation_service,
        "build_snapshot",
        lambda *args, **kwargs: (compatible_snapshot(), []),
    )
    group = calculation_group_service.create(
        session,
        actor_contributor,
        scenario_version_id=version.id,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        selected_candidate_keys=[
            "WEIBULL:ANALYTICAL",
        ],
        idempotency_key="sse-terminal",
    )
    group.current_children[
        0
    ].calculation.status = CalculationStatus.SUCCEEDED
    session.commit()
    group = calculation_group_service.refresh_status(
        session,
        actor_contributor,
        group.id,
    )

    response = client.get(
        (
            "/api/v1/demand/calculation-groups/"
            f"{group.id}/events/stream"
        ),
        params={"last_event_sequence": 1},
        headers=internal_auth_headers(
            role=MaintenanceRole.VIEWER,
        ),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert "id: 2" in response.text
    assert "event: group.status_changed" in response.text

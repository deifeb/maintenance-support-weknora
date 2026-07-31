from __future__ import annotations

from collections.abc import Callable

from app.models.enums import (
    DemandExecutionMode,
    ReliabilityModelType,
)
from app.schemas.model_recommendation import (
    CandidateRecommendation,
    ModelRecommendationSet,
)
from app.security.actor import MaintenanceRole
from app.services.model_recommendation_service import (
    model_recommendation_service,
)
from fastapi.testclient import TestClient


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

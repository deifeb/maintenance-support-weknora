from __future__ import annotations

from collections.abc import Callable

from app.models.enums import (
    AIBlockingLevel,
    AIReviewFindingStatus,
    AISeverity,
)
from app.repositories.ai_review_repository import (
    ai_review_repository,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_demand_review_api_persists_findings(
    client: TestClient,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    contributor_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="review-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    viewer_headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="review-viewer",
        role=MaintenanceRole.VIEWER,
    )

    response = client.post(
        "/api/v1/ai/reviews/demand-lists",
        headers=contributor_headers,
        json={
            "items": [
                {
                    "spare_part_id": 10,
                    "recommended_spare_quantity": (
                        "8"
                    ),
                    "usable_inventory": "3",
                    "net_demand_gap": "5",
                    "inventory_coverage_rate": (
                        "0.375"
                    ),
                    "selected_reliability_profile_id": 2,
                }
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["review_id"] > 0
    assert any(
        item["rule_code"] == "INV-001"
        for item in data["findings"]
    )

    read = client.get(
        f"/api/v1/ai/reviews/{data['review_id']}",
        headers=viewer_headers,
    )
    findings = client.get(
        (
            "/api/v1/ai/reviews/"
            f"{data['review_id']}/findings"
        ),
        headers=viewer_headers,
    )

    assert read.status_code == 200
    assert findings.status_code == 200
    assert any(
        item["rule_code"] == "INV-001"
        for item
        in findings.json()["data"]
    )

def _review_with_finding(
    session: Session,
    *,
    tenant_id: str,
    severity: AISeverity,
):
    run = ai_review_repository.create_run(
        session,
        tenant_id,
        input_snapshot={},
    )
    finding = ai_review_repository.add_finding(
        session,
        tenant_id,
        run.id,
        {
            "rule_code": "RULE-075C",
            "rule_version": "1.0",
            "category": "TENANT_BOUNDARY",
            "severity": severity,
            "blocking_level": (
                AIBlockingLevel.NONE
            ),
            "finding_title": (
                "Task 7.5C finding"
            ),
            "deterministic_message": (
                "Task 7.5C review finding"
            ),
            "suggested_actions_json": [],
        },
    )
    session.commit()
    session.refresh(run)
    session.refresh(finding)
    return run, finding


def test_foreign_tenant_cannot_read_review_or_findings(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    run, _ = _review_with_finding(
        session,
        tenant_id="tenant-review-owner",
        severity=AISeverity.WARNING,
    )
    headers = internal_auth_headers(
        tenant_id="tenant-review-foreign",
        user_id="foreign-viewer",
        role=MaintenanceRole.VIEWER,
    )

    review = client.get(
        f"/api/v1/ai/reviews/{run.id}",
        headers=headers,
    )
    findings = client.get(
        (
            f"/api/v1/ai/reviews/{run.id}"
            "/findings"
        ),
        headers=headers,
    )

    assert review.status_code == 404
    assert findings.status_code == 404


def test_foreign_tenant_cannot_transition_finding(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    _, finding = _review_with_finding(
        session,
        tenant_id="tenant-review-owner",
        severity=AISeverity.WARNING,
    )
    original_status = finding.status

    response = client.post(
        (
            "/api/v1/ai/reviews/findings/"
            f"{finding.id}/resolve"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-review-foreign",
            user_id="foreign-contributor",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        json={"comment": "foreign mutation"},
    )

    assert response.status_code == 404
    session.expire_all()
    reloaded = ai_review_repository.get_finding(
        session,
        "tenant-review-owner",
        finding.id,
    )
    assert reloaded is not None
    assert reloaded.status is original_status
    assert reloaded.resolved_by is None
    assert reloaded.resolution_comment is None


def test_contributor_resolves_ordinary_finding_with_actor_identity(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    _, finding = _review_with_finding(
        session,
        tenant_id="tenant-review",
        severity=AISeverity.WARNING,
    )

    response = client.post(
        (
            "/api/v1/ai/reviews/findings/"
            f"{finding.id}/resolve"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-review",
            user_id="review-contributor",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        json={"comment": "resolved by actor"},
    )

    assert response.status_code == 200
    session.expire_all()
    reloaded = ai_review_repository.get_finding(
        session,
        "tenant-review",
        finding.id,
    )
    assert reloaded is not None
    assert (
        reloaded.status
        is AIReviewFindingStatus.RESOLVED
    )
    assert (
        reloaded.resolved_by
        == "review-contributor"
    )
    assert (
        reloaded.resolution_comment
        == "resolved by actor"
    )
    assert reloaded.resolved_at is not None


def test_contributor_cannot_accept_critical_risk_and_row_is_unchanged(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    _, finding = _review_with_finding(
        session,
        tenant_id="tenant-review",
        severity=AISeverity.CRITICAL,
    )
    original_status = finding.status

    response = client.post(
        (
            "/api/v1/ai/reviews/findings/"
            f"{finding.id}/accept-risk"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-review",
            user_id="review-contributor",
            role=MaintenanceRole.CONTRIBUTOR,
        ),
        json={"comment": "accept critical"},
    )

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    session.expire_all()
    reloaded = ai_review_repository.get_finding(
        session,
        "tenant-review",
        finding.id,
    )
    assert reloaded is not None
    assert reloaded.status is original_status
    assert reloaded.resolved_by is None
    assert reloaded.resolution_comment is None
    assert reloaded.resolved_at is None


def test_admin_critical_accept_risk_requires_confirmation_without_mutation(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[
        ...,
        dict[str, str],
    ],
) -> None:
    _, finding = _review_with_finding(
        session,
        tenant_id="tenant-review",
        severity=AISeverity.CRITICAL,
    )
    original_status = finding.status

    response = client.post(
        (
            "/api/v1/ai/reviews/findings/"
            f"{finding.id}/accept-risk"
        ),
        headers=internal_auth_headers(
            tenant_id="tenant-review",
            user_id="review-admin",
            role=MaintenanceRole.ADMIN,
        ),
        json={"comment": "admin accepts"},
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == (
            "CRITICAL_RISK_"
            "CONFIRMATION_REQUIRED"
        )
    )
    session.expire_all()
    reloaded = ai_review_repository.get_finding(
        session,
        "tenant-review",
        finding.id,
    )
    assert reloaded is not None
    assert reloaded.status is original_status
    assert reloaded.resolved_by is None
    assert reloaded.resolution_comment is None
    assert reloaded.resolved_at is None

from __future__ import annotations

from collections.abc import Callable

from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient


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

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from app.models import DemandCalculation, EquipmentModel, SparePart
from app.models.enums import (
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
)
from app.security.actor import MaintenanceRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def seed_api_summary(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> None:
    now = datetime.now(timezone.utc)
    session.add_all(
        (
            EquipmentModel(
                tenant_id=tenant_id,
                code=f"API-EQ-{suffix}",
                name=f"API Equipment {suffix}",
                is_active=True,
            ),
            SparePart(
                tenant_id=tenant_id,
                code=f"API-SP-{suffix}",
                name=f"API Spare {suffix}",
                unit="piece",
                is_active=True,
            ),
            DemandCalculation(
                tenant_id=tenant_id,
                calculation_code=f"API-CALC-{suffix}",
                calculation_name=f"API Calculation {suffix}",
                execution_type=(
                    CalculationExecutionType.ASYNCHRONOUS
                ),
                requested_mode=DemandExecutionMode.AUTO,
                status=CalculationStatus.RUNNING,
                progress_percent=Decimal("25"),
                input_snapshot_json={},
                input_snapshot_hash=(suffix.lower() * 64)[:64],
                inventory_snapshot_at=now,
                submitted_at=now,
            ),
        )
    )
    session.commit()


def test_dashboard_api_returns_one_aggregate_response(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    seed_api_summary(session, "t-1", "A")
    seed_api_summary(session, "t-2", "B")

    response = client.get(
        "/api/v1/dashboard/summary",
        headers=internal_auth_headers(
            tenant_id="t-1",
            user_id="dashboard-viewer",
            role=MaintenanceRole.VIEWER,
            request_id="dashboard-request",
        ),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    body = response.json()
    assert body["meta"] == {
        "request_id": "dashboard-request",
        "tenant_id": "t-1",
        "version": None,
    }
    assert set(body["data"]) >= {
        "metrics",
        "recent_tasks",
        "risk_items",
        "risk_distribution",
        "generated_at",
    }

    metrics = {
        metric["key"]: metric["value"]
        for metric in body["data"]["metrics"]
    }
    assert metrics["active_equipment_count"] == 1
    assert metrics["active_spare_part_count"] == 1
    assert metrics["running_calculation_count"] == 1
    assert all(
        "B" not in task["title"]
        for task in body["data"]["recent_tasks"]
    )


def test_dashboard_api_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401

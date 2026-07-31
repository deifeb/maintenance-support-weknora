from __future__ import annotations

from collections.abc import Callable

from app.models import ConfigurationVersion, EquipmentModel
from app.models.enums import ConfigurationStatus
from app.security.actor import MaintenanceRole
from app.services.ai_model_runtime import AIModelRuntime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _field(value: object) -> dict[str, object]:
    return {
        "value": value,
        "source": "USER_INPUT",
        "confidence": None,
        "risk": "LOW",
        "confirmed": True,
        "evidence_refs": [],
    }


def test_manual_rest_workflow_does_not_invoke_ai_runtime(
    client: TestClient,
    session: Session,
    internal_auth_headers: Callable[..., dict[str, str]],
    monkeypatch,
) -> None:
    async def unexpected_ai_call(*args, **kwargs):
        del args, kwargs
        raise AssertionError(
            "manual scenario workflow invoked AI runtime"
        )

    monkeypatch.setattr(
        AIModelRuntime,
        "complete_structured",
        unexpected_ai_call,
    )
    monkeypatch.setattr(
        AIModelRuntime,
        "complete_text",
        unexpected_ai_call,
    )

    equipment = EquipmentModel(
        tenant_id="tenant-a",
        code="EQ-MANUAL",
        name="Manual equipment",
    )
    session.add(equipment)
    session.flush()
    configuration = ConfigurationVersion(
        tenant_id="tenant-a",
        equipment_model_id=equipment.id,
        version_code="CFG-MANUAL",
        version_name="Manual configuration",
        status=ConfigurationStatus.PUBLISHED,
        is_active=True,
    )
    session.add(configuration)
    session.commit()

    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="manual-user",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    created_response = client.post(
        "/api/v1/demand/scenario-drafts",
        headers=headers,
        json={
            "title": "Manual readiness",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()["data"]
    draft = created["draft"]
    draft["fields"].update(
        {
            "mission_code": _field("SC-MANUAL"),
            "start_at": _field(
                "2026-08-01T00:00:00Z"
            ),
            "end_at": _field(
                "2026-08-31T00:00:00Z"
            ),
            "priority": _field("HIGH"),
            "equipment_model_id": _field(
                equipment.id
            ),
            "configuration_version_id": _field(
                configuration.id
            ),
            "fleet_groups": _field(
                [
                    {
                        "client_key": "fleet-a",
                        "group_code": "FLEET-A",
                        "group_name": "Fleet A",
                        "configuration_version_id": (
                            configuration.id
                        ),
                        "initial_quantity": 10,
                        "age_groups": [],
                    }
                ]
            ),
            "stages": _field(
                [
                    {
                        "client_key": "stage-a",
                        "stage_code": "STAGE-A",
                        "stage_name": "Stage A",
                        "stage_order": 1,
                        "duration_hours": "100",
                        "fleet_usages": [
                            {
                                "fleet_group_key": (
                                    "fleet-a"
                                ),
                                "active_quantity": 10,
                            }
                        ],
                        "shocks": [],
                    }
                ]
            ),
            "reliability_profiles": _field(
                [{"status": "confirmed"}]
            ),
            "service_level": _field("0.95"),
            "execution_preference": _field("AUTO"),
            "missing_parameter_policy": _field(
                "WARN_AND_SKIP"
            ),
        }
    )

    saved_response = client.put(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}"
        ),
        headers=headers,
        json={
            "expected_version": created["version"],
            "draft": draft,
        },
    )
    assert saved_response.status_code == 200
    saved = saved_response.json()["data"]
    assert saved["blocking_fields"] == []

    materialized = client.post(
        (
            "/api/v1/demand/scenario-drafts/"
            f"{created['session_id']}/materialize"
        ),
        headers={
            **headers,
            "Idempotency-Key": "manual-no-ai",
        },
        json={"expected_version": saved["version"]},
    )

    assert materialized.status_code == 200
    assert (
        materialized.json()["data"]["status"]
        == "DRAFT"
    )

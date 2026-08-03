from app.models import (
    ConfigurationVersion,
    EquipmentModel,
)
from app.models.enums import ConfigurationStatus
from app.schemas.scenario_draft import ScenarioFieldState
from app.security.actor import ActorContext
from app.services.scenario_draft_service import (
    ScenarioDraftService,
)
from sqlalchemy.orm import Session


def _published_configuration(
    session: Session,
    tenant_id: str,
) -> ConfigurationVersion:
    equipment = EquipmentModel(
        tenant_id=tenant_id,
        code="EQ-DRAFT",
        name="Draft equipment",
    )
    session.add(equipment)
    session.flush()
    configuration = ConfigurationVersion(
        tenant_id=tenant_id,
        equipment_model_id=equipment.id,
        version_code="CFG-DRAFT",
        version_name="Draft configuration",
        status=ConfigurationStatus.PUBLISHED,
        is_active=True,
    )
    session.add(configuration)
    session.commit()
    return configuration


def _field(value: object) -> ScenarioFieldState:
    return ScenarioFieldState(
        value=value,
        source="USER_INPUT",
        risk="LOW",
        confirmed=True,
    )


def complete_scenario_draft(
    session: Session,
    actor: ActorContext,
    *,
    code: str = "SC-DRAFT",
):
    configuration = _published_configuration(
        session,
        actor.tenant_id,
    )
    service = ScenarioDraftService()
    created = service.create(
        session,
        actor,
        title="Fleet readiness",
        sensitivity_level="INTERNAL",
    )
    payload = created.draft.model_copy(deep=True)
    payload.fields.update(
        {
            "mission_code": _field(code),
            "start_at": _field("2026-08-01T00:00:00Z"),
            "end_at": _field("2026-08-31T00:00:00Z"),
            "priority": _field("HIGH"),
            "equipment_model_id": _field(
                configuration.equipment_model_id
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
                        "age_groups": [
                            {
                                "group_code": "AGE-A",
                                "group_name": "Age A",
                                "distribution_type": "FIXED",
                                "proportion": "1",
                                "fixed_hours": "100",
                            }
                        ],
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
                                "fleet_group_key": "fleet-a",
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
            "version_code": _field("V1"),
            "version_name": _field(
                "Fleet readiness V1"
            ),
        }
    )
    saved = service.save(
        session,
        actor,
        created.session_id,
        expected_version=created.version,
        draft=payload,
    )
    assert saved.blocking_fields == []
    return saved

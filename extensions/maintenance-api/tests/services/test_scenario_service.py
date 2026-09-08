from decimal import Decimal
from typing import Callable

from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    Part,
    SparePart,
)
from app.models.enums import ConfigurationStatus
from app.schemas.demand_scenario import (
    FleetGroupCreate,
    FleetUsageCreate,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioVersionCreate,
)
from app.security.actor import ActorContext
from app.services.scenario_service import scenario_service
from sqlalchemy.orm import Session


def _master_data(
    session: Session,
    tenant_id: str,
) -> ConfigurationVersion:
    equipment = EquipmentModel(
        tenant_id=tenant_id,
        code="EQ-SC",
        name="Scenario equipment",
    )
    part = Part(
        tenant_id=tenant_id,
        code="PT-SC",
        name="Part",
    )
    spare = SparePart(
        tenant_id=tenant_id,
        code="SP-SC",
        name="Spare",
        unit="piece",
    )
    session.add_all([equipment, part, spare])
    session.flush()
    version = ConfigurationVersion(
        tenant_id=tenant_id,
        equipment_model_id=equipment.id,
        version_code="V1",
        version_name="Version",
        status=ConfigurationStatus.PUBLISHED,
        is_active=True,
    )
    session.add(version)
    session.flush()
    session.add(
        ConfigurationItem(
            tenant_id=tenant_id,
            configuration_version_id=version.id,
            item_code="I1",
            part_id=part.id,
            spare_part_id=spare.id,
            install_quantity=1,
            replacement_ratio=1,
        )
    )
    session.commit()
    return version


def test_scenario_can_publish_after_required_children_exist(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    config = _master_data(
        session,
        actor.tenant_id,
    )
    template = scenario_service.create_template(
        session,
        actor,
        ScenarioTemplateCreate(
            code="SC-1",
            name="Scenario",
        ),
    )
    version = scenario_service.create_version(
        session,
        actor,
        template.id,
        ScenarioVersionCreate(
            version_code="V1",
            version_name="Version",
        ),
    )
    stage = scenario_service.add_stage(
        session,
        actor,
        version.id,
        ScenarioStageCreate(
            stage_code="S1",
            stage_name="Training",
            stage_order=1,
            duration_hours=Decimal("100"),
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        actor,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="Fleet",
            configuration_version_id=config.id,
            initial_quantity=10,
        ),
    )
    scenario_service.add_fleet_usage(
        session,
        actor,
        stage.id,
        FleetUsageCreate(
            fleet_group_id=fleet.id,
            active_quantity=10,
        ),
    )
    validation = scenario_service.validate_version(
        session,
        actor,
        version.id,
    )
    assert validation.valid is True
    published = scenario_service.publish_version(
        session,
        actor,
        version.id,
    )
    assert published.status.value == "PUBLISHED"


def test_clone_rebuilds_children_as_draft(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    config = _master_data(
        session,
        actor.tenant_id,
    )
    template = scenario_service.create_template(
        session,
        actor,
        ScenarioTemplateCreate(
            code="SC-CLONE",
            name="Clone scenario",
        ),
    )
    version = scenario_service.create_version(
        session,
        actor,
        template.id,
        ScenarioVersionCreate(
            version_code="V1",
            version_name="Version 1",
        ),
    )
    stage = scenario_service.add_stage(
        session,
        actor,
        version.id,
        ScenarioStageCreate(
            stage_code="S1",
            stage_name="Training",
            stage_order=1,
            duration_hours=Decimal("100"),
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        actor,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="Fleet",
            configuration_version_id=config.id,
            initial_quantity=10,
        ),
    )
    scenario_service.add_fleet_usage(
        session,
        actor,
        stage.id,
        FleetUsageCreate(
            fleet_group_id=fleet.id,
            active_quantity=10,
        ),
    )
    clone = scenario_service.clone_version(
        session,
        actor,
        version.id,
        "V2",
        "Version 2",
    )
    full = scenario_service.get_version(
        session,
        actor,
        clone.id,
        full=True,
    )
    assert full.status.value == "DRAFT"
    assert full.tenant_id == actor.tenant_id
    assert len(full.stages) == 1
    assert len(full.fleet_groups) == 1
    assert full.stages[0].id != stage.id
    assert full.fleet_groups[0].id != fleet.id
    assert {
        full.tenant_id,
        full.stages[0].tenant_id,
        full.fleet_groups[0].tenant_id,
        full.stages[0].fleet_usages[0].tenant_id,
    } == {actor.tenant_id}

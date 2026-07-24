from decimal import Decimal

from app.models import ConfigurationItem, ConfigurationVersion, EquipmentModel, Part, SparePart
from app.models.enums import ConfigurationStatus
from app.schemas.demand_scenario import (
    FleetGroupCreate,
    FleetUsageCreate,
    ScenarioStageCreate,
    ScenarioTemplateCreate,
    ScenarioVersionCreate,
)
from app.services.scenario_service import scenario_service


def _master_data(session):
    equipment = EquipmentModel(code="EQ-SC", name="场景装备")
    part = Part(code="PT-SC", name="部件")
    spare = SparePart(code="SP-SC", name="器材", unit="件")
    session.add_all([equipment, part, spare])
    session.flush()
    version = ConfigurationVersion(
        equipment_model_id=equipment.id,
        version_code="V1",
        version_name="版本",
        status=ConfigurationStatus.PUBLISHED,
        is_active=True,
    )
    session.add(version)
    session.flush()
    session.add(
        ConfigurationItem(
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


def test_scenario_can_publish_after_required_children_exist(session):
    config = _master_data(session)
    template = scenario_service.create_template(
        session, ScenarioTemplateCreate(code="SC-1", name="场景")
    )
    version = scenario_service.create_version(
        session, template.id, ScenarioVersionCreate(version_code="V1", version_name="版本")
    )
    stage = scenario_service.add_stage(
        session,
        version.id,
        ScenarioStageCreate(
            stage_code="S1", stage_name="训练", stage_order=1, duration_hours=Decimal("100")
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="装备群",
            configuration_version_id=config.id,
            initial_quantity=10,
        ),
    )
    scenario_service.add_fleet_usage(
        session, stage.id, FleetUsageCreate(fleet_group_id=fleet.id, active_quantity=10)
    )
    validation = scenario_service.validate_version(session, version.id)
    assert validation.valid is True
    published = scenario_service.publish_version(session, version.id)
    assert published.status.value == "PUBLISHED"


def test_clone_rebuilds_children_as_draft(session):
    config = _master_data(session)
    template = scenario_service.create_template(
        session, ScenarioTemplateCreate(code="SC-CLONE", name="克隆场景")
    )
    version = scenario_service.create_version(
        session, template.id, ScenarioVersionCreate(version_code="V1", version_name="版本1")
    )
    stage = scenario_service.add_stage(
        session,
        version.id,
        ScenarioStageCreate(
            stage_code="S1", stage_name="训练", stage_order=1, duration_hours=Decimal("100")
        ),
    )
    fleet = scenario_service.add_fleet_group(
        session,
        version.id,
        FleetGroupCreate(
            group_code="F1",
            group_name="装备群",
            configuration_version_id=config.id,
            initial_quantity=10,
        ),
    )
    scenario_service.add_fleet_usage(
        session, stage.id, FleetUsageCreate(fleet_group_id=fleet.id, active_quantity=10)
    )
    clone = scenario_service.clone_version(session, version.id, "V2", "版本2")
    full = scenario_service.get_version(session, clone.id, full=True)
    assert full.status.value == "DRAFT"
    assert len(full.stages) == 1
    assert len(full.fleet_groups) == 1
    assert full.stages[0].id != stage.id
    assert full.fleet_groups[0].id != fleet.id

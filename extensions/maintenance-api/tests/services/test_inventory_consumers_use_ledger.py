from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.exceptions import ResourceInUseError
from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    InventoryBalance,
    InventoryLot,
    InventoryPolicy,
    Part,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import (
    ConfigurationStatus,
    CriticalityLevel,
    DemandExecutionMode,
    MissingParameterPolicy,
)
from app.security.actor import ActorContext
from app.services.ai_tool_adapters import get_inventory_snapshot
from app.services.demand_calculation_service import DemandCalculationService
from app.services.spare_part_service import spare_part_service
from app.services.warehouse_service import warehouse_service
from sqlalchemy import select
from sqlalchemy.orm import Session


def _seed_ledger_inventory(
    session: Session,
) -> tuple[SparePart, Warehouse]:
    equipment = EquipmentModel(
        tenant_id="tenant-a",
        code="EQ-LEDGER",
        name="Ledger equipment",
    )
    configuration = ConfigurationVersion(
        tenant_id="tenant-a",
        equipment_model=equipment,
        version_code="V1",
        version_name="Version 1",
        status=ConfigurationStatus.PUBLISHED,
    )
    part = Part(
        tenant_id="tenant-a",
        code="PART-LEDGER",
        name="Ledger part",
    )
    spare = SparePart(
        tenant_id="tenant-a",
        code="SP-LEDGER",
        name="Ledger spare",
        unit="piece",
        is_repairable=False,
    )
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-LEDGER",
        name="Ledger warehouse",
    )
    session.add_all((equipment, configuration, part, spare, warehouse))
    session.flush()
    session.add(
        ConfigurationItem(
            tenant_id="tenant-a",
            configuration_version_id=configuration.id,
            item_code="ITEM-LEDGER",
            part_id=part.id,
            spare_part_id=spare.id,
            install_quantity=Decimal("1"),
            replacement_ratio=Decimal("1"),
            criticality_level=CriticalityLevel.HIGH,
        )
    )

    shelf = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code="SHELF-A",
        name="Shelf A",
        location_type="SHELF",
    )
    overflow = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code="OVERFLOW-A",
        name="Overflow A",
        location_type="SHELF",
    )
    lot_one = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=spare.id,
        lot_code="LOT-A-1",
    )
    lot_two = InventoryLot(
        tenant_id="tenant-a",
        spare_part_id=spare.id,
        lot_code="LOT-A-2",
    )
    session.add_all((shelf, overflow, lot_one, lot_two))
    session.flush()
    session.add_all(
        (
            InventoryPolicy(
                tenant_id="tenant-a",
                warehouse_id=warehouse.id,
                spare_part_id=spare.id,
                safety_stock=Decimal("2"),
                reorder_point=Decimal("10"),
                maximum_stock=Decimal("30"),
            ),
            InventoryBalance(
                tenant_id="tenant-a",
                warehouse_id=warehouse.id,
                location_id=shelf.id,
                spare_part_id=spare.id,
                lot_id=lot_one.id,
                on_hand_quantity=Decimal("5"),
                reserved_quantity=Decimal("1"),
                damaged_quantity=Decimal("0"),
                quarantined_quantity=Decimal("0"),
                in_transit_quantity=Decimal("2"),
            ),
            InventoryBalance(
                tenant_id="tenant-a",
                warehouse_id=warehouse.id,
                location_id=overflow.id,
                spare_part_id=spare.id,
                lot_id=lot_two.id,
                on_hand_quantity=Decimal("7"),
                reserved_quantity=Decimal("0"),
                damaged_quantity=Decimal("1"),
                quarantined_quantity=Decimal("1"),
                in_transit_quantity=Decimal("3"),
            ),
        )
    )

    foreign_warehouse = Warehouse(
        tenant_id="tenant-b",
        code="WH-FOREIGN",
        name="Foreign warehouse",
    )
    session.add(foreign_warehouse)
    session.flush()
    foreign_location = WarehouseLocation(
        tenant_id="tenant-b",
        warehouse_id=foreign_warehouse.id,
        code="SHELF-B",
        name="Foreign shelf",
        location_type="SHELF",
    )
    session.add(foreign_location)
    session.flush()
    session.add(
        InventoryBalance(
            tenant_id="tenant-b",
            warehouse_id=foreign_warehouse.id,
            location_id=foreign_location.id,
            spare_part_id=spare.id,
            on_hand_quantity=Decimal("99"),
            reserved_quantity=Decimal("0"),
            damaged_quantity=Decimal("0"),
            quarantined_quantity=Decimal("0"),
            in_transit_quantity=Decimal("99"),
        )
    )
    session.commit()
    return spare, warehouse


def _scenario_version(configuration_version_id: int) -> SimpleNamespace:
    fleet = SimpleNamespace(
        group_code="FLEET-A",
        configuration_version_id=configuration_version_id,
        initial_quantity=1,
        stage_usages=[],
        age_groups=[],
    )
    return SimpleNamespace(
        id=901,
        stages=[],
        fleet_groups=[fleet],
        missing_parameter_policy=MissingParameterPolicy.FALLBACK,
        fallback_parameters_json={"failure_rate": "0.01"},
        default_service_level=Decimal("0.9"),
        default_initial_age_hours=Decimal("0"),
        execution_mode=DemandExecutionMode.ANALYTICAL,
        simulation_config_json={},
        formula_version="ledger-consumer-test",
        input_schema_version="1.0",
    )


def test_demand_snapshot_aggregates_all_locations_and_lots_without_tenant_leakage(
    session: Session,
    actor_viewer: ActorContext,
) -> None:
    spare, _ = _seed_ledger_inventory(session)
    configuration_id = session.scalar(
        select(ConfigurationVersion.id).where(
            ConfigurationVersion.tenant_id == actor_viewer.tenant_id
        )
    )
    assert configuration_id is not None

    snapshot, warnings = DemandCalculationService()._snapshot_from_version(
        session,
        actor_viewer,
        _scenario_version(configuration_id),
    )

    assert warnings == [
        {
            "code": "RELIABILITY_PROFILE_FALLBACK",
            "spare_part_id": spare.id,
        }
    ]
    inventory = snapshot["items"][0]["inventory"]
    assert set(inventory) == {
        "on_hand_quantity",
        "available_quantity",
        "in_transit_quantity",
        "safety_stock",
    }
    assert inventory == {
        "on_hand_quantity": "12.0000",
        "available_quantity": "9.0000",
        "in_transit_quantity": "5.0000",
        "safety_stock": "2.0000",
    }


def test_ai_inventory_snapshot_uses_ledger_aggregate_and_actor_tenant(
    session: Session,
    actor_viewer: ActorContext,
) -> None:
    spare, warehouse = _seed_ledger_inventory(session)
    payload = SimpleNamespace(
        model_dump=lambda: {"spare_part_id": spare.id}
    )
    context = SimpleNamespace(
        actor=actor_viewer,
        tenant_id=actor_viewer.tenant_id,
    )

    result = get_inventory_snapshot(session, payload, context)

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["spare_part_id"] == spare.id
    assert item["warehouse_id"] == warehouse.id
    assert Decimal(item["on_hand_quantity"]) == Decimal("12")
    assert Decimal(item["available_quantity"]) == Decimal("9")
    assert Decimal(item["in_transit_quantity"]) == Decimal("5")
    assert Decimal(item["safety_stock"]) == Decimal("2")


def test_ledger_balances_protect_warehouse_and_spare_part_deletion(
    session: Session,
    actor_admin: ActorContext,
) -> None:
    spare, warehouse = _seed_ledger_inventory(session)

    with pytest.raises(ResourceInUseError):
        warehouse_service.delete(session, actor_admin, warehouse.id)
    with pytest.raises(ResourceInUseError):
        spare_part_service.delete(session, actor_admin, spare.id)

    assert session.get(Warehouse, warehouse.id) is not None
    assert session.get(SparePart, spare.id) is not None

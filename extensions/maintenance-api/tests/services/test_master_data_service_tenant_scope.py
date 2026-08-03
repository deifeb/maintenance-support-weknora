from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from inspect import signature

import pytest
from app.core.exceptions import ConflictError, NotFoundError
from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    Part,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
    WarehouseInventory,
)
from app.models.enums import (
    DataSourceType,
    ReliabilityModelType,
)
from app.schemas.equipment import (
    ConfigurationCloneRequest,
    ConfigurationItemCreate,
    ConfigurationVersionCreate,
    ConfigurationVersionUpdate,
)
from app.schemas.inventory import (
    InventoryAdjustment,
    WarehouseInventoryCreate,
    WarehouseInventoryUpdate,
)
from app.schemas.reliability import (
    ReliabilityProfileCreate,
    ReliabilityProfileUpdate,
)
from app.schemas.repair import (
    RepairProfileCreate,
    RepairProfileUpdate,
)
from app.schemas.supplier import (
    SupplierOfferCreate,
    SupplierOfferUpdate,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.services import (
    configuration_service,
    inventory_service,
    reliability_service,
    repair_service,
    supplier_offer_service,
)
from sqlalchemy.orm import Session


def add_equipment(
    session: Session,
    tenant_id: str,
    code: str,
) -> EquipmentModel:
    row = EquipmentModel(
        tenant_id=tenant_id,
        code=code,
        name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_part(
    session: Session,
    tenant_id: str,
    code: str,
) -> Part:
    row = Part(
        tenant_id=tenant_id,
        code=code,
        name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_spare(
    session: Session,
    tenant_id: str,
    code: str,
) -> SparePart:
    row = SparePart(
        tenant_id=tenant_id,
        code=code,
        name=code,
        unit="piece",
    )
    session.add(row)
    session.flush()
    return row


def add_warehouse(
    session: Session,
    tenant_id: str,
    code: str,
) -> Warehouse:
    row = Warehouse(
        tenant_id=tenant_id,
        code=code,
        name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_supplier(
    session: Session,
    tenant_id: str,
    code: str,
) -> Supplier:
    row = Supplier(
        tenant_id=tenant_id,
        code=code,
        name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_version(
    session: Session,
    tenant_id: str,
    equipment_id: int,
    code: str,
) -> ConfigurationVersion:
    row = ConfigurationVersion(
        tenant_id=tenant_id,
        equipment_model_id=equipment_id,
        version_code=code,
        version_name=code,
    )
    session.add(row)
    session.flush()
    return row


def add_inventory(
    session: Session,
    tenant_id: str,
    warehouse_id: int,
    spare_id: int,
) -> WarehouseInventory:
    row = WarehouseInventory(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        spare_part_id=spare_id,
        on_hand_quantity=Decimal("10"),
    )
    session.add(row)
    session.flush()
    return row


def add_reliability(
    session: Session,
    tenant_id: str,
    code: str,
    spare_id: int,
) -> ReliabilityProfile:
    row = ReliabilityProfile(
        tenant_id=tenant_id,
        profile_code=code,
        spare_part_id=spare_id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.01"),
        data_source_type=DataSourceType.MANUAL_ESTIMATE,
    )
    session.add(row)
    session.flush()
    return row


def add_offer(
    session: Session,
    tenant_id: str,
    code: str,
    supplier_id: int,
    spare_id: int,
) -> SupplierOffer:
    row = SupplierOffer(
        tenant_id=tenant_id,
        offer_code=code,
        supplier_id=supplier_id,
        spare_part_id=spare_id,
        unit_price=Decimal("1"),
        lead_time_days=1,
    )
    session.add(row)
    session.flush()
    return row


def add_repair(
    session: Session,
    tenant_id: str,
    code: str,
    spare_id: int,
) -> RepairProfile:
    row = RepairProfile(
        tenant_id=tenant_id,
        profile_code=code,
        profile_name=code,
        spare_part_id=spare_id,
        repair_success_rate=Decimal("0.8"),
        condemnation_rate=Decimal("0.1"),
        repair_turnaround_hours=Decimal("24"),
    )
    session.add(row)
    session.flush()
    return row


SERVICE_METHOD_MATRIX = [
    (
        type(configuration_service),
        (
            "create_version",
            "update_version",
            "create_item",
            "update_item",
            "delete_item",
            "publish",
            "retire",
            "clone",
            "tree",
            "delete",
        ),
    ),
    (
        type(inventory_service),
        (
            "create_inventory",
            "update_inventory",
            "adjust",
        ),
    ),
    (
        type(reliability_service),
        (
            "create_profile",
            "update_profile",
        ),
    ),
    (
        type(supplier_offer_service),
        (
            "create_offer",
            "update_offer",
            "delete",
        ),
    ),
    (
        type(repair_service),
        (
            "create_profile",
            "update_profile",
        ),
    ),
]


@pytest.mark.parametrize(
    ("service_type", "method_names"),
    SERVICE_METHOD_MATRIX,
)
def test_custom_service_methods_require_actor(
    service_type,
    method_names: tuple[str, ...],
) -> None:
    for method_name in method_names:
        assert "actor" in signature(
            getattr(service_type, method_name)
        ).parameters


def test_services_reject_foreign_reference_ids(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    equipment_b = add_equipment(
        session,
        "tenant-b",
        "EQ-B",
    )
    part_b = add_part(session, "tenant-b", "PART-B")
    spare_b = add_spare(session, "tenant-b", "SP-B")
    warehouse_b = add_warehouse(
        session,
        "tenant-b",
        "WH-B",
    )
    supplier_b = add_supplier(
        session,
        "tenant-b",
        "SUP-B",
    )
    version_b = add_version(
        session,
        "tenant-b",
        equipment_b.id,
        "V-B",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        configuration_service.create_version(
            session,
            actor,
            ConfigurationVersionCreate(
                equipment_model_id=equipment_b.id,
                version_code="V-A",
                version_name="Foreign equipment",
            ),
        )

    equipment_a = add_equipment(
        session,
        "tenant-a",
        "EQ-A",
    )
    version_a = configuration_service.create_version(
        session,
        actor,
        ConfigurationVersionCreate(
            equipment_model_id=equipment_a.id,
            version_code="V-A",
            version_name="Version A",
        ),
    )
    with pytest.raises(NotFoundError):
        configuration_service.create_item(
            session,
            actor,
            ConfigurationItemCreate(
                configuration_version_id=version_a.id,
                item_code="ITEM",
                part_id=part_b.id,
                spare_part_id=spare_b.id,
                install_quantity=Decimal("1"),
            ),
        )

    with pytest.raises(NotFoundError):
        inventory_service.create_inventory(
            session,
            actor,
            WarehouseInventoryCreate(
                warehouse_id=warehouse_b.id,
                spare_part_id=spare_b.id,
            ),
        )

    with pytest.raises(NotFoundError):
        reliability_service.create_profile(
            session,
            actor,
            ReliabilityProfileCreate(
                profile_code="RP-A",
                spare_part_id=spare_b.id,
                configuration_version_id=None,
                model_type=(
                    ReliabilityModelType.EXPONENTIAL
                ),
                failure_rate=Decimal("0.01"),
                data_source_type=(
                    DataSourceType.MANUAL_ESTIMATE
                ),
            ),
        )

    spare_a = add_spare(session, "tenant-a", "SP-A")
    with pytest.raises(NotFoundError):
        reliability_service.create_profile(
            session,
            actor,
            ReliabilityProfileCreate(
                profile_code="RP-CONFIG",
                spare_part_id=spare_a.id,
                configuration_version_id=version_b.id,
                model_type=(
                    ReliabilityModelType.EXPONENTIAL
                ),
                failure_rate=Decimal("0.01"),
                data_source_type=(
                    DataSourceType.MANUAL_ESTIMATE
                ),
            ),
        )

    with pytest.raises(NotFoundError):
        supplier_offer_service.create_offer(
            session,
            actor,
            SupplierOfferCreate(
                offer_code="OFFER-A",
                supplier_id=supplier_b.id,
                spare_part_id=spare_a.id,
                unit_price=Decimal("1"),
                lead_time_days=1,
            ),
        )

    with pytest.raises(NotFoundError):
        repair_service.create_profile(
            session,
            actor,
            RepairProfileCreate(
                profile_code="REPAIR-A",
                profile_name="Repair A",
                spare_part_id=spare_b.id,
                repair_success_rate=Decimal("0.8"),
                condemnation_rate=Decimal("0.1"),
                repair_turnaround_hours=Decimal("24"),
            ),
        )



# TASK_72B_REVIEW_FINDING_TESTS


def test_configuration_clone_rejects_foreign_source_references(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    equipment = add_equipment(session, "tenant-a", "EQ-A")
    source = add_version(
        session,
        "tenant-a",
        equipment.id,
        "V1",
    )
    foreign_part = add_part(
        session,
        "tenant-b",
        "PART-B",
    )
    foreign_spare = add_spare(
        session,
        "tenant-b",
        "SP-B",
    )
    session.add(
        ConfigurationItem(
            tenant_id="tenant-a",
            configuration_version_id=source.id,
            item_code="FOREIGN-REFERENCE",
            part_id=foreign_part.id,
            spare_part_id=foreign_spare.id,
            install_quantity=Decimal("1"),
        )
    )
    session.commit()

    with pytest.raises(NotFoundError):
        configuration_service.clone(
            session,
            actor,
            source.id,
            ConfigurationCloneRequest(
                version_code="V2",
                version_name="Version 2",
            ),
        )

    assert (
        configuration_service.configuration_repository
        .get_by_business_key(
            session,
            "tenant-a",
            equipment.id,
            "V2",
        )
        is None
    )


def test_supplier_offer_delete_preserves_historical_rule(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    supplier = add_supplier(
        session,
        "tenant-a",
        "SUP-A",
    )
    spare = add_spare(
        session,
        "tenant-a",
        "SP-A",
    )
    offer = add_offer(
        session,
        "tenant-a",
        "OFFER-A",
        supplier.id,
        spare.id,
    )
    session.commit()

    with pytest.raises(ConflictError):
        supplier_offer_service.delete(
            session,
            actor,
            offer.id,
        )

def test_configuration_clone_preserves_actor_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    equipment = add_equipment(
        session,
        "tenant-a",
        "EQ",
    )
    part = add_part(session, "tenant-a", "PART")
    spare = add_spare(session, "tenant-a", "SPARE")
    session.commit()

    source = configuration_service.create_version(
        session,
        actor,
        ConfigurationVersionCreate(
            equipment_model_id=equipment.id,
            version_code="V1",
            version_name="Version 1",
        ),
    )
    source_item = configuration_service.create_item(
        session,
        actor,
        ConfigurationItemCreate(
            configuration_version_id=source.id,
            item_code="ITEM",
            part_id=part.id,
            spare_part_id=spare.id,
            install_quantity=Decimal("1"),
        ),
    )

    cloned = configuration_service.clone(
        session,
        actor,
        source.id,
        ConfigurationCloneRequest(
            version_code="V2",
            version_name="Version 2",
        ),
    )
    tree = configuration_service.tree(
        session,
        actor,
        cloned.id,
    )

    assert source.tenant_id == "tenant-a"
    assert source_item.tenant_id == "tenant-a"
    assert cloned.tenant_id == "tenant-a"
    assert len(tree.items) == 1
    assert tree.items[0].item_code == "ITEM"

    cloned_row = (
        configuration_service.configuration_repository
        .get_with_items(
            session,
            "tenant-a",
            cloned.id,
        )
    )
    assert cloned_row is not None
    assert {
        item.tenant_id
        for item in cloned_row.items
    } == {"tenant-a"}


def test_custom_service_target_ids_are_tenant_scoped(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
    )
    equipment_b = add_equipment(
        session,
        "tenant-b",
        "EQ-B",
    )
    part_b = add_part(session, "tenant-b", "PART-B")
    spare_b = add_spare(session, "tenant-b", "SP-B")
    warehouse_b = add_warehouse(
        session,
        "tenant-b",
        "WH-B",
    )
    supplier_b = add_supplier(
        session,
        "tenant-b",
        "SUP-B",
    )
    version_b = add_version(
        session,
        "tenant-b",
        equipment_b.id,
        "V-B",
    )
    inventory_b = add_inventory(
        session,
        "tenant-b",
        warehouse_b.id,
        spare_b.id,
    )
    reliability_b = add_reliability(
        session,
        "tenant-b",
        "RP-B",
        spare_b.id,
    )
    offer_b = add_offer(
        session,
        "tenant-b",
        "OFFER-B",
        supplier_b.id,
        spare_b.id,
    )
    repair_b = add_repair(
        session,
        "tenant-b",
        "REPAIR-B",
        spare_b.id,
    )
    session.commit()

    with pytest.raises(NotFoundError):
        configuration_service.update_version(
            session,
            actor,
            version_b.id,
            ConfigurationVersionUpdate(
                version_name="Compromised"
            ),
        )

    with pytest.raises(NotFoundError):
        inventory_service.update_inventory(
            session,
            actor,
            inventory_b.id,
            WarehouseInventoryUpdate(safety_stock=Decimal("9")),
        )

    with pytest.raises(NotFoundError):
        inventory_service.adjust(
            session,
            actor,
            inventory_b.id,
            InventoryAdjustment(
                expected_version=1,
                on_hand_delta=Decimal("1"),
                reason="foreign",
            ),
            idempotency_key="foreign-inventory-adjust",
        )

    with pytest.raises(NotFoundError):
        reliability_service.update_profile(
            session,
            actor,
            reliability_b.id,
            ReliabilityProfileUpdate(notes="foreign"),
        )

    with pytest.raises(NotFoundError):
        supplier_offer_service.update_offer(
            session,
            actor,
            offer_b.id,
            SupplierOfferUpdate(notes="foreign"),
        )

    with pytest.raises(NotFoundError):
        supplier_offer_service.delete(
            session,
            actor,
            offer_b.id,
        )

    with pytest.raises(NotFoundError):
        repair_service.update_profile(
            session,
            actor,
            repair_b.id,
            RepairProfileUpdate(notes="foreign"),
        )

    assert part_b.tenant_id == "tenant-b"

# TASK_72B_FINAL_REVIEW_TESTS


def test_configuration_clone_rejects_foreign_equipment_reference(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    foreign_equipment = add_equipment(
        session,
        "tenant-b",
        "EQ-B",
    )
    source = add_version(
        session,
        "tenant-a",
        foreign_equipment.id,
        "V1",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        configuration_service.clone(
            session,
            actor,
            source.id,
            ConfigurationCloneRequest(
                version_code="V2",
                version_name="Version 2",
            ),
        )

    assert (
        configuration_service.configuration_repository
        .get_by_business_key(
            session,
            "tenant-a",
            foreign_equipment.id,
            "V2",
        )
        is None
    )


def test_inventory_update_rejects_foreign_spare_reference(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    warehouse = add_warehouse(
        session,
        "tenant-a",
        "WH-A",
    )
    foreign_spare = add_spare(
        session,
        "tenant-b",
        "SP-B",
    )
    inventory = add_inventory(
        session,
        "tenant-a",
        warehouse.id,
        foreign_spare.id,
    )
    session.commit()

    with pytest.raises(NotFoundError):
        inventory_service.update_inventory(
            session,
            actor,
            inventory.id,
            WarehouseInventoryUpdate(safety_stock=Decimal("9")),
        )


def test_inventory_adjust_rejects_foreign_spare_reference(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(
        tenant_id="tenant-a",
        role=MaintenanceRole.ADMIN,
    )
    warehouse = add_warehouse(
        session,
        "tenant-a",
        "WH-A",
    )
    foreign_spare = add_spare(
        session,
        "tenant-b",
        "SP-B",
    )
    inventory = add_inventory(
        session,
        "tenant-a",
        warehouse.id,
        foreign_spare.id,
    )
    session.commit()

    with pytest.raises(NotFoundError):
        inventory_service.adjust(
            session,
            actor,
            inventory.id,
            InventoryAdjustment(
                expected_version=1,
                on_hand_delta=Decimal("1"),
                reason="foreign-spare",
            ),
            idempotency_key="foreign-spare-inventory-adjust",
        )

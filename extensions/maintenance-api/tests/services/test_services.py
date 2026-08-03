from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError, ResourceInUseError
from app.models.enums import (
    ConfigurationStatus,
    DataSourceType,
    ReliabilityModelType,
    WarehouseStatus,
)
from app.schemas.catalog import PartCreate, SparePartCreate
from app.schemas.equipment import (
    ConfigurationItemCreate,
    ConfigurationVersionCreate,
    EquipmentModelCreate,
)
from app.schemas.inventory import InventoryAdjustment, WarehouseCreate, WarehouseInventoryCreate
from app.schemas.reliability import ReliabilityProfileCreate
from app.schemas.supplier import SupplierCreate, SupplierOfferCreate
from app.services import (
    configuration_service,
    equipment_service,
    inventory_service,
    part_service,
    reliability_service,
    spare_part_service,
    supplier_offer_service,
    supplier_service,
    warehouse_service,
)


def create_catalog(session, actor_admin):
    equipment = equipment_service.create(
        session, actor_admin, EquipmentModelCreate(code="EQ-1", name="Equipment")
    )
    part = part_service.create(session, actor_admin, PartCreate(code="PT-1", name="Part"))
    spare = spare_part_service.create(session, actor_admin, SparePartCreate(code="SP-1", name="Spare"))
    return equipment, part, spare


def test_unique_equipment_code_is_rejected(session, actor_admin) -> None:
    equipment_service.create(session, actor_admin, EquipmentModelCreate(code="EQ-1", name="A"))
    with pytest.raises(ConflictError):
        equipment_service.create(session, actor_admin, EquipmentModelCreate(code="EQ-1", name="B"))


def test_referenced_equipment_cannot_be_deleted(session, actor_admin) -> None:
    equipment, _, _ = create_catalog(session, actor_admin)
    configuration_service.create_version(
        session, actor_admin,
        ConfigurationVersionCreate(
            equipment_model_id=equipment.id,
            version_code="V1",
            version_name="Version 1",
        ),
    )
    with pytest.raises(ResourceInUseError):
        equipment_service.delete(session, actor_admin, equipment.id)


def test_configuration_publish_clone_and_retire(session, actor_admin) -> None:
    equipment, part, spare = create_catalog(session, actor_admin)
    version = configuration_service.create_version(
        session, actor_admin,
        ConfigurationVersionCreate(
            equipment_model_id=equipment.id,
            version_code="V1",
            version_name="Version 1",
            is_default=True,
        ),
    )
    root = configuration_service.create_item(
        session, actor_admin,
        ConfigurationItemCreate(
            configuration_version_id=version.id,
            item_code="ROOT",
            part_id=part.id,
            spare_part_id=spare.id,
            install_quantity=1,
        ),
    )
    child = configuration_service.create_item(
        session, actor_admin,
        ConfigurationItemCreate(
            configuration_version_id=version.id,
            item_code="CHILD",
            parent_item_id=root.id,
            part_id=part.id,
            spare_part_id=spare.id,
            install_quantity=2,
        ),
    )
    published = configuration_service.publish(session, actor_admin, version.id)
    assert published.status == ConfigurationStatus.PUBLISHED
    tree = configuration_service.tree(session, actor_admin, version.id)
    assert tree.items[0].children[0].id == child.id
    clone = configuration_service.clone(
        session, actor_admin,
        version.id,
        __import__(
            "app.schemas.equipment", fromlist=["ConfigurationCloneRequest"]
        ).ConfigurationCloneRequest(version_code="V2", version_name="Version 2"),
    )
    assert clone.status == ConfigurationStatus.DRAFT
    assert len(configuration_service.tree(session, actor_admin, clone.id).items) == 1
    retired = configuration_service.retire(session, actor_admin, version.id)
    assert retired.status == ConfigurationStatus.RETIRED


def test_inventory_adjustment_and_frozen_warehouse(session, actor_admin) -> None:
    spare = spare_part_service.create(session, actor_admin, SparePartCreate(code="SP-1", name="Spare"))
    warehouse = warehouse_service.create(session, actor_admin, WarehouseCreate(code="WH-1", name="Warehouse"))
    inventory = inventory_service.create_inventory(
        session, actor_admin,
        WarehouseInventoryCreate(
            warehouse_id=warehouse.id,
            spare_part_id=spare.id,
            on_hand_quantity=10,
            safety_stock=2,
            reorder_point=3,
        ),
    )
    adjusted = inventory_service.adjust(
        session, actor_admin, inventory.id, InventoryAdjustment(on_hand_delta=5, reason="count")
    )
    assert adjusted.on_hand_quantity == Decimal("15.0000")
    warehouse.status = WarehouseStatus.FROZEN
    session.commit()
    with pytest.raises(ConflictError):
        inventory_service.adjust(
            session, actor_admin, inventory.id, InventoryAdjustment(on_hand_delta=1, reason="blocked")
        )


def test_reliability_overlap_is_rejected(session, actor_admin) -> None:
    spare = spare_part_service.create(session, actor_admin, SparePartCreate(code="SP-1", name="Spare"))
    payload = ReliabilityProfileCreate(
        profile_code="RP-1",
        spare_part_id=spare.id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate="0.001",
        data_source_type=DataSourceType.DESIGN_PARAMETER,
    )
    reliability_service.create_profile(session, actor_admin, payload)
    with pytest.raises(ConflictError):
        reliability_service.create_profile(
            session, actor_admin,
            payload.model_copy(update={"profile_code": "RP-2"}),
        )


def test_preferred_offer_overlap_is_rejected(session, actor_admin) -> None:
    spare = spare_part_service.create(session, actor_admin, SparePartCreate(code="SP-1", name="Spare"))
    supplier1 = supplier_service.create(session, actor_admin, SupplierCreate(code="SUP-1", name="Supplier 1"))
    supplier2 = supplier_service.create(session, actor_admin, SupplierCreate(code="SUP-2", name="Supplier 2"))
    supplier_offer_service.create_offer(
        session, actor_admin,
        SupplierOfferCreate(
            offer_code="OF-1",
            supplier_id=supplier1.id,
            spare_part_id=spare.id,
            unit_price=10,
            lead_time_days=5,
            is_preferred=True,
        ),
    )
    with pytest.raises(ConflictError):
        supplier_offer_service.create_offer(
            session, actor_admin,
            SupplierOfferCreate(
                offer_code="OF-2",
                supplier_id=supplier2.id,
                spare_part_id=spare.id,
                unit_price=9,
                lead_time_days=4,
                is_preferred=True,
            ),
        )

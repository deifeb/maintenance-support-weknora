from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from app.core.exceptions import ResourceInUseError
from app.db.base import Base
from app.models import (
    InventoryExpiryRule,
    InventoryLot,
    InventoryPolicy,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.security.actor import ActorContext
from app.services.spare_part_service import spare_part_service
from app.services.warehouse_service import warehouse_service
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def migrated_inventory_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE warehouse_inventories")

    local_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield local_session
    finally:
        local_session.close()
        engine.dispose()


def _seed_warehouse_and_spare(
    session: Session,
    suffix: str,
) -> tuple[Warehouse, SparePart]:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    spare = SparePart(
        tenant_id="tenant-a",
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
    )
    session.add_all((warehouse, spare))
    session.commit()
    return warehouse, spare


def _add_location(
    session: Session,
    warehouse: Warehouse,
    suffix: str,
) -> WarehouseLocation:
    location = WarehouseLocation(
        tenant_id="tenant-a",
        warehouse_id=warehouse.id,
        code=f"LOC-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()
    return location


def test_empty_parents_delete_when_legacy_table_is_absent(
    migrated_inventory_session: Session,
    actor_admin: ActorContext,
) -> None:
    warehouse, spare = _seed_warehouse_and_spare(
        migrated_inventory_session,
        "EMPTY",
    )

    warehouse_service.delete(
        migrated_inventory_session,
        actor_admin,
        warehouse.id,
    )
    spare_part_service.delete(
        migrated_inventory_session,
        actor_admin,
        spare.id,
    )

    assert migrated_inventory_session.get(Warehouse, warehouse.id) is None
    assert migrated_inventory_session.get(SparePart, spare.id) is None


@pytest.mark.parametrize(
    "reference_kind",
    ("location", "policy", "serialized_item"),
)
def test_warehouse_new_domain_references_raise_resource_in_use(
    migrated_inventory_session: Session,
    actor_admin: ActorContext,
    reference_kind: str,
) -> None:
    warehouse, spare = _seed_warehouse_and_spare(
        migrated_inventory_session,
        f"WAREHOUSE-{reference_kind}",
    )
    if reference_kind == "location":
        _add_location(migrated_inventory_session, warehouse, reference_kind)
    elif reference_kind == "policy":
        migrated_inventory_session.add(
            InventoryPolicy(
                tenant_id="tenant-a",
                warehouse_id=warehouse.id,
                spare_part_id=spare.id,
                safety_stock=Decimal("0"),
                reorder_point=Decimal("0"),
            )
        )
    else:
        location = _add_location(
            migrated_inventory_session,
            warehouse,
            reference_kind,
        )
        migrated_inventory_session.add(
            SerializedItem(
                tenant_id="tenant-a",
                spare_part_id=spare.id,
                serial_number="SER-WAREHOUSE",
                warehouse_id=warehouse.id,
                location_id=location.id,
                status="IN_STOCK",
            )
        )
    migrated_inventory_session.commit()

    with pytest.raises(ResourceInUseError):
        warehouse_service.delete(
            migrated_inventory_session,
            actor_admin,
            warehouse.id,
        )

    assert migrated_inventory_session.get(Warehouse, warehouse.id) is not None


@pytest.mark.parametrize(
    "reference_kind",
    ("policy", "expiry_rule", "lot", "serialized_item"),
)
def test_spare_part_new_domain_references_raise_resource_in_use(
    migrated_inventory_session: Session,
    actor_admin: ActorContext,
    reference_kind: str,
) -> None:
    warehouse, spare = _seed_warehouse_and_spare(
        migrated_inventory_session,
        f"SPARE-{reference_kind}",
    )
    if reference_kind == "policy":
        migrated_inventory_session.add(
            InventoryPolicy(
                tenant_id="tenant-a",
                warehouse_id=warehouse.id,
                spare_part_id=spare.id,
                safety_stock=Decimal("0"),
                reorder_point=Decimal("0"),
            )
        )
    elif reference_kind == "expiry_rule":
        migrated_inventory_session.add(
            InventoryExpiryRule(
                tenant_id="tenant-a",
                scope_type="SPARE_PART",
                spare_part_id=spare.id,
                warning_days_json={"warning_days": [30]},
            )
        )
    elif reference_kind == "lot":
        migrated_inventory_session.add(
            InventoryLot(
                tenant_id="tenant-a",
                spare_part_id=spare.id,
                lot_code="LOT-SPARE",
            )
        )
    else:
        location = _add_location(
            migrated_inventory_session,
            warehouse,
            reference_kind,
        )
        migrated_inventory_session.add(
            SerializedItem(
                tenant_id="tenant-a",
                spare_part_id=spare.id,
                serial_number="SER-SPARE",
                warehouse_id=warehouse.id,
                location_id=location.id,
                status="IN_STOCK",
            )
        )
    migrated_inventory_session.commit()

    with pytest.raises(ResourceInUseError):
        spare_part_service.delete(
            migrated_inventory_session,
            actor_admin,
            spare.id,
        )

    assert migrated_inventory_session.get(SparePart, spare.id) is not None

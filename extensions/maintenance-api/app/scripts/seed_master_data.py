from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    Part,
    ReliabilityProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
    WarehouseInventory,
)
from app.models.enums import (
    ConfigurationStatus,
    CriticalityLevel,
    DataSourceType,
    ReliabilityModelType,
    WarehouseStatus,
)


def get_or_create(session, model, lookup: dict, defaults: dict):
    instance = session.scalar(select(model).filter_by(**lookup))
    if instance is None:
        instance = model(**lookup, **defaults)
        session.add(instance)
        session.flush()
    return instance


def seed() -> dict[str, int]:
    session = SessionLocal()
    try:
        equipment = [
            get_or_create(
                session,
                EquipmentModel,
                {"code": f"EQ-{index:03d}"},
                {
                    "name": f"示例装备{index}",
                    "category": "示例装备",
                    "manufacturer": "示例制造单位",
                    "service_life_years": Decimal("20"),
                    "is_active": True,
                },
            )
            for index in range(1, 3)
        ]
        parts = [
            get_or_create(
                session,
                Part,
                {"code": f"PT-{index:03d}"},
                {
                    "name": f"示例部件{index}",
                    "part_type": "可更换单元" if index % 2 else "组件",
                    "unit": "件",
                    "is_active": True,
                },
            )
            for index in range(1, 16)
        ]
        spares = [
            get_or_create(
                session,
                SparePart,
                {"code": f"SP-{index:03d}"},
                {
                    "name": f"示例维修器材{index}",
                    "category": "关键件" if index <= 5 else "一般件",
                    "unit": "件",
                    "is_critical": index <= 5,
                    "is_repairable": index % 3 == 0,
                    "default_service_level": Decimal("0.95"),
                    "is_active": True,
                },
            )
            for index in range(1, 21)
        ]
        warehouses = [
            get_or_create(
                session,
                Warehouse,
                {"code": f"WH-{index:03d}"},
                {
                    "name": f"示例库房{index}",
                    "warehouse_type": "中心库" if index == 1 else "保障点",
                    "status": WarehouseStatus.NORMAL,
                    "is_active": True,
                },
            )
            for index in range(1, 4)
        ]
        suppliers = [
            get_or_create(
                session,
                Supplier,
                {"code": f"SUP-{index:03d}"},
                {
                    "name": f"示例供应商{index}",
                    "supplier_type": "制造商" if index <= 2 else "经销商",
                    "rating": Decimal(str(90 - index)),
                    "is_active": True,
                },
            )
            for index in range(1, 5)
        ]

        versions: list[ConfigurationVersion] = []
        for eq_index, eq in enumerate(equipment, start=1):
            for version_index in range(1, 3):
                version = get_or_create(
                    session,
                    ConfigurationVersion,
                    {
                        "equipment_model_id": eq.id,
                        "version_code": f"V{version_index}",
                    },
                    {
                        "version_name": f"示例构型{version_index}",
                        "status": ConfigurationStatus.DRAFT,
                        "is_default": version_index == 1,
                        "is_active": True,
                    },
                )
                versions.append(version)
                for local_index in range(1, 9):
                    global_index = (
                        (eq_index - 1) * 15 + (version_index - 1) * 8 + local_index - 1
                    ) % 15
                    spare_index = (
                        (eq_index - 1) * 15 + (version_index - 1) * 8 + local_index - 1
                    ) % 20
                    item_code = f"N{local_index:02d}"
                    item = session.scalar(
                        select(ConfigurationItem).where(
                            ConfigurationItem.configuration_version_id == version.id,
                            ConfigurationItem.item_code == item_code,
                        )
                    )
                    if item is None:
                        item = ConfigurationItem(
                            configuration_version_id=version.id,
                            item_code=item_code,
                            parent_item_id=None,
                            part_id=parts[global_index].id,
                            spare_part_id=spares[spare_index].id,
                            install_quantity=Decimal(str((local_index % 3) + 1)),
                            criticality_level=(
                                CriticalityLevel.CRITICAL
                                if local_index <= 2
                                else CriticalityLevel.MEDIUM
                            ),
                            replacement_ratio=Decimal("1"),
                            sort_order=local_index,
                        )
                        session.add(item)
                        session.flush()
                    if local_index > 1 and item.parent_item_id is None:
                        parent = session.scalar(
                            select(ConfigurationItem).where(
                                ConfigurationItem.configuration_version_id == version.id,
                                ConfigurationItem.item_code == "N01",
                            )
                        )
                        item.parent_item_id = parent.id
                if version_index == 1:
                    version.status = ConfigurationStatus.PUBLISHED

        model_payloads = [
            (ReliabilityModelType.EXPONENTIAL, {"failure_rate": Decimal("0.0001")}),
            (
                ReliabilityModelType.WEIBULL,
                {"weibull_shape": Decimal("1.5"), "weibull_scale": Decimal("5000")},
            ),
            (
                ReliabilityModelType.BINOMIAL,
                {"binomial_trials": 10, "binomial_probability": Decimal("0.2")},
            ),
            (
                ReliabilityModelType.NEGATIVE_BINOMIAL,
                {"negative_binomial_r": Decimal("3"), "negative_binomial_p": Decimal("0.4")},
            ),
            (
                ReliabilityModelType.EMPIRICAL,
                {"empirical_mean": Decimal("2"), "empirical_variance": Decimal("1")},
            ),
        ]
        for index, (model_type, parameters) in enumerate(model_payloads, start=1):
            get_or_create(
                session,
                ReliabilityProfile,
                {"profile_code": f"RP-{index:03d}"},
                {
                    "spare_part_id": spares[index - 1].id,
                    "configuration_version_id": versions[0].id,
                    "model_type": model_type,
                    "data_source_type": DataSourceType.DESIGN_PARAMETER,
                    "confidence_level": Decimal("0.95"),
                    "is_active": True,
                    **parameters,
                },
            )

        for warehouse in warehouses:
            for spare in spares[:10]:
                get_or_create(
                    session,
                    WarehouseInventory,
                    {"warehouse_id": warehouse.id, "spare_part_id": spare.id},
                    {
                        "on_hand_quantity": Decimal(str(50 + spare.id)),
                        "reserved_quantity": Decimal("2"),
                        "damaged_quantity": Decimal("0"),
                        "quarantined_quantity": Decimal("0"),
                        "in_transit_quantity": Decimal("5"),
                        "safety_stock": Decimal("10"),
                        "reorder_point": Decimal("20"),
                        "maximum_stock": Decimal("100"),
                    },
                )

        for index, spare in enumerate(spares[:12], start=1):
            supplier = suppliers[(index - 1) % len(suppliers)]
            get_or_create(
                session,
                SupplierOffer,
                {"offer_code": f"OF-{index:03d}"},
                {
                    "supplier_id": supplier.id,
                    "spare_part_id": spare.id,
                    "unit_price": Decimal(str(100 + index * 10)),
                    "currency": "CNY",
                    "lead_time_days": 7 + index,
                    "minimum_order_quantity": Decimal("1"),
                    "order_multiple": Decimal("1"),
                    "is_preferred": True,
                    "is_active": True,
                },
            )
        session.commit()
        models = [
            EquipmentModel,
            ConfigurationVersion,
            ConfigurationItem,
            Part,
            SparePart,
            ReliabilityProfile,
            Warehouse,
            WarehouseInventory,
            Supplier,
            SupplierOffer,
        ]
        return {model.__tablename__: len(session.scalars(select(model)).all()) for model in models}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    counts = seed()
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()

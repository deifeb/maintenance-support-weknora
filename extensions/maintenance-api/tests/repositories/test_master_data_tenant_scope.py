from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import signature

import pytest
from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    DemandCalculation,
    DemandCalculationRun,
    DemandParameterOverride,
    DemandRunItemResult,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    EquipmentModel,
    InventoryBalance,
    InventoryPolicy,
    Part,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import (
    CalculationExecutionType,
    DataSourceType,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    ReliabilityModelType,
    ShortageRiskLevel,
)
from app.repositories import (
    ConfigurationItemRepository,
    ConfigurationRepository,
    EquipmentRepository,
    InventoryRepository,
    PartRepository,
    ReliabilityRepository,
    RepairRepository,
    SparePartRepository,
    SupplierOfferRepository,
    SupplierRepository,
    WarehouseRepository,
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


def add_item(
    session: Session,
    tenant_id: str,
    version_id: int,
    code: str,
    part_id: int,
    spare_id: int | None = None,
) -> ConfigurationItem:
    row = ConfigurationItem(
        tenant_id=tenant_id,
        configuration_version_id=version_id,
        item_code=code,
        part_id=part_id,
        spare_part_id=spare_id,
        install_quantity=Decimal("1"),
    )
    session.add(row)
    session.flush()
    return row


def add_reliability(
    session: Session,
    tenant_id: str,
    code: str,
    spare_id: int,
    version_id: int | None = None,
) -> ReliabilityProfile:
    row = ReliabilityProfile(
        tenant_id=tenant_id,
        profile_code=code,
        spare_part_id=spare_id,
        configuration_version_id=version_id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.01"),
        data_source_type=DataSourceType.MANUAL_ESTIMATE,
    )
    session.add(row)
    session.flush()
    return row


def add_inventory(
    session: Session,
    tenant_id: str,
    warehouse_id: int,
    spare_id: int,
) -> InventoryBalance:
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code="DEFAULT",
        name="Default location",
        location_type="DEFAULT",
    )
    session.add(location)
    session.flush()
    session.add(
        InventoryPolicy(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            spare_part_id=spare_id,
        )
    )
    row = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        location_id=location.id,
        spare_part_id=spare_id,
        on_hand_quantity=Decimal("10"),
    )
    session.add(row)
    session.flush()
    return row


def add_balance(
    session: Session,
    tenant_id: str,
    warehouse_id: int,
    spare_id: int,
    suffix: str,
) -> InventoryBalance:
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code=f"LOC-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()
    row = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        location_id=location.id,
        spare_part_id=spare_id,
        on_hand_quantity=Decimal("10"),
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
    *,
    preferred: bool = False,
) -> SupplierOffer:
    row = SupplierOffer(
        tenant_id=tenant_id,
        offer_code=code,
        supplier_id=supplier_id,
        spare_part_id=spare_id,
        unit_price=Decimal("1"),
        lead_time_days=1,
        is_preferred=preferred,
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
        maintenance_level="BASE",
        repair_success_rate=Decimal("0.8"),
        condemnation_rate=Decimal("0.1"),
        repair_turnaround_hours=Decimal("24"),
    )
    session.add(row)
    session.flush()
    return row


METHOD_MATRIX = [
    (EquipmentRepository, ("count_references",)),
    (
        ConfigurationRepository,
        ("get_by_business_key", "get_with_items", "count_references"),
    ),
    (
        ConfigurationItemRepository,
        ("get_by_business_key", "list_for_version"),
    ),
    (PartRepository, ("count_references",)),
    (SparePartRepository, ("count_references",)),
    (
        ReliabilityRepository,
        ("get_by_profile_code", "find_overlap"),
    ),
    (WarehouseRepository, ("count_references",)),
    (InventoryRepository, ("get_default_balance_by_business_key",)),
    (SupplierRepository, ("count_references",)),
    (
        SupplierOfferRepository,
        ("get_by_offer_code", "find_preferred_overlap"),
    ),
    (
        RepairRepository,
        ("find_overlap", "select_candidates", "count_references"),
    ),
]


@pytest.mark.parametrize(("repository_type", "method_names"), METHOD_MATRIX)
def test_specialized_repository_methods_require_tenant_id(
    repository_type,
    method_names: tuple[str, ...],
) -> None:
    for method_name in method_names:
        assert "tenant_id" in signature(
            getattr(repository_type, method_name)
        ).parameters


def test_configuration_queries_filter_root_and_children(
    session: Session,
) -> None:
    equipment_a = add_equipment(session, "tenant-a", "EQ-A")
    equipment_b = add_equipment(session, "tenant-b", "EQ-B")
    part_a = add_part(session, "tenant-a", "PART-A")
    part_b = add_part(session, "tenant-b", "PART-B")
    version_a = add_version(
        session,
        "tenant-a",
        equipment_a.id,
        "V1",
    )
    version_b = add_version(
        session,
        "tenant-b",
        equipment_b.id,
        "V1",
    )
    visible = add_item(
        session,
        "tenant-a",
        version_a.id,
        "VISIBLE",
        part_a.id,
    )
    add_item(
        session,
        "tenant-b",
        version_a.id,
        "FOREIGN",
        part_b.id,
    )
    session.commit()

    equipment_a_id = equipment_a.id
    equipment_b_id = equipment_b.id
    version_a_id = version_a.id
    visible_id = visible.id
    session.expunge_all()

    versions = ConfigurationRepository()
    items = ConfigurationItemRepository()

    matched = versions.get_by_business_key(
        session,
        "tenant-a",
        equipment_a_id,
        "V1",
    )
    assert matched is not None
    assert matched.id == version_a_id
    assert versions.get_by_business_key(
        session,
        "tenant-a",
        equipment_b_id,
        "V1",
    ) is None

    aggregate = versions.get_with_items(
        session,
        "tenant-a",
        version_a_id,
    )
    assert aggregate is not None
    assert [row.id for row in aggregate.items] == [visible_id]
    assert [row.id for row in items.list_for_version(
        session,
        "tenant-a",
        version_a_id,
    )] == [visible_id]
    assert items.get_by_business_key(
        session,
        "tenant-a",
        version_a_id,
        "FOREIGN",
    ) is None
    assert version_b.tenant_id == "tenant-b"


def test_business_keys_and_overlap_queries_are_tenant_scoped(
    session: Session,
) -> None:
    warehouse_a = add_warehouse(session, "tenant-a", "WH-A")
    warehouse_b = add_warehouse(session, "tenant-b", "WH-B")
    spare_a = add_spare(session, "tenant-a", "SP-A")
    spare_b = add_spare(session, "tenant-b", "SP-B")
    supplier_a = add_supplier(session, "tenant-a", "SUP-A")
    supplier_b = add_supplier(session, "tenant-b", "SUP-B")

    inventory_a = add_inventory(
        session,
        "tenant-a",
        warehouse_a.id,
        spare_a.id,
    )
    add_inventory(
        session,
        "tenant-b",
        warehouse_b.id,
        spare_b.id,
    )
    profile_a = add_reliability(
        session,
        "tenant-a",
        "RP",
        spare_a.id,
    )
    profile_b = add_reliability(
        session,
        "tenant-b",
        "RP",
        spare_b.id,
    )
    offer_a = add_offer(
        session,
        "tenant-a",
        "OFFER",
        supplier_a.id,
        spare_a.id,
    )
    offer_b = add_offer(
        session,
        "tenant-b",
        "OFFER",
        supplier_b.id,
        spare_b.id,
    )

    foreign_overlap = add_reliability(
        session,
        "tenant-b",
        "RP-OVERLAP",
        spare_a.id,
    )
    foreign_offer = add_offer(
        session,
        "tenant-b",
        "OF-OVERLAP",
        supplier_b.id,
        spare_a.id,
        preferred=True,
    )
    repair_a = add_repair(
        session,
        "tenant-a",
        "REPAIR-A",
        spare_a.id,
    )
    repair_b = add_repair(
        session,
        "tenant-b",
        "REPAIR-B",
        spare_a.id,
    )
    session.commit()

    inventories = InventoryRepository()
    assert inventories.get_default_balance_by_business_key(
        session,
        "tenant-a",
        warehouse_a.id,
        spare_a.id,
    ).id == inventory_a.id
    assert inventories.get_default_balance_by_business_key(
        session,
        "tenant-a",
        warehouse_b.id,
        spare_b.id,
    ) is None

    reliability = ReliabilityRepository()
    assert reliability.get_by_profile_code(
        session,
        "tenant-a",
        "RP",
    ).id == profile_a.id
    assert reliability.get_by_profile_code(
        session,
        "tenant-b",
        "RP",
    ).id == profile_b.id
    assert reliability.find_overlap(
        session,
        "tenant-a",
        spare_part_id=spare_a.id,
        configuration_version_id=None,
        model_type=ReliabilityModelType.EXPONENTIAL,
        valid_from=None,
        valid_to=None,
    ).id == profile_a.id
    assert reliability.find_overlap(
        session,
        "tenant-b",
        spare_part_id=spare_a.id,
        configuration_version_id=None,
        model_type=ReliabilityModelType.EXPONENTIAL,
        valid_from=None,
        valid_to=None,
    ).id == foreign_overlap.id

    offers = SupplierOfferRepository()
    assert offers.get_by_offer_code(
        session,
        "tenant-a",
        "OFFER",
    ).id == offer_a.id
    assert offers.get_by_offer_code(
        session,
        "tenant-b",
        "OFFER",
    ).id == offer_b.id
    assert offers.find_preferred_overlap(
        session,
        "tenant-a",
        spare_part_id=spare_a.id,
        valid_from=None,
        valid_to=None,
    ) is None
    assert offers.find_preferred_overlap(
        session,
        "tenant-b",
        spare_part_id=spare_a.id,
        valid_from=None,
        valid_to=None,
    ).id == foreign_offer.id

    repairs = RepairRepository()
    assert repairs.find_overlap(
        session,
        "tenant-a",
        spare_part_id=spare_a.id,
        configuration_version_id=None,
        maintenance_level="BASE",
        valid_from=None,
        valid_to=None,
    ).id == repair_a.id
    assert repairs.find_overlap(
        session,
        "tenant-b",
        spare_part_id=spare_a.id,
        configuration_version_id=None,
        maintenance_level="BASE",
        valid_from=None,
        valid_to=None,
    ).id == repair_b.id
    assert [row.id for row in repairs.select_candidates(
        session,
        "tenant-a",
        spare_a.id,
        None,
        "BASE",
        date.today(),
    )] == [repair_a.id]


def test_reference_counts_are_tenant_scoped(
    session: Session,
) -> None:
    equipment = add_equipment(session, "tenant-a", "EQ")
    part = add_part(session, "tenant-a", "PART")
    spare = add_spare(session, "tenant-a", "SPARE")
    spare_b = add_spare(session, "tenant-b", "SPARE-B")
    version_a = add_version(
        session,
        "tenant-a",
        equipment.id,
        "VA",
    )
    version_b = add_version(
        session,
        "tenant-b",
        equipment.id,
        "VB",
    )
    add_item(
        session,
        "tenant-a",
        version_a.id,
        "IA",
        part.id,
        spare.id,
    )
    add_item(
        session,
        "tenant-b",
        version_b.id,
        "IB",
        part.id,
        spare.id,
    )
    add_reliability(
        session,
        "tenant-a",
        "RPA",
        spare.id,
        version_a.id,
    )
    add_reliability(
        session,
        "tenant-b",
        "RPB",
        spare.id,
        version_a.id,
    )

    warehouse_a = add_warehouse(session, "tenant-a", "WHA")
    warehouse_b = add_warehouse(session, "tenant-b", "WHB")
    add_balance(
        session,
        "tenant-a",
        warehouse_a.id,
        spare.id,
        "A",
    )
    add_balance(
        session,
        "tenant-b",
        warehouse_b.id,
        spare.id,
        "B",
    )
    add_balance(
        session,
        "tenant-b",
        warehouse_a.id,
        spare_b.id,
        "C",
    )

    supplier_a = add_supplier(session, "tenant-a", "SUPA")
    supplier_b = add_supplier(session, "tenant-b", "SUPB")
    add_offer(
        session,
        "tenant-a",
        "OFA",
        supplier_a.id,
        spare.id,
    )
    add_offer(
        session,
        "tenant-b",
        "OFB",
        supplier_b.id,
        spare.id,
    )
    add_offer(
        session,
        "tenant-b",
        "OFC",
        supplier_a.id,
        spare_b.id,
    )
    session.commit()

    assert EquipmentRepository().count_references(
        session,
        "tenant-a",
        equipment.id,
    ) == 1
    assert EquipmentRepository().count_references(
        session,
        "tenant-b",
        equipment.id,
    ) == 1
    assert PartRepository().count_references(
        session,
        "tenant-a",
        part.id,
    ) == 1
    assert PartRepository().count_references(
        session,
        "tenant-b",
        part.id,
    ) == 1
    assert SparePartRepository().count_references(
        session,
        "tenant-a",
        spare.id,
    ) == 4
    assert SparePartRepository().count_references(
        session,
        "tenant-b",
        spare.id,
    ) == 4
    assert ConfigurationRepository().count_references(
        session,
        "tenant-a",
        version_a.id,
    ) == 1
    assert ConfigurationRepository().count_references(
        session,
        "tenant-b",
        version_a.id,
    ) == 1
    assert WarehouseRepository().count_references(
        session,
        "tenant-a",
        warehouse_a.id,
    ) == 1
    assert WarehouseRepository().count_references(
        session,
        "tenant-b",
        warehouse_a.id,
    ) == 1
    assert SupplierRepository().count_references(
        session,
        "tenant-a",
        supplier_a.id,
    ) == 1
    assert SupplierRepository().count_references(
        session,
        "tenant-b",
        supplier_a.id,
    ) == 1


def add_repair_references(
    session: Session,
    tenant_id: str,
    suffix: str,
    repair_id: int,
    spare_id: int,
) -> None:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()
    scenario = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-{suffix}",
        version_name=f"Version {suffix}",
    )
    session.add(scenario)
    session.flush()
    session.add(
        DemandParameterOverride(
            tenant_id=tenant_id,
            scenario_version_id=scenario.id,
            spare_part_id=spare_id,
            repair_profile_id=repair_id,
        )
    )

    now = datetime.now(timezone.utc)
    calculation = DemandCalculation(
        tenant_id=tenant_id,
        calculation_code=f"CALC-{suffix}",
        calculation_name=f"Calculation {suffix}",
        execution_type=CalculationExecutionType.SYNCHRONOUS,
        requested_mode=DemandExecutionMode.ANALYTICAL,
        input_snapshot_json={},
        input_snapshot_hash=suffix * 64,
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(calculation)
    session.flush()
    run = DemandCalculationRun(
        tenant_id=tenant_id,
        calculation_id=calculation.id,
        run_mode=DemandExecutionMode.ANALYTICAL,
        engine_version="test",
        formula_version="test",
    )
    session.add(run)
    session.flush()
    zero = Decimal("0")
    session.add(
        DemandRunItemResult(
            tenant_id=tenant_id,
            calculation_run_id=run.id,
            spare_part_id=spare_id,
            spare_part_code_snapshot=f"SP-{suffix}",
            spare_part_name_snapshot=f"Spare {suffix}",
            calculation_status=ItemCalculationStatus.CALCULATED,
            failure_process_mode=FailureProcessMode.AUTO,
            selected_repair_profile_id=repair_id,
            target_service_level=Decimal("0.9"),
            expected_demand=zero,
            variance=zero,
            standard_deviation=zero,
            p50=zero,
            p80=zero,
            p90=zero,
            p95=zero,
            p99=zero,
            target_quantile_demand=zero,
            gross_replacement_demand=zero,
            repair_pipeline_demand=zero,
            repair_pipeline_peak=zero,
            net_consumption_demand=zero,
            recommended_spare_quantity=zero,
            shortage_risk_level=ShortageRiskLevel.NONE,
        )
    )


def test_repair_reference_counts_are_tenant_scoped(
    session: Session,
) -> None:
    spare_a = add_spare(session, "tenant-a", "SP-A")
    spare_b = add_spare(session, "tenant-b", "SP-B")
    repair = add_repair(
        session,
        "tenant-a",
        "REPAIR",
        spare_a.id,
    )
    add_repair_references(
        session,
        "tenant-a",
        "A",
        repair.id,
        spare_a.id,
    )
    add_repair_references(
        session,
        "tenant-b",
        "B",
        repair.id,
        spare_b.id,
    )
    session.commit()

    repository = RepairRepository()
    assert repository.count_references(
        session,
        "tenant-a",
        repair.id,
    ) == 2
    assert repository.count_references(
        session,
        "tenant-b",
        repair.id,
    ) == 2

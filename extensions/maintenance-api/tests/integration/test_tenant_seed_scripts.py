from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
    EquipmentModel,
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryPolicy,
    InventoryTransaction,
    Part,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
)
from app.scripts.seed_demand_scenarios import (
    seed as seed_demand_scenarios,
)
from app.scripts.seed_master_data import (
    seed as seed_master_data,
)
from sqlalchemy import func, select

TENANT_OWNED_SEED_MODELS = (
    EquipmentModel,
    ConfigurationVersion,
    ConfigurationItem,
    Part,
    SparePart,
    ReliabilityProfile,
    Warehouse,
    InventoryPolicy,
    InventoryBalance,
    InventoryTransaction,
    InventoryLedgerEntry,
    Supplier,
    SupplierOffer,
    RepairProfile,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandFleetGroup,
    DemandAgeGroup,
    DemandScenarioStage,
    DemandStageFleetUsage,
    DemandCommonShockRule,
)


def _count_for_tenant(
    session,
    model,
    tenant_id: str,
) -> int:
    return int(
        session.scalar(
            select(func.count(model.id)).where(
                model.tenant_id == tenant_id,
            )
        )
        or 0
    )


def _tenant_counts(
    session,
    tenant_id: str,
) -> dict[type, int]:
    session.expire_all()
    return {
        model: _count_for_tenant(
            session,
            model,
            tenant_id,
        )
        for model in TENANT_OWNED_SEED_MODELS
    }


def test_seed_scripts_are_tenant_scoped_and_idempotent(
    session,
) -> None:
    seed_master_data(tenant_id="tenant-a")
    seed_demand_scenarios(tenant_id="tenant-a")

    first_counts = _tenant_counts(
        session,
        "tenant-a",
    )
    assert all(
        count > 0
        for count in first_counts.values()
    )

    seed_master_data(tenant_id="tenant-a")
    seed_demand_scenarios(tenant_id="tenant-a")

    second_counts = _tenant_counts(
        session,
        "tenant-a",
    )
    assert second_counts == first_counts

    seed_master_data(tenant_id="tenant-b")
    seed_demand_scenarios(tenant_id="tenant-b")

    tenant_b_counts = _tenant_counts(
        session,
        "tenant-b",
    )
    assert tenant_b_counts == first_counts

    equipment_rows = set(
        session.execute(
            select(
                EquipmentModel.tenant_id,
                EquipmentModel.code,
            ).where(
                EquipmentModel.code == "EQ-001",
            )
        ).all()
    )
    assert equipment_rows == {
        ("tenant-a", "EQ-001"),
        ("tenant-b", "EQ-001"),
    }

from collections.abc import Mapping
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance,
    InventoryPolicy,
    WarehouseInventory,
    WarehouseLocation,
)
from app.repositories.base import (
    BaseRepository,
    TenantScopeError,
    tenant_loader_criteria,
)


class InventoryRepository(BaseRepository[WarehouseInventory]):
    def __init__(self) -> None:
        super().__init__(WarehouseInventory)

    def get_by_business_key(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
        spare_part_id: int,
    ) -> WarehouseInventory | None:
        return session.scalar(
            select(WarehouseInventory)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                WarehouseInventory.tenant_id == tenant_id,
                WarehouseInventory.warehouse_id == warehouse_id,
                WarehouseInventory.spare_part_id == spare_part_id,
            )
        )

    def get_balance(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> InventoryBalance | None:
        return session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id == identifier,
            )
        )

    def get_compatibility_balance(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> InventoryBalance | None:
        return session.scalar(
            select(InventoryBalance)
            .join(
                WarehouseLocation,
                and_(
                    WarehouseLocation.tenant_id == tenant_id,
                    WarehouseLocation.id
                    == InventoryBalance.location_id,
                    WarehouseLocation.warehouse_id
                    == InventoryBalance.warehouse_id,
                ),
            )
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id == identifier,
                InventoryBalance.lot_id.is_(None),
                WarehouseLocation.code == "DEFAULT",
            )
        )

    def get_default_balance_by_business_key(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
        spare_part_id: int,
    ) -> InventoryBalance | None:
        return session.scalar(
            select(InventoryBalance)
            .join(
                WarehouseLocation,
                and_(
                    WarehouseLocation.tenant_id == tenant_id,
                    WarehouseLocation.id == InventoryBalance.location_id,
                ),
            )
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.warehouse_id == warehouse_id,
                InventoryBalance.spare_part_id == spare_part_id,
                InventoryBalance.lot_id.is_(None),
                WarehouseLocation.code == "DEFAULT",
            )
        )

    def get_policy_by_business_key(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
        spare_part_id: int,
    ) -> InventoryPolicy | None:
        return session.scalar(
            select(InventoryPolicy).where(
                InventoryPolicy.tenant_id == tenant_id,
                InventoryPolicy.warehouse_id == warehouse_id,
                InventoryPolicy.spare_part_id == spare_part_id,
            )
        )

    def get_default_location(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
    ) -> WarehouseLocation | None:
        return session.scalar(
            select(WarehouseLocation).where(
                WarehouseLocation.tenant_id == tenant_id,
                WarehouseLocation.warehouse_id == warehouse_id,
                WarehouseLocation.code == "DEFAULT",
            )
        )

    def create_default_identity(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int,
        spare_part_id: int,
        policy_data: Mapping[str, Any],
    ) -> tuple[InventoryBalance, InventoryPolicy]:
        location = self.get_default_location(
            session,
            tenant_id,
            warehouse_id,
        )
        if location is None:
            location = WarehouseLocation(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                code="DEFAULT",
                name="Default location",
                location_type="DEFAULT",
                is_pickable=True,
                is_active=True,
            )
            session.add(location)
            session.flush()
        policy = InventoryPolicy(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            **policy_data,
        )
        balance = InventoryBalance(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            location_id=location.id,
            spare_part_id=spare_part_id,
        )
        session.add_all([policy, balance])
        session.flush()
        return balance, policy

    @staticmethod
    def update_policy(
        session: Session,
        tenant_id: str,
        policy: InventoryPolicy,
        data: Mapping[str, Any],
    ) -> InventoryPolicy:
        if policy.tenant_id != tenant_id:
            raise TenantScopeError(
                "InventoryPolicy belongs to another tenant"
            )
        for key, value in data.items():
            setattr(policy, key, value)
        policy.version += 1
        session.flush()
        return policy

    def list_for_spare(
        self,
        session: Session,
        tenant_id: str,
        spare_part_id: int,
    ) -> list[WarehouseInventory]:
        return list(
            session.scalars(
                select(WarehouseInventory)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .execution_options(
                    populate_existing=True
                )
                .where(
                    WarehouseInventory.tenant_id
                    == tenant_id,
                    WarehouseInventory.spare_part_id
                    == spare_part_id,
                )
                .order_by(
                    WarehouseInventory.warehouse_id,
                    WarehouseInventory.id,
                )
            ).all()
        )

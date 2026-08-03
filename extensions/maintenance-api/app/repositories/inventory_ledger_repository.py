from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    InventoryBalance,
    InventoryPolicy,
    SerializedItem,
    WarehouseLocation,
)


class InventoryLedgerRepository:
    def get_balance(
        self,
        session: Session,
        tenant_id: str,
        balance_id: int,
    ) -> InventoryBalance | None:
        return session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id == balance_id,
            )
        )

    def list_balances(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        warehouse_id: int | None = None,
        spare_part_id: int | None = None,
        location_id: int | None = None,
        lot_id: int | None = None,
        serial_item_id: int | None = None,
    ) -> tuple[list[InventoryBalance], int]:
        conditions = self._balance_conditions(
            tenant_id,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=location_id,
            lot_id=lot_id,
            serial_item_id=serial_item_id,
        )
        statement = (
            select(InventoryBalance)
            .where(*conditions)
            .order_by(InventoryBalance.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total = int(
            session.scalar(select(func.count()).select_from(InventoryBalance).where(*conditions)) or 0
        )
        return list(session.scalars(statement).all()), total

    def list_summaries(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        warehouse_id: int | None = None,
        spare_part_id: int | None = None,
        location_id: int | None = None,
        lot_id: int | None = None,
        serial_item_id: int | None = None,
        compatibility_identity: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = self._balance_conditions(
            tenant_id,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=location_id,
            lot_id=lot_id,
            serial_item_id=serial_item_id,
        )
        if compatibility_identity:
            conditions.append(
                self._compatibility_identity_exists(tenant_id)
            )
        statement = (
            select(
                InventoryBalance.warehouse_id.label("warehouse_id"),
                InventoryBalance.spare_part_id.label("spare_part_id"),
                func.sum(InventoryBalance.on_hand_quantity).label("on_hand_quantity"),
                func.sum(InventoryBalance.reserved_quantity).label("reserved_quantity"),
                func.sum(InventoryBalance.damaged_quantity).label("damaged_quantity"),
                func.sum(InventoryBalance.quarantined_quantity).label("quarantined_quantity"),
                func.sum(InventoryBalance.in_transit_quantity).label("in_transit_quantity"),
                func.coalesce(InventoryPolicy.safety_stock, Decimal("0")).label("safety_stock"),
                func.coalesce(InventoryPolicy.reorder_point, Decimal("0")).label("reorder_point"),
                InventoryPolicy.maximum_stock.label("maximum_stock"),
            )
            .outerjoin(
                InventoryPolicy,
                and_(
                    InventoryPolicy.tenant_id == tenant_id,
                    InventoryPolicy.warehouse_id == InventoryBalance.warehouse_id,
                    InventoryPolicy.spare_part_id == InventoryBalance.spare_part_id,
                ),
            )
            .where(*conditions)
            .group_by(
                InventoryBalance.warehouse_id,
                InventoryBalance.spare_part_id,
                InventoryPolicy.safety_stock,
                InventoryPolicy.reorder_point,
                InventoryPolicy.maximum_stock,
            )
            .order_by(InventoryBalance.warehouse_id, InventoryBalance.spare_part_id)
        )
        total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = session.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        ).mappings()
        return [dict(row) for row in rows], total

    @staticmethod
    def _compatibility_identity_exists(tenant_id: str):
        identity_balance = aliased(InventoryBalance)
        identity_location = aliased(WarehouseLocation)
        return (
            select(identity_balance.id)
            .join(
                identity_location,
                and_(
                    identity_location.tenant_id == tenant_id,
                    identity_location.id
                    == identity_balance.location_id,
                    identity_location.warehouse_id
                    == identity_balance.warehouse_id,
                ),
            )
            .where(
                identity_balance.tenant_id == tenant_id,
                identity_balance.warehouse_id
                == InventoryBalance.warehouse_id,
                identity_balance.spare_part_id
                == InventoryBalance.spare_part_id,
                identity_balance.lot_id.is_(None),
                identity_location.code == "DEFAULT",
            )
            .exists()
        )

    def serial_item_ids_by_balance(
        self,
        session: Session,
        tenant_id: str,
        balances: Sequence[InventoryBalance],
    ) -> dict[int, list[int]]:
        balance_ids = sorted({balance.id for balance in balances})
        if not balance_ids:
            return {}
        rows = session.execute(
            select(InventoryBalance.id, SerializedItem.id)
            .join(
                SerializedItem,
                and_(
                    SerializedItem.tenant_id == tenant_id,
                    SerializedItem.warehouse_id == InventoryBalance.warehouse_id,
                    SerializedItem.location_id == InventoryBalance.location_id,
                    SerializedItem.spare_part_id == InventoryBalance.spare_part_id,
                    or_(
                        SerializedItem.lot_id == InventoryBalance.lot_id,
                        and_(SerializedItem.lot_id.is_(None), InventoryBalance.lot_id.is_(None)),
                    ),
                ),
            )
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id.in_(balance_ids),
            )
            .order_by(InventoryBalance.id, SerializedItem.id)
        )
        result: dict[int, list[int]] = defaultdict(list)
        for balance_id, serial_item_id in rows:
            result[balance_id].append(serial_item_id)
        return dict(result)

    def lock_balances_statement(
        self,
        tenant_id: str,
        balance_ids: Sequence[int],
    ) -> Select[tuple[InventoryBalance]]:
        ids = sorted(set(balance_ids))
        return (
            select(InventoryBalance)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.id.in_(ids),
            )
            .order_by(InventoryBalance.id)
            .with_for_update()
        )

    def lock_balances(
        self,
        session: Session,
        tenant_id: str,
        balance_ids: Sequence[int],
    ) -> list[InventoryBalance]:
        return list(session.scalars(self.lock_balances_statement(tenant_id, balance_ids)).all())

    @staticmethod
    def _balance_conditions(
        tenant_id: str,
        *,
        warehouse_id: int | None,
        spare_part_id: int | None,
        location_id: int | None,
        lot_id: int | None,
        serial_item_id: int | None,
    ) -> list[Any]:
        conditions: list[Any] = [InventoryBalance.tenant_id == tenant_id]
        if warehouse_id is not None:
            conditions.append(InventoryBalance.warehouse_id == warehouse_id)
        if spare_part_id is not None:
            conditions.append(InventoryBalance.spare_part_id == spare_part_id)
        if location_id is not None:
            conditions.append(InventoryBalance.location_id == location_id)
        if lot_id is not None:
            conditions.append(InventoryBalance.lot_id == lot_id)
        if serial_item_id is not None:
            conditions.append(
                select(SerializedItem.id)
                .where(
                    SerializedItem.tenant_id == tenant_id,
                    SerializedItem.id == serial_item_id,
                    SerializedItem.warehouse_id == InventoryBalance.warehouse_id,
                    SerializedItem.location_id == InventoryBalance.location_id,
                    SerializedItem.spare_part_id == InventoryBalance.spare_part_id,
                    or_(
                        SerializedItem.lot_id == InventoryBalance.lot_id,
                        and_(SerializedItem.lot_id.is_(None), InventoryBalance.lot_id.is_(None)),
                    ),
                )
                .exists()
            )
        return conditions

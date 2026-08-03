from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    InventoryBalance,
    InventoryExpiryRule,
    InventoryLot,
    InventoryPolicy,
    SerializedItem,
    SparePart,
    Warehouse,
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
        statement = self._summary_statement(
            tenant_id,
            conditions,
        )
        total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = session.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        ).mappings()
        return [dict(row) for row in rows], total

    def summaries_for_parts(
        self,
        session: Session,
        tenant_id: str,
        spare_part_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        conditions = self._balance_conditions(
            tenant_id,
            warehouse_id=None,
            spare_part_id=None,
            location_id=None,
            lot_id=None,
            serial_item_id=None,
        )
        if spare_part_ids is not None:
            ids = sorted(set(spare_part_ids))
            if not ids:
                return []
            conditions.append(InventoryBalance.spare_part_id.in_(ids))
        rows = session.execute(
            self._summary_statement(tenant_id, conditions)
        ).mappings()
        return [dict(row) for row in rows]

    def count_balance_references(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int | None = None,
        spare_part_id: int | None = None,
    ) -> int:
        conditions = self._balance_conditions(
            tenant_id,
            warehouse_id=warehouse_id,
            spare_part_id=spare_part_id,
            location_id=None,
            lot_id=None,
            serial_item_id=None,
        )
        return int(
            session.scalar(
                select(func.count())
                .select_from(InventoryBalance)
                .where(*conditions)
            )
            or 0
        )

    def count_warehouse_references(
        self,
        session: Session,
        tenant_id: str,
        warehouse_id: int,
    ) -> int:
        references = (
            select(WarehouseLocation.id).where(
                WarehouseLocation.tenant_id == tenant_id,
                WarehouseLocation.warehouse_id == warehouse_id,
            ).exists(),
            select(InventoryPolicy.id).where(
                InventoryPolicy.tenant_id == tenant_id,
                InventoryPolicy.warehouse_id == warehouse_id,
            ).exists(),
            select(SerializedItem.id).where(
                SerializedItem.tenant_id == tenant_id,
                SerializedItem.warehouse_id == warehouse_id,
            ).exists(),
            select(InventoryBalance.id).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.warehouse_id == warehouse_id,
            ).exists(),
        )
        return int(bool(session.scalar(select(or_(*references)))))

    def count_spare_part_references(
        self,
        session: Session,
        tenant_id: str,
        spare_part_id: int,
    ) -> int:
        references = (
            select(InventoryPolicy.id).where(
                InventoryPolicy.tenant_id == tenant_id,
                InventoryPolicy.spare_part_id == spare_part_id,
            ).exists(),
            select(InventoryExpiryRule.id).where(
                InventoryExpiryRule.tenant_id == tenant_id,
                InventoryExpiryRule.spare_part_id == spare_part_id,
            ).exists(),
            select(InventoryLot.id).where(
                InventoryLot.tenant_id == tenant_id,
                InventoryLot.spare_part_id == spare_part_id,
            ).exists(),
            select(SerializedItem.id).where(
                SerializedItem.tenant_id == tenant_id,
                SerializedItem.spare_part_id == spare_part_id,
            ).exists(),
            select(InventoryBalance.id).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.spare_part_id == spare_part_id,
            ).exists(),
        )
        return int(bool(session.scalar(select(or_(*references)))))

    def count_low_stock_spare_parts(
        self,
        session: Session,
        tenant_id: str,
    ) -> int:
        summaries = (
            self._summary_statement(
                tenant_id,
                self._balance_conditions(
                    tenant_id,
                    warehouse_id=None,
                    spare_part_id=None,
                    location_id=None,
                    lot_id=None,
                    serial_item_id=None,
                ),
            )
            .order_by(None)
            .subquery()
        )
        available_quantity = (
            summaries.c.on_hand_quantity
            - summaries.c.reserved_quantity
            - summaries.c.damaged_quantity
            - summaries.c.quarantined_quantity
        )
        return int(
            session.scalar(
                select(func.count(func.distinct(summaries.c.spare_part_id)))
                .select_from(summaries)
                .join(
                    Warehouse,
                    and_(
                        Warehouse.id == summaries.c.warehouse_id,
                        Warehouse.tenant_id == tenant_id,
                    ),
                )
                .join(
                    SparePart,
                    and_(
                        SparePart.id == summaries.c.spare_part_id,
                        SparePart.tenant_id == tenant_id,
                    ),
                )
                .where(
                    Warehouse.is_active.is_(True),
                    SparePart.is_active.is_(True),
                    available_quantity < summaries.c.reorder_point,
                )
            )
            or 0
        )

    @staticmethod
    def _summary_statement(
        tenant_id: str,
        conditions: Sequence[Any],
    ) -> Select:
        return (
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

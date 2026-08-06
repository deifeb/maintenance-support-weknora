from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import NotFoundError
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

if TYPE_CHECKING:
    from app.services.inventory_fefo_service import FEFOCandidate


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

    def list_fefo_candidates(
        self,
        session: Session,
        tenant_id: str,
        *,
        spare_part_id: int,
        warehouse_id: int,
        location_id: int | None = None,
        lot_id: int | None = None,
        serial_item_id: int | None = None,
    ) -> list[FEFOCandidate]:
        from app.services.inventory_fefo_service import FEFOCandidate

        conditions = [
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.spare_part_id == spare_part_id,
            InventoryBalance.warehouse_id == warehouse_id,
        ]
        if location_id is not None:
            conditions.append(InventoryBalance.location_id == location_id)
        if lot_id is not None:
            conditions.append(InventoryBalance.lot_id == lot_id)
        if serial_item_id is not None:
            conditions.append(SerializedItem.id == serial_item_id)

        available_quantity = (
            InventoryBalance.on_hand_quantity
            - InventoryBalance.reserved_quantity
            - InventoryBalance.damaged_quantity
            - InventoryBalance.quarantined_quantity
        )
        statement = (
            select(
                InventoryBalance.id.label("balance_id"),
                InventoryBalance.location_id.label("location_id"),
                InventoryBalance.lot_id.label("lot_id"),
                SerializedItem.id.label("serial_item_id"),
                InventoryLot.expiry_date.label("expiry_date"),
                InventoryLot.received_date.label("received_date"),
                available_quantity.label("available_quantity"),
                WarehouseLocation.is_active.label("location_active"),
                WarehouseLocation.is_pickable.label("location_pickable"),
                InventoryLot.is_frozen.label("lot_frozen"),
                InventoryLot.quality_status.label("lot_quality"),
                SerializedItem.status.label("serial_status"),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.id == InventoryBalance.warehouse_id,
                ),
            )
            .join(
                SparePart,
                and_(
                    SparePart.tenant_id == tenant_id,
                    SparePart.id == InventoryBalance.spare_part_id,
                ),
            )
            .join(
                WarehouseLocation,
                and_(
                    WarehouseLocation.tenant_id == tenant_id,
                    WarehouseLocation.id == InventoryBalance.location_id,
                    WarehouseLocation.warehouse_id == InventoryBalance.warehouse_id,
                ),
            )
            .outerjoin(
                InventoryLot,
                and_(
                    InventoryLot.tenant_id == tenant_id,
                    InventoryLot.id == InventoryBalance.lot_id,
                    InventoryLot.spare_part_id == InventoryBalance.spare_part_id,
                ),
            )
            .outerjoin(
                SerializedItem,
                and_(
                    SerializedItem.tenant_id == tenant_id,
                    SerializedItem.warehouse_id == InventoryBalance.warehouse_id,
                    SerializedItem.location_id == InventoryBalance.location_id,
                    SerializedItem.spare_part_id == InventoryBalance.spare_part_id,
                    or_(
                        SerializedItem.lot_id == InventoryBalance.lot_id,
                        and_(
                            SerializedItem.lot_id.is_(None),
                            InventoryBalance.lot_id.is_(None),
                        ),
                    ),
                ),
            )
            .where(*conditions)
            .order_by(InventoryBalance.id, SerializedItem.id)
        )

        return [
            FEFOCandidate(
                balance_id=row.balance_id,
                location_id=row.location_id,
                lot_id=row.lot_id,
                serial_item_id=row.serial_item_id,
                expiry_date=row.expiry_date,
                received_date=row.received_date,
                available_quantity=Decimal(row.available_quantity),
                exclusion_facts=self._fefo_exclusion_facts(
                    location_active=row.location_active,
                    location_pickable=row.location_pickable,
                    lot_frozen=row.lot_frozen,
                    lot_quality=row.lot_quality,
                    serial_status=row.serial_status,
                ),
            )
            for row in session.execute(statement)
        ]

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

    def inventory_export_rows(
        self,
        session: Session,
        tenant_id: str,
        *,
        keyword: str,
        warehouse_id: int | None,
        spare_part_id: int | None,
        sort_by: str,
        sort_order: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        on_hand = func.sum(InventoryBalance.on_hand_quantity)
        reserved = func.sum(InventoryBalance.reserved_quantity)
        damaged = func.sum(InventoryBalance.damaged_quantity)
        quarantined = func.sum(InventoryBalance.quarantined_quantity)
        in_transit = func.sum(InventoryBalance.in_transit_quantity)
        available = on_hand - reserved - damaged - quarantined
        conditions = [
            InventoryBalance.tenant_id == tenant_id,
            Warehouse.tenant_id == tenant_id,
            SparePart.tenant_id == tenant_id,
        ]
        if warehouse_id is not None:
            conditions.append(InventoryBalance.warehouse_id == warehouse_id)
        if spare_part_id is not None:
            conditions.append(InventoryBalance.spare_part_id == spare_part_id)
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    Warehouse.code.ilike(pattern),
                    Warehouse.name.ilike(pattern),
                    SparePart.code.ilike(pattern),
                    SparePart.name.ilike(pattern),
                )
            )
        statement = (
            select(
                Warehouse.id.label("warehouse_id"),
                SparePart.id.label("spare_part_id"),
                Warehouse.code.label("warehouse_code"),
                SparePart.code.label("spare_part_code"),
                on_hand.label("on_hand_quantity"),
                reserved.label("reserved_quantity"),
                damaged.label("damaged_quantity"),
                quarantined.label("quarantined_quantity"),
                in_transit.label("in_transit_quantity"),
                available.label("available_quantity"),
                func.coalesce(InventoryPolicy.safety_stock, Decimal("0")).label(
                    "safety_stock"
                ),
                func.coalesce(InventoryPolicy.reorder_point, Decimal("0")).label(
                    "reorder_point"
                ),
                InventoryPolicy.maximum_stock.label("maximum_stock"),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.id == InventoryBalance.warehouse_id,
                    Warehouse.tenant_id == tenant_id,
                ),
            )
            .join(
                SparePart,
                and_(
                    SparePart.id == InventoryBalance.spare_part_id,
                    SparePart.tenant_id == tenant_id,
                ),
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
                Warehouse.id,
                SparePart.id,
                Warehouse.code,
                SparePart.code,
                InventoryPolicy.safety_stock,
                InventoryPolicy.reorder_point,
                InventoryPolicy.maximum_stock,
            )
        )
        sort_expression = {
            "on_hand_quantity": on_hand,
            "available_quantity": available,
        }.get(sort_by)
        ordering = []
        if sort_expression is not None:
            ordering.append(
                sort_expression.desc()
                if sort_order == "desc"
                else sort_expression.asc()
            )
        ordering.extend((Warehouse.id.asc(), SparePart.id.asc()))
        rows = session.execute(
            statement.order_by(*ordering).limit(limit)
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
    def _fefo_exclusion_facts(
        *,
        location_active: bool,
        location_pickable: bool,
        lot_frozen: bool | None,
        lot_quality: str | None,
        serial_status: str | None,
    ) -> tuple[str, ...]:
        facts: list[str] = []
        if not location_active:
            facts.append("LOCATION_INACTIVE")
        if not location_pickable:
            facts.append("LOCATION_NOT_PICKABLE")
        if lot_frozen:
            facts.append("LOT_FROZEN")
        if lot_quality in {"QUARANTINED", "DAMAGED", "REJECTED"}:
            facts.append(f"LOT_QUALITY_{lot_quality}")
        if serial_status == "FROZEN":
            facts.append("SERIAL_FROZEN")
        elif serial_status is not None and serial_status != "IN_STOCK":
            facts.append(f"SERIAL_STATUS_{serial_status}")
        return tuple(facts)

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
        requested_ids = sorted(set(balance_ids))
        balances = list(
            session.scalars(
                self.lock_balances_statement(tenant_id, requested_ids)
            ).all()
        )
        self._require_complete_ids(
            resource="inventory_balance",
            requested_ids=requested_ids,
            loaded_ids=[balance.id for balance in balances],
        )
        return balances

    def lock_lots(
        self,
        session: Session,
        tenant_id: str,
        lot_ids: Sequence[int],
    ) -> list[InventoryLot]:
        requested_ids = sorted(set(lot_ids))
        if not requested_ids:
            return []
        lots = list(
            session.scalars(
                select(InventoryLot)
                .where(
                    InventoryLot.tenant_id == tenant_id,
                    InventoryLot.id.in_(requested_ids),
                )
                .order_by(InventoryLot.id)
                .with_for_update()
            ).all()
        )
        self._require_complete_ids(
            resource="inventory_lot",
            requested_ids=requested_ids,
            loaded_ids=[lot.id for lot in lots],
        )
        return lots

    def lock_serial_items(
        self,
        session: Session,
        tenant_id: str,
        serial_item_ids: Sequence[int],
    ) -> list[SerializedItem]:
        requested_ids = sorted(set(serial_item_ids))
        if not requested_ids:
            return []
        serial_items = list(
            session.scalars(
                select(SerializedItem)
                .where(
                    SerializedItem.tenant_id == tenant_id,
                    SerializedItem.id.in_(requested_ids),
                )
                .order_by(SerializedItem.id)
                .with_for_update()
            ).all()
        )
        self._require_complete_ids(
            resource="serialized_item",
            requested_ids=requested_ids,
            loaded_ids=[item.id for item in serial_items],
        )
        return serial_items

    @staticmethod
    def _require_complete_ids(
        *,
        resource: str,
        requested_ids: Sequence[int],
        loaded_ids: Sequence[int],
    ) -> None:
        missing_ids = sorted(set(requested_ids) - set(loaded_ids))
        if missing_ids:
            raise NotFoundError(resource, missing_ids[0])

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

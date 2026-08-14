from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance,
    InventoryStocktake,
    InventoryStocktakeLine,
    WarehouseLocation,
)
from app.security.actor import ActorContext


class InventoryStocktakeRepository:
    def get(
        self,
        session: Session,
        tenant_id: str,
        stocktake_id: int,
    ) -> InventoryStocktake | None:
        return session.scalar(
            select(InventoryStocktake).where(
                InventoryStocktake.tenant_id == tenant_id,
                InventoryStocktake.id == stocktake_id,
            )
        )

    def lock(
        self,
        session: Session,
        tenant_id: str,
        stocktake_id: int,
    ) -> InventoryStocktake | None:
        return session.scalar(
            select(InventoryStocktake)
            .where(
                InventoryStocktake.tenant_id == tenant_id,
                InventoryStocktake.id == stocktake_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def lock_line(
        self,
        session: Session,
        tenant_id: str,
        stocktake_id: int,
        line_id: int,
    ) -> InventoryStocktakeLine | None:
        return session.scalar(
            select(InventoryStocktakeLine)
            .where(
                InventoryStocktakeLine.tenant_id == tenant_id,
                InventoryStocktakeLine.stocktake_id == stocktake_id,
                InventoryStocktakeLine.id == line_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def list_lines(
        self,
        session: Session,
        tenant_id: str,
        stocktake_id: int,
    ) -> list[InventoryStocktakeLine]:
        return list(
            session.scalars(
                select(InventoryStocktakeLine)
                .where(
                    InventoryStocktakeLine.tenant_id == tenant_id,
                    InventoryStocktakeLine.stocktake_id == stocktake_id,
                )
                .order_by(InventoryStocktakeLine.id)
            ).all()
        )

    def list_unresolved_lines(
        self,
        session: Session,
        tenant_id: str,
        stocktake_id: int,
    ) -> list[InventoryStocktakeLine]:
        return list(
            session.scalars(
                select(InventoryStocktakeLine)
                .where(
                    InventoryStocktakeLine.tenant_id == tenant_id,
                    InventoryStocktakeLine.stocktake_id == stocktake_id,
                    InventoryStocktakeLine.resolution != "ADJUSTED",
                )
                .order_by(InventoryStocktakeLine.id)
            ).all()
        )

    def scope_exists(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int,
        location_id: int,
    ) -> bool:
        location = session.scalar(
            select(WarehouseLocation.id).where(
                WarehouseLocation.tenant_id == tenant_id,
                WarehouseLocation.id == location_id,
                WarehouseLocation.warehouse_id == warehouse_id,
            )
        )
        return location is not None

    def list_scope_balances(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int,
        location_id: int,
    ) -> list[InventoryBalance]:
        return list(
            session.scalars(
                select(InventoryBalance)
                .where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.warehouse_id == warehouse_id,
                    InventoryBalance.location_id == location_id,
                )
                .order_by(InventoryBalance.id)
                .with_for_update()
            ).all()
        )

    def create(
        self,
        session: Session,
        *,
        actor: ActorContext,
        warehouse_id: int,
        location_id: int,
        snapshot_at: datetime,
    ) -> InventoryStocktake:
        stocktake = InventoryStocktake(
            tenant_id=actor.tenant_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            status="DRAFT",
            snapshot_at=snapshot_at,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
        )
        session.add(stocktake)
        session.flush()
        return stocktake

    def create_lines(
        self,
        session: Session,
        *,
        stocktake: InventoryStocktake,
        balances: Sequence[InventoryBalance],
    ) -> list[InventoryStocktakeLine]:
        lines = [
            InventoryStocktakeLine(
                tenant_id=stocktake.tenant_id,
                stocktake_id=stocktake.id,
                balance_id=balance.id,
                spare_part_id=balance.spare_part_id,
                lot_id=balance.lot_id,
                serial_item_id=None,
                system_quantity=balance.on_hand_quantity,
                counted_quantity=None,
                variance_quantity=None,
                snapshot_balance_version=balance.version,
                confirmed_transaction_id=None,
                resolution="PENDING",
                conflict_details_json=None,
            )
            for balance in balances
        ]
        session.add_all(lines)
        session.flush()
        return lines

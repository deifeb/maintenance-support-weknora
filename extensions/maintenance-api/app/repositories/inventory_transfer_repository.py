from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance,
    InventoryTransfer,
    InventoryTransferLine,
)
from app.security.actor import ActorContext


class InventoryTransferRepository:
    def get_transfer(
        self,
        session: Session,
        tenant_id: str,
        transfer_id: int,
    ) -> InventoryTransfer | None:
        return session.scalar(
            select(InventoryTransfer).where(
                InventoryTransfer.tenant_id == tenant_id,
                InventoryTransfer.id == transfer_id,
            )
        )

    def lock_transfer(
        self,
        session: Session,
        tenant_id: str,
        transfer_id: int,
    ) -> InventoryTransfer | None:
        return session.scalar(
            self.lock_statement(
                tenant_id,
                transfer_id,
            ).execution_options(populate_existing=True)
        )

    def lock_statement(
        self,
        tenant_id: str,
        transfer_id: int,
    ) -> Select[tuple[InventoryTransfer]]:
        return (
            select(InventoryTransfer)
            .where(
                InventoryTransfer.tenant_id == tenant_id,
                InventoryTransfer.id == transfer_id,
            )
            .with_for_update()
        )

    def list_lines(
        self,
        session: Session,
        tenant_id: str,
        transfer_id: int,
    ) -> list[InventoryTransferLine]:
        return list(
            session.scalars(
                select(InventoryTransferLine)
                .where(
                    InventoryTransferLine.tenant_id
                    == tenant_id,
                    InventoryTransferLine.transfer_id
                    == transfer_id,
                )
                .order_by(InventoryTransferLine.id)
            ).all()
        )

    def get_target_balance(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int,
        location_id: int,
        spare_part_id: int,
        lot_id: int | None,
    ) -> InventoryBalance | None:
        statement = select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.warehouse_id
            == warehouse_id,
            InventoryBalance.location_id
            == location_id,
            InventoryBalance.spare_part_id
            == spare_part_id,
        )

        if lot_id is None:
            statement = statement.where(
                InventoryBalance.lot_id.is_(None)
            )
        else:
            statement = statement.where(
                InventoryBalance.lot_id == lot_id
            )

        return session.scalar(statement)

    def resolve_target_balance(
        self,
        session: Session,
        tenant_id: str,
        *,
        warehouse_id: int,
        location_id: int,
        spare_part_id: int,
        lot_id: int | None,
    ) -> InventoryBalance:
        existing = self.get_target_balance(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            spare_part_id=spare_part_id,
            lot_id=lot_id,
        )
        if existing is not None:
            return existing

        try:
            with session.begin_nested():
                balance = InventoryBalance(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    location_id=location_id,
                    spare_part_id=spare_part_id,
                    lot_id=lot_id,
                    on_hand_quantity=Decimal("0.0000"),
                    reserved_quantity=Decimal("0.0000"),
                    damaged_quantity=Decimal("0.0000"),
                    quarantined_quantity=Decimal("0.0000"),
                    in_transit_quantity=Decimal("0.0000"),
                    version=1,
                )
                session.add(balance)
                session.flush()
                return balance
        except IntegrityError:
            winner = self.get_target_balance(
                session,
                tenant_id,
                warehouse_id=warehouse_id,
                location_id=location_id,
                spare_part_id=spare_part_id,
                lot_id=lot_id,
            )
            if winner is None:
                raise
            return winner

    def create_transfer(
        self,
        session: Session,
        *,
        actor: ActorContext,
        source_warehouse_id: int,
        source_location_id: int,
        target_warehouse_id: int,
        target_location_id: int,
        reference_type: str | None,
        reference_id: str | None,
        reason: str,
    ) -> InventoryTransfer:
        transfer = InventoryTransfer(
            tenant_id=actor.tenant_id,
            status="DRAFT",
            source_warehouse_id=source_warehouse_id,
            source_location_id=source_location_id,
            target_warehouse_id=target_warehouse_id,
            target_location_id=target_location_id,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
            version=1,
        )
        session.add(transfer)
        session.flush()
        return transfer

    def create_lines(
        self,
        session: Session,
        *,
        transfer: InventoryTransfer,
        lines: Sequence[dict],
    ) -> list[InventoryTransferLine]:
        created: list[InventoryTransferLine] = []

        for values in lines:
            line = InventoryTransferLine(
                tenant_id=transfer.tenant_id,
                transfer_id=transfer.id,
                spare_part_id=values["spare_part_id"],
                source_balance_id=values[
                    "source_balance_id"
                ],
                target_balance_id=values[
                    "target_balance_id"
                ],
                lot_id=values.get("lot_id"),
                serial_item_id=values.get(
                    "serial_item_id"
                ),
                requested_quantity=Decimal(
                    values["requested_quantity"]
                ),
                dispatched_quantity=Decimal(
                    "0.0000"
                ),
                received_quantity=Decimal(
                    "0.0000"
                ),
                expected_source_version=values[
                    "expected_source_version"
                ],
                expected_target_version=values[
                    "expected_target_version"
                ],
                version=1,
            )
            session.add(line)
            session.flush()
            created.append(line)

        return created

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import InventoryReservation, InventoryReservationLine
from app.security.actor import ActorContext


class InventoryReservationRepository:
    def get(
        self,
        session: Session,
        tenant_id: str,
        reservation_id: int,
    ) -> InventoryReservation | None:
        return session.scalar(
            select(InventoryReservation).where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.id == reservation_id,
            )
        )

    def list(
        self,
        session: Session,
        tenant_id: str,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
        status: str | None = None,
    ) -> list[InventoryReservation]:
        conditions = [InventoryReservation.tenant_id == tenant_id]
        if owner_type is not None:
            conditions.append(InventoryReservation.owner_type == owner_type)
        if owner_id is not None:
            conditions.append(InventoryReservation.owner_id == owner_id)
        if status is not None:
            conditions.append(InventoryReservation.status == status)
        return list(
            session.scalars(
                select(InventoryReservation)
                .where(*conditions)
                .order_by(InventoryReservation.id)
            ).all()
        )

    def list_lines(
        self,
        session: Session,
        tenant_id: str,
        reservation_id: int,
    ) -> list[InventoryReservationLine]:
        return list(
            session.scalars(
                select(InventoryReservationLine)
                .where(
                    InventoryReservationLine.tenant_id == tenant_id,
                    InventoryReservationLine.reservation_id == reservation_id,
                )
                .order_by(InventoryReservationLine.id)
            ).all()
        )

    def lock_statement(
        self,
        tenant_id: str,
        reservation_id: int,
    ) -> Select[tuple[InventoryReservation]]:
        return (
            select(InventoryReservation)
            .where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.id == reservation_id,
            )
            .with_for_update()
        )

    def lock_aggregate(
        self,
        session: Session,
        tenant_id: str,
        reservation_id: int,
    ) -> tuple[InventoryReservation, list[InventoryReservationLine]] | None:
        reservation = session.scalar(self.lock_statement(tenant_id, reservation_id))
        if reservation is None:
            return None
        lines = list(
            session.scalars(
                select(InventoryReservationLine)
                .where(
                    InventoryReservationLine.tenant_id == tenant_id,
                    InventoryReservationLine.reservation_id == reservation_id,
                )
                .order_by(InventoryReservationLine.id)
                .with_for_update()
            ).all()
        )
        return reservation, lines

    def list_expired_candidates(
        self,
        session: Session,
        tenant_id: str,
        *,
        as_of: datetime,
        limit: int,
    ) -> list[InventoryReservation]:
        if limit <= 0:
            return []
        return list(
            session.scalars(
                select(InventoryReservation)
                .where(
                    InventoryReservation.tenant_id == tenant_id,
                    InventoryReservation.status.in_(("ACTIVE", "PARTIALLY_ISSUED")),
                    InventoryReservation.expires_at.is_not(None),
                    InventoryReservation.expires_at <= as_of,
                )
                .order_by(
                    InventoryReservation.expires_at,
                    InventoryReservation.id,
                )
                .limit(limit)
            ).all()
        )

    def create(
        self,
        session: Session,
        *,
        actor: ActorContext,
        owner_type: str,
        owner_id: str,
        expires_at: datetime | None,
        allow_partial: bool,
    ) -> InventoryReservation:
        reservation = InventoryReservation(
            tenant_id=actor.tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            status="ACTIVE",
            expires_at=expires_at,
            allow_partial=allow_partial,
            actor_user_id=actor.user_id,
            actor_roles_json=[actor.role.value],
            request_id=actor.request_id,
            version=1,
        )
        session.add(reservation)
        session.flush()
        return reservation

    def create_lines(
        self,
        session: Session,
        *,
        reservation: InventoryReservation,
        lines: Sequence[dict],
    ) -> list[InventoryReservationLine]:
        created: list[InventoryReservationLine] = []
        for values in lines:
            line = InventoryReservationLine(
                tenant_id=reservation.tenant_id,
                reservation_id=reservation.id,
                spare_part_id=values["spare_part_id"],
                balance_id=values["balance_id"],
                lot_id=values.get("lot_id"),
                serial_item_id=values.get("serial_item_id"),
                requested_quantity=Decimal(values["requested_quantity"]),
                reserved_quantity=Decimal(values["reserved_quantity"]),
                issued_quantity=Decimal("0.0000"),
                released_quantity=Decimal("0.0000"),
                expected_balance_version=values["expected_balance_version"],
                fefo_rank=values["fefo_rank"],
                fefo_override_reason=values.get("fefo_override_reason"),
                recommended_selection_json=values.get("recommended_selection_json"),
                actual_selection_json=values.get("actual_selection_json"),
                version=1,
            )
            session.add(line)
            session.flush()
            created.append(line)
        return created

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models import InventoryReservation
from app.schemas.inventory_reservation import ExpireCommand
from app.security.actor import ActorContext, MaintenanceRole
from app.services.inventory_reservation_service import InventoryReservationService
from app.workers.task_registry import reservation_expiry_registry

SessionFactory = Callable[[], Session]
_ELIGIBLE_STATUSES = ("ACTIVE", "PARTIALLY_ISSUED")


@dataclass(frozen=True, slots=True)
class ExpiryItemResult:
    tenant_id: str
    reservation_id: int
    transaction_id: int | None
    code: str
    request_id: str


@dataclass(frozen=True, slots=True)
class ExpiryBatchResult:
    items: tuple[ExpiryItemResult, ...]


def expiry_idempotency_key(tenant_id: str, reservation_id: int, version: int) -> str:
    return f"reservation-expire:{tenant_id}:{reservation_id}:{version}"


def expire_inventory_reservations(
    session_factory: SessionFactory,
    *,
    as_of: datetime,
    batch_size: int = 100,
) -> ExpiryBatchResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    observed = _scan_expired_reservations(
        session_factory,
        as_of=as_of,
        batch_size=batch_size,
    )
    items: list[ExpiryItemResult] = []
    for tenant_id, reservation_id in observed:
        item = _expire_one(
            session_factory,
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            as_of=as_of,
        )
        if item is not None:
            items.append(item)
    return ExpiryBatchResult(items=tuple(items))


def _scan_expired_reservations(
    session_factory: SessionFactory,
    *,
    as_of: datetime,
    batch_size: int,
) -> tuple[tuple[str, int], ...]:
    session = session_factory()
    try:
        rows = session.execute(
            select(
                InventoryReservation.tenant_id,
                InventoryReservation.id,
            )
            .where(
                InventoryReservation.status.in_(_ELIGIBLE_STATUSES),
                InventoryReservation.expires_at.is_not(None),
                InventoryReservation.expires_at <= as_of,
            )
            .order_by(
                InventoryReservation.tenant_id,
                InventoryReservation.id,
            )
            .limit(batch_size)
        ).all()
        return tuple((str(tenant_id), int(reservation_id)) for tenant_id, reservation_id in rows)
    finally:
        session.close()


def _expire_one(
    session_factory: SessionFactory,
    *,
    tenant_id: str,
    reservation_id: int,
    as_of: datetime,
) -> ExpiryItemResult | None:
    task_key = (tenant_id, reservation_id)
    if not reservation_expiry_registry.register(task_key):
        return None

    session = session_factory()
    try:
        reservation = session.scalar(
            select(InventoryReservation)
            .where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.id == reservation_id,
            )
            .with_for_update()
        )
        if (
            reservation is None
            or reservation.status not in _ELIGIBLE_STATUSES
            or reservation.expires_at is None
            or _as_utc(reservation.expires_at) > _as_utc(as_of)
        ):
            session.rollback()
            return None

        observed_version = reservation.version
        idempotency_key = expiry_idempotency_key(
            tenant_id,
            reservation_id,
            observed_version,
        )
        request_id = f"reservation-expiry:{tenant_id}:{reservation_id}:{observed_version}"
        actor = ActorContext(
            user_id="inventory-reservation-expiry-worker",
            tenant_id=tenant_id,
            role=MaintenanceRole.CONTRIBUTOR,
            request_id=request_id,
            token_id="inventory-reservation-expiry-worker",
        )
        service = InventoryReservationService()
        service.expire(
            session,
            actor,
            reservation_id,
            command=ExpireCommand(
                observed_version=observed_version,
                as_of=as_of,
            ),
            idempotency_key=idempotency_key,
        )
        transaction = service.transaction_repository.get_idempotent(
            session,
            tenant_id,
            "UNRESERVE",
            idempotency_key,
        )
        transaction_id = transaction.id if transaction is not None else None
        session.commit()
        return ExpiryItemResult(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            transaction_id=transaction_id,
            code="EXPIRED",
            request_id=request_id,
        )
    except AppException as exc:
        session.rollback()
        return ExpiryItemResult(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            transaction_id=None,
            code=exc.code,
            request_id=exc.request_id or f"reservation-expiry:{tenant_id}:{reservation_id}",
        )
    except Exception:
        session.rollback()
        return ExpiryItemResult(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            transaction_id=None,
            code="INVENTORY_RESERVATION_EXPIRY_FAILED",
            request_id=f"reservation-expiry:{tenant_id}:{reservation_id}",
        )
    finally:
        session.close()
        reservation_expiry_registry.unregister(task_key)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

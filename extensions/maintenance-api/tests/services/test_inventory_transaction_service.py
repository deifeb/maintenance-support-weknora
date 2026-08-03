import hashlib
import json
from decimal import Decimal

import pytest
from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    InsufficientMaintenanceRoleError,
    NotFoundError,
)
from app.db.session import SessionLocal
from app.models import (
    InventoryBalance,
    InventoryLedgerEntry,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from pydantic import ValidationError
from sqlalchemy import func, select


def _transaction_api():
    from app.repositories.inventory_transaction_repository import (
        InventoryTransactionRepository,
    )
    from app.schemas.inventory_ledger import InventoryQuantityDelta
    from app.services.inventory_transaction_service import (
        InventoryTransactionService,
        inventory_transaction_service,
    )

    return (
        InventoryQuantityDelta,
        InventoryTransactionRepository,
        InventoryTransactionService,
        inventory_transaction_service,
    )


def _seed_balance(
    session,
    *,
    tenant_id: str = "tenant-a",
    suffix: str = "A",
    on_hand: str = "0",
    reserved: str = "0",
    damaged: str = "0",
    quarantined: str = "0",
    in_transit: str = "0",
) -> InventoryBalance:
    warehouse = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-TX-{suffix}",
        name=f"Warehouse {suffix}",
    )
    part = SparePart(
        tenant_id=tenant_id,
        code=f"SP-TX-{suffix}",
        name=f"Spare {suffix}",
    )
    session.add_all([warehouse, part])
    session.flush()
    location = WarehouseLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=f"LOC-TX-{suffix}",
        name=f"Location {suffix}",
        location_type="SHELF",
    )
    session.add(location)
    session.flush()
    balance = InventoryBalance(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        spare_part_id=part.id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal(reserved),
        damaged_quantity=Decimal(damaged),
        quarantined_quantity=Decimal(quarantined),
        in_transit_quantity=Decimal(in_transit),
    )
    session.add(balance)
    session.flush()
    return balance


def test_adjust_is_idempotent_balanced_and_scoped_to_actor_tenant(
    session,
    actor_admin,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)
    expected_hash_payload = {
        "balance_id": balance.id,
        "deltas": {
            "damaged": "0",
            "in_transit": "0",
            "on_hand": "3",
            "quarantined": "0",
            "reserved": "0",
        },
        "expected_version": 1,
        "operation_type": "ADJUST",
        "reason": "cycle correction",
    }
    expected_hash = hashlib.sha256(
        json.dumps(
            expected_hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    first = service.adjust(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
        reason="cycle correction",
        idempotency_key="adj-1",
    )
    replay = service.adjust(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=1,
        deltas=InventoryQuantityDelta(on_hand=Decimal("3.0000")),
        reason="cycle correction",
        idempotency_key="adj-1",
    )

    assert replay == first
    assert first.tenant_id == actor_admin.tenant_id
    assert first.actor_user_id == actor_admin.user_id
    assert first.actor_roles == ["admin"]
    assert first.request_hash == expected_hash
    assert len(first.entries) == 1
    entry = first.entries[0]
    assert entry.on_hand_delta == Decimal("3.0000")
    assert entry.state_before_json == {
        "on_hand": "0.0000",
        "reserved": "0.0000",
        "damaged": "0.0000",
        "quarantined": "0.0000",
        "in_transit": "0.0000",
    }
    assert entry.state_after_json == {
        "on_hand": "3.0000",
        "reserved": "0.0000",
        "damaged": "0.0000",
        "quarantined": "0.0000",
        "in_transit": "0.0000",
    }
    assert entry.resulting_balance_version == 2
    assert balance.on_hand_quantity == Decimal("3.0000")
    assert balance.version == 2
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 1


def test_opening_allows_contributor_but_adjust_requires_admin(
    session,
    actor_contributor,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)

    opened = service.opening(
        session,
        actor_contributor,
        balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("5")),
        reason="initial count",
        idempotency_key="open-1",
    )

    assert opened.operation_type == "OPENING"
    assert opened.tenant_id == actor_contributor.tenant_id
    with pytest.raises(InsufficientMaintenanceRoleError) as exc_info:
        service.adjust(
            session,
            actor_contributor,
            balance_id=balance.id,
            expected_version=balance.version,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason="unauthorized correction",
            idempotency_key="adj-forbidden",
        )
    assert exc_info.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"
    assert exc_info.value.request_id == actor_contributor.request_id


def test_opening_rejects_viewer(session, actor_viewer) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)

    with pytest.raises(InsufficientMaintenanceRoleError) as exc_info:
        service.opening(
            session,
            actor_viewer,
            balance_id=balance.id,
            expected_version=balance.version,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason="initial count",
            idempotency_key="open-viewer",
        )

    assert exc_info.value.details == {
        "required_role": "contributor",
        "actual_role": "viewer",
    }


def test_adjust_rejects_stale_version_and_cross_tenant_balance(
    session,
    actor_admin,
    actor_context,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)

    with pytest.raises(ConflictError) as exc_info:
        service.adjust(
            session,
            actor_admin,
            balance_id=balance.id,
            expected_version=balance.version + 1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason="stale correction",
            idempotency_key="adj-stale",
        )
    assert exc_info.value.code == "INVENTORY_VERSION_CONFLICT"
    assert exc_info.value.details == {
        "balance_id": balance.id,
        "expected_version": 2,
        "actual_version": 1,
        "conflict_object": "inventory_balance",
        "retryable": True,
    }

    with pytest.raises(NotFoundError):
        service.adjust(
            session,
            actor_context(tenant_id="tenant-b", role=actor_admin.role),
            balance_id=balance.id,
            expected_version=balance.version,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason="cross tenant correction",
            idempotency_key="adj-cross-tenant",
        )


@pytest.mark.parametrize(
    ("balance_values", "delta_values", "expected_code"),
    [
        (
            {"on_hand": "2"},
            {"on_hand": Decimal("-3")},
            "INVENTORY_NEGATIVE_QUANTITY",
        ),
        (
            {"on_hand": "5", "reserved": "4"},
            {"damaged": Decimal("2")},
            "INVENTORY_ALLOCATION_EXCEEDS_ON_HAND",
        ),
        (
            {"on_hand": "99999999999999"},
            {"on_hand": Decimal("1")},
            "INVENTORY_QUANTITY_OUT_OF_RANGE",
        ),
    ],
)
def test_adjust_rejects_invalid_resulting_quantity_state(
    session,
    actor_admin,
    balance_values,
    delta_values,
    expected_code,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session, **balance_values)

    with pytest.raises(BusinessValidationError) as exc_info:
        service.adjust(
            session,
            actor_admin,
            balance_id=balance.id,
            expected_version=balance.version,
            deltas=InventoryQuantityDelta(**delta_values),
            reason="invalid correction",
            idempotency_key=f"adj-{expected_code}",
        )

    assert exc_info.value.code == expected_code
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0


def test_quantity_operation_rejects_zero_delta(session, actor_admin) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)

    with pytest.raises(BusinessValidationError) as exc_info:
        service.adjust(
            session,
            actor_admin,
            balance_id=balance.id,
            expected_version=balance.version,
            deltas=InventoryQuantityDelta(),
            reason="no correction",
            idempotency_key="adj-zero",
        )

    assert exc_info.value.code == "INVENTORY_ZERO_DELTA"


def test_idempotency_identity_includes_operation_and_rejects_changed_payload(
    session,
    actor_admin,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)
    key = "shared-operation-key"

    opening = service.opening(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("2")),
        reason="initial count",
        idempotency_key=key,
    )
    adjustment = service.adjust(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
        reason="cycle correction",
        idempotency_key=key,
    )

    assert opening.id != adjustment.id
    with pytest.raises(ConflictError) as exc_info:
        service.adjust(
            session,
            actor_admin,
            balance_id=balance.id,
            expected_version=2,
            deltas=InventoryQuantityDelta(on_hand=Decimal("9")),
            reason="changed payload",
            idempotency_key=key,
        )
    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 2
    assert balance.on_hand_quantity == Decimal("3.0000")


def test_decimal_contract_rejects_float_excess_scale_and_precision() -> None:
    InventoryQuantityDelta, _, _, _ = _transaction_api()

    for invalid in [1.25, "0.00001", "100000000000000.0000"]:
        with pytest.raises(ValidationError):
            InventoryQuantityDelta(on_hand=invalid)


def test_failed_append_rolls_back_balance_transaction_and_entry(
    session,
    actor_admin,
) -> None:
    (
        InventoryQuantityDelta,
        InventoryTransactionRepository,
        InventoryTransactionService,
        _,
    ) = _transaction_api()
    balance = _seed_balance(session)
    session.commit()
    balance_id = balance.id

    class FailingRepository(InventoryTransactionRepository):
        def append_entry(self, *args, **kwargs):
            super().append_entry(*args, **kwargs)
            raise RuntimeError("simulated append failure")

    service = InventoryTransactionService(transaction_repository=FailingRepository())
    with pytest.raises(RuntimeError, match="simulated append failure"):
        service.adjust(
            session,
            actor_admin,
            balance_id=balance_id,
            expected_version=1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
            reason="cycle correction",
            idempotency_key="adj-rollback",
        )

    session.expire_all()
    persisted = session.get(InventoryBalance, balance_id)
    assert persisted.on_hand_quantity == Decimal("0.0000")
    assert persisted.version == 1
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0


def test_caller_controls_outer_commit(session, actor_admin) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session)
    session.commit()
    balance_id = balance.id

    service.adjust(
        session,
        actor_admin,
        balance_id=balance_id,
        expected_version=1,
        deltas=InventoryQuantityDelta(on_hand=Decimal("2")),
        reason="uncommitted correction",
        idempotency_key="adj-caller-rollback",
    )
    session.rollback()

    persisted = session.get(InventoryBalance, balance_id)
    assert persisted.on_hand_quantity == Decimal("0.0000")
    assert persisted.version == 1
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0


def test_same_balance_race_rechecks_receipt_after_lock_and_replays(
    session,
    actor_admin,
) -> None:
    (
        InventoryQuantityDelta,
        InventoryTransactionRepository,
        InventoryTransactionService,
        service,
    ) = _transaction_api()
    balance = _seed_balance(session, suffix="RACE-SAME")
    session.commit()
    balance_id = balance.id
    winner_session = SessionLocal()
    loser_session = SessionLocal()

    class FirstReadIsStaleRepository(InventoryTransactionRepository):
        def __init__(self) -> None:
            self.stale_reads = 1

        def get_idempotent(self, *args, **kwargs):
            if self.stale_reads:
                self.stale_reads -= 1
                return None
            return super().get_idempotent(*args, **kwargs)

    try:
        winner = service.adjust(
            winner_session,
            actor_admin,
            balance_id=balance_id,
            expected_version=1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
            reason="concurrent correction",
            idempotency_key="race-same-balance",
        )
        winner_session.commit()
        loser_service = InventoryTransactionService(
            transaction_repository=FirstReadIsStaleRepository()
        )

        replay = loser_service.adjust(
            loser_session,
            actor_admin,
            balance_id=balance_id,
            expected_version=1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
            reason="concurrent correction",
            idempotency_key="race-same-balance",
        )

        assert replay == winner
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryTransaction)
        ) == 1
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryLedgerEntry)
        ) == 1
    finally:
        loser_session.rollback()
        loser_session.close()
        winner_session.close()


def test_different_balance_race_recovers_unique_winner_as_domain_conflict(
    session,
    actor_admin,
) -> None:
    (
        InventoryQuantityDelta,
        InventoryTransactionRepository,
        InventoryTransactionService,
        service,
    ) = _transaction_api()
    winner_balance = _seed_balance(session, suffix="RACE-WINNER")
    loser_balance = _seed_balance(session, suffix="RACE-LOSER")
    session.commit()
    winner_balance_id = winner_balance.id
    loser_balance_id = loser_balance.id
    winner_session = SessionLocal()
    loser_session = SessionLocal()

    class ReadsBeforeUniqueFlushAreStaleRepository(InventoryTransactionRepository):
        def __init__(self) -> None:
            self.stale_reads = 2

        def get_idempotent(self, *args, **kwargs):
            if self.stale_reads:
                self.stale_reads -= 1
                return None
            return super().get_idempotent(*args, **kwargs)

    try:
        winner = service.adjust(
            winner_session,
            actor_admin,
            balance_id=winner_balance_id,
            expected_version=1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason="winner correction",
            idempotency_key="race-different-balance",
        )
        winner_session.commit()
        loser_service = InventoryTransactionService(
            transaction_repository=ReadsBeforeUniqueFlushAreStaleRepository()
        )

        with pytest.raises(ConflictError) as exc_info:
            loser_service.adjust(
                loser_session,
                actor_admin,
                balance_id=loser_balance_id,
                expected_version=1,
                deltas=InventoryQuantityDelta(on_hand=Decimal("2")),
                reason="loser correction",
                idempotency_key="race-different-balance",
            )

        assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryTransaction)
        ) == 1
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryLedgerEntry)
        ) == 1
        persisted_winner = loser_session.get(InventoryTransaction, winner.id)
        assert persisted_winner.response_snapshot_json == winner.model_dump(mode="json")
        persisted_loser = loser_session.get(InventoryBalance, loser_balance_id)
        assert persisted_loser.on_hand_quantity == Decimal("0.0000")
        assert persisted_loser.version == 1
    finally:
        loser_session.rollback()
        loser_session.close()
        winner_session.close()


def test_idempotency_key_and_reason_accept_persistence_boundaries(
    session,
    actor_admin,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session, suffix="TEXT-BOUNDARY")

    result = service.adjust(
        session,
        actor_admin,
        balance_id=balance.id,
        expected_version=1,
        deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
        reason="r" * 500,
        idempotency_key="k" * 128,
    )

    assert result.idempotency_key == "k" * 128
    assert result.reason == "r" * 500


@pytest.mark.parametrize(
    ("idempotency_key", "reason", "expected_code"),
    [
        ("k" * 129, "valid reason", "INVALID_IDEMPOTENCY_KEY"),
        ("valid-key", "r" * 501, "INVENTORY_REASON_INVALID"),
    ],
)
def test_idempotency_key_and_reason_reject_values_over_persistence_limits(
    session,
    actor_admin,
    idempotency_key,
    reason,
    expected_code,
) -> None:
    InventoryQuantityDelta, _, _, service = _transaction_api()
    balance = _seed_balance(session, suffix=expected_code)

    with pytest.raises(BusinessValidationError) as exc_info:
        service.adjust(
            session,
            actor_admin,
            balance_id=balance.id,
            expected_version=1,
            deltas=InventoryQuantityDelta(on_hand=Decimal("1")),
            reason=reason,
            idempotency_key=idempotency_key,
        )

    assert exc_info.value.code == expected_code
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryLedgerEntry)) == 0

from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.db.session import SessionLocal
from app.models import (
    InventoryBalance,
    InventoryPolicy,
    InventoryTargetReceipt,
    InventoryTargetReceiptStatus,
    InventoryTransaction,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.mixins import utc_now
from app.repositories.inventory_target_receipt_repository import (
    InventoryTargetReceiptRepository,
)
from app.schemas.inventory import InventoryQuantities
from app.services.inventory_target_adapter import (
    InventoryTargetAdapter,
    inventory_target_adapter,
)
from app.services.snapshot_service import snapshot_service
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_inventory_target_receipt_constraints_compile_for_postgresql():
    ddl = str(
        CreateTable(InventoryTargetReceipt.__table__).compile(
            dialect=postgresql.dialect()
        )
    )

    assert "CONSTRAINT uq_inventory_target_receipt_tenant_key UNIQUE" in ddl
    assert "CONSTRAINT ck_inventory_target_receipt_status" in ddl
    assert "CONSTRAINT ck_inventory_target_receipt_state" in ddl
    assert "CONSTRAINT ck_inventory_target_receipt_source_hash" in ddl


def _identity(session, *, code: str, quantity: str = "0"):
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code=f"WH-{code}",
        name=f"Warehouse {code}",
    )
    spare = SparePart(
        tenant_id="tenant-a",
        code=f"SP-{code}",
        name=f"Spare {code}",
        unit="EA",
    )
    session.add_all([warehouse, spare])
    session.flush()
    if quantity != "new":
        location = WarehouseLocation(
            tenant_id="tenant-a",
            warehouse_id=warehouse.id,
            code="DEFAULT",
            name="Default",
            location_type="DEFAULT",
        )
        session.add(location)
        session.flush()
        session.add_all(
            [
                InventoryPolicy(
                    tenant_id="tenant-a",
                    warehouse_id=warehouse.id,
                    spare_part_id=spare.id,
                ),
                InventoryBalance(
                    tenant_id="tenant-a",
                    warehouse_id=warehouse.id,
                    location_id=location.id,
                    spare_part_id=spare.id,
                    on_hand_quantity=Decimal(quantity),
                ),
            ]
        )
    session.flush()
    return warehouse, spare


def _target(
    session,
    actor,
    warehouse,
    spare,
    *,
    key: str,
    source: dict,
    on_hand: str,
):
    return inventory_target_adapter.apply_target(
        session,
        actor,
        warehouse_id=warehouse.id,
        spare_part_id=spare.id,
        quantities=InventoryQuantities(
            on_hand_quantity=Decimal(on_hand),
        ),
        notes=None,
        idempotency_key=key,
        source_payload=source,
        reason="receipt concurrency test",
    )


def test_one_source_receipt_namespace_spans_warehouses_and_operations(
    session,
    actor_admin,
):
    adjusted_warehouse, adjusted_spare = _identity(
        session,
        code="ADJUST",
        quantity="5",
    )
    opening_warehouse, opening_spare = _identity(
        session,
        code="OPENING",
        quantity="new",
    )
    session.commit()

    first = _target(
        session,
        actor_admin,
        adjusted_warehouse,
        adjusted_spare,
        key="one-source-key",
        source={"command": "first"},
        on_hand="6",
    )
    session.commit()
    assert first.operation_type == "ADJUST"

    with pytest.raises(ConflictError) as raised:
        _target(
            session,
            actor_admin,
            opening_warehouse,
            opening_spare,
            key="one-source-key",
            source={"command": "different"},
            on_hand="3",
        )
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert session.scalar(select(func.count()).select_from(InventoryTargetReceipt)) == 1
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1


def test_completed_same_hash_receipt_replays_without_reading_another_target(
    session,
    actor_admin,
):
    first_warehouse, first_spare = _identity(session, code="FIRST", quantity="5")
    second_warehouse, second_spare = _identity(session, code="SECOND", quantity="new")
    session.commit()
    source = {"logical": ["same", "command"]}

    first = _target(
        session,
        actor_admin,
        first_warehouse,
        first_spare,
        key="same-source-key",
        source=source,
        on_hand="6",
    )
    session.commit()
    replay = _target(
        session,
        actor_admin,
        second_warehouse,
        second_spare,
        key="same-source-key",
        source=source,
        on_hand="99",
    )

    assert replay.replayed is True
    assert replay.transaction_id == first.transaction_id
    assert session.scalar(
        select(func.count()).select_from(InventoryPolicy).where(
            InventoryPolicy.warehouse_id == second_warehouse.id
        )
    ) == 0
    assert session.scalar(select(func.count()).select_from(InventoryTargetReceipt)) == 1


@pytest.mark.parametrize(
    ("stored_hash", "expected_code"),
    [
        ("same", "IDEMPOTENT_RESPONSE_UNAVAILABLE"),
        ("different", "IDEMPOTENCY_KEY_REUSED"),
    ],
)
def test_pending_receipt_never_mutates_inventory(
    session,
    actor_admin,
    stored_hash,
    expected_code,
):
    warehouse, spare = _identity(session, code=stored_hash, quantity="new")
    source = {"command": "pending"}
    source_hash = snapshot_service.canonical_hash(source)
    session.add(
        InventoryTargetReceipt(
            tenant_id=actor_admin.tenant_id,
            idempotency_key="pending-key",
            source_hash=(source_hash if stored_hash == "same" else "f" * 64),
            status=InventoryTargetReceiptStatus.PENDING,
            actor_user_id="winner",
            actor_roles_json=["admin"],
            request_id="winner-request",
        )
    )
    session.commit()

    with pytest.raises(ConflictError) as raised:
        _target(
            session,
            actor_admin,
            warehouse,
            spare,
            key="pending-key",
            source=source,
            on_hand="4",
        )
    assert raised.value.code == expected_code
    assert session.scalar(select(func.count()).select_from(InventoryPolicy)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryBalance)) == 0
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0


def test_malformed_completed_receipt_is_not_accepted_as_replay(
    session,
    actor_admin,
):
    warehouse, spare = _identity(session, code="MALFORMED", quantity="new")
    source = {"command": "malformed"}
    session.add(
        InventoryTargetReceipt(
            tenant_id=actor_admin.tenant_id,
            idempotency_key="malformed-key",
            source_hash=snapshot_service.canonical_hash(source),
            status=InventoryTargetReceiptStatus.COMPLETED,
            result_json={"created_identity": "yes"},
            actor_user_id="winner",
            actor_roles_json=["admin"],
            request_id="winner-request",
            completed_at=utc_now(),
        )
    )
    session.commit()

    with pytest.raises(ConflictError) as raised:
        _target(
            session,
            actor_admin,
            warehouse,
            spare,
            key="malformed-key",
            source=source,
            on_hand="4",
        )
    assert raised.value.code == "IDEMPOTENT_RESPONSE_UNAVAILABLE"
    assert session.scalar(select(func.count()).select_from(InventoryPolicy)) == 0


class _StaleFirstReadReceiptRepository(InventoryTargetReceiptRepository):
    def __init__(self) -> None:
        self.reads = 0

    def get(self, *args, **kwargs):
        self.reads += 1
        if self.reads == 1:
            return None
        return super().get(*args, **kwargs)


@pytest.mark.parametrize("winner_zero", [False, True])
@pytest.mark.parametrize("same_source", [False, True])
def test_two_session_stale_read_recovers_one_cross_warehouse_source_winner(
    session,
    actor_admin,
    winner_zero,
    same_source,
):
    winner_warehouse, winner_spare = _identity(
        session,
        code=f"WIN-{winner_zero}-{same_source}",
        quantity="0" if winner_zero else "5",
    )
    loser_warehouse, loser_spare = _identity(
        session,
        code=f"LOSE-{winner_zero}-{same_source}",
        quantity="new",
    )
    winner_ids = (winner_warehouse.id, winner_spare.id)
    loser_ids = (loser_warehouse.id, loser_spare.id)
    session.commit()
    winner_source = {"race": "winner"}
    loser_source = winner_source if same_source else {"race": "loser"}

    with SessionLocal() as winner_session:
        first = inventory_target_adapter.apply_target(
            winner_session,
            actor_admin,
            warehouse_id=winner_ids[0],
            spare_part_id=winner_ids[1],
            quantities=InventoryQuantities(
                on_hand_quantity=Decimal("0" if winner_zero else "6")
            ),
            notes=None,
            idempotency_key="two-session-race-key",
            source_payload=winner_source,
            reason="winner",
        )
        winner_session.commit()

    stale_adapter = InventoryTargetAdapter(
        receipt_repository=_StaleFirstReadReceiptRepository()
    )
    with SessionLocal() as loser_session:
        if same_source:
            replay = stale_adapter.apply_target(
                loser_session,
                actor_admin,
                warehouse_id=loser_ids[0],
                spare_part_id=loser_ids[1],
                quantities=InventoryQuantities(on_hand_quantity=Decimal("9")),
                notes=None,
                idempotency_key="two-session-race-key",
                source_payload=loser_source,
                reason="loser",
            )
            assert replay.replayed is True
            assert replay.transaction_id == first.transaction_id
        else:
            with pytest.raises(ConflictError) as raised:
                stale_adapter.apply_target(
                    loser_session,
                    actor_admin,
                    warehouse_id=loser_ids[0],
                    spare_part_id=loser_ids[1],
                    quantities=InventoryQuantities(on_hand_quantity=Decimal("9")),
                    notes=None,
                    idempotency_key="two-session-race-key",
                    source_payload=loser_source,
                    reason="loser",
                )
            assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryPolicy).where(
                InventoryPolicy.warehouse_id == loser_ids[0]
            )
        ) == 0
        assert loser_session.scalar(
            select(func.count()).select_from(InventoryTargetReceipt)
        ) == 1

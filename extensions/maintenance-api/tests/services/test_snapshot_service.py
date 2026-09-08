from decimal import Decimal

from app.services.snapshot_service import SnapshotService


def test_snapshot_hash_is_order_and_decimal_scale_independent():
    service = SnapshotService()
    left = {"b": Decimal("1.00"), "a": [{"x": Decimal("2.0")}]}
    right = {"a": [{"x": Decimal("2.000")}], "b": Decimal("1.0")}
    assert service.canonical_hash(left) == service.canonical_hash(right)

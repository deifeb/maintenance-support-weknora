from app.models import InventoryLedgerEntry


def test_transaction_repository_exposes_append_only_ledger_contract() -> None:
    from app.repositories.inventory_transaction_repository import (
        InventoryTransactionRepository,
    )

    repository = InventoryTransactionRepository()

    assert callable(repository.append_entry)
    assert callable(repository.list_entries)
    for forbidden_name in (
        "update_entry",
        "delete_entry",
        "update_ledger_entry",
        "delete_ledger_entry",
    ):
        assert not hasattr(repository, forbidden_name)


def test_ledger_entry_mapper_has_no_update_or_delete_cascade() -> None:
    transaction_fk = next(
        iter(InventoryLedgerEntry.__table__.c.transaction_id.foreign_keys)
    )
    balance_fk = next(iter(InventoryLedgerEntry.__table__.c.balance_id.foreign_keys))

    assert transaction_fk.ondelete == "RESTRICT"
    assert balance_fk.ondelete == "RESTRICT"

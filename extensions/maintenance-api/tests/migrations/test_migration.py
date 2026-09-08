from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_TABLES = {
    "equipment_models",
    "configuration_versions",
    "configuration_items",
    "parts",
    "spare_parts",
    "reliability_profiles",
    "warehouses",
    "warehouse_locations",
    "inventory_policies",
    "inventory_expiry_rules",
    "inventory_lots",
    "serialized_items",
    "inventory_balances",
    "inventory_transactions",
    "inventory_ledger_entries",
    "suppliers",
    "supplier_offers",
}


def test_upgrade_downgrade_upgrade(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migration.db"
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert not (EXPECTED_TABLES & set(inspect(engine).get_table_names()))
    command.upgrade(config, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()
    get_settings.cache_clear()

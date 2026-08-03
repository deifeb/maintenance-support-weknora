from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect

REVISION = "20260803_09"
PREVIOUS_REVISION = "20260803_08"


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv(
        "INTERNAL_JWT_SECRET",
        "inventory-target-receipt-migration-secret-0001",
    )
    get_settings.cache_clear()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def test_inventory_target_receipt_revision_is_single_head_and_has_contract(
    tmp_path,
    monkeypatch,
):
    config, url = _config(tmp_path / "receipt.db", monkeypatch)
    script = ScriptDirectory.from_config(config)
    assert script.get_revision(REVISION).down_revision == PREVIOUS_REVISION

    command.upgrade(config, REVISION)
    inspector = inspect(create_engine(url))
    assert {
        "id",
        "tenant_id",
        "idempotency_key",
        "source_hash",
        "status",
        "result_json",
        "actor_user_id",
        "actor_roles_json",
        "request_id",
        "version",
        "completed_at",
        "created_at",
        "updated_at",
    } <= {column["name"] for column in inspector.get_columns("inventory_target_receipts")}
    assert any(
        constraint["name"] == "uq_inventory_target_receipt_tenant_key"
        and constraint["column_names"] == ["tenant_id", "idempotency_key"]
        for constraint in inspector.get_unique_constraints("inventory_target_receipts")
    )
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("inventory_target_receipts")
    }
    assert {
        "ck_inventory_target_receipt_status",
        "ck_inventory_target_receipt_state",
        "ck_inventory_target_receipt_source_hash",
    } <= check_names

    command.downgrade(config, PREVIOUS_REVISION)
    assert "inventory_target_receipts" not in inspect(create_engine(url)).get_table_names()
    command.upgrade(config, REVISION)
    assert "inventory_target_receipts" in inspect(create_engine(url)).get_table_names()

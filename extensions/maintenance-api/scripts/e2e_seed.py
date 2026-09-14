from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

FIXTURE_ALIASES = (
    "tenant-a-equipment-model",
    "tenant-a-part",
    "tenant-a-spare-part",
    "tenant-a-warehouse",
    "tenant-a-scenario",
    "tenant-b-equipment-model",
    "tenant-b-part",
    "tenant-b-spare-part",
    "tenant-b-warehouse",
    "tenant-b-scenario",
)
ACTOR_MANIFEST_ENV = "E2E_ACTOR_MANIFEST_PATH"

REQUIRED_ACTORS = ("tenant-b-admin", "tenant-a-admin", "tenant-a-viewer", "tenant-a-contributor")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--manifest-path", required=True)
    return parser.parse_args(argv)


def validate_manifest(manifest: dict[str, Any]) -> None:
    actors = manifest.get("actors")
    if actors is not None:
        if not isinstance(actors, dict):
            raise ValueError("actors must be an object")
        for alias in REQUIRED_ACTORS:
            if alias not in actors:
                raise ValueError(f"missing actor {alias}")
        return

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, dict) or not fixtures:
        raise ValueError("fixtures must be a non-empty object")
    if any(not isinstance(alias, str) or not isinstance(value, str) for alias, value in fixtures.items()):
        raise ValueError("fixture manifest must contain aliases only")


def build_fixture_manifest() -> dict[str, dict[str, str]]:
    manifest = {"fixtures": {alias: alias for alias in FIXTURE_ALIASES}}
    validate_manifest(manifest)
    return manifest


def tenant_ids_from_actor_manifest() -> tuple[str, ...]:
    manifest_path = os.environ.get(ACTOR_MANIFEST_ENV)
    if not manifest_path:
        raise ValueError(f"{ACTOR_MANIFEST_ENV} is required")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    actors = manifest.get("actors")
    if not isinstance(actors, dict):
        raise ValueError("actor manifest actors must be an object")
    tenant_ids = {
        actor.get("tenant")
        for actor in actors.values()
        if isinstance(actor, dict) and isinstance(actor.get("tenant"), str)
    }
    if len(tenant_ids) != 2 or any(not tenant_id for tenant_id in tenant_ids):
        raise ValueError("actor manifest must identify exactly two tenants")
    return tuple(sorted(tenant_ids))


def migrate_database(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def seed_database(database_url: str, manifest_path: str) -> None:
    migrate_database(database_url)
    from app.scripts.seed_demand_scenarios import seed as seed_demand_scenarios
    from app.scripts.seed_master_data import seed as seed_master_data

    for tenant_id in tenant_ids_from_actor_manifest():
        seed_master_data(tenant_id=tenant_id)
        seed_demand_scenarios(tenant_id=tenant_id)

    manifest = build_fixture_manifest()
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    seed_database(args.database_url, args.manifest_path)


if __name__ == "__main__":
    main()

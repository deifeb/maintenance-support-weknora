from __future__ import annotations

import json

import pytest
from e2e_seed import (
    build_fixture_manifest,
    parse_args,
    tenant_ids_from_actor_manifest,
    validate_manifest,
)


def test_manifest_rejects_missing_actor() -> None:
    with pytest.raises(ValueError, match="tenant-b-admin"):
        validate_manifest({"actors": {}})


def test_fixture_manifest_contains_aliases_without_raw_identifiers() -> None:
    manifest = build_fixture_manifest()
    encoded = json.dumps(manifest)

    assert manifest["fixtures"]
    assert "id" not in encoded.lower()
    assert "database" not in encoded.lower()
    assert "password" not in encoded.lower()
    assert all(isinstance(value, str) for value in manifest["fixtures"].values())


def test_cli_accepts_only_database_url_and_manifest_path() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--database-url", "sqlite:///private", "--manifest-path", "fixtures.json", "--password", "secret"])


def test_tenant_ids_come_from_the_actor_manifest(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "actors.json"
    manifest_path.write_text(
        json.dumps({
            "actors": {
                "tenant-a-viewer": {"role": "VIEWER", "tenant": "10000"},
                "tenant-a-admin": {"role": "ADMIN", "tenant": "10000"},
                "tenant-b-admin": {"role": "ADMIN", "tenant": "10001"},
                "tenant-a-contributor": {"role": "CONTRIBUTOR", "tenant": "10000"},
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("E2E_ACTOR_MANIFEST_PATH", str(manifest_path))

    assert tenant_ids_from_actor_manifest() == ("10000", "10001")

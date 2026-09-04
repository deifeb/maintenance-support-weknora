from app.services.report_version_provenance import (
    build_authoritative_source_snapshot,
    public_source_versions,
    source_snapshot_digest,
)


def test_snapshot_11_digest_is_canonical() -> None:
    left = {
        "schema_version": "1.1",
        "sources": [
            {
                "type": "AI_SESSION",
                "id": 7,
                "version": "2",
                "lineage_id": None,
                "digest": None,
            }
        ],
    }
    right = {
        "sources": [
            {
                "version": "2",
                "id": 7,
                "digest": None,
                "type": "AI_SESSION",
                "lineage_id": None,
            }
        ],
        "schema_version": "1.1",
    }

    assert source_snapshot_digest(left) == source_snapshot_digest(right)


def test_public_source_versions_supports_10_and_11() -> None:
    legacy = public_source_versions(
        {
            "schema_version": "1.0",
            "capture_mode": "AUTHORITATIVE_CREATE",
            "sources": {"session": {"id": 7, "version": 2}},
        }
    )
    current = public_source_versions(
        {
            "schema_version": "1.1",
            "capture_mode": "AUTHORITATIVE_CREATE",
            "generation_seed": {"private": "do not expose"},
            "sources": [
                {
                    "type": "AI_SESSION",
                    "id": 7,
                    "version": "2",
                    "lineage_id": None,
                    "digest": None,
                    "evidence": {"session_code": "private"},
                    "unrecognized": "do not expose",
                }
            ],
        }
    )

    assert legacy["sources"]["session"]["id"] == 7
    assert current["sources"][0] == {
        "type": "AI_SESSION",
        "id": 7,
        "version": "2",
        "lineage_id": None,
        "digest": None,
    }
    assert "generation_seed" not in current


def test_authoritative_snapshot_11_declares_complete_provenance() -> None:
    snapshot = build_authoritative_source_snapshot(
        report_type="MANAGEMENT_DECISION",
        template_version="1.0",
        metadata=None,
        source_records=(),
    )

    assert snapshot["provenance_completeness"] == "AUTHORITATIVE"
    assert public_source_versions(snapshot)["provenance_completeness"] == (
        "AUTHORITATIVE"
    )


def test_public_source_versions_fails_closed_for_unknown_or_malformed_snapshots() -> None:
    malformed = [
        None,
        "not a snapshot",
        {"schema_version": "2.0", "sources": {"api_key": "secret"}},
        {"schema_version": "1.1", "sources": {"type": "AI_SESSION"}},
        {
            "schema_version": "1.1",
            "capture_mode": ["nested"],
            "sources": [
                {
                    "type": "AI_SESSION",
                    "id": {"tenant_id": "secret"},
                    "version": ["2"],
                    "lineage_id": {"path": "/private"},
                    "digest": ["digest"],
                    "evidence": {"jwt": "secret"},
                }
            ],
        },
        {
            "schema_version": "1.0",
            "sources": ["not", "a", "mapping"],
        },
    ]

    for snapshot in malformed:
        assert public_source_versions(snapshot) == {}


def test_public_source_versions_10_uses_scalar_safe_source_allowlists() -> None:
    projection = public_source_versions(
        {
            "schema_version": "1.0",
            "capture_mode": "AUTHORITATIVE_CREATE",
            "sources": {
                "session": {
                    "id": 7,
                    "version": 2,
                    "session_code": "private",
                    "tenant_id": "private",
                },
                "scenario_version": {
                    "id": {"private": "nested"},
                    "version": "3",
                    "version_code": "SCN-003",
                },
            },
        }
    )

    assert projection == {
        "capture_mode": "AUTHORITATIVE_CREATE",
        "sources": {
            "session": {"id": 7, "version": 2},
            "scenario_version": {"version": "3"},
        },
    }

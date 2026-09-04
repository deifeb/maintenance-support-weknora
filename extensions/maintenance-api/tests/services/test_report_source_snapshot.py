from app.services.report_version_provenance import (
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

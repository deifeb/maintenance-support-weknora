from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.models.enums import AIReportSourceType
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
            "provenance_completeness": "AUTHORITATIVE",
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
            "session": {
                "id": 7,
                "version": 2,
                "session_code": "private",
            },
            "scenario_version": {
                "version": "3",
                "version_code": "SCN-003",
            },
        },
    }


def test_public_source_versions_preserves_safe_legacy_builder_fields() -> None:
    captured_at = datetime(2026, 9, 4, 8, 30, tzinfo=timezone.utc)
    snapshot = build_authoritative_source_snapshot(
        report_type="MANAGEMENT_DECISION",
        template_version="1.0",
        metadata=None,
        ai_session=SimpleNamespace(
            id=7,
            version=2,
            session_code="AI-007",
        ),
        scenario_version=SimpleNamespace(
            id=8,
            version=3,
            version_code="SCN-003",
            formula_version="formula-1",
            input_schema_version="input-1",
        ),
        calculation_run=SimpleNamespace(
            id=9,
            calculation_id=10,
            attempt_number=4,
            run_mode="SCHEDULED",
            engine_version="engine-1",
            formula_version="formula-2",
        ),
        calculation=SimpleNamespace(
            input_snapshot_hash="a" * 64,
            inventory_snapshot_at=captured_at,
        ),
        review_run=SimpleNamespace(
            id=11,
            version=5,
            rule_set_version="rules-1",
            scenario_version_id=8,
            calculation_run_id=9,
        ),
    )
    snapshot["sources"]["calculation_run"]["provider_token"] = "secret"
    snapshot["sources"]["calculation_run"]["nested"] = {"jwt": "secret"}

    assert public_source_versions(snapshot) == {
        "capture_mode": "AUTHORITATIVE_CREATE",
        "sources": {
            "session": {
                "id": 7,
                "version": 2,
                "session_code": "AI-007",
            },
            "scenario_version": {
                "id": 8,
                "version": 3,
                "version_code": "SCN-003",
                "formula_version": "formula-1",
                "input_schema_version": "input-1",
            },
            "calculation_run": {
                "id": 9,
                "calculation_id": 10,
                "attempt_number": 4,
                "run_mode": "SCHEDULED",
                "engine_version": "engine-1",
                "formula_version": "formula-2",
                "input_snapshot_hash": "a" * 64,
                "inventory_snapshot_at": str(captured_at),
            },
            "review_run": {
                "id": 11,
                "version": 5,
                "rule_set_version": "rules-1",
                "scenario_version_id": 8,
                "calculation_run_id": 9,
            },
            "inventory": {"snapshot_at": str(captured_at)},
        },
    }


def _valid_snapshot_11() -> dict:
    return {
        "schema_version": "1.1",
        "capture_mode": "AUTHORITATIVE_CREATE",
        "provenance_completeness": "AUTHORITATIVE",
        "sources": [
            {
                "type": AIReportSourceType.AI_SESSION.value,
                "id": "7",
                "version": "2",
                "lineage_id": None,
                "digest": "a" * 64,
            }
        ],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda snapshot: snapshot.pop("capture_mode"),
        lambda snapshot: snapshot.__setitem__("capture_mode", "UNKNOWN"),
        lambda snapshot: snapshot.pop("provenance_completeness"),
        lambda snapshot: snapshot.__setitem__(
            "provenance_completeness",
            "PERSISTED_LINKS_ONLY",
        ),
        lambda snapshot: snapshot.__setitem__("sources", [{}]),
        lambda snapshot: snapshot["sources"][0].__setitem__(
            "type",
            "UNKNOWN_SOURCE",
        ),
        lambda snapshot: snapshot["sources"][0].pop("id"),
        lambda snapshot: snapshot["sources"][0].__setitem__("version", None),
        lambda snapshot: snapshot["sources"][0].__setitem__(
            "digest",
            "not-a-sha256",
        ),
        lambda snapshot: snapshot["sources"][0].__setitem__(
            "lineage_id",
            {"nested": "unsafe"},
        ),
    ],
)
def test_public_source_versions_11_rejects_invalid_required_fields(
    mutate,
) -> None:
    snapshot = _valid_snapshot_11()
    mutate(snapshot)

    assert public_source_versions(snapshot) == {}

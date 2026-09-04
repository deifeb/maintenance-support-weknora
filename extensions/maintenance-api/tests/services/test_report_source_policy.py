from types import SimpleNamespace

from app.services.report_source_policy import build_source_records


def test_current_report_sources_become_stable_ordered_records() -> None:
    ai_session = SimpleNamespace(
        id=7,
        version=2,
        session_code="AI-007",
    )
    scenario = SimpleNamespace(
        id=8,
        version=3,
        version_code="SCN-003",
        formula_version="formula-1",
    )
    calculation = SimpleNamespace(input_snapshot_hash="a" * 64)
    run = SimpleNamespace(
        id=9,
        attempt_number=1,
        calculation_id=10,
        engine_version="engine-1",
    )
    review = SimpleNamespace(
        id=11,
        version=4,
        rule_set_version="rules-1",
        scenario_version_id=8,
        calculation_run_id=9,
    )

    records = build_source_records(
        ai_session=ai_session,
        scenario_version=scenario,
        calculation_run=run,
        calculation=calculation,
        review_run=review,
    )

    assert [record.source_type.value for record in records] == [
        "AI_SESSION",
        "SCENARIO_VERSION",
        "CALCULATION_RUN",
        "DEMAND_REVIEW",
    ]
    assert all(record.source_version for record in records)
    assert list(enumerate(records))[-1][0] == 3
    assert records[0].source_digest
    assert records[2].evidence["input_snapshot_hash"] == "a" * 64

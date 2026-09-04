from __future__ import annotations

import importlib

import pytest
from app.core.exceptions import BusinessValidationError
from app.models.ai_report import (
    AIReportCitation,
    AIReportExport,
    AIReportSection,
    AIReportValidationFinding,
)
from app.models.enums import (
    AIExecutionMode,
    AIExportFormat,
    AIReportJobStatus,
    AIReportVersionStatus,
    AISeverity,
)
from app.schemas.ai_report import AIReportCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_report_service import ai_report_service
from sqlalchemy import select


def _actor(actor_context, *, role=MaintenanceRole.CONTRIBUTOR):
    return actor_context(
        tenant_id="tenant-c2b",
        user_id=f"c2b-{role.value.lower()}",
        role=role,
    )


def _create_job(session, actor):
    return ai_report_service.create(
        session,
        actor,
        AIReportCreateRequest(
            title="C2B regeneration lineage",
            report_type="MANAGEMENT_DECISION",
            metadata={
                "allowed_numbers": [],
                "purpose": "c2b-red",
            },
        ),
    )


def _require_regenerate():
    assert hasattr(ai_report_service, "regenerate"), (
        "C2B RED S02: AIReportService.regenerate is absent"
    )
    return getattr(ai_report_service, "regenerate")


def _require_provenance_module():
    try:
        return importlib.import_module(
            "app.services.report_version_provenance"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "C2B RED S06: report_version_provenance "
            "module is absent",
            pytrace=False,
        )


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _version_artifacts(session, version_id: int) -> dict[str, list]:
    return {
        "sections": list(
            session.scalars(
                select(AIReportSection.id)
                .where(
                    AIReportSection.report_version_id
                    == version_id
                )
                .order_by(AIReportSection.id)
            )
        ),
        "citations": list(
            session.scalars(
                select(AIReportCitation.id)
                .where(
                    AIReportCitation.report_version_id
                    == version_id
                )
                .order_by(AIReportCitation.id)
            )
        ),
        "findings": list(
            session.scalars(
                select(AIReportValidationFinding.id)
                .where(
                    AIReportValidationFinding.report_version_id
                    == version_id
                )
                .order_by(AIReportValidationFinding.id)
            )
        ),
        "exports": list(
            session.scalars(
                select(AIReportExport.id)
                .where(
                    AIReportExport.report_version_id
                    == version_id
                )
                .order_by(AIReportExport.id)
            )
        ),
    }


def test_create_report_captures_authoritative_source_snapshot(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    version = ai_report_service.latest_version(
        session,
        actor,
        job.id,
    )

    required = {
        "parent_version_id",
        "source_snapshot_json",
        "input_digest",
        "generation_mode",
        "generated_at",
    }
    missing = {
        name
        for name in required
        if not hasattr(version, name)
    }
    assert not missing, (
        "C2B RED S01: AIReportVersion provenance "
        f"fields are absent: {sorted(missing)}"
    )

    assert version.parent_version_id is None
    assert version.input_digest
    assert len(version.input_digest) == 64
    assert version.generation_mode is None
    assert version.generated_at is None
    assert version.source_snapshot_json["schema_version"] == "1.1"
    assert (
        version.source_snapshot_json["capture_mode"]
        == "AUTHORITATIVE_CREATE"
    )
    assert (
        version.source_snapshot_json["provenance_completeness"]
        == "AUTHORITATIVE"
    )


def test_regenerate_appends_version_on_same_job(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    regenerate = _require_regenerate()

    v2 = regenerate(session, actor, job.id)
    versions = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )

    assert [row.version_number for row in versions] == [1, 2]
    assert v2.report_job_id == job.id
    assert v2.parent_version_id == v1.id
    assert v2.id != v1.id


def test_regenerate_builds_linear_parent_chain(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    regenerate = _require_regenerate()

    v2 = regenerate(session, actor, job.id)
    v3 = regenerate(session, actor, job.id)

    assert v2.parent_version_id == v1.id
    assert v3.parent_version_id == v2.id
    assert [row.version_number for row in ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )] == [1, 2, 3]


def test_regenerate_preserves_parent_version_content_and_exports(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )

    session.add(
        AIReportValidationFinding(
            tenant_id=actor.tenant_id,
            report_version_id=v1.id,
            code="C2B_PARENT_FINDING",
            severity=AISeverity.INFO,
            message="parent artifact must remain immutable",
            details_json={"source": "c2b-red"},
            resolved=True,
        )
    )
    session.add(
        AIReportExport(
            tenant_id=actor.tenant_id,
            report_version_id=v1.id,
            export_format=AIExportFormat.JSON,
            file_name="parent-v1.json",
            content_type="application/json",
            file_path=None,
            content_digest="a" * 64,
            size_bytes=2,
        )
    )
    session.commit()
    session.refresh(v1)

    before = _version_artifacts(session, v1.id)
    before_digest = v1.content_digest
    before_status = v1.status
    regenerate = _require_regenerate()

    regenerate(session, actor, job.id)
    session.expire_all()
    v1_after = session.get(type(v1), v1.id)

    assert v1_after is not None
    assert v1_after.content_digest == before_digest
    assert v1_after.status is before_status
    assert _version_artifacts(session, v1.id) == before


def test_seed_metadata_copies_only_generation_seed() -> None:
    module = _require_provenance_module()

    result = module.seed_metadata(
        {
            "purpose": "keep",
            "allowed_numbers": ["8"],
            "_draft_sections": [{"section_code": "x"}],
            "_draft_citations": [{"citation_id": "E1"}],
            "_section_tables": {"x": [{"rows": [["derived"]]}]},
            "_section_citations": {"x": ["derived"]},
            "_other_private": "drop",
        }
    )

    assert result["purpose"] == "keep"
    assert result["allowed_numbers"] == ["8"]
    assert "_draft_sections" in result
    assert "_draft_citations" in result
    assert "_section_tables" not in result
    assert "_section_citations" not in result
    assert "_other_private" not in result


def test_source_snapshot_digest_is_canonical() -> None:
    module = _require_provenance_module()

    left = {
        "schema_version": "1.0",
        "sources": {"b": 2, "a": 1},
    }
    right = {
        "sources": {"a": 1, "b": 2},
        "schema_version": "1.0",
    }

    assert (
        module.source_snapshot_digest(left)
        == module.source_snapshot_digest(right)
    )
    assert len(module.source_snapshot_digest(left)) == 64


def test_regenerate_preserves_input_digest_for_copied_snapshot(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    regenerate = _require_regenerate()

    v2 = regenerate(session, actor, job.id)

    assert v1.source_snapshot_json == v2.source_snapshot_json
    assert (
        v2.source_snapshot_json["provenance_completeness"]
        == "AUTHORITATIVE"
    )
    assert v1.input_digest == v2.input_digest
    assert v1.content_digest
    assert v2.content_digest


def test_deterministic_generation_records_rule_fallback_and_time(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    version = ai_report_service.generate(
        session,
        actor,
        job.id,
    )

    assert hasattr(version, "generation_mode"), (
        "C2B RED S09: generation_mode is absent"
    )
    assert hasattr(version, "generated_at"), (
        "C2B RED S09: generated_at is absent"
    )
    assert (
        _enum_value(version.generation_mode)
        == AIExecutionMode.RULE_FALLBACK.value
    )
    assert version.generated_at is not None


def test_serialize_carries_version_and_source_provenance(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    version = ai_report_service.generate(
        session,
        actor,
        job.id,
    )

    report = ai_report_service.serialize(
        session,
        actor,
        job,
        version,
    )

    required = {
        "parent_version_id",
        "input_digest",
        "generation_mode",
        "generated_at",
        "source_versions",
    }
    assert required <= set(report), (
        "C2B RED E01: serialized report provenance "
        f"is absent: {sorted(required - set(report))}"
    )


def test_regenerate_legacy_version_uses_explicit_degraded_provenance(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    assert hasattr(v1, "source_snapshot_json"), (
        "C2B RED S10: source_snapshot_json is absent"
    )
    assert hasattr(v1, "input_digest"), (
        "C2B RED S10: input_digest is absent"
    )
    v1.source_snapshot_json = None
    v1.input_digest = None
    session.commit()
    regenerate = _require_regenerate()

    v2 = regenerate(session, actor, job.id)

    assert (
        v2.source_snapshot_json["capture_mode"]
        == "LEGACY_RECONSTRUCTED"
    )
    assert (
        v2.source_snapshot_json["provenance_completeness"]
        == "PERSISTED_LINKS_ONLY"
    )
    assert v2.input_digest


def test_regenerate_rejects_ungenerated_latest_without_mutation(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    regenerate = _require_regenerate()
    before = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )

    with pytest.raises(BusinessValidationError) as exc_info:
        regenerate(session, actor, job.id)

    assert (
        exc_info.value.code
        == "REPORT_REGENERATE_SOURCE_NOT_READY"
    )
    assert len(
        ai_report_service.list_versions(
            session,
            actor,
            job.id,
        )
    ) == len(before)


def test_generate_rejects_already_generated_version_without_mutation(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    version = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    before = _version_artifacts(session, version.id)
    before_digest = version.content_digest

    with pytest.raises(BusinessValidationError) as exc_info:
        ai_report_service.generate(
            session,
            actor,
            job.id,
        )

    assert (
        exc_info.value.code
        == "REPORT_VERSION_ALREADY_GENERATED"
    )
    session.expire_all()
    version_after = ai_report_service.latest_version(
        session,
        actor,
        job.id,
    )
    assert version_after.content_digest == before_digest
    assert _version_artifacts(
        session,
        version.id,
    ) == before


def test_validate_requires_generation_without_mutation(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    version = ai_report_service.latest_version(
        session,
        actor,
        job.id,
    )
    before_status = version.status

    with pytest.raises(BusinessValidationError) as exc_info:
        ai_report_service.validate(
            session,
            actor,
            job.id,
        )

    assert exc_info.value.code == "REPORT_GENERATION_REQUIRED"
    session.expire_all()
    version_after = ai_report_service.latest_version(
        session,
        actor,
        job.id,
    )
    assert version_after.status is before_status


def test_validate_rejects_final_version_without_mutation(
    session,
    actor_context,
) -> None:
    contributor = _actor(actor_context)
    admin = _actor(
        actor_context,
        role=MaintenanceRole.ADMIN,
    )
    job = _create_job(session, contributor)
    ai_report_service.generate(
        session,
        contributor,
        job.id,
    )
    findings = ai_report_service.validate(
        session,
        contributor,
        job.id,
    )
    assert findings == []
    final = ai_report_service.finalize(
        session,
        admin,
        job.id,
    )
    assert final.status is AIReportVersionStatus.FINAL

    with pytest.raises(BusinessValidationError) as exc_info:
        ai_report_service.validate(
            session,
            contributor,
            job.id,
        )

    assert (
        exc_info.value.code
        == "REPORT_FINAL_VERSION_IMMUTABLE"
    )
    session.expire_all()
    final_after = ai_report_service.latest_version(
        session,
        contributor,
        job.id,
    )
    assert final_after.status is AIReportVersionStatus.FINAL
    assert final_after.finalized_by == admin.user_id


def test_regenerate_resets_job_execution_error_state(
    session,
    actor_context,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    job.status = AIReportJobStatus.FAILED
    job.progress_percent = 100
    job.error_code = "OLD_ERROR"
    job.error_message = "old error must be cleared"
    session.commit()
    regenerate = _require_regenerate()

    version = regenerate(session, actor, job.id)
    session.expire_all()
    job_after = ai_report_service.get_job(
        session,
        actor,
        job.id,
    )

    assert version.version_number == 2
    assert job_after.error_code is None
    assert job_after.error_message is None
    assert (
        job_after.status
        is AIReportJobStatus.VALIDATING_NUMBERS
    )
    assert job_after.progress_percent == 75


def test_regenerate_generation_failure_preserves_parent_and_lineage(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    parent_digest = v1.content_digest
    regenerate = _require_regenerate()
    assert hasattr(ai_report_service, "_generate_version"), (
        "C2B RED S16: version-targeted generation helper is absent"
    )

    def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic c2b generation failure")

    monkeypatch.setattr(
        ai_report_service,
        "_generate_version",
        boom,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic c2b generation failure",
    ):
        regenerate(session, actor, job.id)

    session.expire_all()
    versions = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )
    job_after = ai_report_service.get_job(
        session,
        actor,
        job.id,
    )
    v1_after = versions[0]

    assert [row.version_number for row in versions] == [1, 2]
    assert v1_after.content_digest == parent_digest
    assert versions[1].parent_version_id == v1.id
    assert versions[1].status is AIReportVersionStatus.DRAFT
    assert job_after.status is AIReportJobStatus.FAILED
    assert job_after.error_code == "REPORT_GENERATION_FAILED"

def test_generate_retry_after_regeneration_failure_clears_stale_error_state(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    v1 = ai_report_service.generate(session, actor, job.id)
    original_generate_version = ai_report_service._generate_version

    def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "synthetic c2c regeneration generation failure"
        )

    monkeypatch.setattr(
        ai_report_service,
        "_generate_version",
        boom,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic c2c regeneration generation failure",
    ):
        ai_report_service.regenerate(session, actor, job.id)

    session.expire_all()
    failed_job = ai_report_service.get_job(
        session,
        actor,
        job.id,
    )
    failed_versions = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )

    assert failed_job.status.value == "FAILED"
    assert failed_job.error_code == "REPORT_GENERATION_FAILED"
    assert failed_job.error_message == "Report generation failed"
    assert len(failed_versions) == 2
    v2 = failed_versions[-1]
    v2_id = v2.id
    assert v2.parent_version_id == v1.id
    assert v2.generated_at is None

    monkeypatch.setattr(
        ai_report_service,
        "_generate_version",
        original_generate_version,
    )

    retried = ai_report_service.generate(
        session,
        actor,
        job.id,
    )
    retried_id = retried.id

    session.expire_all()
    retried_job = ai_report_service.get_job(
        session,
        actor,
        job.id,
    )
    retried_versions = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )

    assert retried_id == v2_id
    assert len(retried_versions) == 2
    assert retried_job.status.value == "VALIDATING_NUMBERS"
    assert retried_job.progress_percent == 75
    assert retried_job.error_code is None, (
        "C2C RED: successful generate retry must clear stale "
        "REPORT_GENERATION_FAILED"
    )
    assert retried_job.error_message is None
    assert retried_versions[-1].generated_at is not None


def test_failed_generate_retry_preserves_persisted_generation_failure_state(
    session,
    actor_context,
    monkeypatch,
) -> None:
    actor = _actor(actor_context)
    job = _create_job(session, actor)
    ai_report_service.generate(session, actor, job.id)

    def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(
            "synthetic c2c persistent retry failure"
        )

    monkeypatch.setattr(
        ai_report_service,
        "_generate_version",
        boom,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic c2c persistent retry failure",
    ):
        ai_report_service.regenerate(session, actor, job.id)

    session.expire_all()
    failed_version_id = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )[-1].id

    with pytest.raises(
        RuntimeError,
        match="synthetic c2c persistent retry failure",
    ):
        ai_report_service.generate(session, actor, job.id)

    session.expire_all()
    failed_job = ai_report_service.get_job(
        session,
        actor,
        job.id,
    )
    versions_after = ai_report_service.list_versions(
        session,
        actor,
        job.id,
    )

    assert failed_job.status.value == "FAILED"
    assert failed_job.error_code == "REPORT_GENERATION_FAILED"
    assert failed_job.error_message == "Report generation failed"
    assert len(versions_after) == 2
    assert versions_after[-1].id == failed_version_id
    assert versions_after[-1].generated_at is None

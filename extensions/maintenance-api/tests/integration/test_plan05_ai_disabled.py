from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.core.exceptions import NotFoundError
from app.models import AIModelCall, CalculationGroup, DemandScenarioVersion
from app.models.enums import (
    AIExecutionMode,
    AIModelCallStatus,
    AIReportJobStatus,
    AIReportSourceType,
    AIReportVersionStatus,
    DemandListStatus,
    DemandReviewStatus,
)
from app.schemas.ai_report import ReportSourceRefInput
from app.schemas.report_center import ReportJobCreateRequest
from app.security.actor import MaintenanceRole
from app.services.ai_model_runtime import AIModelRuntime
from app.services.ai_orchestration_service import ai_orchestration_service
from app.services.demand_review_service import DemandReviewService
from app.services.report_center_service import ReportCenterQueryService
from fastapi.testclient import TestClient
from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel
from maintenance_ai.providers import DeterministicTestProvider, RuleFallbackProvider
from maintenance_ai.routing import ModelDefinition, ModelRegistry, ModelRouter, RouteDefinition
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_plan05_04_cross_domain_invariants import (
    _seed_published_review_source,
)


def _provider_disabled_runtime() -> AIModelRuntime:
    remote = DeterministicTestProvider(model="remote-plan05-model")
    remote.failures["scenario_parsing"] = "unavailable"
    local = DeterministicTestProvider(model="local-plan05-model")
    local.failures["scenario_parsing"] = "unavailable"
    models = {
        "remote-plan05": ModelDefinition(
            name="remote-plan05",
            provider=ProviderKind.OPENAI_COMPATIBLE,
            model="remote-plan05-model",
            base_url="https://provider.plan05.invalid/v1",
            capabilities={ModelCapability.STRUCTURED_OUTPUT},
            sensitivity_allowed=set(SensitivityLevel),
        ),
        "local-plan05": ModelDefinition(
            name="local-plan05",
            provider=ProviderKind.OLLAMA,
            model="local-plan05-model",
            base_url="http://ollama.plan05.invalid:11434",
            capabilities={ModelCapability.STRUCTURED_OUTPUT},
            sensitivity_allowed=set(SensitivityLevel),
        ),
    }
    registry = ModelRegistry(
        models=models,
        routes={
            "scenario_parsing": RouteDefinition(
                primary="remote-plan05",
                fallbacks=("local-plan05", "RULE_FALLBACK"),
                required_capabilities={ModelCapability.STRUCTURED_OUTPUT},
            )
        },
    )
    return AIModelRuntime(
        router=ModelRouter(
            registry,
            providers={
                "remote-plan05": remote,
                "local-plan05": local,
            },
            rule_fallback=RuleFallbackProvider(),
        ),
        configured_secrets=(
            "PLAN05-REMOTE-SECRET",
            "PLAN05-WEKNORA-SECRET",
        ),
    )


def test_plan05_ai_disabled_workflow_uses_rule_fallback(
    authenticated_client: TestClient,
    session: Session,
    actor_context,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        ai_orchestration_service,
        "runtime_factory",
        _provider_disabled_runtime,
    )

    created_session = authenticated_client.post(
        "/api/v1/ai/sessions",
        json={
            "title": "Plan 05 provider-disabled workflow",
            "sensitivity_level": "INTERNAL",
        },
    )
    assert created_session.status_code == 200
    ai_session_id = created_session.json()["data"]["id"]
    parsed = authenticated_client.post(
        f"/api/v1/ai/sessions/{ai_session_id}/messages",
        json={
            "content": (
                "示例装备1采用V1构型，10台执行30天任务，保障率95%"
            )
        },
    )
    assert parsed.status_code == 200
    parsed_data = parsed.json()["data"]
    assert parsed_data["summary"] == {
        "execution_mode": "RULE_FALLBACK",
        "llm_generated": False,
    }
    assert parsed_data["scenario_draft"]["equipment_quantity"]["value"] == 10
    assert parsed_data["scenario_draft"]["duration_days"]["value"] == 30
    assert parsed_data["scenario_draft"]["service_level"]["value"] == 0.95

    model_calls = list(
        session.scalars(
            select(AIModelCall)
            .where(AIModelCall.session_id == ai_session_id)
            .order_by(AIModelCall.id)
        ).all()
    )
    assert [call.status for call in model_calls] == [
        AIModelCallStatus.FAILED,
        AIModelCallStatus.FAILED,
        AIModelCallStatus.SUCCEEDED,
    ]
    assert [call.provider for call in model_calls] == [
        ProviderKind.OPENAI_COMPATIBLE.value,
        ProviderKind.OLLAMA.value,
        ProviderKind.RULE_FALLBACK.value,
    ]

    contributor = actor_context(
        tenant_id="tenant-a",
        user_id="plan05-ai-disabled-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="plan05-ai-disabled-contributor-request",
        token_id="plan05-ai-disabled-contributor-token",
    )
    admin = actor_context(
        tenant_id=contributor.tenant_id,
        user_id="plan05-ai-disabled-admin",
        role=MaintenanceRole.ADMIN,
        request_id="plan05-ai-disabled-admin-request",
        token_id="plan05-ai-disabled-admin-token",
    )
    foreign_viewer = actor_context(
        tenant_id="tenant-plan05-ai-disabled-b",
        user_id="plan05-ai-disabled-foreign-viewer",
        role=MaintenanceRole.VIEWER,
        request_id="plan05-ai-disabled-foreign-request",
        token_id="plan05-ai-disabled-foreign-token",
    )
    source, source_item, _ = _seed_published_review_source(session, contributor)
    scenario = session.get(DemandScenarioVersion, source.scenario_version_id)
    calculation = session.get(CalculationGroup, source.calculation_group_id)
    assert scenario is not None
    assert scenario.scenario_template_id is not None
    assert calculation is not None
    assert calculation.status.value == "COMPLETED"
    assert calculation.primary_candidate_key == "WEIBULL:ANALYTICAL"
    assert source.status is DemandListStatus.PUBLISHED
    assert source_item.interval_snapshot_json["candidates"][0][
        "execution_mode"
    ] == "ANALYTICAL"

    review = DemandReviewService().run(
        session,
        contributor,
        source.id,
        expected_source_version=source.version,
        idempotency_key="plan05-ai-disabled-review-run",
    )
    assert review.status is DemandReviewStatus.OPEN
    assert review.rule_set_version
    assert review.findings

    report_center = ReportCenterQueryService()
    created_report = report_center.create_job(
        session,
        contributor,
        ReportJobCreateRequest(
            title="Plan 05 provider-disabled demand review report",
            report_type="DEMAND_REVIEW",
            source_refs=[
                ReportSourceRefInput(
                    type=AIReportSourceType.DEMAND_REVIEW,
                    id=review.id,
                    version=str(review.version),
                )
            ],
        ),
    )
    assert created_report.job_status is AIReportJobStatus.CREATED
    assert created_report.latest_version.status is AIReportVersionStatus.DRAFT

    owner_reports = report_center.list(session, contributor)
    foreign_reports = report_center.list(session, foreign_viewer)
    assert [item.report_id for item in owner_reports.items] == [
        created_report.report_id
    ]
    assert foreign_reports.items == []
    with pytest.raises(NotFoundError):
        report_center.detail(session, foreign_viewer, created_report.report_id)

    generated = report_center.generate(
        session,
        contributor,
        created_report.report_id,
    )
    assert generated.job_status is AIReportJobStatus.VALIDATING_NUMBERS
    assert generated.latest_version.status is AIReportVersionStatus.DRAFT
    assert generated.latest_version.generation_mode is AIExecutionMode.RULE_FALLBACK

    validated = report_center.validate(
        session,
        contributor,
        created_report.report_id,
    )
    assert validated.job_status is AIReportJobStatus.READY_FOR_REVIEW
    assert validated.latest_version.status is AIReportVersionStatus.REVIEWED
    assert validated.latest_version.generation_mode is AIExecutionMode.RULE_FALLBACK

    finalized = report_center.finalize(
        session,
        admin,
        created_report.report_id,
    )
    assert finalized.job_status is AIReportJobStatus.FINALIZED
    assert finalized.latest_version.status is AIReportVersionStatus.FINAL
    assert finalized.latest_version.generation_mode is AIExecutionMode.RULE_FALLBACK

    output_dir = tmp_path / "plan05-ai-disabled-report"
    monkeypatch.setattr(
        "app.services.ai_report_service.get_settings",
        lambda: SimpleNamespace(ai_report_export_dir=str(output_dir)),
    )
    content, content_type, file_name = report_center.export(
        session,
        contributor,
        created_report.report_id,
        "JSON",
    )
    exported = json.loads(content)
    assert exported["generation_mode"] == "RULE_FALLBACK"
    assert exported["status"] == "FINAL"
    assert content_type == "application/json; charset=utf-8"
    assert file_name.endswith(".json")
    assert (output_dir / file_name).read_bytes() == content

    visible_output = json.dumps(
        {
            "scenario": parsed_data,
            "report": report_center.detail(
                session,
                contributor,
                created_report.report_id,
            ),
            "export": exported,
        },
        ensure_ascii=False,
        default=str,
    )
    for private_value in (
        "PLAN05-REMOTE-SECRET",
        "PLAN05-WEKNORA-SECRET",
        "https://provider.plan05.invalid/v1",
        "http://ollama.plan05.invalid:11434",
        "remote-plan05-model",
        "local-plan05-model",
    ):
        assert private_value not in visible_output

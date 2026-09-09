from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    AIModelCall,
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    ReliabilityProfile,
)
from app.models.enums import (
    AIExecutionMode,
    AIModelCallStatus,
    AIReportJobStatus,
    AIReportSourceType,
    AIReportVersionStatus,
    CalculationGroupStatus,
    CalculationStatus,
    ConfigurationStatus,
    DataSourceType,
    DemandListStatus,
    DemandReviewStatus,
    ReliabilityModelType,
    ScenarioVersionStatus,
)
from app.schemas.ai_report import ReportSourceRefInput
from app.schemas.report_center import ReportJobCreateRequest
from app.schemas.scenario_draft import ScenarioDraftPayload, ScenarioFieldState
from app.scripts.seed_demand_scenarios import seed as seed_demand_scenarios
from app.security.actor import MaintenanceRole
from app.services.ai_model_runtime import AIModelRuntime
from app.services.ai_orchestration_service import ai_orchestration_service
from app.services.calculation_group_service import CalculationGroupService
from app.services.demand_list_service import DemandListService
from app.services.demand_review_service import DemandReviewService
from app.services.report_center_service import ReportCenterQueryService
from app.services.scenario_draft_service import ScenarioDraftService
from app.services.scenario_service import scenario_service
from app.workers.calculation_group_executor import CalculationGroupObserver
from fastapi.testclient import TestClient
from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel
from maintenance_ai.providers import DeterministicTestProvider, RuleFallbackProvider
from maintenance_ai.routing import ModelDefinition, ModelRegistry, ModelRouter, RouteDefinition
from sqlalchemy import select
from sqlalchemy.orm import Session


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


def _confirmed_ai_field(value: object) -> ScenarioFieldState:
    return ScenarioFieldState(
        value=value,
        source="AI_INFERRED",
        confidence=Decimal("1"),
        risk="LOW",
        confirmed=True,
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
    session.commit()
    seed_demand_scenarios(tenant_id=contributor.tenant_id)
    session.expire_all()
    fallback_draft = parsed_data["scenario_draft"]
    configuration = session.scalar(
        select(ConfigurationVersion)
        .join(EquipmentModel)
        .where(
            ConfigurationVersion.tenant_id == contributor.tenant_id,
            ConfigurationVersion.status == ConfigurationStatus.PUBLISHED,
            ConfigurationVersion.version_code
            == fallback_draft["configuration_version"]["value"],
            EquipmentModel.name == fallback_draft["equipment_model"]["value"],
        )
        .order_by(ConfigurationVersion.id)
    )
    assert configuration is not None
    spare_part_ids = list(
        session.scalars(
            select(ConfigurationItem.spare_part_id)
            .where(
                ConfigurationItem.tenant_id == contributor.tenant_id,
                ConfigurationItem.configuration_version_id == configuration.id,
                ConfigurationItem.spare_part_id.is_not(None),
            )
            .distinct()
            .order_by(ConfigurationItem.spare_part_id)
        ).all()
    )
    assert spare_part_ids
    session.add_all(
        [
            ReliabilityProfile(
                tenant_id=contributor.tenant_id,
                profile_code=f"PLAN05-FALLBACK-WEIBULL-{spare_part_id}",
                spare_part_id=spare_part_id,
                configuration_version_id=configuration.id,
                model_type=ReliabilityModelType.WEIBULL,
                weibull_shape=Decimal("1.5"),
                weibull_scale=Decimal("5000"),
                data_source_type=DataSourceType.DESIGN_PARAMETER,
                confidence_level=Decimal("1"),
                is_active=True,
            )
            for spare_part_id in spare_part_ids
        ]
    )
    session.commit()

    quantity = int(fallback_draft["equipment_quantity"]["value"])
    duration_days = Decimal(str(fallback_draft["duration_days"]["value"]))
    service_level = Decimal(str(fallback_draft["service_level"]["value"]))
    [fallback_stage] = fallback_draft["stages"]["value"]
    structured_draft = ScenarioDraftPayload(
        scenario_name=str(fallback_draft["scenario_name"]["value"]),
        current_step=6,
        fields={
            "mission_code": _confirmed_ai_field("SC-PLAN05-AI-DISABLED"),
            "start_at": _confirmed_ai_field("2026-10-01T00:00:00Z"),
            "end_at": _confirmed_ai_field("2026-10-31T00:00:00Z"),
            "priority": _confirmed_ai_field("HIGH"),
            "equipment_model_id": _confirmed_ai_field(
                configuration.equipment_model_id
            ),
            "configuration_version_id": _confirmed_ai_field(configuration.id),
            "fleet_groups": _confirmed_ai_field(
                [
                    {
                        "client_key": "fallback-fleet",
                        "group_code": "FALLBACK-FLEET",
                        "group_name": str(
                            fallback_draft["equipment_model"]["value"]
                        ),
                        "configuration_version_id": configuration.id,
                        "initial_quantity": quantity,
                        "age_groups": [
                            {
                                "group_code": "FALLBACK-AGE",
                                "group_name": "Fallback fixed age",
                                "distribution_type": "FIXED",
                                "proportion": "1",
                                "fixed_hours": "100",
                            }
                        ],
                    }
                ]
            ),
            "stages": _confirmed_ai_field(
                [
                    {
                        "client_key": "fallback-stage",
                        "stage_code": fallback_stage["code"],
                        "stage_name": fallback_stage["name"],
                        "stage_order": 1,
                        "duration_hours": fallback_stage["duration_hours"],
                        "mission_intensity_factor": fallback_stage[
                            "usage_intensity"
                        ],
                        "fleet_usages": [
                            {
                                "fleet_group_key": "fallback-fleet",
                                "active_quantity": quantity,
                            }
                        ],
                        "shocks": [],
                    }
                ]
            ),
            "reliability_profiles": _confirmed_ai_field(
                [{"status": "confirmed"}]
            ),
            "service_level": _confirmed_ai_field(service_level),
            "execution_preference": _confirmed_ai_field("ANALYTICAL"),
            "missing_parameter_policy": _confirmed_ai_field("WARN_AND_SKIP"),
            "version_code": _confirmed_ai_field("V1"),
            "version_name": _confirmed_ai_field(
                "Plan 05 AI-disabled scenario V1"
            ),
        },
    )
    draft_service = ScenarioDraftService()
    created_draft = draft_service.create(
        session,
        contributor,
        title=structured_draft.scenario_name,
        sensitivity_level="INTERNAL",
        origin="AI",
        draft=structured_draft,
    )
    assert created_draft.blocking_fields == []
    materialized = draft_service.materialize(
        session,
        contributor,
        created_draft.session_id,
        expected_version=created_draft.version,
        idempotency_key="plan05-ai-disabled-materialize",
    )
    assert materialized.validation.valid is True
    scenario = scenario_service.publish_version(
        session,
        admin,
        materialized.scenario_version.id,
    )
    assert scenario.status is ScenarioVersionStatus.PUBLISHED
    scenario = scenario_service.get_version(
        session,
        contributor,
        scenario.id,
        full=True,
    )
    assert scenario.fleet_groups[0].initial_quantity == quantity
    assert scenario.stages[0].duration_hours == duration_days * Decimal("24")
    assert scenario.default_service_level == service_level

    group_service = CalculationGroupService()
    recommendation = group_service.recommendation_service.recommend(
        session,
        contributor,
        scenario.id,
    )
    candidate_key = "WEIBULL:ANALYTICAL"
    analytical = next(
        item
        for item in recommendation.items
        if item.candidate_key == candidate_key
    )
    assert analytical.applicable is True
    calculation_group = group_service.create(
        session,
        contributor,
        scenario_version_id=scenario.id,
        primary_candidate_key=candidate_key,
        selected_candidate_keys=[candidate_key],
        idempotency_key="plan05-ai-disabled-calculation",
        random_seed=20260909,
    )
    assert calculation_group.status is CalculationGroupStatus.PENDING
    [calculation_child] = calculation_group.current_children
    calculation = group_service.calculation_service.run_internal(
        session,
        tenant_id=contributor.tenant_id,
        calculation_id=calculation_child.calculation_id,
        observer=CalculationGroupObserver(
            contributor.tenant_id,
            calculation_group.id,
            calculation_child.id,
        ),
    )
    assert calculation.status in {
        CalculationStatus.SUCCEEDED,
        CalculationStatus.PARTIAL_SUCCESS,
    }
    calculation_group = group_service.get(
        session,
        contributor,
        calculation_group.id,
    )
    assert calculation_group.status is CalculationGroupStatus.COMPLETED
    assert calculation_group.primary_candidate_key == candidate_key
    comparison = group_service.comparison(
        session,
        contributor,
        calculation_group.id,
    )
    assert comparison.rows
    for row in comparison.rows:
        candidate = row.candidates[candidate_key]
        assert candidate.status == "SUCCEEDED"
        assert candidate.execution_mode.value == "ANALYTICAL"
        assert candidate.recommended_quantity is not None
        group_service.save_decision(
            session,
            contributor,
            calculation_group.id,
            spare_part_id=row.spare_part_id,
            expected_version=0,
            selected_child_id=candidate.child_id,
            final_quantity=candidate.recommended_quantity,
            reason=None,
        )

    demand_service = DemandListService()
    draft_list = demand_service.create_from_group(
        session,
        contributor,
        calculation_group_id=calculation_group.id,
        name="Plan 05 AI-disabled demand list",
        description="Derived from the provider-disabled structured scenario",
        idempotency_key="plan05-ai-disabled-demand-create",
    )
    assert draft_list.status is DemandListStatus.DRAFT
    submitted = demand_service.submit(
        session,
        contributor,
        draft_list.id,
        expected_version=draft_list.version,
        idempotency_key="plan05-ai-disabled-demand-submit",
    )
    assert submitted.status is DemandListStatus.PENDING_CONFIRMATION
    confirmed = demand_service.confirm(
        session,
        admin,
        submitted.id,
        expected_version=submitted.version,
        confirmation_note="Confirm deterministic provider-disabled demand",
        idempotency_key="plan05-ai-disabled-demand-confirm",
    )
    assert confirmed.status is DemandListStatus.CONFIRMED
    source = demand_service.publish(
        session,
        admin,
        confirmed.id,
        expected_version=confirmed.version,
        idempotency_key="plan05-ai-disabled-demand-publish",
    )
    assert source.status is DemandListStatus.PUBLISHED
    assert source.scenario_version_id == scenario.id
    assert source.calculation_group_id == calculation_group.id
    assert source.items
    assert all(
        item.execution_mode is not None
        and item.execution_mode.value == "ANALYTICAL"
        for item in source.items
    )

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

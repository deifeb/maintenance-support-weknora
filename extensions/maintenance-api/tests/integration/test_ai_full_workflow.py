import time

from app.models import (
    AIModelCall,
    AIReviewRun,
    DemandCalculation,
    DemandScenarioVersion,
)
from app.models.enums import CalculationStatus, ScenarioVersionStatus
from app.scripts.seed_demand_scenarios import seed as seed_demand_scenarios
from sqlalchemy import func, select


def _wait_for_calculation(session, timeout: float = 15.0) -> DemandCalculation:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.expire_all()
        row = session.scalar(select(DemandCalculation).order_by(DemandCalculation.id.desc()))
        if row is not None and row.status in {
            CalculationStatus.SUCCEEDED,
            CalculationStatus.PARTIAL_SUCCESS,
            CalculationStatus.FAILED,
        }:
            return row
        time.sleep(0.05)
    raise AssertionError("demand calculation did not finish")


def test_ai_api_full_workflow_reaches_calculation_review_and_docx(
    client, session, monkeypatch
) -> None:
    from app.services.ai_model_runtime import AIModelRuntime
    from app.services.ai_orchestration_service import ai_orchestration_service
    from tests.ai.factories import make_router

    monkeypatch.setattr(
        ai_orchestration_service,
        "runtime_factory",
        lambda: AIModelRuntime(router=make_router(function_name="scenario_parsing")),
    )
    seed_demand_scenarios()
    session.expire_all()
    scenario = session.scalar(
        select(DemandScenarioVersion)
        .where(DemandScenarioVersion.status == ScenarioVersionStatus.PUBLISHED)
        .order_by(DemandScenarioVersion.id)
    )
    assert scenario is not None

    created = client.post(
        "/api/v1/ai/sessions",
        json={
            "title": "端到端维修保障分析",
            "sensitivity_level": "INTERNAL",
            "active_scenario_version_id": scenario.id,
        },
    )
    assert created.status_code == 200
    ai_session_id = created.json()["data"]["id"]

    clarification = client.post(
        f"/api/v1/ai/sessions/{ai_session_id}/messages",
        json={"content": "准备一次保障任务"},
    )
    assert clarification.status_code == 200
    assert clarification.json()["data"]["status"] == "CLARIFICATION_REQUIRED"

    clarified = client.post(
        f"/api/v1/ai/sessions/{ai_session_id}/messages",
        json={
            "content": "示例装备1采用V1构型，10台执行30天高强度任务，保障率95%，启用修理，不考虑共同冲击"
        },
    )
    assert clarified.status_code == 200
    assert clarified.json()["data"]["status"] == "PLANNED"
    assert clarified.json()["data"]["summary"] == {
        "execution_mode": "LLM",
        "llm_generated": True,
    }

    confirmation = client.post(
        f"/api/v1/ai/sessions/{ai_session_id}/messages",
        json={"content": "按当前场景执行正式需求计算"},
    )
    assert confirmation.status_code == 200
    confirmation_data = confirmation.json()["data"]
    assert confirmation_data["status"] == "CONFIRMATION_REQUIRED"

    detail = client.get(f"/api/v1/ai/sessions/{ai_session_id}").json()["data"]
    pending = detail["pending_confirmation"]
    approved = client.post(
        f"/api/v1/ai/confirmations/{pending['id']}/approve",
        json={
            "confirmation_token": confirmation_data["confirmation_token"],
            "expected_input_digest": pending["input_digest"],
            "comment": "确认执行",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["workflow_submitted"] is True

    calculation = _wait_for_calculation(session)
    assert calculation.status in {
        CalculationStatus.SUCCEEDED,
        CalculationStatus.PARTIAL_SUCCESS,
    }
    assert session.scalar(select(func.count(DemandCalculation.id))) == 1

    resumed = client.post(f"/api/v1/ai/sessions/{ai_session_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["data"]["status"] == "COMPLETED"

    review = client.post(
        "/api/v1/ai/reviews/demand-lists",
        json={
            "calculation_id": calculation.id,
            "items": [
                {
                    "spare_part_id": 1,
                    "recommended_spare_quantity": "8",
                    "usable_inventory": "3",
                    "net_demand_gap": "5",
                    "inventory_coverage_rate": "0.375",
                    "selected_reliability_profile_id": 1,
                }
            ],
        },
    )
    assert review.status_code == 200
    assert review.json()["data"]["findings"]
    assert session.scalar(select(func.count(AIReviewRun.id))) == 1

    report = client.post(
        "/api/v1/ai/reports",
        json={
            "title": "维修保障管理决策报告",
            "report_type": "MANAGEMENT_DECISION",
            "session_id": ai_session_id,
            "review_run_id": review.json()["data"]["review_id"],
            "metadata": {"execution_mode": "LLM", "llm_generated": True},
            "sections": [
                {
                    "section_code": "management_summary",
                    "title": "管理摘要",
                    "content": "本报告依据确定性计算快照与审查结果生成。[E-001]",
                    "source_type": "DETERMINISTIC",
                }
            ],
            "citations": [
                {
                    "citation_id": "E-001",
                    "source_type": "CALCULATION_SNAPSHOT",
                    "source_name": "需求计算快照",
                }
            ],
        },
    )
    assert report.status_code == 200
    report_id = report.json()["data"]["id"]
    assert client.post(f"/api/v1/ai/reports/{report_id}/generate").status_code == 200
    validated = client.post(f"/api/v1/ai/reports/{report_id}/validate")
    assert validated.status_code == 200
    assert validated.json()["data"]["findings"] == []
    docx = client.get(f"/api/v1/ai/reports/{report_id}/exports/docx")
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"

    model_calls = list(session.scalars(select(AIModelCall)).all())
    assert all(row.provider == "DETERMINISTIC_TEST" for row in model_calls)

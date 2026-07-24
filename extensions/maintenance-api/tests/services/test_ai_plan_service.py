from app.models.enums import AISessionStatus
from app.services.ai_plan_service import ai_plan_service
from tests.ai.factories import create_ai_session


def test_plan_service_persists_validated_plan(session) -> None:
    row = create_ai_session(session)
    plan = ai_plan_service.create_and_validate(
        session,
        row.id,
        "按当前场景执行正式需求计算",
    )
    session.refresh(row)
    assert plan.validation_status == "VALID"
    assert row.status is AISessionStatus.PLANNED

from app.models.enums import AISessionStatus
from app.workers.ai_recovery import recover_interrupted_ai_tasks
from tests.ai.factories import create_ai_session


def test_restart_recovery_is_idempotent(session) -> None:
    row = create_ai_session(session, status=AISessionStatus.EXECUTING)
    session.commit()

    assert recover_interrupted_ai_tasks(session) == 1
    assert recover_interrupted_ai_tasks(session) == 0
    session.refresh(row)
    assert row.status is AISessionStatus.PARTIALLY_COMPLETED

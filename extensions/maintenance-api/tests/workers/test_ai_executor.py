from threading import Event

from app.models.enums import AISessionStatus
from app.workers.ai_executor import ai_task_executor, submit_ai_session
from tests.ai.factories import create_ai_session


def test_ai_executor_uses_independent_database_session(session, monkeypatch) -> None:
    row = create_ai_session(session, status=AISessionStatus.PLANNED)
    session.commit()
    completed = Event()
    seen_sessions = []

    async def fake_execute(db, session_id, **kwargs):
        seen_sessions.append(db)
        target = db.get(type(row), session_id)
        target.status = AISessionStatus.COMPLETED
        db.commit()
        completed.set()

    monkeypatch.setattr(
        "app.workers.ai_executor.ai_orchestration_service.execute_plan", fake_execute
    )
    future = submit_ai_session(
        row.id,
        user_id="tester",
        permissions={"AI_EXECUTE"},
    )

    assert future is not None
    assert completed.wait(timeout=5)
    future.result(timeout=5)
    session.expire_all()
    assert session.get(type(row), row.id).status is AISessionStatus.COMPLETED
    assert seen_sessions and seen_sessions[0] is not session
    ai_task_executor.shutdown(wait=True)

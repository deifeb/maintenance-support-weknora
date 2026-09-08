from __future__ import annotations

from inspect import signature
from threading import Event

import app.workers.ai_executor as ai_executor_module
from app.models.enums import AISessionStatus
from app.security.actor import ActorContext
from tests.ai.factories import create_ai_session


class ImmediateExecutor:
    def submit(
        self,
        task_type: str,
        task_id: int,
        operation,
    ) -> object:
        operation()
        return object()


class FakeSession:
    def __init__(
        self,
        captured: dict[str, object],
    ) -> None:
        self.captured = captured

    def close(self) -> None:
        self.captured["closed"] = True


def test_ai_worker_entrypoints_require_actor() -> None:
    session_parameters = signature(
        ai_executor_module.submit_ai_session
    ).parameters
    report_parameters = signature(
        ai_executor_module.submit_report_job
    ).parameters

    assert "actor" in session_parameters
    assert "user_id" not in session_parameters
    assert "permissions" not in (
        session_parameters
    )
    assert "actor" in report_parameters


def test_ai_session_worker_preserves_actor(
    monkeypatch,
    actor_contributor: ActorContext,
) -> None:
    captured: dict[str, object] = {}

    async def fake_execute_plan(
        session,
        actor,
        session_id,
        *,
        permissions,
        workspace_id,
    ) -> None:
        captured["session"] = session
        captured["actor"] = actor
        captured["session_id"] = session_id
        captured["permissions"] = permissions
        captured["workspace_id"] = (
            workspace_id
        )

    monkeypatch.setattr(
        ai_executor_module,
        "ai_task_executor",
        ImmediateExecutor(),
    )
    monkeypatch.setattr(
        ai_executor_module,
        "SessionLocal",
        lambda: FakeSession(captured),
    )
    monkeypatch.setattr(
        ai_executor_module
        .ai_orchestration_service,
        "execute_plan",
        fake_execute_plan,
    )

    result = (
        ai_executor_module.submit_ai_session(
            19,
            actor_contributor,
        )
    )

    assert result is not None
    assert (
        captured["actor"]
        is actor_contributor
    )
    assert captured["session_id"] == 19
    assert captured["closed"] is True
    assert (
        captured["permissions"]
        == {
            "SCENARIO_DRAFT",
            "CALCULATION_EXECUTE",
            "CALCULATION_CANCEL",
            "REPORT_CREATE",
            "REVIEW_EXECUTE",
        }
    )


def test_report_worker_preserves_actor(
    monkeypatch,
    actor_admin: ActorContext,
) -> None:
    captured: dict[str, object] = {
        "calls": [],
    }

    def fake_generate(
        session,
        actor,
        report_job_id,
    ) -> None:
        captured["calls"].append(
            (
                "generate",
                session,
                actor,
                report_job_id,
            )
        )

    def fake_validate(
        session,
        actor,
        report_job_id,
    ) -> None:
        captured["calls"].append(
            (
                "validate",
                session,
                actor,
                report_job_id,
            )
        )

    monkeypatch.setattr(
        ai_executor_module,
        "ai_task_executor",
        ImmediateExecutor(),
    )
    monkeypatch.setattr(
        ai_executor_module,
        "SessionLocal",
        lambda: FakeSession(captured),
    )
    monkeypatch.setattr(
        ai_executor_module
        .ai_report_service,
        "generate",
        fake_generate,
    )
    monkeypatch.setattr(
        ai_executor_module
        .ai_report_service,
        "validate",
        fake_validate,
    )

    result = (
        ai_executor_module.submit_report_job(
            27,
            actor_admin,
        )
    )

    assert result is not None
    calls = captured["calls"]
    assert [
        call[0]
        for call in calls
    ] == [
        "generate",
        "validate",
    ]
    assert all(
        call[2] is actor_admin
        for call in calls
    )
    assert all(
        call[3] == 27
        for call in calls
    )
    assert captured["closed"] is True


def test_ai_executor_uses_independent_database_session(
    session,
    monkeypatch,
    actor_contributor: ActorContext,
) -> None:
    row = create_ai_session(
        session,
        status=AISessionStatus.PLANNED,
        tenant_id=(
            actor_contributor.tenant_id
        ),
    )
    session.commit()
    completed = Event()
    seen_sessions = []

    async def fake_execute(
        db,
        actor,
        session_id,
        *,
        permissions,
        workspace_id,
    ) -> None:
        assert actor is actor_contributor
        assert permissions
        assert workspace_id == "default"
        seen_sessions.append(db)
        target = db.get(
            type(row),
            session_id,
        )
        target.status = (
            AISessionStatus.COMPLETED
        )
        db.commit()
        completed.set()

    monkeypatch.setattr(
        ai_executor_module
        .ai_orchestration_service,
        "execute_plan",
        fake_execute,
    )
    future = (
        ai_executor_module.submit_ai_session(
            row.id,
            actor_contributor,
        )
    )

    assert future is not None
    assert completed.wait(timeout=5)
    future.result(timeout=5)
    session.expire_all()
    persisted = session.get(
        type(row),
        row.id,
    )
    assert persisted is not None
    assert (
        persisted.status
        is AISessionStatus.COMPLETED
    )
    assert (
        seen_sessions
        and seen_sessions[0] is not session
    )
    ai_executor_module.ai_task_executor.shutdown(
        wait=True
    )

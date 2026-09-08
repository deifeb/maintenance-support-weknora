from __future__ import annotations

import asyncio
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from threading import Lock
from typing import Callable

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.security.actor import ActorContext
from app.services.ai_orchestration_service import (
    ai_orchestration_service,
)
from app.services.ai_report_service import (
    ai_report_service,
)
from app.services.ai_tool_registry import (
    permissions_for_actor,
)


class AITaskExecutor:
    def __init__(self) -> None:
        self._executor: (
            ThreadPoolExecutor | None
        ) = None
        self._futures: dict[
            tuple[str, int],
            Future[None],
        ] = {}
        self._lock = Lock()

    def _pool(
        self,
    ) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = (
                ThreadPoolExecutor(
                    max_workers=(
                        get_settings()
                        .ai_worker_count
                    ),
                    thread_name_prefix=(
                        "ai-task"
                    ),
                )
            )
        return self._executor

    def submit(
        self,
        task_type: str,
        task_id: int,
        operation: Callable[[], None],
    ) -> Future[None] | None:
        key = (task_type, task_id)
        with self._lock:
            existing = self._futures.get(key)
            if (
                existing is not None
                and not existing.done()
            ):
                return existing
            active = sum(
                not future.done()
                for future
                in self._futures.values()
            )
            if (
                active
                >= get_settings()
                .ai_max_pending_tasks
            ):
                return None
            future = self._pool().submit(
                operation
            )
            self._futures[key] = future
            future.add_done_callback(
                lambda completed,
                task_key=key: self._discard(
                    task_key,
                    completed,
                )
            )
            return future

    def _discard(
        self,
        key: tuple[str, int],
        completed: Future[None],
    ) -> None:
        with self._lock:
            if (
                self._futures.get(key)
                is completed
            ):
                self._futures.pop(
                    key,
                    None,
                )

    def is_active(
        self,
        task_type: str,
        task_id: int,
    ) -> bool:
        with self._lock:
            future = self._futures.get(
                (task_type, task_id)
            )
            return bool(
                future is not None
                and not future.done()
            )

    def shutdown(
        self,
        wait: bool = False,
    ) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
            self._futures.clear()
        if executor is not None:
            executor.shutdown(
                wait=wait,
                cancel_futures=False,
            )


ai_task_executor = AITaskExecutor()


def submit_ai_session(
    session_id: int,
    actor: ActorContext,
    *,
    workspace_id: str = "default",
) -> Future[None] | None:
    def run() -> None:
        session = SessionLocal()
        try:
            asyncio.run(
                ai_orchestration_service
                .execute_plan(
                    session,
                    actor,
                    session_id,
                    permissions=set(
                        permissions_for_actor(
                            actor
                        )
                    ),
                    workspace_id=(
                        workspace_id
                    ),
                )
            )
        finally:
            session.close()

    return ai_task_executor.submit(
        "session",
        session_id,
        run,
    )


def submit_report_job(
    report_job_id: int,
    actor: ActorContext,
) -> Future[None] | None:
    def run() -> None:
        session = SessionLocal()
        try:
            ai_report_service.generate(
                session,
                actor,
                report_job_id,
            )
            ai_report_service.validate(
                session,
                actor,
                report_job_id,
            )
        finally:
            session.close()

    return ai_task_executor.submit(
        "report",
        report_job_id,
        run,
    )

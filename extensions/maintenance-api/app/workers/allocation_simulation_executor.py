from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.allocation_simulation_service import (
    allocation_simulation_service,
)
from app.workers.task_registry import TaskRegistry

allocation_simulation_registry = TaskRegistry()


class AllocationSimulationExecutor:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None

    def _pool(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=(
                    get_settings().allocation_simulation_worker_count
                ),
                thread_name_prefix="allocation-simulation",
            )
        return self._executor

    def submit(
        self,
        tenant_id: str,
        simulation_id: int,
    ) -> bool:
        key = (tenant_id, simulation_id)
        if not allocation_simulation_registry.register(key):
            return False
        try:
            self._pool().submit(
                self._run,
                tenant_id,
                simulation_id,
            )
        except Exception:
            allocation_simulation_registry.unregister(key)
            raise
        return True

    @staticmethod
    def _run(
        tenant_id: str,
        simulation_id: int,
    ) -> None:
        key = (tenant_id, simulation_id)
        session = SessionLocal()
        try:
            claimed = allocation_simulation_service.claim(
                session,
                tenant_id,
                simulation_id,
            )
            if claimed is None:
                session.rollback()
                return
            session.commit()

            allocation_simulation_service.run_claimed(
                session,
                tenant_id,
                simulation_id,
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            allocation_simulation_service.fail_safely(
                tenant_id,
                simulation_id,
                exc,
            )
        finally:
            session.close()
            allocation_simulation_registry.unregister(key)

    def shutdown(self, wait: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(
                wait=wait,
                cancel_futures=False,
            )
            self._executor = None


allocation_simulation_executor = AllocationSimulationExecutor()

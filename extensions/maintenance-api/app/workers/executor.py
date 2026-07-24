from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.demand_calculation_service import calculation_service
from app.workers.task_registry import registry


class DemandTaskExecutor:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None

    def _pool(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=get_settings().demand_worker_count, thread_name_prefix="demand-calc"
            )
        return self._executor

    def submit(self, calculation_id: int) -> bool:
        if not registry.register(calculation_id):
            return False
        self._pool().submit(self._run, calculation_id)
        return True

    @staticmethod
    def _run(calculation_id: int) -> None:
        session = SessionLocal()
        try:
            calculation_service.run(session, calculation_id)
        except Exception:
            pass
        finally:
            session.close()
            registry.unregister(calculation_id)

    def shutdown(self, wait: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=wait, cancel_futures=False)
            self._executor = None


demand_task_executor = DemandTaskExecutor()

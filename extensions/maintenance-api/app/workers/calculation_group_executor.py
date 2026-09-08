from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import CalculationGroupChild, DemandCalculation
from app.models.enums import CalculationStatus
from app.services.calculation_group_service import (
    calculation_group_service,
)
from app.services.demand_calculation_service import (
    calculation_service,
)
from app.workers.task_registry import group_registry


class CalculationGroupObserver:
    def __init__(
        self,
        tenant_id: str,
        group_id: int,
        child_id: int,
    ) -> None:
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.child_id = child_id

    def _event(
        self,
        session,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        calculation_group_service.group_repository.append_event(
            session,
            self.tenant_id,
            self.group_id,
            child_id=self.child_id,
            event_type=event_type,
            payload=payload,
        )

    def started(
        self,
        session,
        calculation: DemandCalculation,
    ) -> None:
        self._event(
            session,
            "child.started",
            {"calculation_id": calculation.id},
        )
        calculation_group_service.refresh_status_internal(
            session,
            self.tenant_id,
            self.group_id,
        )

    def progress(
        self,
        session,
        calculation: DemandCalculation,
        percent: Decimal,
    ) -> None:
        self._event(
            session,
            "child.progress",
            {
                "calculation_id": calculation.id,
                "progress_percent": str(percent),
            },
        )

    def completed(
        self,
        session,
        calculation: DemandCalculation,
    ) -> None:
        self._event(
            session,
            "child.completed",
            {
                "calculation_id": calculation.id,
                "status": calculation.status.value,
            },
        )
        calculation_group_service.refresh_status_internal(
            session,
            self.tenant_id,
            self.group_id,
        )

    def failed(
        self,
        session,
        calculation: DemandCalculation,
        error: Exception,
    ) -> None:
        cancelled = (
            calculation.status is CalculationStatus.CANCELLED
        )
        self._event(
            session,
            (
                "child.cancelled"
                if cancelled
                else "child.failed"
            ),
            {
                "calculation_id": calculation.id,
                "status": calculation.status.value,
                "error": str(error)[:500],
            },
        )
        calculation_group_service.refresh_status_internal(
            session,
            self.tenant_id,
            self.group_id,
        )


class CalculationGroupExecutor:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None

    def _pool(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=get_settings().demand_worker_count,
                thread_name_prefix="calculation-group",
            )
        return self._executor

    def submit(
        self,
        tenant_id: str,
        group_child_id: int,
    ) -> bool:
        key = (tenant_id, group_child_id)
        if not group_registry.register(key):
            return False
        try:
            self._pool().submit(
                self._run,
                tenant_id,
                group_child_id,
            )
        except Exception:
            group_registry.unregister(key)
            raise
        return True

    @staticmethod
    def _run(
        tenant_id: str,
        group_child_id: int,
    ) -> None:
        key = (tenant_id, group_child_id)
        session = SessionLocal()
        try:
            child = session.scalar(
                select(CalculationGroupChild).where(
                    CalculationGroupChild.tenant_id
                    == tenant_id,
                    CalculationGroupChild.id
                    == group_child_id,
                    CalculationGroupChild
                    .is_current_attempt
                    .is_(True),
                )
            )
            if child is None:
                return
            observer = CalculationGroupObserver(
                tenant_id,
                child.group_id,
                child.id,
            )
            calculation_service.run_internal(
                session,
                tenant_id=tenant_id,
                calculation_id=child.calculation_id,
                observer=observer,
            )
        except Exception:
            pass
        finally:
            session.close()
            group_registry.unregister(key)

    def shutdown(self, wait: bool = False) -> None:
        if self._executor is not None:
            self._executor.shutdown(
                wait=wait,
                cancel_futures=False,
            )
            self._executor = None


calculation_group_executor = CalculationGroupExecutor()

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CalculationGroupChild,
    DemandCalculation,
)
from app.models.enums import CalculationStatus
from app.services.calculation_group_service import (
    calculation_group_service,
)
from app.workers.calculation_group_executor import (
    calculation_group_executor,
)


def recover_interrupted_calculations(session: Session) -> int:
    current_children = list(
        session.scalars(
            select(CalculationGroupChild).where(
                CalculationGroupChild
                .is_current_attempt
                .is_(True)
            )
        ).all()
    )
    child_by_calculation = {
        child.calculation_id: child
        for child in current_children
    }
    rows = list(
        session.scalars(
            select(DemandCalculation).where(DemandCalculation.status == CalculationStatus.RUNNING)
        ).all()
    )
    for row in rows:
        row.status = CalculationStatus.INTERRUPTED
        row.error_code = "WORKER_INTERRUPTED"
        row.error_message = "The service stopped while the calculation was running"
        row.completed_at = datetime.now(timezone.utc)
        child = child_by_calculation.get(row.id)
        if child is not None:
            calculation_group_service.group_repository.append_event(
                session,
                row.tenant_id,
                child.group_id,
                child_id=child.id,
                event_type="child.interrupted",
                payload={"calculation_id": row.id},
            )
    for group_id, tenant_id in {
        (child.group_id, child.tenant_id)
        for child in current_children
        if child.calculation_id in {
            row.id
            for row in rows
        }
    }:
        calculation_group_service.refresh_status_internal(
            session,
            tenant_id,
            group_id,
        )
    session.commit()
    pending_ids = {
        row.id
        for row in session.scalars(
            select(DemandCalculation).where(
                DemandCalculation.status
                == CalculationStatus.PENDING
            )
        ).all()
    }
    for child in current_children:
        if child.calculation_id in pending_ids:
            calculation_group_executor.submit(
                child.tenant_id,
                child.id,
            )
    return len(rows)

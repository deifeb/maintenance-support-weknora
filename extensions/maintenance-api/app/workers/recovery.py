from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DemandCalculation
from app.models.enums import CalculationStatus


def recover_interrupted_calculations(session: Session) -> int:
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
    session.commit()
    return len(rows)

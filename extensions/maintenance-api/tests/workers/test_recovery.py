from datetime import datetime, timezone

from app.models import DemandCalculation
from app.models.enums import (
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
)
from app.workers.recovery import recover_interrupted_calculations


def add_running_calculation(session, tenant_id: str, suffix: str):
    row = DemandCalculation(
        tenant_id=tenant_id,
        calculation_code=f"REC-{suffix}",
        calculation_name=f"Interrupted {suffix}",
        execution_type=CalculationExecutionType.ASYNCHRONOUS,
        requested_mode=DemandExecutionMode.MONTE_CARLO,
        status=CalculationStatus.RUNNING,
        input_snapshot_json={"stages": [], "items": []},
        input_snapshot_hash=(suffix * 64)[:64],
        inventory_snapshot_at=datetime.now(timezone.utc),
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def test_recovery_marks_running_calculations_interrupted(session):
    first = add_running_calculation(session, "tenant-a", "A")
    second = add_running_calculation(session, "tenant-b", "B")
    session.commit()

    assert recover_interrupted_calculations(session) == 2

    session.refresh(first)
    session.refresh(second)
    for row in (first, second):
        assert row.status is CalculationStatus.INTERRUPTED
        assert row.error_code == "WORKER_INTERRUPTED"

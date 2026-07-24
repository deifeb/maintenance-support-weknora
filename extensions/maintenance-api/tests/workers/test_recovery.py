from datetime import datetime, timezone

from app.models import DemandCalculation
from app.models.enums import CalculationExecutionType, CalculationStatus, DemandExecutionMode
from app.workers.recovery import recover_interrupted_calculations


def test_recovery_marks_running_calculations_interrupted(session):
    row = DemandCalculation(
        calculation_code="REC-1",
        calculation_name="中断任务",
        execution_type=CalculationExecutionType.ASYNCHRONOUS,
        requested_mode=DemandExecutionMode.MONTE_CARLO,
        status=CalculationStatus.RUNNING,
        input_snapshot_json={"stages": [], "items": []},
        input_snapshot_hash="a" * 64,
        inventory_snapshot_at=datetime.now(timezone.utc),
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    assert recover_interrupted_calculations(session) == 1
    session.refresh(row)
    assert row.status is CalculationStatus.INTERRUPTED
    assert row.error_code == "WORKER_INTERRUPTED"

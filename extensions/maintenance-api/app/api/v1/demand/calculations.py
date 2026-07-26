from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.responses import success_response
from app.db.session import get_db_session
from app.exporters import export_calculation_excel, export_calculation_json
from app.models import DemandCalculation, DemandCalculationRun
from app.models.enums import CalculationExecutionType, CalculationStatus
from app.schemas.demand_calculation import CalculationCreateRequest, CalculationPreviewRequest
from app.security.actor import ActorContext
from app.security.dependencies import get_actor
from app.services.demand_calculation_service import calculation_service
from app.workers.executor import demand_task_executor

router = APIRouter(prefix="/calculations", tags=["demand: calculations"])
SessionDep = Annotated[Session, Depends(get_db_session)]
ActorDep = Annotated[ActorContext, Depends(get_actor)]


def _calculation_dict(row: DemandCalculation):
    return {
        "id": row.id,
        "calculation_code": row.calculation_code,
        "calculation_name": row.calculation_name,
        "status": row.status.value,
        "execution_type": row.execution_type.value,
        "requested_mode": row.requested_mode.value,
        "progress_percent": float(row.progress_percent),
        "current_stage": row.current_stage,
        "input_snapshot_hash": row.input_snapshot_hash,
        "warnings": row.warnings_json,
        "result_summary": row.result_summary_json,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "submitted_at": row.submitted_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    }


@router.post("/preview")
def preview(
    payload: CalculationPreviewRequest,
    session: SessionDep,
    actor: ActorDep,
):
    return success_response(
        calculation_service.preview(
            session,
            actor,
            payload,
        )
    )


@router.post("")
def submit(
    payload: CalculationCreateRequest,
    session: SessionDep,
    actor: ActorDep,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    calculation = calculation_service.submit(
        session,
        actor,
        payload,
        idempotency_key=idempotency_key,
    )
    if (
        calculation.execution_type
        is CalculationExecutionType.ASYNCHRONOUS
        and calculation.status is CalculationStatus.PENDING
    ):
        if not demand_task_executor.submit(
            actor.tenant_id,
            calculation.id,
        ):
            raise ConflictError(
                "calculation is already queued",
                code="CALCULATION_ALREADY_RUNNING",
            )
    return success_response(
        _calculation_dict(calculation),
        "Calculation submitted",
    )


@router.get("")
def list_calculations(
    session: SessionDep,
    actor: ActorDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: CalculationStatus | None = None,
):
    stmt = (
        select(DemandCalculation)
        .where(
            DemandCalculation.tenant_id
            == actor.tenant_id
        )
        .order_by(DemandCalculation.id.desc())
    )
    if status is not None:
        stmt = stmt.where(
            DemandCalculation.status == status
        )
    rows = list(
        session.scalars(
            stmt.offset(
                (page - 1) * page_size
            ).limit(page_size)
        ).all()
    )
    return success_response(
        {
            "items": [
                _calculation_dict(row)
                for row in rows
            ],
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{calculation_id}")
def get_calculation(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    return success_response(
        _calculation_dict(
            calculation_service.get(
                session,
                actor,
                calculation_id,
            )
        )
    )


@router.get("/{calculation_id}/status")
def get_status(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    row = calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    return success_response(
        {
            "id": row.id,
            "status": row.status.value,
            "progress_percent": float(row.progress_percent),
            "current_stage": row.current_stage,
            "error_code": row.error_code,
            "error_message": row.error_message,
        }
    )


@router.post("/{calculation_id}/cancel")
def cancel(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    return success_response(
        _calculation_dict(
            calculation_service.cancel(
                session,
                actor,
                calculation_id,
            )
        ),
        "Cancellation requested",
    )


@router.post("/{calculation_id}/retry")
def retry(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    row = calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    if row.status not in {
        CalculationStatus.FAILED,
        CalculationStatus.INTERRUPTED,
    }:
        raise ConflictError(
            "calculation is not retryable",
            code="CALCULATION_NOT_RETRYABLE",
        )
    row.status = CalculationStatus.PENDING
    row.error_code = None
    row.error_message = None
    row.cancel_requested = False
    session.commit()
    session.refresh(row)
    if (
        row.execution_type
        is CalculationExecutionType.ASYNCHRONOUS
    ):
        demand_task_executor.submit(
            actor.tenant_id,
            row.id,
        )
    else:
        calculation_service.run(
            session,
            actor,
            row.id,
        )
    return success_response(
        _calculation_dict(row),
        "Calculation retried",
    )


@router.post("/{calculation_id}/replay")
def replay(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    source = calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    request = CalculationCreateRequest(
        calculation_name=(
            f"{source.calculation_name} - snapshot replay"
        ),
        temporary_scenario=source.input_snapshot_json,
        requested_mode=source.requested_mode,
        execution_preference=(
            "ASYNC"
            if (
                source.execution_type
                is CalculationExecutionType.ASYNCHRONOUS
            )
            else "SYNC"
        ),
    )
    created = calculation_service.submit(
        session,
        actor,
        request,
    )
    created.source_calculation_id = source.id
    session.commit()
    session.refresh(created)
    if (
        created.execution_type
        is CalculationExecutionType.ASYNCHRONOUS
    ):
        demand_task_executor.submit(
            actor.tenant_id,
            created.id,
        )
    return success_response(
        _calculation_dict(created)
    )


@router.post("/{calculation_id}/rerun-latest")
def rerun_latest(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    source = calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    if source.scenario_version_id is None:
        return replay(
            calculation_id,
            session,
            actor,
        )
    request = CalculationCreateRequest(
        calculation_name=(
            f"{source.calculation_name} - latest data"
        ),
        scenario_version_id=source.scenario_version_id,
        requested_mode=source.requested_mode,
        execution_preference="AUTO",
    )
    created = calculation_service.submit(
        session,
        actor,
        request,
    )
    created.source_calculation_id = source.id
    session.commit()
    session.refresh(created)
    if (
        created.execution_type
        is CalculationExecutionType.ASYNCHRONOUS
    ):
        demand_task_executor.submit(
            actor.tenant_id,
            created.id,
        )
    return success_response(
        _calculation_dict(created)
    )


@router.get("/{calculation_id}/results/items")
def result_items(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    calculation = session.scalar(
        select(DemandCalculation)
        .where(
            DemandCalculation.id == calculation_id,
            DemandCalculation.tenant_id
            == actor.tenant_id,
        )
        .options(
            selectinload(
                DemandCalculation.runs
            ).selectinload(
                DemandCalculationRun.item_results
            )
        )
    )
    if calculation is None:
        raise NotFoundError(
            "demand_calculation",
            calculation_id,
        )
    rows = []
    for run in calculation.runs:
        for item in run.item_results:
            rows.append(
                {
                    "run_mode": run.run_mode.value,
                    "spare_part_id": item.spare_part_id,
                    "spare_part_code": (
                        item.spare_part_code_snapshot
                    ),
                    "spare_part_name": (
                        item.spare_part_name_snapshot
                    ),
                    "expected_demand": item.expected_demand,
                    "p50": item.p50,
                    "p80": item.p80,
                    "p90": item.p90,
                    "p95": item.p95,
                    "p99": item.p99,
                    "recommended_spare_quantity": (
                        item.recommended_spare_quantity
                    ),
                    "usable_inventory": item.usable_inventory,
                    "net_demand_gap": item.net_demand_gap,
                    "inventory_coverage_rate": (
                        item.inventory_coverage_rate
                    ),
                    "shortage_risk_level": (
                        item.shortage_risk_level.value
                    ),
                    "warnings": item.warning_codes_json,
                }
            )
    return success_response(rows)


@router.get("/{calculation_id}/runs")
def runs(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    rows = list(
        session.scalars(
            select(DemandCalculationRun).where(
                DemandCalculationRun.calculation_id
                == calculation_id
            )
        ).all()
    )
    return success_response(
        [
            {
                "id": row.id,
                "mode": row.run_mode.value,
                "status": row.status.value,
                "attempt_number": row.attempt_number,
                "actual_simulation_runs": (
                    row.actual_simulation_runs
                ),
                "converged": row.converged,
                "stop_reason": row.stop_reason,
            }
            for row in rows
        ]
    )


@router.get("/{calculation_id}/comparison")
def comparison(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
):
    row = calculation_service.get(
        session,
        actor,
        calculation_id,
    )
    return success_response(
        (row.result_summary_json or {}).get(
            "comparison"
        )
    )


@router.get("/{calculation_id}/export")
def export(
    calculation_id: int,
    session: SessionDep,
    actor: ActorDep,
    format: str = Query(
        "xlsx",
        pattern="^(xlsx|json)$",
    ),
):
    calculation = session.scalar(
        select(DemandCalculation)
        .where(
            DemandCalculation.id == calculation_id,
            DemandCalculation.tenant_id
            == actor.tenant_id,
        )
        .options(
            selectinload(
                DemandCalculation.runs
            ).selectinload(
                DemandCalculationRun.item_results
            )
        )
    )
    if calculation is None:
        raise NotFoundError(
            "demand_calculation",
            calculation_id,
        )
    if format == "json":
        data = export_calculation_json(
            calculation,
            calculation.runs,
        )
        return Response(
            data,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    "attachment; "
                    f'filename="{calculation.calculation_code}.json"'
                )
            },
        )
    data = export_calculation_excel(
        calculation,
        calculation.runs,
    )
    return Response(
        data,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                "attachment; "
                f'filename="{calculation.calculation_code}.xlsx"'
            )
        },
    )

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DemandCalculation,
    DemandCalculationRun,
    DemandRunContribution,
    DemandRunItemResult,
)
from app.models.enums import DemandExecutionMode
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class DemandCalculationRepository(
    BaseRepository[DemandCalculation]
):
    def __init__(self) -> None:
        super().__init__(DemandCalculation)

    def get_by_idempotency_key(
        self,
        session: Session,
        tenant_id: str,
        key: str,
    ) -> DemandCalculation | None:
        return session.scalar(
            select(DemandCalculation)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandCalculation.tenant_id == tenant_id,
                DemandCalculation.idempotency_key == key,
            )
        )

    def get_full(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> DemandCalculation | None:
        return session.scalar(
            select(DemandCalculation)
            .options(
                tenant_loader_criteria(tenant_id),
                selectinload(
                    DemandCalculation.runs
                ).selectinload(
                    DemandCalculationRun.item_results
                ),
                selectinload(
                    DemandCalculation.runs
                ).selectinload(
                    DemandCalculationRun.contributions
                ),
            )
            .execution_options(populate_existing=True)
            .where(
                DemandCalculation.tenant_id == tenant_id,
                DemandCalculation.id == identifier,
            )
        )


class DemandCalculationRunRepository(
    BaseRepository[DemandCalculationRun]
):
    def __init__(self) -> None:
        super().__init__(DemandCalculationRun)

    def list_for_calculation(
        self,
        session: Session,
        tenant_id: str,
        calculation_id: int,
    ) -> list[DemandCalculationRun]:
        return list(
            session.scalars(
                select(DemandCalculationRun)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    DemandCalculationRun.tenant_id == tenant_id,
                    DemandCalculationRun.calculation_id
                    == calculation_id,
                )
                .order_by(
                    DemandCalculationRun.attempt_number,
                    DemandCalculationRun.id,
                )
            ).all()
        )

    def next_attempt(
        self,
        session: Session,
        tenant_id: str,
        calculation_id: int,
        mode: DemandExecutionMode,
    ) -> int:
        current = session.scalar(
            select(
                func.max(
                    DemandCalculationRun.attempt_number
                )
            ).where(
                DemandCalculationRun.tenant_id
                == tenant_id,
                DemandCalculationRun.calculation_id
                == calculation_id,
                DemandCalculationRun.run_mode == mode,
            )
        )
        return int(current or 0) + 1



class DemandRunItemResultRepository(
    BaseRepository[DemandRunItemResult]
):
    def __init__(self) -> None:
        super().__init__(DemandRunItemResult)

    def list_for_run(
        self,
        session: Session,
        tenant_id: str,
        run_id: int,
    ) -> list[DemandRunItemResult]:
        return list(
            session.scalars(
                select(DemandRunItemResult)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    DemandRunItemResult.tenant_id == tenant_id,
                    DemandRunItemResult.calculation_run_id == run_id,
                )
                .order_by(
                    DemandRunItemResult.spare_part_code_snapshot,
                    DemandRunItemResult.id,
                )
            ).all()
        )


class DemandRunContributionRepository(
    BaseRepository[DemandRunContribution]
):
    def __init__(self) -> None:
        super().__init__(DemandRunContribution)

    def list_for_run(
        self,
        session: Session,
        tenant_id: str,
        run_id: int,
    ) -> list[DemandRunContribution]:
        return list(
            session.scalars(
                select(DemandRunContribution)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    DemandRunContribution.tenant_id == tenant_id,
                    DemandRunContribution.calculation_run_id == run_id,
                )
                .order_by(
                    DemandRunContribution.spare_part_id,
                    DemandRunContribution.id,
                )
            ).all()
        )

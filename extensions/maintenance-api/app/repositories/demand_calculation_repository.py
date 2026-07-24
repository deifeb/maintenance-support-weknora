from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import DemandCalculation, DemandCalculationRun, DemandRunItemResult
from app.repositories.base import BaseRepository


class DemandCalculationRepository(BaseRepository[DemandCalculation]):
    def __init__(self) -> None:
        super().__init__(DemandCalculation)

    def get_by_idempotency_key(self, session: Session, key: str) -> DemandCalculation | None:
        return session.scalar(
            select(DemandCalculation).where(DemandCalculation.idempotency_key == key)
        )

    def get_full(self, session: Session, identifier: int) -> DemandCalculation | None:
        return session.scalar(
            select(DemandCalculation)
            .where(DemandCalculation.id == identifier)
            .options(
                selectinload(DemandCalculation.runs).selectinload(DemandCalculationRun.item_results)
            )
        )

    def list_item_results(self, session: Session, run_id: int) -> list[DemandRunItemResult]:
        return list(
            session.scalars(
                select(DemandRunItemResult)
                .where(DemandRunItemResult.calculation_run_id == run_id)
                .order_by(DemandRunItemResult.spare_part_code_snapshot)
            ).all()
        )

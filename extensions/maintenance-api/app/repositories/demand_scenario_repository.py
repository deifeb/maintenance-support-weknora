from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DemandFleetGroup,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.repositories.base import BaseRepository


class DemandScenarioTemplateRepository(BaseRepository[DemandScenarioTemplate]):
    def __init__(self) -> None:
        super().__init__(DemandScenarioTemplate)

    def count_references(self, session: Session, identifier: int) -> int:
        return (
            session.query(DemandScenarioVersion)
            .filter(DemandScenarioVersion.scenario_template_id == identifier)
            .count()
        )


class DemandScenarioVersionRepository(BaseRepository[DemandScenarioVersion]):
    def __init__(self) -> None:
        super().__init__(DemandScenarioVersion)

    def get_full(self, session: Session, identifier: int) -> DemandScenarioVersion | None:
        stmt = (
            select(DemandScenarioVersion)
            .where(DemandScenarioVersion.id == identifier)
            .options(
                selectinload(DemandScenarioVersion.stages).selectinload(
                    DemandScenarioStage.fleet_usages
                ),
                selectinload(DemandScenarioVersion.stages).selectinload(DemandScenarioStage.shocks),
                selectinload(DemandScenarioVersion.fleet_groups).selectinload(
                    DemandFleetGroup.age_groups
                ),
                selectinload(DemandScenarioVersion.fleet_groups).selectinload(
                    DemandFleetGroup.stage_usages
                ),
                selectinload(DemandScenarioVersion.overrides),
            )
        )
        return session.scalar(stmt)

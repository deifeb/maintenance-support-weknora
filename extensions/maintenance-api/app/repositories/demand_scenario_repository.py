from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DemandAgeGroup,
    DemandCommonShockRule,
    DemandFleetGroup,
    DemandParameterOverride,
    DemandScenarioStage,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    DemandStageFleetUsage,
)
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class DemandScenarioTemplateRepository(
    BaseRepository[DemandScenarioTemplate]
):
    def __init__(self) -> None:
        super().__init__(DemandScenarioTemplate)

    def count_references(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(DemandScenarioVersion)
                .where(
                    DemandScenarioVersion.tenant_id == tenant_id,
                    DemandScenarioVersion.scenario_template_id
                    == identifier,
                )
            )
            or 0
        )


class DemandScenarioVersionRepository(
    BaseRepository[DemandScenarioVersion]
):
    def __init__(self) -> None:
        super().__init__(DemandScenarioVersion)

    def get_by_business_key(
        self,
        session: Session,
        tenant_id: str,
        scenario_template_id: int,
        version_code: str,
    ) -> DemandScenarioVersion | None:
        return session.scalar(
            select(DemandScenarioVersion)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandScenarioVersion.tenant_id == tenant_id,
                DemandScenarioVersion.scenario_template_id
                == scenario_template_id,
                DemandScenarioVersion.version_code == version_code,
            )
        )

    def list_for_template(
        self,
        session: Session,
        tenant_id: str,
        scenario_template_id: int,
    ) -> list[DemandScenarioVersion]:
        return list(
            session.scalars(
                select(DemandScenarioVersion)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    DemandScenarioVersion.tenant_id == tenant_id,
                    DemandScenarioVersion.scenario_template_id
                    == scenario_template_id,
                )
                .order_by(
                    DemandScenarioVersion.created_at.desc(),
                    DemandScenarioVersion.id.desc(),
                )
            ).all()
        )

    def get_full(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> DemandScenarioVersion | None:
        stmt = (
            select(DemandScenarioVersion)
            .options(
                tenant_loader_criteria(tenant_id),
                selectinload(
                    DemandScenarioVersion.stages
                ).selectinload(
                    DemandScenarioStage.fleet_usages
                ),
                selectinload(
                    DemandScenarioVersion.stages
                ).selectinload(
                    DemandScenarioStage.shocks
                ),
                selectinload(
                    DemandScenarioVersion.fleet_groups
                ).selectinload(
                    DemandFleetGroup.age_groups
                ),
                selectinload(
                    DemandScenarioVersion.fleet_groups
                ).selectinload(
                    DemandFleetGroup.stage_usages
                ),
                selectinload(
                    DemandScenarioVersion.overrides
                ),
            )
            .execution_options(populate_existing=True)
            .where(
                DemandScenarioVersion.tenant_id == tenant_id,
                DemandScenarioVersion.id == identifier,
            )
        )
        return session.scalar(stmt)


class DemandScenarioStageRepository(
    BaseRepository[DemandScenarioStage]
):
    def __init__(self) -> None:
        super().__init__(DemandScenarioStage)


class DemandFleetGroupRepository(
    BaseRepository[DemandFleetGroup]
):
    def __init__(self) -> None:
        super().__init__(DemandFleetGroup)


class DemandAgeGroupRepository(
    BaseRepository[DemandAgeGroup]
):
    def __init__(self) -> None:
        super().__init__(DemandAgeGroup)


class DemandStageFleetUsageRepository(
    BaseRepository[DemandStageFleetUsage]
):
    def __init__(self) -> None:
        super().__init__(DemandStageFleetUsage)


class DemandParameterOverrideRepository(
    BaseRepository[DemandParameterOverride]
):
    def __init__(self) -> None:
        super().__init__(DemandParameterOverride)


class DemandCommonShockRepository(
    BaseRepository[DemandCommonShockRule]
):
    def __init__(self) -> None:
        super().__init__(DemandCommonShockRule)

from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import RepairProfile
from app.repositories.base import BaseRepository, tenant_loader_criteria


class RepairRepository(BaseRepository[RepairProfile]):
    def __init__(self) -> None:
        super().__init__(RepairProfile)

    def find_overlap(
        self,
        session: Session,
        tenant_id: str,
        *,
        spare_part_id: int,
        configuration_version_id: int | None,
        maintenance_level: str | None,
        valid_from: date | None,
        valid_to: date | None,
        exclude_id: int | None = None,
    ) -> RepairProfile | None:
        start = valid_from or date.min
        end = valid_to or date.max
        stmt = (
            select(RepairProfile)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                RepairProfile.tenant_id == tenant_id,
                RepairProfile.spare_part_id == spare_part_id,
                RepairProfile.configuration_version_id.is_(
                    configuration_version_id
                )
                if configuration_version_id is None
                else RepairProfile.configuration_version_id
                == configuration_version_id,
                RepairProfile.maintenance_level.is_(maintenance_level)
                if maintenance_level is None
                else RepairProfile.maintenance_level
                == maintenance_level,
                RepairProfile.is_active.is_(True),
                and_(
                    or_(
                        RepairProfile.valid_to.is_(None),
                        RepairProfile.valid_to > start,
                    ),
                    or_(
                        RepairProfile.valid_from.is_(None),
                        RepairProfile.valid_from < end,
                    ),
                ),
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(RepairProfile.id != exclude_id)
        return session.scalar(stmt.limit(1))

    def select_candidates(
        self,
        session: Session,
        tenant_id: str,
        spare_part_id: int,
        configuration_version_id: int | None,
        maintenance_level: str | None,
        valid_at: date,
    ) -> list[RepairProfile]:
        stmt = (
            select(RepairProfile)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                RepairProfile.tenant_id == tenant_id,
                RepairProfile.spare_part_id == spare_part_id,
                RepairProfile.is_active.is_(True),
                or_(
                    RepairProfile.valid_from.is_(None),
                    RepairProfile.valid_from <= valid_at,
                ),
                or_(
                    RepairProfile.valid_to.is_(None),
                    RepairProfile.valid_to > valid_at,
                ),
            )
        )
        rows = list(session.scalars(stmt).all())
        return sorted(
            rows,
            key=lambda row: (
                row.configuration_version_id
                != configuration_version_id,
                row.configuration_version_id is None,
                row.maintenance_level != maintenance_level,
                row.maintenance_level is None,
                row.profile_code,
            ),
        )

    def count_references(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> int:
        from app.models import (
            DemandParameterOverride,
            DemandRunItemResult,
        )

        counts = (
            session.scalar(
                select(func.count())
                .select_from(DemandParameterOverride)
                .where(
                    DemandParameterOverride.tenant_id == tenant_id,
                    DemandParameterOverride.repair_profile_id
                    == identifier,
                )
            ),
            session.scalar(
                select(func.count())
                .select_from(DemandRunItemResult)
                .where(
                    DemandRunItemResult.tenant_id == tenant_id,
                    DemandRunItemResult.selected_repair_profile_id
                    == identifier,
                )
            ),
        )
        return sum(int(value or 0) for value in counts)

    def list_active_for_selection(
        self,
        session: Session,
        tenant_id: str,
        spare_part_id: int,
        valid_at: date,
    ) -> list[RepairProfile]:
        return list(
            session.scalars(
                select(RepairProfile)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .execution_options(
                    populate_existing=True
                )
                .where(
                    RepairProfile.tenant_id
                    == tenant_id,
                    RepairProfile.spare_part_id
                    == spare_part_id,
                    RepairProfile.is_active.is_(
                        True
                    ),
                    or_(
                        RepairProfile.valid_from.is_(
                            None
                        ),
                        RepairProfile.valid_from
                        <= valid_at,
                    ),
                    or_(
                        RepairProfile.valid_to.is_(
                            None
                        ),
                        RepairProfile.valid_to
                        > valid_at,
                    ),
                )
            ).all()
        )

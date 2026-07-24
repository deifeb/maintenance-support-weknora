from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import RepairProfile
from app.repositories.base import BaseRepository


class RepairRepository(BaseRepository[RepairProfile]):
    def __init__(self) -> None:
        super().__init__(RepairProfile)

    def find_overlap(
        self,
        session: Session,
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
        stmt = select(RepairProfile).where(
            RepairProfile.spare_part_id == spare_part_id,
            RepairProfile.configuration_version_id.is_(configuration_version_id)
            if configuration_version_id is None
            else RepairProfile.configuration_version_id == configuration_version_id,
            RepairProfile.maintenance_level.is_(maintenance_level)
            if maintenance_level is None
            else RepairProfile.maintenance_level == maintenance_level,
            RepairProfile.is_active.is_(True),
            and_(
                or_(RepairProfile.valid_to.is_(None), RepairProfile.valid_to > start),
                or_(RepairProfile.valid_from.is_(None), RepairProfile.valid_from < end),
            ),
        )
        if exclude_id is not None:
            stmt = stmt.where(RepairProfile.id != exclude_id)
        return session.scalar(stmt.limit(1))

    def select_candidates(
        self,
        session: Session,
        spare_part_id: int,
        configuration_version_id: int | None,
        maintenance_level: str | None,
        valid_at: date,
    ) -> list[RepairProfile]:
        stmt = select(RepairProfile).where(
            RepairProfile.spare_part_id == spare_part_id,
            RepairProfile.is_active.is_(True),
            or_(RepairProfile.valid_from.is_(None), RepairProfile.valid_from <= valid_at),
            or_(RepairProfile.valid_to.is_(None), RepairProfile.valid_to > valid_at),
        )
        rows = list(session.scalars(stmt).all())
        return sorted(
            rows,
            key=lambda row: (
                row.configuration_version_id != configuration_version_id,
                row.configuration_version_id is None,
                row.maintenance_level != maintenance_level,
                row.maintenance_level is None,
                row.profile_code,
            ),
        )

    def count_references(self, session: Session, identifier: int) -> int:
        from app.models import DemandParameterOverride, DemandRunItemResult

        return sum(
            (
                session.query(DemandParameterOverride)
                .filter(DemandParameterOverride.repair_profile_id == identifier)
                .count(),
                session.query(DemandRunItemResult)
                .filter(DemandRunItemResult.selected_repair_profile_id == identifier)
                .count(),
            )
        )

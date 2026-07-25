from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import ReliabilityProfile
from app.models.enums import ReliabilityModelType
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class ReliabilityRepository(BaseRepository[ReliabilityProfile]):
    def __init__(self) -> None:
        super().__init__(ReliabilityProfile)

    def get_by_profile_code(
        self,
        session: Session,
        tenant_id: str,
        profile_code: str,
    ) -> ReliabilityProfile | None:
        return self.get_by_code(
            session,
            tenant_id,
            profile_code,
            "profile_code",
        )

    def find_overlap(
        self,
        session: Session,
        tenant_id: str,
        *,
        spare_part_id: int,
        configuration_version_id: int | None,
        model_type: ReliabilityModelType,
        valid_from: date | None,
        valid_to: date | None,
        exclude_id: int | None = None,
    ) -> ReliabilityProfile | None:
        start = valid_from or date.min
        end = valid_to or date.max
        stmt = (
            select(ReliabilityProfile)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                ReliabilityProfile.tenant_id == tenant_id,
                ReliabilityProfile.spare_part_id == spare_part_id,
                ReliabilityProfile.configuration_version_id.is_(
                    configuration_version_id
                )
                if configuration_version_id is None
                else ReliabilityProfile.configuration_version_id
                == configuration_version_id,
                ReliabilityProfile.model_type == model_type,
                ReliabilityProfile.is_active.is_(True),
                and_(
                    or_(
                        ReliabilityProfile.valid_to.is_(None),
                        ReliabilityProfile.valid_to > start,
                    ),
                    or_(
                        ReliabilityProfile.valid_from.is_(None),
                        ReliabilityProfile.valid_from < end,
                    ),
                ),
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(
                ReliabilityProfile.id != exclude_id
            )
        return session.scalar(stmt.limit(1))

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import ConfigurationVersion, SparePart
from app.repositories import ReliabilityRepository
from app.schemas.reliability import (
    ReliabilityProfileCreate,
    ReliabilityProfileRead,
    ReliabilityProfileUpdate,
)
from app.services.base import CrudService


class ReliabilityService(CrudService):
    def __init__(self) -> None:
        self.reliability_repository = ReliabilityRepository()
        super().__init__(
            self.reliability_repository,
            resource_name="reliability_profile",
            read_schema=ReliabilityProfileRead,
            code_field="profile_code",
            keyword_fields=("profile_code", "data_source_reference"),
        )

    def _validate_references(self, session: Session, spare_part_id: int, configuration_version_id: int | None) -> None:
        if session.get(SparePart, spare_part_id) is None:
            raise NotFoundError("spare_part", spare_part_id)
        if configuration_version_id is not None and session.get(ConfigurationVersion, configuration_version_id) is None:
            raise NotFoundError("configuration_version", configuration_version_id)

    def _validate_overlap(self, session: Session, payload: ReliabilityProfileCreate, exclude_id: int | None = None) -> None:
        if payload.is_active and self.reliability_repository.find_overlap(
            session,
            spare_part_id=payload.spare_part_id,
            configuration_version_id=payload.configuration_version_id,
            model_type=payload.model_type,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            exclude_id=exclude_id,
        ):
            raise ConflictError("active reliability profile validity interval overlaps an existing profile")

    def create_profile(self, session: Session, payload: ReliabilityProfileCreate, *, commit: bool = True):
        self._validate_references(session, payload.spare_part_id, payload.configuration_version_id)
        self._validate_overlap(session, payload)
        return super().create(session, payload, commit=commit)

    def update_profile(self, session: Session, identifier: int, payload: ReliabilityProfileUpdate):
        current = self.get(session, identifier)
        merged = ReliabilityProfileCreate.model_validate(
            {
                **ReliabilityProfileRead.model_validate(current).model_dump(exclude={"id", "created_at", "updated_at"}),
                **payload.model_dump(exclude_unset=True),
            }
        )
        self._validate_references(session, merged.spare_part_id, merged.configuration_version_id)
        self._validate_overlap(session, merged, exclude_id=identifier)
        return super().update(session, identifier, payload)


reliability_service = ReliabilityService()

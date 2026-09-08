from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories import (
    ConfigurationRepository,
    ReliabilityRepository,
    SparePartRepository,
)
from app.schemas.reliability import (
    ReliabilityProfileCreate,
    ReliabilityProfileRead,
    ReliabilityProfileUpdate,
)
from app.security.actor import ActorContext
from app.services.base import CrudService


class ReliabilityService(CrudService):
    def __init__(self) -> None:
        self.reliability_repository = ReliabilityRepository()
        self.spare_part_repository = SparePartRepository()
        self.configuration_repository = ConfigurationRepository()
        super().__init__(
            self.reliability_repository,
            resource_name="reliability_profile",
            read_schema=ReliabilityProfileRead,
            code_field="profile_code",
            keyword_fields=(
                "profile_code",
                "data_source_reference",
            ),
        )

    def _validate_references(
        self,
        session: Session,
        actor: ActorContext,
        spare_part_id: int,
        configuration_version_id: int | None,
    ) -> None:
        if self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            spare_part_id,
        ) is None:
            raise NotFoundError(
                "spare_part",
                spare_part_id,
            )
        if (
            configuration_version_id is not None
            and self.configuration_repository.get_by_id(
                session,
                actor.tenant_id,
                configuration_version_id,
            )
            is None
        ):
            raise NotFoundError(
                "configuration_version",
                configuration_version_id,
            )

    def _validate_overlap(
        self,
        session: Session,
        actor: ActorContext,
        payload: ReliabilityProfileCreate,
        exclude_id: int | None = None,
    ) -> None:
        if (
            payload.is_active
            and self.reliability_repository.find_overlap(
                session,
                actor.tenant_id,
                spare_part_id=payload.spare_part_id,
                configuration_version_id=(
                    payload.configuration_version_id
                ),
                model_type=payload.model_type,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
                exclude_id=exclude_id,
            )
        ):
            raise ConflictError(
                "active reliability profile validity interval "
                "overlaps an existing profile"
            )

    def create_profile(
        self,
        session: Session,
        actor: ActorContext,
        payload: ReliabilityProfileCreate,
        *,
        commit: bool = True,
    ):
        self._validate_references(
            session,
            actor,
            payload.spare_part_id,
            payload.configuration_version_id,
        )
        self._validate_overlap(
            session,
            actor,
            payload,
        )
        return super().create(
            session,
            actor,
            payload,
            commit=commit,
        )

    def update_profile(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: ReliabilityProfileUpdate,
    ):
        current = self.get(
            session,
            actor,
            identifier,
        )
        merged = ReliabilityProfileCreate.model_validate(
            {
                **ReliabilityProfileRead.model_validate(
                    current
                ).model_dump(
                    exclude={
                        "id",
                        "created_at",
                        "updated_at",
                    }
                ),
                **payload.model_dump(exclude_unset=True),
            }
        )
        self._validate_references(
            session,
            actor,
            merged.spare_part_id,
            merged.configuration_version_id,
        )
        self._validate_overlap(
            session,
            actor,
            merged,
            exclude_id=identifier,
        )
        return super().update(
            session,
            actor,
            identifier,
            payload,
        )


reliability_service = ReliabilityService()

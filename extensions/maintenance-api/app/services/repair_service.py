from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import RepairProfile
from app.repositories import (
    ConfigurationRepository,
    RepairRepository,
    SparePartRepository,
)
from app.schemas.repair import (
    RepairProfileCreate,
    RepairProfileRead,
    RepairProfileUpdate,
)
from app.security.actor import ActorContext
from app.services.base import CrudService


class RepairService(CrudService):
    def __init__(self) -> None:
        self.repair_repository = RepairRepository()
        self.spare_part_repository = SparePartRepository()
        self.configuration_repository = ConfigurationRepository()
        super().__init__(
            self.repair_repository,
            resource_name="repair_profile",
            read_schema=RepairProfileRead,
            code_field="profile_code",
            keyword_fields=(
                "profile_code",
                "profile_name",
            ),
        )

    def _validate_references(
        self,
        session: Session,
        actor: ActorContext,
        payload: RepairProfileCreate,
    ) -> None:
        if self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            payload.spare_part_id,
        ) is None:
            raise NotFoundError(
                "spare_part",
                payload.spare_part_id,
            )
        if (
            payload.configuration_version_id is not None
            and self.configuration_repository.get_by_id(
                session,
                actor.tenant_id,
                payload.configuration_version_id,
            )
            is None
        ):
            raise NotFoundError(
                "configuration_version",
                payload.configuration_version_id,
            )

    def _validate_overlap(
        self,
        session: Session,
        actor: ActorContext,
        payload: RepairProfileCreate,
        exclude_id: int | None = None,
    ) -> None:
        if (
            payload.is_active
            and self.repair_repository.find_overlap(
                session,
                actor.tenant_id,
                spare_part_id=payload.spare_part_id,
                configuration_version_id=(
                    payload.configuration_version_id
                ),
                maintenance_level=payload.maintenance_level,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
                exclude_id=exclude_id,
            )
        ):
            raise ConflictError(
                "active repair profile validity interval "
                "overlaps an existing profile"
            )

    def create_profile(
        self,
        session: Session,
        actor: ActorContext,
        payload: RepairProfileCreate,
    ) -> RepairProfile:
        self._validate_references(
            session,
            actor,
            payload,
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
        )

    def update_profile(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: RepairProfileUpdate,
    ) -> RepairProfile:
        current = self.get(
            session,
            actor,
            identifier,
        )
        merged = RepairProfileCreate.model_validate(
            {
                **RepairProfileRead.model_validate(
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
            merged,
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


repair_service = RepairService()

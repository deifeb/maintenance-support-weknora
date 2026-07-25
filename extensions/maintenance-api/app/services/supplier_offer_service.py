from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.repositories import (
    SparePartRepository,
    SupplierOfferRepository,
    SupplierRepository,
)
from app.schemas.supplier import (
    SupplierOfferCreate,
    SupplierOfferRead,
    SupplierOfferUpdate,
)
from app.security.actor import ActorContext
from app.services.base import CrudService


class SupplierOfferService(CrudService):
    def __init__(self) -> None:
        self.offer_repository = SupplierOfferRepository()
        self.supplier_repository = SupplierRepository()
        self.spare_part_repository = SparePartRepository()
        super().__init__(
            self.offer_repository,
            resource_name="supplier_offer",
            read_schema=SupplierOfferRead,
            code_field="offer_code",
            keyword_fields=(
                "offer_code",
                "quality_level",
            ),
        )

    def _validate_references(
        self,
        session: Session,
        actor: ActorContext,
        supplier_id: int,
        spare_part_id: int,
    ) -> None:
        if self.supplier_repository.get_by_id(
            session,
            actor.tenant_id,
            supplier_id,
        ) is None:
            raise NotFoundError(
                "supplier",
                supplier_id,
            )
        if self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            spare_part_id,
        ) is None:
            raise NotFoundError(
                "spare_part",
                spare_part_id,
            )

    def _validate_preferred(
        self,
        session: Session,
        actor: ActorContext,
        payload: SupplierOfferCreate,
        exclude_id: int | None = None,
    ) -> None:
        if (
            payload.is_active
            and payload.is_preferred
            and self.offer_repository.find_preferred_overlap(
                session,
                actor.tenant_id,
                spare_part_id=payload.spare_part_id,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
                exclude_id=exclude_id,
            )
        ):
            raise ConflictError(
                "preferred supplier offer validity interval "
                "overlaps an existing preferred offer"
            )

    def create_offer(
        self,
        session: Session,
        actor: ActorContext,
        payload: SupplierOfferCreate,
        *,
        commit: bool = True,
    ):
        self._validate_references(
            session,
            actor,
            payload.supplier_id,
            payload.spare_part_id,
        )
        self._validate_preferred(
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

    def update_offer(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: SupplierOfferUpdate,
    ):
        current = self.get(
            session,
            actor,
            identifier,
        )
        merged = SupplierOfferCreate.model_validate(
            {
                **SupplierOfferRead.model_validate(
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
            merged.supplier_id,
            merged.spare_part_id,
        )
        self._validate_preferred(
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

    def delete(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> None:
        self.get(
            session,
            actor,
            identifier,
        )
        raise ConflictError(
            "supplier offers are historical records "
            "and cannot be physically deleted"
        )


supplier_offer_service = SupplierOfferService()

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import SparePart, Supplier
from app.repositories import SupplierOfferRepository
from app.schemas.supplier import SupplierOfferCreate, SupplierOfferRead, SupplierOfferUpdate
from app.services.base import CrudService


class SupplierOfferService(CrudService):
    def __init__(self) -> None:
        self.offer_repository = SupplierOfferRepository()
        super().__init__(
            self.offer_repository,
            resource_name="supplier_offer",
            read_schema=SupplierOfferRead,
            code_field="offer_code",
            keyword_fields=("offer_code", "quality_level"),
        )

    def _validate_references(self, session: Session, supplier_id: int, spare_part_id: int) -> None:
        if session.get(Supplier, supplier_id) is None:
            raise NotFoundError("supplier", supplier_id)
        if session.get(SparePart, spare_part_id) is None:
            raise NotFoundError("spare_part", spare_part_id)

    def _validate_preferred(self, session: Session, payload: SupplierOfferCreate, exclude_id: int | None = None) -> None:
        if payload.is_active and payload.is_preferred and self.offer_repository.find_preferred_overlap(
            session,
            spare_part_id=payload.spare_part_id,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            exclude_id=exclude_id,
        ):
            raise ConflictError("preferred supplier offer validity interval overlaps an existing preferred offer")

    def create_offer(self, session: Session, payload: SupplierOfferCreate, *, commit: bool = True):
        self._validate_references(session, payload.supplier_id, payload.spare_part_id)
        self._validate_preferred(session, payload)
        return super().create(session, payload, commit=commit)

    def update_offer(self, session: Session, identifier: int, payload: SupplierOfferUpdate):
        current = self.get(session, identifier)
        merged = SupplierOfferCreate.model_validate(
            {
                **SupplierOfferRead.model_validate(current).model_dump(exclude={"id", "created_at", "updated_at"}),
                **payload.model_dump(exclude_unset=True),
            }
        )
        self._validate_references(session, merged.supplier_id, merged.spare_part_id)
        self._validate_preferred(session, merged, exclude_id=identifier)
        return super().update(session, identifier, payload)

    def delete(self, session: Session, identifier: int) -> None:
        raise ConflictError("supplier offers are historical records and cannot be physically deleted")


supplier_offer_service = SupplierOfferService()

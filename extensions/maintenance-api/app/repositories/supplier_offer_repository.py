from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import SupplierOffer
from app.repositories.base import BaseRepository


class SupplierOfferRepository(BaseRepository[SupplierOffer]):
    def __init__(self) -> None:
        super().__init__(SupplierOffer)

    def get_by_offer_code(self, session: Session, offer_code: str) -> SupplierOffer | None:
        return self.get_by_code(session, offer_code, "offer_code")

    def find_preferred_overlap(
        self,
        session: Session,
        *,
        spare_part_id: int,
        valid_from: date | None,
        valid_to: date | None,
        exclude_id: int | None = None,
    ) -> SupplierOffer | None:
        start = valid_from or date.min
        end = valid_to or date.max
        stmt = select(SupplierOffer).where(
            SupplierOffer.spare_part_id == spare_part_id,
            SupplierOffer.is_preferred.is_(True),
            SupplierOffer.is_active.is_(True),
            and_(
                or_(SupplierOffer.valid_to.is_(None), SupplierOffer.valid_to > start),
                or_(SupplierOffer.valid_from.is_(None), SupplierOffer.valid_from < end),
            ),
        )
        if exclude_id is not None:
            stmt = stmt.where(SupplierOffer.id != exclude_id)
        return session.scalar(stmt.limit(1))

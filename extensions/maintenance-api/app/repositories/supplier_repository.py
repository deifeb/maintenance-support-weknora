from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Supplier, SupplierOffer
from app.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self) -> None:
        super().__init__(Supplier)

    def count_references(self, session: Session, identifier: int) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(SupplierOffer)
                .where(SupplierOffer.supplier_id == identifier)
            )
            or 0
        )

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConfigurationItem, Part
from app.repositories.base import BaseRepository


class PartRepository(BaseRepository[Part]):
    def __init__(self) -> None:
        super().__init__(Part)

    def count_references(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ConfigurationItem)
                .where(
                    ConfigurationItem.tenant_id == tenant_id,
                    ConfigurationItem.part_id == identifier,
                )
            )
            or 0
        )

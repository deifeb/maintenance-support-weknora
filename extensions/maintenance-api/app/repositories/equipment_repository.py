from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConfigurationVersion, EquipmentModel
from app.repositories.base import BaseRepository


class EquipmentRepository(BaseRepository[EquipmentModel]):
    def __init__(self) -> None:
        super().__init__(EquipmentModel)

    def count_references(self, session: Session, identifier: int) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ConfigurationVersion)
                .where(ConfigurationVersion.equipment_model_id == identifier)
            )
            or 0
        )

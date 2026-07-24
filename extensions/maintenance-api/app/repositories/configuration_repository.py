from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ConfigurationItem, ConfigurationVersion, ReliabilityProfile
from app.repositories.base import BaseRepository


class ConfigurationRepository(BaseRepository[ConfigurationVersion]):
    def __init__(self) -> None:
        super().__init__(ConfigurationVersion)

    def get_by_business_key(
        self, session: Session, equipment_model_id: int, version_code: str
    ) -> ConfigurationVersion | None:
        return session.scalar(
            select(ConfigurationVersion).where(
                ConfigurationVersion.equipment_model_id == equipment_model_id,
                ConfigurationVersion.version_code == version_code,
            )
        )

    def get_with_items(self, session: Session, identifier: int) -> ConfigurationVersion | None:
        return session.scalar(
            select(ConfigurationVersion)
            .options(selectinload(ConfigurationVersion.items))
            .where(ConfigurationVersion.id == identifier)
        )

    def count_references(self, session: Session, identifier: int) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ReliabilityProfile)
                .where(ReliabilityProfile.configuration_version_id == identifier)
            )
            or 0
        )


class ConfigurationItemRepository(BaseRepository[ConfigurationItem]):
    def __init__(self) -> None:
        super().__init__(ConfigurationItem)

    def get_by_business_key(
        self, session: Session, configuration_version_id: int, item_code: str
    ) -> ConfigurationItem | None:
        return session.scalar(
            select(ConfigurationItem).where(
                ConfigurationItem.configuration_version_id == configuration_version_id,
                ConfigurationItem.item_code == item_code,
            )
        )

    def list_for_version(
        self, session: Session, configuration_version_id: int
    ) -> list[ConfigurationItem]:
        return list(
            session.scalars(
                select(ConfigurationItem)
                .where(ConfigurationItem.configuration_version_id == configuration_version_id)
                .order_by(ConfigurationItem.sort_order, ConfigurationItem.id)
            ).all()
        )

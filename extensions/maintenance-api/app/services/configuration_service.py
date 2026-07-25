from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    ConflictError,
    NotFoundError,
    ResourceInUseError,
)
from app.models import ConfigurationItem, ConfigurationVersion
from app.models.enums import ConfigurationStatus
from app.repositories import (
    ConfigurationItemRepository,
    ConfigurationRepository,
    EquipmentRepository,
    PartRepository,
    SparePartRepository,
)
from app.schemas.equipment import (
    ConfigurationCloneRequest,
    ConfigurationItemCreate,
    ConfigurationItemUpdate,
    ConfigurationTree,
    ConfigurationTreeNode,
    ConfigurationVersionCreate,
    ConfigurationVersionRead,
    ConfigurationVersionUpdate,
)
from app.security.actor import ActorContext
from app.services.base import CrudService


class ConfigurationService(CrudService):
    def __init__(self) -> None:
        self.configuration_repository = ConfigurationRepository()
        self.item_repository = ConfigurationItemRepository()
        self.equipment_repository = EquipmentRepository()
        self.part_repository = PartRepository()
        self.spare_part_repository = SparePartRepository()
        super().__init__(
            self.configuration_repository,
            resource_name="configuration_version",
            read_schema=ConfigurationVersionRead,
            code_field="version_code",
            keyword_fields=("version_code", "version_name"),
        )

    def create_version(
        self,
        session: Session,
        actor: ActorContext,
        payload: ConfigurationVersionCreate,
        *,
        commit: bool = True,
    ) -> ConfigurationVersion:
        equipment = self.equipment_repository.get_by_id(
            session,
            actor.tenant_id,
            payload.equipment_model_id,
        )
        if equipment is None:
            raise NotFoundError(
                "equipment_model",
                payload.equipment_model_id,
            )
        if self.configuration_repository.get_by_business_key(
            session,
            actor.tenant_id,
            payload.equipment_model_id,
            payload.version_code,
        ):
            raise ConflictError(
                "configuration version already exists for equipment model",
                details={
                    "equipment_model_id": payload.equipment_model_id,
                    "version_code": payload.version_code,
                },
            )
        if payload.status != ConfigurationStatus.DRAFT:
            raise BusinessValidationError(
                "new configuration versions must start as DRAFT"
            )
        instance = self.configuration_repository.create(
            session,
            actor.tenant_id,
            payload.model_dump(),
        )
        if commit:
            self._commit(session)
            session.refresh(instance)
        return instance

    def update_version(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: ConfigurationVersionUpdate,
    ) -> ConfigurationVersion:
        version = self.get(session, actor, identifier)
        if version.status != ConfigurationStatus.DRAFT:
            raise ConflictError(
                "only DRAFT configuration versions can be edited"
            )
        data = payload.model_dump(exclude_unset=True)
        effective = data.get(
            "effective_date",
            version.effective_date,
        )
        expiry = data.get(
            "expiry_date",
            version.expiry_date,
        )
        if effective and expiry and expiry <= effective:
            raise BusinessValidationError(
                "expiry_date must be later than effective_date"
            )
        self.configuration_repository.update(
            session,
            actor.tenant_id,
            version,
            data,
        )
        self._commit(session)
        session.refresh(version)
        return version

    def _validate_item_references(
        self,
        session: Session,
        actor: ActorContext,
        *,
        version: ConfigurationVersion,
        part_id: int,
        spare_part_id: int | None,
        parent_item_id: int | None,
        current_item_id: int | None = None,
    ) -> None:
        part = self.part_repository.get_by_id(
            session,
            actor.tenant_id,
            part_id,
        )
        if part is None:
            raise NotFoundError("part", part_id)

        if (
            spare_part_id is not None
            and self.spare_part_repository.get_by_id(
                session,
                actor.tenant_id,
                spare_part_id,
            )
            is None
        ):
            raise NotFoundError(
                "spare_part",
                spare_part_id,
            )

        if parent_item_id is None:
            return

        parent = self.item_repository.get_by_id(
            session,
            actor.tenant_id,
            parent_item_id,
        )
        if parent is None:
            raise NotFoundError(
                "configuration_item",
                parent_item_id,
            )
        if parent.configuration_version_id != version.id:
            raise BusinessValidationError(
                "parent item must belong to the same "
                "configuration version"
            )

        if current_item_id is not None:
            cursor = parent
            seen: set[int] = set()
            while cursor is not None:
                if cursor.id == current_item_id:
                    raise BusinessValidationError(
                        "configuration hierarchy cannot "
                        "contain a cycle"
                    )
                if cursor.id in seen:
                    raise BusinessValidationError(
                        "configuration hierarchy already "
                        "contains a cycle"
                    )
                seen.add(cursor.id)
                cursor = cursor.parent

    def create_item(
        self,
        session: Session,
        actor: ActorContext,
        payload: ConfigurationItemCreate,
        *,
        commit: bool = True,
    ) -> ConfigurationItem:
        version = self.get(
            session,
            actor,
            payload.configuration_version_id,
        )
        if version.status != ConfigurationStatus.DRAFT:
            raise ConflictError(
                "published or retired configuration items are locked"
            )
        if self.item_repository.get_by_business_key(
            session,
            actor.tenant_id,
            payload.configuration_version_id,
            payload.item_code,
        ):
            raise ConflictError(
                "configuration item code already exists in this version"
            )
        self._validate_item_references(
            session,
            actor,
            version=version,
            part_id=payload.part_id,
            spare_part_id=payload.spare_part_id,
            parent_item_id=payload.parent_item_id,
        )
        item = self.item_repository.create(
            session,
            actor.tenant_id,
            payload.model_dump(),
        )
        if commit:
            self._commit(session)
            session.refresh(item)
        return item

    def update_item(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: ConfigurationItemUpdate,
    ) -> ConfigurationItem:
        item = self.item_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if item is None:
            raise NotFoundError(
                "configuration_item",
                identifier,
            )
        version = self.get(
            session,
            actor,
            item.configuration_version_id,
        )
        if version.status != ConfigurationStatus.DRAFT:
            raise ConflictError(
                "published or retired configuration items are locked"
            )
        data = payload.model_dump(exclude_unset=True)
        self._validate_item_references(
            session,
            actor,
            version=version,
            part_id=data.get("part_id", item.part_id),
            spare_part_id=data.get(
                "spare_part_id",
                item.spare_part_id,
            ),
            parent_item_id=data.get(
                "parent_item_id",
                item.parent_item_id,
            ),
            current_item_id=item.id,
        )
        self.item_repository.update(
            session,
            actor.tenant_id,
            item,
            data,
        )
        self._commit(session)
        session.refresh(item)
        return item

    def delete_item(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> None:
        item = self.item_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if item is None:
            raise NotFoundError(
                "configuration_item",
                identifier,
            )
        version = self.get(
            session,
            actor,
            item.configuration_version_id,
        )
        if version.status != ConfigurationStatus.DRAFT:
            raise ConflictError(
                "published or retired configuration items are locked"
            )
        if item.children:
            raise ResourceInUseError(
                "configuration_item",
                identifier,
            )
        self.item_repository.delete(
            session,
            actor.tenant_id,
            item,
        )
        self._commit(session)

    def publish(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> ConfigurationVersion:
        version = self.configuration_repository.get_with_items(
            session,
            actor.tenant_id,
            identifier,
        )
        if version is None:
            raise NotFoundError(
                "configuration_version",
                identifier,
            )
        if version.status != ConfigurationStatus.DRAFT:
            raise ConflictError(
                "only DRAFT configuration versions can be published"
            )
        if not version.items:
            raise BusinessValidationError(
                "configuration must contain at least one "
                "item before publish"
            )

        for item in version.items:
            if item.part is None:
                raise BusinessValidationError(
                    "configuration references an unavailable part",
                    details={"part_id": item.part_id},
                )
            if not item.part.is_active:
                raise BusinessValidationError(
                    "configuration references an inactive part",
                    details={"part_id": item.part_id},
                )
            if (
                item.spare_part_id is not None
                and item.spare_part is None
            ):
                raise BusinessValidationError(
                    "configuration references an unavailable "
                    "spare part",
                    details={
                        "spare_part_id": item.spare_part_id,
                    },
                )
            if (
                item.spare_part is not None
                and not item.spare_part.is_active
            ):
                raise BusinessValidationError(
                    "configuration references an inactive "
                    "spare part",
                    details={
                        "spare_part_id": item.spare_part_id,
                    },
                )

        if version.is_default:
            session.execute(
                update(ConfigurationVersion)
                .where(
                    ConfigurationVersion.tenant_id
                    == actor.tenant_id,
                    ConfigurationVersion.equipment_model_id
                    == version.equipment_model_id,
                    ConfigurationVersion.id != version.id,
                )
                .values(is_default=False)
            )

        version.status = ConfigurationStatus.PUBLISHED
        self._commit(session)
        session.refresh(version)
        return version

    def retire(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> ConfigurationVersion:
        version = self.get(session, actor, identifier)
        if version.status != ConfigurationStatus.PUBLISHED:
            raise ConflictError(
                "only PUBLISHED configuration versions can be retired"
            )
        version.status = ConfigurationStatus.RETIRED
        version.is_default = False
        version.is_active = False
        self._commit(session)
        session.refresh(version)
        return version

    def clone(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: ConfigurationCloneRequest,
    ) -> ConfigurationVersion:
        source = self.configuration_repository.get_with_items(
            session,
            actor.tenant_id,
            identifier,
        )
        if source is None:
            raise NotFoundError(
                "configuration_version",
                identifier,
            )
        if self.equipment_repository.get_by_id(
            session,
            actor.tenant_id,
            source.equipment_model_id,
        ) is None:
            raise NotFoundError(
                "equipment_model",
                source.equipment_model_id,
            )
        if self.configuration_repository.get_by_business_key(
            session,
            actor.tenant_id,
            source.equipment_model_id,
            payload.version_code,
        ):
            raise ConflictError(
                "target configuration version already exists"
            )
        for source_item in source.items:
            self._validate_item_references(
                session,
                actor,
                version=source,
                part_id=source_item.part_id,
                spare_part_id=source_item.spare_part_id,
                parent_item_id=source_item.parent_item_id,
                current_item_id=source_item.id,
            )

        target = self.configuration_repository.create(
            session,
            actor.tenant_id,
            {
                "equipment_model_id": source.equipment_model_id,
                "version_code": payload.version_code,
                "version_name": payload.version_name,
                "status": ConfigurationStatus.DRAFT,
                "effective_date": payload.effective_date,
                "expiry_date": None,
                "is_default": payload.is_default,
                "is_active": True,
                "source_reference": (
                    f"cloned:{source.version_code}"
                ),
                "description": source.description,
            },
        )
        old_to_new: dict[int, ConfigurationItem] = {}
        for source_item in sorted(
            source.items,
            key=lambda item: (
                item.sort_order,
                item.id,
            ),
        ):
            cloned = self.item_repository.create(
                session,
                actor.tenant_id,
                {
                    "configuration_version_id": target.id,
                    "item_code": source_item.item_code,
                    "parent_item_id": None,
                    "part_id": source_item.part_id,
                    "spare_part_id": source_item.spare_part_id,
                    "install_quantity": (
                        source_item.install_quantity
                    ),
                    "position_code": source_item.position_code,
                    "position_name": source_item.position_name,
                    "criticality_level": (
                        source_item.criticality_level
                    ),
                    "replacement_ratio": (
                        source_item.replacement_ratio
                    ),
                    "maintenance_level": (
                        source_item.maintenance_level
                    ),
                    "is_mandatory": source_item.is_mandatory,
                    "sort_order": source_item.sort_order,
                    "notes": source_item.notes,
                },
            )
            old_to_new[source_item.id] = cloned

        for source_item in source.items:
            if source_item.parent_item_id is not None:
                old_to_new[
                    source_item.id
                ].parent_item_id = old_to_new[
                    source_item.parent_item_id
                ].id

        self._commit(session)
        session.refresh(target)
        return target

    def tree(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> ConfigurationTree:
        version = self.configuration_repository.get_with_items(
            session,
            actor.tenant_id,
            identifier,
        )
        if version is None:
            raise NotFoundError(
                "configuration_version",
                identifier,
            )
        nodes = {
            item.id: ConfigurationTreeNode(
                id=item.id,
                item_code=item.item_code,
                parent_item_id=item.parent_item_id,
                part_id=item.part_id,
                spare_part_id=item.spare_part_id,
                install_quantity=item.install_quantity,
                position_code=item.position_code,
                position_name=item.position_name,
                criticality_level=item.criticality_level,
                replacement_ratio=item.replacement_ratio,
                maintenance_level=item.maintenance_level,
                is_mandatory=item.is_mandatory,
                sort_order=item.sort_order,
                notes=item.notes,
                children=[],
            )
            for item in version.items
        }
        roots: list[ConfigurationTreeNode] = []
        for item in sorted(
            version.items,
            key=lambda value: (
                value.sort_order,
                value.id,
            ),
        ):
            node = nodes[item.id]
            if item.parent_item_id is None:
                roots.append(node)
            else:
                parent = nodes.get(item.parent_item_id)
                if parent is None:
                    raise BusinessValidationError(
                        "configuration hierarchy references "
                        "an unavailable parent item",
                        details={
                            "parent_item_id": item.parent_item_id,
                        },
                    )
                parent.children.append(node)
        return ConfigurationTree(
            version=ConfigurationVersionRead.model_validate(
                version
            ),
            items=roots,
        )

    def delete(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> None:
        version = self.get(session, actor, identifier)
        if version.status != ConfigurationStatus.DRAFT:
            raise ResourceInUseError(
                "configuration_version",
                identifier,
            )
        if (
            self.configuration_repository.count_references(
                session,
                actor.tenant_id,
                identifier,
            )
            > 0
        ):
            raise ResourceInUseError(
                "configuration_version",
                identifier,
            )
        self.configuration_repository.delete(
            session,
            actor.tenant_id,
            version,
        )
        self._commit(session)


configuration_service = ConfigurationService()

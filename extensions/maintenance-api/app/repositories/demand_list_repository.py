from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.demand_list import (
    DemandList,
    DemandListEvent,
    DemandListItem,
)
from app.models.enums import DemandListEventType, DemandListStatus
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class DemandListRepository(BaseRepository[DemandList]):
    def __init__(self) -> None:
        super().__init__(DemandList)

    def get(
        self,
        session: Session,
        tenant_id: str,
        demand_list_id: int,
    ) -> DemandList | None:
        return session.scalar(
            select(DemandList)
            .options(
                tenant_loader_criteria(tenant_id),
                selectinload(DemandList.items),
                selectinload(DemandList.events),
            )
            .execution_options(populate_existing=True)
            .where(
                DemandList.tenant_id == tenant_id,
                DemandList.id == demand_list_id,
            )
        )

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        demand_list_id: int,
    ) -> DemandList | None:
        return session.scalar(
            select(DemandList)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandList.tenant_id == tenant_id,
                DemandList.id == demand_list_id,
            )
            .with_for_update()
        )

    def list_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        status: DemandListStatus | str | None = None,
        lineage_id: str | None = None,
    ) -> tuple[list[DemandList], int]:
        filters: dict[str, Any] = {}
        if status is not None:
            filters["status"] = status
        if lineage_id is not None:
            filters["lineage_id"] = lineage_id
        return super().list_page(
            session,
            tenant_id,
            page=page,
            page_size=page_size,
            keyword_fields=("name", "description"),
            filters=filters,
            sort_by="created_at",
            sort_order="desc",
        )

    def current_published_for_update(
        self,
        session: Session,
        tenant_id: str,
        lineage_id: str,
    ) -> DemandList | None:
        return session.scalar(
            select(DemandList)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandList.tenant_id == tenant_id,
                DemandList.lineage_id == lineage_id,
                DemandList.status == DemandListStatus.PUBLISHED,
                DemandList.is_current.is_(True),
            )
            .with_for_update()
        )

    def create_version(
        self,
        session: Session,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> DemandList:
        values = dict(data)
        lineage_id = str(values.get("lineage_id") or uuid4())
        current_version = session.scalar(
            select(func.max(DemandList.version_number)).where(
                DemandList.tenant_id == tenant_id,
                DemandList.lineage_id == lineage_id,
            )
        )
        values["lineage_id"] = lineage_id
        values["version_number"] = int(current_version or 0) + 1
        values.setdefault("status", DemandListStatus.DRAFT)
        values.setdefault("is_current", False)
        return self.create(session, tenant_id, values)

    def add_item(
        self,
        session: Session,
        tenant_id: str,
        *,
        demand_list_id: int,
        spare_part_id: int,
        original_quantity: Decimal,
        final_quantity: Decimal,
        source_snapshot: Mapping[str, Any],
        **snapshot_fields: Any,
    ) -> DemandListItem:
        if self.get_for_update(
            session,
            tenant_id,
            demand_list_id,
        ) is None:
            raise LookupError("demand list not found")
        item = DemandListItem(
            tenant_id=tenant_id,
            demand_list_id=demand_list_id,
            spare_part_id=spare_part_id,
            original_quantity=original_quantity,
            final_quantity=final_quantity,
            source_snapshot_json=dict(source_snapshot),
            **snapshot_fields,
        )
        session.add(item)
        session.flush()
        return item

    def append_event(
        self,
        session: Session,
        tenant_id: str,
        *,
        demand_list_id: int,
        event_type: DemandListEventType,
        actor_user_id: str,
        actor_roles: Sequence[str],
        request_id: str,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        before_summary: Mapping[str, Any] | None = None,
        after_summary: Mapping[str, Any] | None = None,
        response_snapshot: Mapping[str, Any] | None = None,
    ) -> DemandListEvent:
        if self.get_for_update(
            session,
            tenant_id,
            demand_list_id,
        ) is None:
            raise LookupError("demand list not found")
        event = DemandListEvent(
            tenant_id=tenant_id,
            demand_list_id=demand_list_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_roles_json=list(actor_roles),
            request_id=request_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            before_summary_json=(
                dict(before_summary)
                if before_summary is not None
                else None
            ),
            after_summary_json=(
                dict(after_summary)
                if after_summary is not None
                else None
            ),
            response_snapshot_json=(
                dict(response_snapshot)
                if response_snapshot is not None
                else None
            ),
        )
        session.add(event)
        session.flush()
        return event

    def get_event_by_idempotency_key(
        self,
        session: Session,
        tenant_id: str,
        idempotency_key: str,
    ) -> DemandListEvent | None:
        return session.scalar(
            select(DemandListEvent)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandListEvent.tenant_id == tenant_id,
                DemandListEvent.idempotency_key == idempotency_key,
            )
        )


class DemandListItemRepository(BaseRepository[DemandListItem]):
    def __init__(self) -> None:
        super().__init__(DemandListItem)

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        demand_list_id: int,
        item_id: int,
    ) -> DemandListItem | None:
        return session.scalar(
            select(DemandListItem)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                DemandListItem.tenant_id == tenant_id,
                DemandListItem.demand_list_id == demand_list_id,
                DemandListItem.id == item_id,
            )
            .with_for_update()
        )

    def list_for_demand_list(
        self,
        session: Session,
        tenant_id: str,
        demand_list_id: int,
    ) -> list[DemandListItem]:
        return list(
            session.scalars(
                select(DemandListItem)
                .options(tenant_loader_criteria(tenant_id))
                .execution_options(populate_existing=True)
                .where(
                    DemandListItem.tenant_id == tenant_id,
                    DemandListItem.demand_list_id == demand_list_id,
                )
                .order_by(DemandListItem.id)
            ).all()
        )

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.calculation_group import (
    CalculationGroup,
    CalculationGroupChild,
    CalculationGroupEvent,
    CalculationItemDecision,
)
from app.repositories.base import (
    BaseRepository,
    tenant_loader_criteria,
)


class CalculationGroupRepository(
    BaseRepository[CalculationGroup]
):
    def __init__(self) -> None:
        super().__init__(CalculationGroup)

    def get(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
    ) -> CalculationGroup | None:
        return self.get_by_id(
            session,
            tenant_id,
            group_id,
        )

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
    ) -> CalculationGroup | None:
        return session.scalar(
            select(CalculationGroup)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                CalculationGroup.tenant_id == tenant_id,
                CalculationGroup.id == group_id,
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
        status: str | None = None,
    ) -> tuple[list[CalculationGroup], int]:
        filters: dict[str, Any] = {}
        if status is not None:
            filters["status"] = status
        return super().list_page(
            session,
            tenant_id,
            page=page,
            page_size=page_size,
            keyword_fields=(),
            filters=filters,
            sort_by="created_at",
            sort_order="desc",
        )

    def append_event(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        child_id: int | None = None,
    ) -> CalculationGroupEvent:
        group = self.get_for_update(
            session,
            tenant_id,
            group_id,
        )
        if group is None:
            raise LookupError("calculation group not found")
        group.last_event_sequence += 1
        event = CalculationGroupEvent(
            tenant_id=tenant_id,
            group_id=group.id,
            child_id=child_id,
            sequence=group.last_event_sequence,
            event_type=event_type,
            payload_json=dict(payload),
        )
        session.add(event)
        session.flush()
        return event


class CalculationGroupChildRepository(
    BaseRepository[CalculationGroupChild]
):
    def __init__(self) -> None:
        super().__init__(CalculationGroupChild)

    def current_for_group(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
    ) -> list[CalculationGroupChild]:
        return list(
            session.scalars(
                select(CalculationGroupChild)
                .options(
                    tenant_loader_criteria(tenant_id)
                )
                .execution_options(populate_existing=True)
                .where(
                    CalculationGroupChild.tenant_id
                    == tenant_id,
                    CalculationGroupChild.group_id
                    == group_id,
                    CalculationGroupChild
                    .is_current_attempt
                    .is_(True),
                )
                .order_by(
                    CalculationGroupChild.candidate_key,
                    CalculationGroupChild.id,
                )
            ).all()
        )

    def create_attempt(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
        data: Mapping[str, Any],
    ) -> CalculationGroupChild:
        candidate_key = str(data["candidate_key"])
        session.execute(
            update(CalculationGroupChild)
            .where(
                CalculationGroupChild.tenant_id == tenant_id,
                CalculationGroupChild.group_id == group_id,
                CalculationGroupChild.candidate_key
                == candidate_key,
                CalculationGroupChild
                .is_current_attempt
                .is_(True),
            )
            .values(is_current_attempt=False)
        )
        current_attempt = session.scalar(
            select(
                func.max(
                    CalculationGroupChild.attempt_number
                )
            ).where(
                CalculationGroupChild.tenant_id == tenant_id,
                CalculationGroupChild.group_id == group_id,
                CalculationGroupChild.candidate_key
                == candidate_key,
            )
        )
        values = dict(data)
        values["group_id"] = group_id
        values["candidate_key"] = candidate_key
        values["attempt_number"] = int(
            values.get(
                "attempt_number",
                int(current_attempt or 0) + 1,
            )
        )
        values["is_current_attempt"] = True
        return self.create(
            session,
            tenant_id,
            values,
        )


class CalculationItemDecisionRepository(
    BaseRepository[CalculationItemDecision]
):
    def __init__(self) -> None:
        super().__init__(CalculationItemDecision)

    def get_for_update(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
        spare_part_id: int,
    ) -> CalculationItemDecision | None:
        return session.scalar(
            select(CalculationItemDecision)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                CalculationItemDecision.tenant_id
                == tenant_id,
                CalculationItemDecision.group_id
                == group_id,
                CalculationItemDecision.spare_part_id
                == spare_part_id,
            )
            .with_for_update()
        )

    def upsert(
        self,
        session: Session,
        tenant_id: str,
        group_id: int,
        spare_part_id: int,
        data: Mapping[str, Any],
    ) -> CalculationItemDecision:
        decision = self.get_for_update(
            session,
            tenant_id,
            group_id,
            spare_part_id,
        )
        values = {
            **data,
            "group_id": group_id,
            "spare_part_id": spare_part_id,
        }
        if decision is None:
            return self.create(
                session,
                tenant_id,
                values,
            )
        decision.version += 1
        return self.update(
            session,
            tenant_id,
            decision,
            values,
        )

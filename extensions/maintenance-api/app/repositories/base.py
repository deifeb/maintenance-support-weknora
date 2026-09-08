from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.mixins import TenantScopedMixin

ModelT = TypeVar("ModelT")

PROTECTED_WRITE_FIELDS = frozenset(
    {
        "id",
        "tenant_id",
        "version",
    }
)


class TenantScopeError(RuntimeError):
    pass


def tenant_loader_criteria(tenant_id: str):
    return with_loader_criteria(
        TenantScopedMixin,
        lambda model: model.tenant_id == tenant_id,
        include_aliases=True,
    )


def _clean_write_data(
    data: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if key not in PROTECTED_WRITE_FIELDS
    }


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    def get_by_id(
        self,
        session: Session,
        tenant_id: str,
        identifier: int,
    ) -> ModelT | None:
        return session.scalar(
            select(self.model)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                self.model.id == identifier,
                self.model.tenant_id == tenant_id,
            )
        )

    def get_by_code(
        self,
        session: Session,
        tenant_id: str,
        code: str,
        field_name: str = "code",
    ) -> ModelT | None:
        field = getattr(self.model, field_name)
        return session.scalar(
            select(self.model)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(
                field == code,
                self.model.tenant_id == tenant_id,
            )
        )

    def create(
        self,
        session: Session,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> ModelT:
        instance = self.model(
            tenant_id=tenant_id,
            **_clean_write_data(data),
        )
        session.add(instance)
        session.flush()
        return instance

    def update(
        self,
        session: Session,
        tenant_id: str,
        instance: ModelT,
        data: Mapping[str, Any],
    ) -> ModelT:
        self._require_tenant(instance, tenant_id)

        for key, value in _clean_write_data(data).items():
            setattr(instance, key, value)

        session.flush()
        return instance

    def delete(
        self,
        session: Session,
        tenant_id: str,
        instance: ModelT,
    ) -> None:
        self._require_tenant(instance, tenant_id)
        session.delete(instance)
        session.flush()

    def exists(
        self,
        session: Session,
        tenant_id: str,
        **filters: Any,
    ) -> bool:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == tenant_id)
        )
        for key, value in filters.items():
            if key == "tenant_id":
                continue
            stmt = stmt.where(
                getattr(self.model, key) == value
            )
        return bool(session.scalar(stmt))

    def list_page(
        self,
        session: Session,
        tenant_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        keyword_fields: Sequence[str] = ("code", "name"),
        filters: dict[str, Any] | None = None,
        include_inactive: bool = False,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> tuple[list[ModelT], int]:
        stmt: Select[Any] = (
            select(self.model)
            .options(tenant_loader_criteria(tenant_id))
            .execution_options(populate_existing=True)
            .where(self.model.tenant_id == tenant_id)
        )
        count_stmt: Select[Any] = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == tenant_id)
        )

        if (
            hasattr(self.model, "is_active")
            and not include_inactive
        ):
            active_column = getattr(self.model, "is_active")
            stmt = stmt.where(active_column.is_(True))
            count_stmt = count_stmt.where(
                active_column.is_(True)
            )

        for key, value in (filters or {}).items():
            if value is None or key == "tenant_id":
                continue
            column = getattr(self.model, key)
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)

        if keyword:
            conditions = [
                getattr(self.model, field).ilike(
                    f"%{keyword}%"
                )
                for field in keyword_fields
                if hasattr(self.model, field)
            ]
            if conditions:
                keyword_filter = or_(*conditions)
                stmt = stmt.where(keyword_filter)
                count_stmt = count_stmt.where(
                    keyword_filter
                )

        if not hasattr(self.model, sort_by):
            sort_by = "id"
        sort_column = getattr(self.model, sort_by)
        stmt = stmt.order_by(
            sort_column.desc()
            if sort_order.lower() == "desc"
            else sort_column.asc()
        )
        stmt = stmt.offset(
            (page - 1) * page_size
        ).limit(page_size)

        items = list(session.scalars(stmt).all())
        total = int(session.scalar(count_stmt) or 0)
        return items, total

    def _require_tenant(
        self,
        instance: ModelT,
        tenant_id: str,
    ) -> None:
        if getattr(instance, "tenant_id", None) != tenant_id:
            raise TenantScopeError(
                f"{self.model.__name__} belongs to another tenant"
            )

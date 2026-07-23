from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    def get_by_id(self, session: Session, identifier: int) -> ModelT | None:
        return session.get(self.model, identifier)

    def get_by_code(self, session: Session, code: str, field_name: str = "code") -> ModelT | None:
        field = getattr(self.model, field_name)
        return session.scalar(select(self.model).where(field == code))

    def create(self, session: Session, data: dict[str, Any]) -> ModelT:
        instance = self.model(**data)
        session.add(instance)
        session.flush()
        return instance

    def update(self, session: Session, instance: ModelT, data: dict[str, Any]) -> ModelT:
        for key, value in data.items():
            setattr(instance, key, value)
        session.flush()
        return instance

    def delete(self, session: Session, instance: ModelT) -> None:
        session.delete(instance)
        session.flush()

    def exists(self, session: Session, **filters: Any) -> bool:
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return bool(session.scalar(stmt))

    def list_page(
        self,
        session: Session,
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
        stmt: Select[Any] = select(self.model)
        count_stmt: Select[Any] = select(func.count()).select_from(self.model)

        if hasattr(self.model, "is_active") and not include_inactive:
            stmt = stmt.where(getattr(self.model, "is_active").is_(True))
            count_stmt = count_stmt.where(getattr(self.model, "is_active").is_(True))

        for key, value in (filters or {}).items():
            if value is None:
                continue
            column = getattr(self.model, key)
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)

        if keyword:
            conditions = [
                getattr(self.model, field).ilike(f"%{keyword}%")
                for field in keyword_fields
                if hasattr(self.model, field)
            ]
            if conditions:
                stmt = stmt.where(or_(*conditions))
                count_stmt = count_stmt.where(or_(*conditions))

        if not hasattr(self.model, sort_by):
            sort_by = "id"
        sort_column = getattr(self.model, sort_by)
        stmt = stmt.order_by(sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        items = list(session.scalars(stmt).all())
        total = int(session.scalar(count_stmt) or 0)
        return items, total

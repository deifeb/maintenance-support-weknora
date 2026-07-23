from math import ceil
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ResourceInUseError
from app.repositories.base import BaseRepository
from app.schemas.common import PageData

ModelT = TypeVar("ModelT")
ReadT = TypeVar("ReadT", bound=BaseModel)


class CrudService(Generic[ModelT, ReadT]):
    def __init__(
        self,
        repository: BaseRepository[ModelT],
        *,
        resource_name: str,
        read_schema: type[ReadT],
        code_field: str = "code",
        keyword_fields: tuple[str, ...] = ("code", "name"),
    ) -> None:
        self.repository = repository
        self.resource_name = resource_name
        self.read_schema = read_schema
        self.code_field = code_field
        self.keyword_fields = keyword_fields

    def _commit(self, session: Session) -> None:
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ConflictError(
                f"{self.resource_name} conflicts with an existing record",
                details={"resource": self.resource_name},
            ) from exc

    def get(self, session: Session, identifier: int) -> ModelT:
        instance = self.repository.get_by_id(session, identifier)
        if instance is None:
            raise NotFoundError(self.resource_name, identifier)
        return instance

    def list(
        self,
        session: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        include_inactive: bool,
        sort_by: str,
        sort_order: str,
        filters: dict[str, Any] | None = None,
    ) -> PageData[ReadT]:
        items, total = self.repository.list_page(
            session,
            page=page,
            page_size=page_size,
            keyword=keyword,
            keyword_fields=self.keyword_fields,
            include_inactive=include_inactive,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )
        return PageData[ReadT](
            items=[self.read_schema.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=ceil(total / page_size) if total else 0,
        )

    def create(self, session: Session, payload: BaseModel, *, commit: bool = True) -> ModelT:
        code = getattr(payload, self.code_field, None)
        if code is not None and self.repository.get_by_code(session, code, self.code_field):
            raise ConflictError(
                f"{self.resource_name} code already exists",
                details={self.code_field: code},
            )
        instance = self.repository.create(session, payload.model_dump())
        if commit:
            self._commit(session)
            session.refresh(instance)
        return instance

    def update(
        self,
        session: Session,
        identifier: int,
        payload: BaseModel,
        *,
        commit: bool = True,
    ) -> ModelT:
        instance = self.get(session, identifier)
        data = payload.model_dump(exclude_unset=True)
        self.repository.update(session, instance, data)
        if commit:
            self._commit(session)
            session.refresh(instance)
        return instance

    def set_active(self, session: Session, identifier: int, is_active: bool) -> ModelT:
        instance = self.get(session, identifier)
        self.repository.update(session, instance, {"is_active": is_active})
        self._commit(session)
        session.refresh(instance)
        return instance

    def count_references(self, session: Session, identifier: int) -> int:
        counter = getattr(self.repository, "count_references", None)
        return int(counter(session, identifier)) if counter else 0

    def delete(self, session: Session, identifier: int) -> None:
        instance = self.get(session, identifier)
        if self.count_references(session, identifier) > 0:
            raise ResourceInUseError(self.resource_name, identifier)
        self.repository.delete(session, instance)
        self._commit(session)

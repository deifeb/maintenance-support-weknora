from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str = ""


class ApiMeta(BaseModel):
    request_id: str
    tenant_id: str
    version: int | None = None


class MaintenanceSuccessResponse(SuccessResponse[T], Generic[T]):
    meta: ApiMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail = Field(...)


class PageData(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int

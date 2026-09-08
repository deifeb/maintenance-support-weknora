from typing import Any

from fastapi import Query


def list_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None, max_length=200),
    include_inactive: bool = Query(default=False),
    sort_by: str = Query(default="id", max_length=64),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    return {
        "page": page,
        "page_size": page_size,
        "keyword": keyword,
        "include_inactive": include_inactive,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }

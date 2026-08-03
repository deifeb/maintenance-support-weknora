from typing import Any, overload

from app.schemas.common import (
    ApiMeta,
    MaintenanceSuccessResponse,
    SuccessResponse,
)
from app.security.actor import ActorContext


@overload
def success_response(
    data: Any,
    message: str = "",
    *,
    actor: None = None,
    version: None = None,
) -> SuccessResponse[Any]: ...


@overload
def success_response(
    data: Any,
    message: str = "",
    *,
    actor: ActorContext,
    version: int | None = None,
) -> MaintenanceSuccessResponse[Any]: ...


def success_response(
    data: Any,
    message: str = "",
    *,
    actor: ActorContext | None = None,
    version: int | None = None,
) -> SuccessResponse[Any] | MaintenanceSuccessResponse[Any]:
    if actor is None:
        if version is not None:
            raise ValueError(
                "version metadata requires an authenticated actor"
            )
        return SuccessResponse(data=data, message=message)

    return MaintenanceSuccessResponse(
        data=data,
        message=message,
        meta=ApiMeta(
            request_id=actor.request_id,
            tenant_id=actor.tenant_id,
            version=version,
        ),
    )

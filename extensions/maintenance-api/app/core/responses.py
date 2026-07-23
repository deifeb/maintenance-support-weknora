from typing import Any

from app.schemas.common import SuccessResponse


def success_response(
    data: Any,
    message: str = "",
) -> SuccessResponse[Any]:
    return SuccessResponse(
        data=data,
        message=message,
    )

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.request_id = request_id


class InsufficientMaintenanceRoleError(AppException):
    def __init__(
        self,
        *,
        required_role: str,
        actual_role: str,
        request_id: str,
    ) -> None:
        super().__init__(
            status_code=403,
            code="INSUFFICIENT_MAINTENANCE_ROLE",
            message=f"{required_role} role is required",
            details={
                "required_role": required_role,
                "actual_role": actual_role,
            },
            request_id=request_id,
        )


class DatabaseUnavailableError(AppException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="Database connection failed",
        )


class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} was not found",
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(AppException):
    def __init__(
        self,
        message: str,
        details: Any | None = None,
        code: str = "RESOURCE_CONFLICT",
    ) -> None:
        super().__init__(
            status_code=409,
            code=code,
            message=message,
            details=details,
        )


class ResourceInUseError(ConflictError):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            code="RESOURCE_IN_USE",
            message=f"{resource} is referenced and cannot be deleted; deactivate it instead",
            details={"resource": resource, "identifier": identifier},
        )


class BusinessValidationError(AppException):
    def __init__(
        self,
        message: str,
        details: Any | None = None,
        code: str = "BUSINESS_VALIDATION_ERROR",
    ) -> None:
        super().__init__(
            status_code=422,
            code=code,
            message=message,
            details=details,
        )


def build_error_body(
    *,
    code: str,
    message: str,
    details: Any | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details,
    }
    if request_id is not None:
        error["request_id"] = request_id

    return {"success": False, "error": error}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(
                build_error_body(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    request_id=exc.request_id,
                )
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                build_error_body(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details=exc.errors(),
                )
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=500,
            content=build_error_body(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred",
            ),
        )

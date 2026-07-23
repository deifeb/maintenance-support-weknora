from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class DatabaseUnavailableError(AppException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="Database connection failed",
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

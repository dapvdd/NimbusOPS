"""Typed error contract for non-validation failures.

All handler-raised errors serialize as:
    {"error": {"code": "<STABLE_CODE>", "message": "<human text>"}}
Validation (422) keeps FastAPI's default body shape, documented in
docs/API.md.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .codes import ErrorCode


class ApiError(Exception):
    """Raised by handlers/services to produce a typed error response."""

    def __init__(self, status: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code.value, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep FastAPI's 422 shape; ensure it is JSON-serializable.
        safe_errors = []
        for err in exc.errors():
            clean = {k: v for k, v in err.items() if k not in ("ctx", "input", "url")}
            clean["msg"] = err.get("msg", "validation error")
            safe_errors.append(clean)
        return JSONResponse(status_code=422, content={"detail": safe_errors})

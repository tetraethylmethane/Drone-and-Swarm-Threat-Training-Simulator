"""Structured error responses.

Every error body has the shape ``{"error": {"code", "message", "details"}}``.
Internal errors never expose stack traces or SQL to clients.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("drikr.api")


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You do not have permission to perform this action") -> ApiError:
    return ApiError(403, "forbidden", message)


def conflict(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(409, code, message, details)


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def _clean_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in errors:
        loc = [str(p) for p in e.get("loc", ())]
        # Never echo submitted values back (they may contain passwords).
        out.append({"path": ".".join(loc), "message": e.get("msg", "invalid"), "type": e.get("type", "")})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content=_body(exc.code, exc.message, exc.details), headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body(
                "validation_error", "Request validation failed", _clean_validation_errors(list(exc.errors()))
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(
            status_code=exc.status_code, content=_body(code, str(exc.detail)), headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        log.warning(
            "integrity_error", extra={"constraint": getattr(getattr(exc.orig, "diag", None), "constraint_name", None)}
        )
        return JSONResponse(status_code=409, content=_body("conflict", "The request conflicts with existing data"))

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, exc: OperationalError) -> JSONResponse:
        log.error("database_unavailable")
        return JSONResponse(
            status_code=503,
            content=_body("database_unavailable", "The database is temporarily unavailable. Retry shortly."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return JSONResponse(status_code=500, content=_body("internal_error", "An unexpected error occurred"))

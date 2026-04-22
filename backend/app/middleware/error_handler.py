"""Unified error response formatting.

All error responses use the shape `{"error": {"code": str, "message": str}}`
to stay compatible with `docs/04_api.md` and `frontend/src/types/docdelta.ts`
(`DocdeltaErrorResponse`). FastAPI's default `{"detail": ...}` shape is
replaced by registering handlers for:

  * `RequestValidationError` (Pydantic) → 422 VALIDATION
  * `HTTPException` → original status code, converted envelope
  * bare `Exception` → 500 INTERNAL (no stack traces in the body)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request


def _envelope(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    """Attach the three top-level exception handlers to *app*."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # `exc.errors()` is a list of dicts; slice to keep the body small and
        # the message roughly readable.
        errors = exc.errors()
        message = str(errors[:3]) if errors else "validation error"
        return JSONResponse(status_code=422, content=_envelope("VALIDATION", message))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        detail: Any = exc.detail
        # Handler-raised HTTPException may pass either a structured dict
        # `{"code": "...", "message": "..."}` (preferred by our routers) or a
        # bare string (legacy / defaults).
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=_envelope(str(detail["code"]), str(detail["message"])),
            )
        message = detail if isinstance(detail, str) else str(detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("HTTP_ERROR", message),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # Never leak internal details — secrets, stack frames, etc.
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL", "Internal server error"),
        )

"""Error envelope shared across the API.

Shape: `{"error": {"code": str, "message": str}}` — see docs/04_api.md.
Mirrors `DocdeltaErrorResponse` on the frontend (frontend/src/types/docdelta.ts).
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody

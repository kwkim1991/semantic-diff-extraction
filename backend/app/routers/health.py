"""Health probe router. Mounted under `/api` → `GET /api/health`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Simple liveness probe. No dependencies, no DB, no external calls."""
    return {"status": "ok"}

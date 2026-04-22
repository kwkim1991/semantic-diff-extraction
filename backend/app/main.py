"""FastAPI application entrypoint for the Wiki Workspace backend.

Run locally:
    uvicorn app.main:app --reload --port 3001
or:
    python -m app.main
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .env import env
from .middleware.error_handler import register_error_handlers
from .middleware.request_id import RequestIDMiddleware
from .routers import ai, health

app = FastAPI(title="Wiki Workspace Backend", version="0.1.0")

# CORS — the Vite dev server origin is the only allowed source in the PoC.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[env.CORS_ORIGIN],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Request ID goes after CORS so preflight responses also get one.
app.add_middleware(RequestIDMiddleware)

# Register exception handlers (validation / HTTP / catch-all).
register_error_handlers(app)

# Routers.
app.include_router(health.router, prefix="/api")
app.include_router(ai.router, prefix="/api/ai")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=env.PORT)

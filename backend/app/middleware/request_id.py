"""X-Request-ID middleware.

Uses the inbound `X-Request-ID` header if present, otherwise generates a
fresh UUID4. Echoes the chosen value on the response so clients can correlate
logs and error reports.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Attach to the request scope so route handlers / loggers can read it
        # via `request.state.request_id` without re-parsing headers.
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

"""Provider Protocol for `POST /api/ai/docdelta`.

`DocdeltaProvider` is a PEP 544 Protocol. Implementations live under
`backend/app/services/providers/` and are selected by
`backend/app/services/docdelta.py` based on `env.LLM_PROVIDER`.

Rationale (see `_workspace/02_architect_decision.md` §6.1): async contract
unifies both mock (sync body wrapped) and finetuned (real async httpx call)
so the router can always `await provider.analyze(req)` without branching.
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.docdelta import DocdeltaRequest, DocdeltaResponse


class DocdeltaProvider(Protocol):
    """Contract for docdelta backends.

    Implementations must:
    * echo `req.source_id` on the response (shape per reference/doc_scheme.json),
    * populate `output.new` and `output.conflict` per the scheme,
    * raise `fastapi.HTTPException` for upstream failures (mapped to the
      standard error envelope by the error_handler middleware).
    """

    async def analyze(self, req: DocdeltaRequest) -> DocdeltaResponse: ...

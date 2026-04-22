"""Deterministic mock provider for `POST /api/ai/docdelta`.

Moved from `backend/app/services/docdelta_mock.py` on 2026-04-22 as part of
the provider abstraction refactor (see `_workspace/02_architect_decision.md`
§6.2.2). The `analyze_docdelta_mock` function body is preserved verbatim so
response shape/content stays identical byte-for-byte; only the module path
changed. `MockProvider` wraps the function to satisfy the `DocdeltaProvider`
Protocol (async `analyze`).

Behavior:
  * `output.new`  — one bullet per element of `new_doc`, echoing the first
                    80 chars of `context`.
  * `output.conflict` — if there is at least one known doc AND at least one
                    new_doc, emit a single synthetic conflict with
                    `severity="medium"`. Otherwise an empty array.
  * `source_id` — echoed verbatim from the request.
"""

from __future__ import annotations

from ...schemas.docdelta import (
    DocdeltaConflict,
    DocdeltaOutput,
    DocdeltaRequest,
    DocdeltaResponse,
)


def analyze_docdelta_mock(req: DocdeltaRequest) -> DocdeltaResponse:
    """Produce a deterministic mock DocdeltaResponse."""

    # new: one line per new_doc element.
    new_items: list[str] = [
        f"[MOCK] new from {d.doc_id}: {d.context[:80]}..."
        for d in req.new_doc
    ]

    # conflict: flatten known_docs and pair the first known doc with the first
    # new_doc to synthesize a single sample conflict. If either is empty, emit
    # no conflicts.
    flat_known = [d for group in req.known_docs for d in group]
    conflicts: list[DocdeltaConflict] = []
    if flat_known and req.new_doc:
        k = flat_known[0]
        n = req.new_doc[0]
        conflicts.append(
            DocdeltaConflict(
                doc_id=k.doc_id,
                known_text=k.context[:100],
                new_text=n.context[:100],
                reason="[MOCK] 샘플 충돌 — 실제 LLM 연동 전 PoC 응답",
                severity="medium",
            )
        )

    return DocdeltaResponse(
        source_id=req.source_id,
        output=DocdeltaOutput(new=new_items, conflict=conflicts),
    )


class MockProvider:
    """DocdeltaProvider implementation wrapping the deterministic mock."""

    async def analyze(self, req: DocdeltaRequest) -> DocdeltaResponse:
        return analyze_docdelta_mock(req)

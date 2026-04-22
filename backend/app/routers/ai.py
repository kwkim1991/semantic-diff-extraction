"""AI endpoints router. Mounted under `/api/ai`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.docdelta import DocdeltaRequest, DocdeltaResponse
from ..services.docdelta import get_provider

router = APIRouter()


@router.post("/docdelta", response_model=DocdeltaResponse)
async def docdelta(req: DocdeltaRequest) -> DocdeltaResponse:
    """Analyze a docdelta request against the known/new doc sets.

    Pydantic handles shape/field validation automatically (→ 422 via the
    `RequestValidationError` handler). We additionally reject empty `new_doc`
    at the application layer because the contract (03_data_contract.md §4)
    requires a non-empty `new_doc`. Provider selection (mock vs finetuned)
    is handled by `services.docdelta.get_provider()`.
    """
    if not req.new_doc:
        # Application-level VALIDATION; the error_handler middleware will
        # preserve the dict payload as the JSON body.
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION",
                "message": "new_doc must not be empty",
            },
        )
    return await get_provider().analyze(req)

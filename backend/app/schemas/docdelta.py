"""Pydantic models for `POST /api/ai/docdelta`.

These models map 1:1 to `reference/doc_scheme.json` (the authoritative contract)
and are kept in sync with `frontend/src/types/docdelta.ts` manually
(packages/shared is a Phase 3 trigger — see T12).

Field names match the scheme byte-for-byte, including `new` (not a Python
reserved keyword — it is a built-in name but usable as an attribute).
`extra="forbid"` is applied so that unknown request fields are rejected at
the Pydantic layer, which is what the VALIDATION contract (422) prescribes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocdeltaDocRef(BaseModel):
    """A single document reference. Used in `known_docs`, `new_doc`, `convert_doc`."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    context: str


class DocdeltaRequest(BaseModel):
    """Request body for `POST /api/ai/docdelta`."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    instruction: str
    known_docs: list[list[DocdeltaDocRef]]
    new_doc: list[DocdeltaDocRef]
    convert_doc: list[DocdeltaDocRef] = Field(default_factory=list)


class DocdeltaConflict(BaseModel):
    """A single conflict entry in `output.conflict[]`."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    known_text: str
    new_text: str
    reason: str
    severity: Literal["low", "medium", "high"]


class DocdeltaOutput(BaseModel):
    """The `output` object inside the response."""

    model_config = ConfigDict(extra="forbid")

    new: list[str]
    conflict: list[DocdeltaConflict]


class DocdeltaResponse(BaseModel):
    """200 OK response body for `POST /api/ai/docdelta`."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    output: DocdeltaOutput

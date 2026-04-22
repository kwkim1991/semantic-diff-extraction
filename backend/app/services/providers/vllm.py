"""vLLM provider for `POST /api/ai/docdelta`.

Third provider (after mock, finetuned) selected when `env.LLM_PROVIDER == "vllm"`
by the dispatcher in `backend/app/services/docdelta.py`. Calls the vendored
`get_diff()` (sync, OpenAI SDK + HuggingFace tokenizer + vLLM guided_json)
from `./_vendor/infer_diff.py`, wrapping it in `asyncio.to_thread` so the event
loop stays responsive.

Vendored path: `backend/app/services/providers/_vendor/{infer_diff.py, prompt_text.py}`.
See `_workspace/02_architect_decision.md` §3 for why we vendor rather than
depend on `train/finetune/` at runtime. Heavy deps (`openai`, `transformers`)
live in the `[vllm]` optional extra — imports are deferred to method-body so
mock/finetuned bootstrapping never pays the cost.

Error mapping (contract: `_workspace/03_data_contract.md` §4):
* VLLM_ENDPOINT unset                    -> 500 AI_UPSTREAM
* `[vllm]` extra not installed           -> 500 AI_UPSTREAM (with install hint)
* `openai.APITimeoutError`               -> 504 TIMEOUT
* other `openai.APIError` / network err  -> 502 AI_UPSTREAM
* `ValueError` (endpoint None path)      -> 500 AI_UPSTREAM (normally pre-empted)
* `json.JSONDecodeError`                 -> 502 AI_UPSTREAM
* any other `Exception`                  -> 502 AI_UPSTREAM (msg capped 200 chars)
* `DocdeltaResponse` Pydantic revalidate -> 502 AI_UPSTREAM
"""

from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException
from pydantic import ValidationError

from ...env import env
from ...schemas.docdelta import (
    DocdeltaConflict,
    DocdeltaDocRef,
    DocdeltaOutput,
    DocdeltaRequest,
    DocdeltaResponse,
)


def _resolve_doc_id(known_text: str, refs: list[DocdeltaDocRef]) -> str:
    """Recover `doc_id` for a conflict entry via 3-stage fallback.

    Authoritative rule: see `_workspace/03_data_contract.md` §3.4.
    1) substring `in` match — return first hit's doc_id
    2) first flat_known_refs entry's doc_id
    3) literal string "unknown" (known_docs empty)
    """
    for r in refs:
        if known_text and known_text in r.context:
            return r.doc_id
    if refs:
        return refs[0].doc_id
    return "unknown"


class VllmProvider:
    """DocdeltaProvider that forwards to a vLLM endpoint via vendored get_diff."""

    async def analyze(self, req: DocdeltaRequest) -> DocdeltaResponse:
        # 1) Endpoint must be configured before we do anything else.
        if not env.VLLM_ENDPOINT:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "AI_UPSTREAM",
                    "message": "VLLM_ENDPOINT is not configured",
                },
            )

        # 2) Defer the heavy vendored import so mock/finetuned never pay the cost.
        #    This also catches the `[vllm]` extra-not-installed case (openai/
        #    transformers missing) with a clear install hint.
        try:
            from ._vendor.infer_diff import get_diff
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "AI_UPSTREAM",
                    "message": (
                        f"vllm extras not installed: {e}. "
                        "Install with `pip install \".[vllm]\"` or `uv sync --extra vllm`."
                    ),
                },
            ) from e

        # 3) Flatten known_docs preserving order; keep parallel refs list for doc_id recovery.
        flat_known_refs: list[DocdeltaDocRef] = [
            ref for group in req.known_docs for ref in group
        ]
        flat_known_texts: list[str] = [r.context for r in flat_known_refs]

        # 4) Defensive: if new_doc is empty (router 422 normally pre-empts this),
        #    return an empty response rather than invoke the upstream.
        if not req.new_doc:
            return DocdeltaResponse(
                source_id=req.source_id,
                output=DocdeltaOutput(new=[], conflict=[]),
            )

        merged_new: list[str] = []
        merged_conflict: list[DocdeltaConflict] = []

        # 5) Call get_diff once per new_doc entry via asyncio.to_thread (sync -> thread).
        #    Note: `_vendor/infer_diff.py` lazy-imports `transformers` (in
        #    `_get_tokenizer`) and `openai` (in `_get_client`), so the top-of-
        #    method `from ._vendor.infer_diff import get_diff` succeeds even
        #    when the `[vllm]` extra is missing. The ImportError actually
        #    surfaces here, on first call — which is why we need a dedicated
        #    `except ImportError` arm **inside** this per-call try block.
        for nd in req.new_doc:
            # openai.APITimeoutError / APIError are only importable when the
            # `[vllm]` extra is installed. Probe lazily; if openai itself is
            # missing, the ImportError arm below will catch the downstream
            # failure first, so these bindings just need to be safe no-ops.
            try:
                from openai import APIError, APITimeoutError
            except ImportError:
                APIError = ()  # type: ignore[assignment,misc]
                APITimeoutError = ()  # type: ignore[assignment,misc]

            try:
                result = await asyncio.to_thread(
                    get_diff,
                    flat_known_texts,
                    nd.context,
                    vllm_endpoint=env.VLLM_ENDPOINT,
                    vllm_model=env.VLLM_MODEL,
                    vllm_api_key=env.VLLM_API_KEY,
                    tokenizer_source=env.HF_TOKENIZER,
                )
            except HTTPException:
                raise
            except APITimeoutError as e:  # type: ignore[misc]
                raise HTTPException(
                    status_code=504,
                    detail={
                        "code": "TIMEOUT",
                        "message": f"vLLM API timeout: {str(e)[:200]}",
                    },
                ) from e
            except ImportError as e:
                # `[vllm]` extra missing — `_vendor/infer_diff.py` lazy-imports
                # transformers/openai from inside helper functions, so this is
                # the first place the failure becomes visible. Contract
                # (03_data_contract §4 row 2): 500 AI_UPSTREAM + install hint.
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "AI_UPSTREAM",
                        "message": (
                            f"vllm extras not installed ({e}). "
                            'Install with `pip install ".[vllm]"` or '
                            "`uv sync --extra vllm`."
                        ),
                    },
                ) from e
            except ValueError as e:
                # infer_diff.py raises ValueError when endpoint is missing.
                # Step 1 normally pre-empts this; treat as 500 AI_UPSTREAM.
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "AI_UPSTREAM",
                        "message": f"vLLM configuration error: {str(e)[:200]}",
                    },
                ) from e
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "AI_UPSTREAM",
                        "message": f"vLLM output JSON parse failed: {str(e)[:200]}",
                    },
                ) from e
            except APIError as e:  # type: ignore[misc]
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "AI_UPSTREAM",
                        "message": f"vLLM API error: {str(e)[:200]}",
                    },
                ) from e
            except Exception as e:
                # Fallback for any other exception (socket errors, SSL, etc.).
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "AI_UPSTREAM",
                        "message": f"vLLM upstream error: {str(e)[:200]}",
                    },
                ) from e

            # DEBUG (temporary): log raw vLLM output to stderr so we can see
            # whether empty results are model-driven or our pipeline's fault.
            import sys as _dbg_sys
            print(
                f"[vllm-debug] source_id={req.source_id} "
                f"known_count={len(flat_known_refs)} new_doc_len={len(nd.context)} "
                f"raw_result={json.dumps(result, ensure_ascii=False)[:500]}",
                file=_dbg_sys.stderr,
                flush=True,
            )

            # 6) Merge this call's new + conflict into the rolling outputs.
            new_items = result.get("new", []) if isinstance(result, dict) else []
            merged_new.extend(new_items)

            conflicts = result.get("conflict", []) if isinstance(result, dict) else []
            for c in conflicts:
                if not isinstance(c, dict):
                    continue
                known_text = c.get("known_text", "")
                merged_conflict.append(
                    DocdeltaConflict(
                        doc_id=_resolve_doc_id(known_text, flat_known_refs),
                        known_text=known_text,
                        new_text=c.get("new_text", ""),
                        reason=c.get("reason", ""),
                        severity="medium",
                    )
                )

        # 7) Final assembly + Pydantic re-validation. Validation failure means
        #    the vendored provider emitted something the contract does not accept;
        #    map to 502 AI_UPSTREAM.
        try:
            return DocdeltaResponse.model_validate(
                {
                    "source_id": req.source_id,
                    "output": {
                        "new": merged_new,
                        "conflict": [c.model_dump() for c in merged_conflict],
                    },
                }
            )
        except ValidationError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "AI_UPSTREAM",
                    "message": f"vLLM response validation failed: {str(e)[:200]}",
                },
            ) from e

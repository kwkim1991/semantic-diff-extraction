"""Finetuned upstream provider stub for `POST /api/ai/docdelta`.

Forwards the DocdeltaRequest to a user-hosted finetuned model endpoint and
re-validates the response against the reference scheme (via Pydantic).
Selected when `env.LLM_PROVIDER == "finetuned"` by the dispatcher in
`backend/app/services/docdelta.py`.

Failure modes:
* Missing `FINETUNED_API_URL` -> 500 AI_UPSTREAM (configuration error).
* httpx timeout                -> 504 TIMEOUT.
* httpx transport error        -> 502 AI_UPSTREAM.
* upstream 4xx/5xx response    -> 502 AI_UPSTREAM (body truncated to 200 chars).
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from ...env import env
from ...schemas.docdelta import DocdeltaRequest, DocdeltaResponse


class FinetunedProvider:
    """DocdeltaProvider that proxies to an external finetuned model service."""

    async def analyze(self, req: DocdeltaRequest) -> DocdeltaResponse:
        if not env.FINETUNED_API_URL:
            raise HTTPException(
                status_code=500,
                detail={"code": "AI_UPSTREAM", "message": "FINETUNED_API_URL is not configured"},
            )
        headers = {"Content-Type": "application/json"}
        if env.FINETUNED_API_KEY:
            headers["Authorization"] = f"Bearer {env.FINETUNED_API_KEY}"
        try:
            async with httpx.AsyncClient(timeout=env.FINETUNED_TIMEOUT_SEC) as client:
                resp = await client.post(
                    env.FINETUNED_API_URL,
                    json=req.model_dump(mode="json"),
                    headers=headers,
                )
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail={"code": "TIMEOUT", "message": f"Finetuned API timeout: {e}"},
            ) from e
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502,
                detail={"code": "AI_UPSTREAM", "message": f"Finetuned API error: {e}"},
            ) from e
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "AI_UPSTREAM",
                    "message": f"Finetuned API {resp.status_code}: {resp.text[:200]}",
                },
            )
        return DocdeltaResponse.model_validate_json(resp.text)

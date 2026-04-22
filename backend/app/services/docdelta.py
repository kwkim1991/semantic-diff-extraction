"""Provider dispatcher for `POST /api/ai/docdelta`.

Centralizes provider selection so routers stay thin (see
`_workspace/02_architect_decision.md` §6.3 — dispatcher lives in services/,
not in the router, to keep provider lifecycle logic out of the HTTP layer
and to let future AI endpoints reuse the same selection pattern).

Selection rule:
* `LLM_PROVIDER == "finetuned"` -> `FinetunedProvider`
* `LLM_PROVIDER == "vllm"`      -> `VllmProvider`
* anything else (including default "mock")  -> `MockProvider`
"""

from __future__ import annotations

from ..env import env
from .docdelta_provider import DocdeltaProvider
from .providers.finetuned import FinetunedProvider
from .providers.mock import MockProvider
from .providers.vllm import VllmProvider


def get_provider() -> DocdeltaProvider:
    """Return the provider implementation selected by env.LLM_PROVIDER."""
    if env.LLM_PROVIDER == "finetuned":
        return FinetunedProvider()
    elif env.LLM_PROVIDER == "vllm":
        return VllmProvider()
    return MockProvider()

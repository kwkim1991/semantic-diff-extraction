"""Environment configuration for the Wiki Workspace backend.

Single source of truth for env vars. Values are read once at import time via
`dotenv.load_dotenv()` and exposed as attributes on the `env` singleton.
Do not read `os.environ` directly elsewhere — go through `env` so the PoC
behavior matches the docs/architecture decision (fail-fast, no surprise reads).

Secrets (`GEMINI_API_KEY`, `FINETUNED_API_KEY`, `VLLM_API_KEY`) are never
logged or echoed in API responses.
"""

from __future__ import annotations

import os
from typing import Literal, Optional, cast

from dotenv import load_dotenv

load_dotenv()


_PROVIDER_VALUES: tuple[str, ...] = ("mock", "finetuned", "vllm")


def _read_provider() -> Literal["mock", "finetuned", "vllm"]:
    """Read LLM_PROVIDER with a safe fallback to "mock" on invalid values.

    Rationale (see `_workspace/02_architect_decision.md` §7.2): a typo in
    `.env` should not prevent the PoC server from booting — fall back to
    the safe default.
    """
    val = os.environ.get("LLM_PROVIDER", "mock")
    if val not in _PROVIDER_VALUES:
        val = "mock"
    return cast(Literal["mock", "finetuned", "vllm"], val)


class Env:
    """Container for runtime environment values.

    All defaults match `.env.example` and _workspace/02_architect_decision.md §6 / §7.
    """

    PORT: int = int(os.environ.get("PORT", "3001"))
    CORS_ORIGIN: str = os.environ.get("CORS_ORIGIN", "http://localhost:3000")
    GEMINI_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY") or None

    # Provider abstraction for /api/ai/docdelta (2026-04-22 refactor).
    LLM_PROVIDER: Literal["mock", "finetuned", "vllm"] = _read_provider()
    FINETUNED_API_URL: Optional[str] = os.environ.get("FINETUNED_API_URL") or None
    FINETUNED_API_KEY: Optional[str] = os.environ.get("FINETUNED_API_KEY") or None
    FINETUNED_TIMEOUT_SEC: int = int(os.environ.get("FINETUNED_TIMEOUT_SEC", "30"))

    # vLLM provider (2026-04-22). See _workspace/02_architect_decision.md §9.
    # Note: `str | None` is used here (vs sibling `Optional[str]`) to satisfy
    # ruff UP045; existing Optional[str] lines above are pre-existing state.
    VLLM_ENDPOINT: str | None = os.environ.get("VLLM_ENDPOINT") or None
    VLLM_MODEL: str = os.environ.get("VLLM_MODEL", "vllmlora")
    VLLM_API_KEY: str = os.environ.get("VLLM_API_KEY", "EMPTY")
    HF_TOKENIZER: str = os.environ.get(
        "HF_TOKENIZER", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
    )


env = Env()

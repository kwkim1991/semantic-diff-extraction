#!/usr/bin/env python3
"""vLLM 엔드포인트로 diff 추출 inference 수행하는 모듈.

기본 사용:

    from finetune.infer_diff import get_diff

    result = get_diff(
        known_docs=["기존 문서1 본문", "기존 문서2 본문"],
        new_doc="신규 문서 본문",
        vllm_endpoint="http://localhost:9983/v1",   # or env VLLM_ENDPOINT
        vllm_model="vllmlora",                       # or env VLLM_MODEL
    )
    # -> {"new": [str, ...], "conflict": [{known_text, new_text, reason}, ...]}

환경변수:
    VLLM_ENDPOINT, VLLM_MODEL, VLLM_API_KEY, HF_TOKENIZER
    (키워드 인자가 환경변수보다 우선)

동작 개요
    1) known_docs/new_doc 을 학습 스키마(`known_docs: List[List[Doc]]`,
       `new_doc: List[Doc]`) 구조로 감싸고 prompt_text.format_prompt_text 로
       plain-text 프롬프트 생성 (학습과 동일 포맷).
    2) HF tokenizer 의 apply_chat_template(enable_thinking=False) 로 감싸서
       `<|im_start|>assistant\\n<think></think>\\n` 까지 프리픽스를 만든다.
    3) OpenAI SDK → vLLM `/v1/completions` 호출. `extra_body={"guided_json": schema}`
       로 출력이 반드시 DiffOutput 스키마를 만족하게 강제.
    4) json.loads 해서 dict 반환.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from pydantic import BaseModel, Field

# finetune/ 디렉토리 외부에서 import 될 때도 prompt_text 를 찾도록 sys.path 보강.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from prompt_text import format_prompt_text  # noqa: E402


DEFAULT_TOKENIZER = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
DEFAULT_VLLM_MODEL = "vllmlora"
DEFAULT_API_KEY = "EMPTY"


class Conflict(BaseModel):
    known_text: str = Field(description="Substring of a KNOWN_DOC")
    new_text: str = Field(description="Substring of NEW_DOC contradicting known_text")
    reason: str = Field(description="One-line reason")


class DiffOutput(BaseModel):
    new: list[str] = Field(default_factory=list)
    conflict: list[Conflict] = Field(default_factory=list)


# --- 캐시 (같은 프로세스에서 여러 번 호출 시 tokenizer / client 를 재사용) ---
_tokenizer_cache: dict[str, Any] = {}
_client_cache: dict[tuple[str, str], Any] = {}
_schema_cache: dict[str, dict] = {}


def _get_tokenizer(name: str):
    cached = _tokenizer_cache.get(name)
    if cached is not None:
        return cached
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
    _tokenizer_cache[name] = tok
    return tok


def _get_client(endpoint: str, api_key: str):
    key = (endpoint, api_key)
    cached = _client_cache.get(key)
    if cached is not None:
        return cached
    from openai import OpenAI

    client = OpenAI(base_url=endpoint, api_key=api_key or DEFAULT_API_KEY)
    _client_cache[key] = client
    return client


def _get_schema() -> dict:
    if "default" not in _schema_cache:
        _schema_cache["default"] = DiffOutput.model_json_schema()
    return _schema_cache["default"]


def _build_prompt(known_docs: list[str], new_doc: str, tokenizer) -> str:
    """학습 때와 동일한 plain-text prompt + non-thinking chat template."""
    # 학습 schema v2 와 동일 shape 로 감싼다 (단일 그룹).
    payload = {
        "known_docs": [[{"context": s} for s in known_docs]],
        "new_doc": [{"context": new_doc}],
    }
    user_text = format_prompt_text(json.dumps(payload, ensure_ascii=False))
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": user_text}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def get_diff(
    known_docs: list[str],
    new_doc: str,
    *,
    vllm_endpoint: str | None = None,
    vllm_model: str | None = None,
    vllm_api_key: str | None = None,
    tokenizer_source: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    top_p: float = 1.0,
) -> dict:
    """vLLM 엔드포인트를 통해 문서 diff 를 추출한다.

    Args:
        known_docs: 기존 문서 본문 리스트.
        new_doc: 신규 문서 본문.
        vllm_endpoint: OpenAI 호환 vLLM URL (예 "http://localhost:9983/v1").
            미지정 시 env VLLM_ENDPOINT 사용. 둘 다 없으면 ValueError.
        vllm_model: vLLM 에 등록된 모델 이름. 미지정 시 env VLLM_MODEL, 없으면 "vllmlora".
        vllm_api_key: OpenAI SDK placeholder 키. 미지정 시 env VLLM_API_KEY, 없으면 "EMPTY".
        tokenizer_source: chat-template 포맷팅에 쓸 HF repo id / 로컬 경로.
            미지정 시 env HF_TOKENIZER, 없으면 Nemotron 3 Nano 기본값.
        max_tokens / temperature / top_p: generation hyperparameters.
            기본값은 greedy (temperature=0).

    Returns:
        dict with keys `new: list[str]` and `conflict: list[dict]` (각 conflict 는
        `known_text / new_text / reason` 필드). guided_json 으로 스키마를 강제하므로
        항상 위 형태를 만족한다.
    """
    endpoint = vllm_endpoint or os.environ.get("VLLM_ENDPOINT")
    if not endpoint:
        raise ValueError(
            "vLLM endpoint 가 지정되지 않았습니다. vllm_endpoint 인자 또는 "
            "VLLM_ENDPOINT 환경변수를 설정하세요."
        )
    model = vllm_model or os.environ.get("VLLM_MODEL") or DEFAULT_VLLM_MODEL
    api_key = vllm_api_key or os.environ.get("VLLM_API_KEY") or DEFAULT_API_KEY
    tok_src = tokenizer_source or os.environ.get("HF_TOKENIZER") or DEFAULT_TOKENIZER

    tokenizer = _get_tokenizer(tok_src)
    prompt = _build_prompt(known_docs, new_doc, tokenizer)
    schema_dict = _get_schema()
    client = _get_client(endpoint, api_key)

    resp = client.completions.create(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        extra_body={"guided_json": schema_dict},
    )
    text = resp.choices[0].text or ""
    return json.loads(text)


if __name__ == "__main__":
    # Smoke test: `python finetune/infer_diff.py` 로 간단한 샘플 실행.
    # VLLM_ENDPOINT 등은 환경변수에서 로드.
    sample_result = get_diff(
        known_docs=[
            "회의일시: 2025-03-10. 안건: 신규 프로젝트 킥오프. "
            "결론: 4/1 착수, 박경태 PM 지정. 개발 인력 3명 배정.",
            "회의일시: 2025-03-17. 안건: 리소스 재점검. "
            "결론: 개발 인력 3명 고정, 추가 채용은 없음.",
        ],
        new_doc=(
            "회의일시: 2025-03-24. 안건: 프로젝트 킥오프 일정. "
            "결론: 4/15 로 착수일 연기, PM 은 김주은으로 변경. "
            "개발 인력 5명으로 증원. 별도 QA 인력 1명 신규 배정."
        ),
    )
    print(json.dumps(sample_result, ensure_ascii=False, indent=2))

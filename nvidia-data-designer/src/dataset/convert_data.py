"""
doc_scheme JSONL의 각 scheme에 대해 output(new + conflict)을 OpenAI API로 생성.

- Anthropic 버전(generate_doc_output.py)과 동일한 시스템 프롬프트/스키마/재개 로직 사용.
- Structured Outputs(json_schema, strict=True)로 JSON 형식 보장.
- OpenAI는 1024 토큰 이상 프리픽스를 자동 캐싱하므로 별도 cache_control 지시 불필요.

사용법:
    pip install openai tqdm
    export OPENAI_API_KEY=sk-...

    python generate_doc_output_openai.py \
        --input  out/validation(yes,no)_scheme.jsonl \
        --output out/validation(yes,no)_scheme_filled.jsonl

    # 모델/동시성 조정, 샘플 N개만
    python generate_doc_output_openai.py --input ... --output ... \
        --model gpt-4.1 --concurrency 16 --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import openai
from tqdm.asyncio import tqdm as atqdm


SYSTEM_PROMPT = """당신은 한국 행정·법률·정책 문서를 정밀하게 비교·대조하는 문서 분석 전문가입니다. 주어진 문서들을 대조하여 아래 두 가지를 추출해 JSON으로 반환합니다.

[과제 1 — new]
new_doc 안에서 known_docs 어디에도 명시되지 않은 새로운 내용(사실·수치·날짜·금액·고유명사·조항·결론·판단 등)을 짧은 문장 리스트로 제시합니다.
- 판정 기준: known_docs 전체와 대조하여 '해당 내용이 전혀 언급되지 않은 경우'에만 new로 인정합니다.
- 단순 paraphrase, 용어·문체 차이, 동일 사실의 다른 서술, 일반적 배경 설명은 제외합니다.
- 항목은 라벨이 있는 짧은 문장을 권장합니다 (예: "배경: 문서 수동 분류에 연간 8,000 man-hour 투입").
- 정말로 새로운 내용이 없으면 빈 리스트([])를 반환합니다. 억지로 채우지 마세요.

[과제 2 — conflict]
이 과제의 비교 대상은 mutation_doc 각 항목의 context(원본)와 mutation_context(의도적 변조본) 쌍입니다.
mutation_context는 context를 기반으로 만들어졌으며, 다음과 같은 구조입니다:
- (A) 전반에 걸친 경미한 paraphrase — 동의어·조사·어미·표현의 미세 변경.
- (B) 1~2곳의 '사실 교체' — 수치·날짜·금액·기간·요건·결론·판단의 값 자체가 원본과 다른 값으로 교체됨.

→ 여기서 찾아야 할 conflict는 오직 (B)의 '사실 교체' 지점입니다. 각 mutation_doc 항목에는 대체로 1~2개의 사실 교체가 존재하므로, 이를 꼼꼼히 찾아 모두 기록하세요.

필드:
- doc_id: 해당 mutation_doc 항목의 doc_id.
- known_text: context(원본)에서 충돌 구간의 원문을 그대로 최소 범위로 인용. 원본 값이 드러나야 함.
- new_text: mutation_context(변조본)에서 대응되는 충돌 구간의 원문을 그대로 최소 범위로 인용. 교체된 값이 드러나야 함.
- reason: 무엇이 어떻게 교체되었는지 한 문장으로. 예: "금액이 5억원에서 3억원으로 변경", "결론이 적법에서 위법으로 반전".
- severity: 다음 기준으로 low / medium / high 중 하나.
  * high  : 허용↔금지, 결론·판단의 반전, 법적 요건·상한선·의무의 값 변경.
  * medium: 수치·기간·요건·절차의 값 교체, 적용 범위·대상의 변경.
  * low   : 경미한 표기/세부 값 변경.

[중요 — paraphrase vs 사실 교체 구분]
mutation_context는 의도적으로 어휘·표현이 paraphrase되어 있습니다. 따라서 다음은 conflict가 아닙니다:
- "살펴보다" ↔ "검토하다" 같은 동의어 교체.
- "-며" ↔ "-고" 같은 어미·조사 변경.
- 수동/능동 전환, 명사화/동사화.
- 같은 뜻의 다른 표현으로 다시 쓴 문장.
오직 '값 자체가 다른 사실'만 conflict로 인정합니다:
- 숫자·금액·비율이 원본과 다른 값 (예: 5억원 → 3억원).
- 날짜·연도·기간의 값이 다름.
- 결론·판단이 반전됨 (적법 ↔ 위법, 허용 ↔ 금지).
- 요건·상한·기준의 값이 교체됨.
- 절차·주체의 구체 값이 다름.

[엄수 원칙]
- 문서 내용에만 근거. 외부 지식·추측 금지.
- known_text / new_text는 각 원문에서 그대로 인용 (줄임표·패러프레이즈·가공 금지, 값이 확인 가능한 최소 구간).
- conflict의 doc_id는 반드시 mutation_doc의 doc_id. 그 외 값은 금지.
- 각 mutation_doc 항목에 보통 1~2개의 사실 교체가 있으므로 빠뜨리지 말고 모두 기록. 하지만 명백한 값 교체가 정말 없다면 억지로 만들지 않습니다(그 항목은 0건 허용).

[출력 형식]
JSON 객체 하나만 반환. 코드블럭 표시(```)·머리말·설명 등 다른 텍스트 금지."""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "new": {
            "type": "array",
            "description": "new_doc에서 known_docs 어디에도 없는 새로운 내용. 라벨이 있는 짧은 문장 권장.",
            "items": {"type": "string"},
        },
        "conflict": {
            "type": "array",
            "description": "mutation_doc 각 항목의 context(원본)와 mutation_context(변조본) 사이의 사실 교체 지점. 각 항목당 1~2건 기대, 전체 0~4건.",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "mutation_doc 항목의 doc_id. 그 외 값은 금지.",
                    },
                    "known_text": {
                        "type": "string",
                        "description": "context(원본)에서 충돌 구간 원문 인용 (최소 범위, 원본 값이 드러나도록).",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "mutation_context(변조본)에서 대응되는 충돌 구간 원문 인용 (최소 범위, 교체된 값이 드러나도록).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "충돌 사유 한 문장.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["doc_id", "known_text", "new_text", "reason", "severity"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["new", "conflict"],
    "additionalProperties": False,
}


def format_doc(doc: dict) -> str:
    return f"[doc_id: {doc['doc_id']}]\n{doc['context']}"


def build_user_message(scheme: dict) -> str:
    known_parts: list[str] = []
    for i, group in enumerate(scheme["known_docs"], start=1):
        group_text = "\n\n".join(format_doc(d) for d in group)
        known_parts.append(f"--- known_docs 그룹 {i} ---\n{group_text}")
    known_block = "\n\n".join(known_parts)

    new_doc_block = "\n\n".join(format_doc(d) for d in scheme["new_doc"])

    mutation_parts: list[str] = []
    for i, md in enumerate(scheme["mutation_doc"], start=1):
        mutation_parts.append(
            f"--- mutation_doc 항목 {i} ---\n"
            f"doc_id: {md['doc_id']}\n\n"
            f"[context — 원본]\n{md['context']}\n\n"
            f"[mutation_context — 의도적 변조본 (1~2곳 사실 교체 포함)]\n{md['mutation_context']}"
        )
    mutation_block = "\n\n".join(mutation_parts)

    return (
        "[과제 1 — new 에 사용할 자료]\n"
        f"[known_docs]\n{known_block}\n\n"
        f"[new_doc]\n{new_doc_block}\n\n"
        "=====\n\n"
        "[과제 2 — conflict 에 사용할 자료]\n"
        "아래 각 항목에는 context(원본)와 mutation_context(변조본)가 쌍으로 주어집니다. "
        "mutation_context는 context를 바탕으로 어휘·표현이 paraphrase되어 있고, "
        "그 안에 1~2곳의 '사실 교체(수치·날짜·결론 등의 값 변경)'가 의도적으로 삽입되어 있습니다. "
        "이 사실 교체 지점이 곧 conflict 입니다. paraphrase 차이는 무시하고 오직 값 교체만 기록하세요.\n\n"
        f"{mutation_block}\n\n"
        "=====\n\n"
        "시스템 프롬프트의 지시에 따라 new와 conflict를 추출해 JSON 하나로 반환하세요."
    )


def scheme_id(scheme: dict) -> str:
    first_doc_id = scheme["known_docs"][0][0]["doc_id"]
    return f"{scheme['source_id']}::{first_doc_id}"


def load_processed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(scheme_id(json.loads(line)))
            except Exception:
                continue
    return done


def read_schemes(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def validate_output(scheme: dict, data: dict) -> tuple[bool, str]:
    """conflict의 doc_id가 mutation_doc 범위 안에 있는지 등 사후 검증."""
    mutation_ids = {d["doc_id"] for d in scheme["mutation_doc"]}
    for i, c in enumerate(data.get("conflict", [])):
        if c["doc_id"] not in mutation_ids:
            return False, f"conflict[{i}].doc_id={c['doc_id']!r} not in mutation_doc {sorted(mutation_ids)}"
    return True, ""


async def generate_one(
    client: openai.AsyncOpenAI,
    scheme: dict,
    model: str,
    sem: asyncio.Semaphore,
    max_tokens: int,
    max_retries: int = 3,
) -> dict[str, Any]:
    user_msg = build_user_message(scheme)

    async with sem:
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    max_completion_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "doc_output",
                            "schema": OUTPUT_SCHEMA,
                            "strict": True,
                        },
                    },
                )
                choice = response.choices[0]
                if choice.finish_reason == "length":
                    last_err = ValueError("response truncated (finish_reason=length)")
                    await asyncio.sleep(1)
                    continue
                text = choice.message.content
                if text is None:
                    refusal = getattr(choice.message, "refusal", None)
                    last_err = ValueError(f"empty content (refusal={refusal!r})")
                    await asyncio.sleep(1)
                    continue
                data = json.loads(text)
                ok, err = validate_output(scheme, data)
                if not ok:
                    last_err = ValueError(err)
                    await asyncio.sleep(1)
                    continue
                return {"ok": True, "output": data, "usage": response.usage}
            except (openai.RateLimitError, openai.APIStatusError) as e:
                last_err = e
                if isinstance(e, openai.APIStatusError) and e.status_code < 500:
                    break
                await asyncio.sleep(2 ** attempt)
            except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as e:
                last_err = e
                await asyncio.sleep(1)

        return {"ok": False, "error": repr(last_err)}


async def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    error_path = output_path.with_suffix(".errors.jsonl")

    if not input_path.exists():
        sys.exit(f"입력 파일 없음: {input_path}")

    all_schemes = read_schemes(input_path)
    processed = load_processed_ids(output_path)
    todo = [s for s in all_schemes if scheme_id(s) not in processed]
    if args.limit:
        todo = todo[: args.limit]

    print(
        f"전체 {len(all_schemes)}개 중 {len(processed)}개 처리됨, {len(todo)}개 남음",
        file=sys.stderr,
    )
    if not todo:
        print("모두 처리 완료.", file=sys.stderr)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = openai.AsyncOpenAI()
    sem = asyncio.Semaphore(args.concurrency)

    out_f = output_path.open("a", encoding="utf-8")
    err_f = error_path.open("a", encoding="utf-8")
    write_lock = asyncio.Lock()

    total_input = 0
    total_output = 0
    total_cache_read = 0
    success = 0
    failure = 0

    async def worker(scheme: dict) -> None:
        nonlocal total_input, total_output, total_cache_read, success, failure
        result = await generate_one(client, scheme, args.model, sem, args.max_tokens)
        async with write_lock:
            if result["ok"]:
                filled = dict(scheme)
                filled["output"] = result["output"]
                out_f.write(json.dumps(filled, ensure_ascii=False) + "\n")
                out_f.flush()
                usage = result["usage"]
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                cached = 0
                details = getattr(usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = getattr(details, "cached_tokens", 0) or 0
                total_input += max(prompt_tokens - cached, 0)
                total_output += completion_tokens
                total_cache_read += cached
                success += 1
            else:
                err_f.write(
                    json.dumps(
                        {"scheme_id": scheme_id(scheme), "error": result["error"]},
                        ensure_ascii=False,
                    ) + "\n"
                )
                err_f.flush()
                failure += 1

    tasks = [worker(s) for s in todo]
    await atqdm.gather(*tasks, desc="output 생성 중")

    out_f.close()
    err_f.close()

    print(f"\n성공 {success} / 실패 {failure}", file=sys.stderr)
    print(f"토큰 — 입력(uncached): {total_input:,}  출력: {total_output:,}", file=sys.stderr)
    print(f"캐시 — 읽기: {total_cache_read:,}", file=sys.stderr)
    if failure:
        print(f"실패 로그: {error_path}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(
        description="doc_scheme JSONL의 output(new+conflict)을 OpenAI API로 생성"
    )
    p.add_argument("--input", required=True, help="입력 JSONL 경로")
    p.add_argument("--output", required=True, help="출력 JSONL 경로 (이미 있으면 재개)")
    p.add_argument("--model", default="gpt-4.1", help="모델 ID (예: gpt-4.1, gpt-4.1-mini, gpt-4o)")
    p.add_argument("--concurrency", type=int, default=8, help="동시 요청 수 (기본 8)")
    p.add_argument("--max-tokens", type=int, default=4096, help="응답 max_completion_tokens")
    p.add_argument("--limit", type=int, default=0, help="처리할 최대 scheme 수 (0=전체)")
    args = p.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

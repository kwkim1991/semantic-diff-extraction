"""NVIDIA Data Designer로 validation.csv → validation.jsonl 형식 변환.

파이프라인:
1. Pre-process: CSV를 source_id 그룹으로 묶어 scheme 단위 seed parquet 생성
   - 한 scheme = 연속된 10개 문서 (known_docs 3+3+2 = 8개, new_doc 2개)
   - mutation_doc = known_docs 중 임의 2건 (context만 복사, mutation_context는 이후 생성)
2. Data Designer: vLLM(localhost:5000/v1, nano) 엔드포인트로 두 LLM 컬럼 생성
   - mutations: mutation_doc 각 항목의 mutation_context (paraphrase + 1~2개 사실 교체)
   - output: {new, conflict} — convert_data.py의 시스템 프롬프트/스키마 그대로
3. Post-process: 생성 결과를 최종 nested JSONL로 재조립

사용법:
    python generate_with_datadesigner.py \\
        --input  src/dataset/validation1.csv \\
        --output src/dataset/validation1_generated.jsonl \\
        --limit 2            # 테스트용 샘플 N개만
"""
from __future__ import annotations
# python generate_with_datadesigner.py --input  src/dataset/validation1.csv --output src/dataset/validation1_generated.jsonl --limit 2
import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from data_designer.essentials import (
    ChatCompletionInferenceParams,
    DataDesigner,
    DataDesignerConfigBuilder,
    LLMStructuredColumnConfig,
    ModelConfig,
    ModelProvider,
)


INSTRUCTION = (
    "주어진 기존 문서들(known_docs)을 기준으로 신규 문서(new_doc)에서 다음을 추출하세요. "
    "new: 기존 문서들 어디에도 없는 새로운 내용. "
    "conflict: 기존 문서들 중 어느 하나와 충돌하는 내용. "
    "기존 문서들에 이미 있는 내용이거나 단순 paraphrase는 출력하지 않습니다."
)


MUTATION_SYSTEM_PROMPT = """당신은 한국 행정·법률·정책 문서를 변조하는 전문가입니다. 주어진 각 context에 대해 mutation_context를 생성합니다.

[변조 방식]
(A) 전반에 걸친 경미한 paraphrase — 동의어·조사·어미·표현의 미세 변경.
(B) 1~2곳의 '사실 교체' — 수치·날짜·금액·기간·요건·결론·판단의 값 자체를 원본과 다른 값으로 교체.

[원칙]
- 문장 구조·흐름·길이는 원본과 유사하게 유지.
- 사실 교체는 실제 값을 다른 그럴듯한 값으로 교체 (예: 5억원 → 3억원, 2020년 → 2019년, 적법 → 위법).
- 교체된 값은 명백히 서로 다른 값이어야 함(동일 표현·오타 수준 금지).
- 문서의 다른 부분은 paraphrase 수준만 변경.
- 원문의 doc_id는 그대로 유지.

[출력 형식]
JSON 객체 하나만 반환. 각 입력 항목(doc_id)에 대응하는 mutation_context 문자열을 포함."""


OUTPUT_SYSTEM_PROMPT = """당신은 한국 행정·법률·정책 문서를 정밀하게 비교·대조하는 문서 분석 전문가입니다. 주어진 문서들을 대조하여 아래 두 가지를 추출해 JSON으로 반환합니다.

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


class MutationItem(BaseModel):
    doc_id: str
    mutation_context: str


class MutationsOutput(BaseModel):
    mutations: list[MutationItem] = Field(description="입력 mutation 대상 각각에 대한 변조된 문맥")


class ConflictItem(BaseModel):
    doc_id: str = Field(description="mutation_doc 항목의 doc_id. 그 외 값은 금지.")
    known_text: str = Field(description="context(원본)에서 충돌 구간 원문 인용 (최소 범위)")
    new_text: str = Field(description="mutation_context(변조본)에서 대응되는 충돌 구간 원문 인용 (최소 범위)")
    reason: str = Field(description="충돌 사유 한 문장")
    severity: str = Field(description="low / medium / high 중 하나")


class NewConflictOutput(BaseModel):
    new: list[str] = Field(description="new_doc에서 known_docs 어디에도 없는 새로운 내용")
    conflict: list[ConflictItem] = Field(description="mutation_doc 각 항목의 사실 교체 지점")


def format_doc(doc: dict[str, Any]) -> str:
    return f"[doc_id: {doc['doc_id']}]\n{doc['context']}"


def format_known_docs(known_docs: list[list[dict]]) -> str:
    parts = []
    for i, group in enumerate(known_docs, start=1):
        group_text = "\n\n".join(format_doc(d) for d in group)
        parts.append(f"--- known_docs 그룹 {i} ---\n{group_text}")
    return "\n\n".join(parts)


def format_new_doc(new_doc: list[dict]) -> str:
    return "\n\n".join(format_doc(d) for d in new_doc)


def format_mutation_targets(mutation_doc: list[dict]) -> str:
    """mutation_context 생성 입력용: doc_id + context만."""
    parts = []
    for i, md in enumerate(mutation_doc, start=1):
        parts.append(
            f"--- mutation 대상 {i} ---\n"
            f"doc_id: {md['doc_id']}\n\n"
            f"[context — 원본]\n{md['context']}"
        )
    return "\n\n".join(parts)


def format_mutation_pairs(mutation_doc: list[dict]) -> str:
    """conflict 판정 입력용: doc_id + context + mutation_context 3종."""
    parts = []
    for i, md in enumerate(mutation_doc, start=1):
        parts.append(
            f"--- mutation_doc 항목 {i} ---\n"
            f"doc_id: {md['doc_id']}\n\n"
            f"[context — 원본]\n{md['context']}\n\n"
            f"[mutation_context — 변조본]\n{md['mutation_context']}"
        )
    return "\n\n".join(parts)


def build_schemes_from_csv(
    csv_path: Path,
    docs_per_scheme: int = 10,
    known_group_sizes: tuple[int, ...] = (3, 3, 2),
    new_doc_count: int = 2,
    mutation_doc_count: int = 2,
    limit: int | None = None,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """CSV → scheme dict 리스트. 각 scheme은 source_id당 연속 10개 문서로 구성."""
    assert sum(known_group_sizes) + new_doc_count == docs_per_scheme, (
        f"known_group_sizes({sum(known_group_sizes)}) + new_doc_count({new_doc_count}) "
        f"must equal docs_per_scheme({docs_per_scheme})"
    )

    df = pd.read_csv(csv_path)
    df.columns = [c.lstrip("﻿") for c in df.columns]

    rng = random.Random(seed)
    schemes: list[dict[str, Any]] = []

    for source_id, grp in df.groupby("source_id", sort=False):
        rows = grp.reset_index(drop=True)
        n = len(rows)
        for start in range(0, n - docs_per_scheme + 1, docs_per_scheme):
            chunk = rows.iloc[start:start + docs_per_scheme]

            docs = [
                {"doc_id": r["context_id"], "context": r["context"]}
                for _, r in chunk.iterrows()
            ]
            known_flat = docs[:sum(known_group_sizes)]
            new_doc = docs[sum(known_group_sizes):]

            known_docs: list[list[dict]] = []
            offset = 0
            for sz in known_group_sizes:
                known_docs.append(known_flat[offset:offset + sz])
                offset += sz

            mutation_picks = rng.sample(known_flat, k=min(mutation_doc_count, len(known_flat)))
            mutation_doc = [
                {"doc_id": d["doc_id"], "context": d["context"]}
                for d in mutation_picks
            ]

            schemes.append({
                "source_id": str(source_id),
                "instruction": INSTRUCTION,
                "known_docs": known_docs,
                "new_doc": new_doc,
                "mutation_doc": mutation_doc,
            })

            if limit is not None and len(schemes) >= limit:
                return schemes

    return schemes


def schemes_to_seed_dataframe(schemes: list[dict]) -> pd.DataFrame:
    """Data Designer seed로 쓸 DataFrame (각 row = scheme 1개).

    JSON 문자열은 post-processing에서 복원, pre-rendered 텍스트는 LLM 프롬프트에서 {{ ... }}로 참조."""
    rows = []
    for s in schemes:
        rows.append({
            "source_id": s["source_id"],
            "known_docs_json": json.dumps(s["known_docs"], ensure_ascii=False),
            "new_doc_json": json.dumps(s["new_doc"], ensure_ascii=False),
            "mutation_doc_json": json.dumps(s["mutation_doc"], ensure_ascii=False),
            "known_docs_text": format_known_docs(s["known_docs"]),
            "new_doc_text": format_new_doc(s["new_doc"]),
            "mutation_targets_text": format_mutation_targets(s["mutation_doc"]),
        })
    return pd.DataFrame(rows)


def build_config(model_alias: str, served_model_name: str) -> DataDesignerConfigBuilder:
    """Data Designer config: 2개의 LLM 컬럼(mutations, output)을 추가."""
    model = ModelConfig(
        alias=model_alias,
        model=served_model_name,
        provider="vllm-local",
        inference_parameters=ChatCompletionInferenceParams(
            temperature=0.4,
            top_p=0.95,
            max_tokens=6144,
            max_parallel_requests=4,
        ),
    )

    builder = DataDesignerConfigBuilder(model_configs=[model])

    builder.add_column(LLMStructuredColumnConfig(
        name="mutations",
        model_alias=model_alias,
        system_prompt=MUTATION_SYSTEM_PROMPT,
        prompt=(
            "다음 mutation 대상 각각에 대해 mutation_context를 생성하세요.\n"
            "각 항목의 doc_id를 그대로 유지하고, mutation_context는 paraphrase + 1~2곳 사실 교체 규칙을 따릅니다.\n\n"
            "{{ mutation_targets_text }}"
        ),
        output_format=MutationsOutput,
    ))

    builder.add_column(LLMStructuredColumnConfig(
        name="output",
        model_alias=model_alias,
        system_prompt=OUTPUT_SYSTEM_PROMPT,
        prompt=(
            "[과제 1 — new 에 사용할 자료]\n"
            "[known_docs]\n"
            "{{ known_docs_text }}\n\n"
            "[new_doc]\n"
            "{{ new_doc_text }}\n\n"
            "=====\n\n"
            "[과제 2 — conflict 에 사용할 자료]\n"
            "아래 각 항목에는 context(원본)와 mutation_context(변조본)가 쌍으로 주어집니다. "
            "mutation_context는 context를 바탕으로 어휘·표현이 paraphrase되어 있고, "
            "그 안에 1~2곳의 '사실 교체(수치·날짜·결론 등의 값 변경)'가 의도적으로 삽입되어 있습니다. "
            "이 사실 교체 지점이 곧 conflict 입니다. paraphrase 차이는 무시하고 오직 값 교체만 기록하세요.\n\n"
            "{% for m in mutations.mutations %}"
            "--- mutation_doc 항목 {{ loop.index }} ---\n"
            "doc_id: {{ m.doc_id }}\n\n"
            "[mutation_context — 변조본]\n{{ m.mutation_context }}\n\n"
            "{% endfor %}"
            "(각 항목의 [context — 원본]은 known_docs 내에서 동일한 doc_id의 문서를 참조하세요.)\n\n"
            "=====\n\n"
            "시스템 프롬프트의 지시에 따라 new와 conflict를 추출해 JSON 하나로 반환하세요."
        ),
        output_format=NewConflictOutput,
    ))

    return builder


def _pyify(x: Any) -> Any:
    """numpy/pandas → plain Python (list/dict/scalar). JSON 직렬화 대비."""
    if isinstance(x, np.ndarray):
        return [_pyify(v) for v in x.tolist()]
    if isinstance(x, (list, tuple)):
        return [_pyify(v) for v in x]
    if isinstance(x, dict):
        return {k: _pyify(v) for k, v in x.items()}
    if isinstance(x, np.generic):
        return x.item()
    return x


def assemble_final_record(row: dict) -> dict:
    """Data Designer 출력 row → 최종 JSONL record."""
    known_docs = json.loads(row["known_docs_json"])
    new_doc = json.loads(row["new_doc_json"])
    mutation_doc_src = json.loads(row["mutation_doc_json"])

    mutations_val = _pyify(row["mutations"])
    if isinstance(mutations_val, str):
        mutations_val = json.loads(mutations_val)
    mut_list = mutations_val.get("mutations", []) if isinstance(mutations_val, dict) else []
    mut_by_id = {m["doc_id"]: m["mutation_context"] for m in mut_list}

    mutation_doc = [
        {
            "doc_id": d["doc_id"],
            "context": d["context"],
            "mutation_context": mut_by_id.get(d["doc_id"], ""),
        }
        for d in mutation_doc_src
    ]

    output_val = _pyify(row["output"])
    if isinstance(output_val, str):
        output_val = json.loads(output_val)

    return {
        "source_id": row["source_id"],
        "instruction": INSTRUCTION,
        "known_docs": known_docs,
        "new_doc": new_doc,
        "mutation_doc": mutation_doc,
        "output": output_val,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Data Designer로 validation 데이터 생성")
    p.add_argument("--input", required=True, help="입력 CSV (validation*.csv)")
    p.add_argument("--output", required=True, help="출력 JSONL 경로")
    p.add_argument("--limit", type=int, default=0, help="처리할 scheme 최대 수 (0=전체)")
    p.add_argument("--endpoint", default="http://localhost:5000/v1", help="vLLM OpenAI 호환 엔드포인트")
    p.add_argument("--served-model-name", default="vllmlora",
                   help="vLLM 서버의 --served-model-name (/v1/models id)")
    p.add_argument("--model-alias", default="nemotron", help="Data Designer 내부 모델 alias")
    p.add_argument("--artifact-path", default="./dd_artifacts", help="Data Designer artifact 저장 경로")
    p.add_argument("--dataset-name", default="validation_generated", help="artifact 내 dataset 이름")
    p.add_argument("--preview", action="store_true", help="preview 모드 (디스크 저장 없이 메모리)")
    p.add_argument("--seed-parquet", default=None, help="중간 seed parquet 경로 (기본: output 옆)")
    args = p.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        sys.exit(f"입력 파일 없음: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    seed_parquet = Path(args.seed_parquet) if args.seed_parquet else output_path.with_suffix(".seed.parquet")

    print(f"[1/4] CSV → scheme 변환: {input_path}", file=sys.stderr)
    schemes = build_schemes_from_csv(
        input_path,
        limit=(args.limit or None),
    )
    print(f"  → scheme {len(schemes)}개", file=sys.stderr)
    if not schemes:
        sys.exit("scheme이 비어있습니다. CSV 내용을 확인하세요.")

    print(f"[2/4] seed parquet 쓰기: {seed_parquet}", file=sys.stderr)
    seed_df = schemes_to_seed_dataframe(schemes)
    seed_df.to_parquet(seed_parquet, index=False)

    print(f"[3/4] Data Designer 구성 + 생성 (endpoint={args.endpoint})", file=sys.stderr)
    vllm_provider = ModelProvider(
        name="vllm-local",
        endpoint=args.endpoint,
        provider_type="openai",
        api_key="not-used",
    )
    builder = build_config(args.model_alias, args.served_model_name)
    seed_ref = DataDesigner.make_seed_reference_from_file(seed_parquet)
    builder.with_seed_dataset(seed_ref)

    dd = DataDesigner(
        artifact_path=args.artifact_path,
        model_providers=[vllm_provider],
    )

    n = len(schemes)
    if args.preview:
        result_df = dd.preview(builder, num_records=n).dataset
    else:
        results = dd.create(builder, num_records=n, dataset_name=args.dataset_name)
        result_df = results.load_dataset()

    print(f"  → 생성 완료 ({len(result_df)} rows, cols={list(result_df.columns)})", file=sys.stderr)

    print(f"[4/4] 최종 JSONL 쓰기: {output_path}", file=sys.stderr)
    with output_path.open("w", encoding="utf-8") as f:
        for _, row in result_df.iterrows():
            rec = assemble_final_record(row.to_dict())
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"완료. {len(result_df)} records → {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

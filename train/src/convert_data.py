#!/usr/bin/env python3
"""Convert our diff-extraction JSONL (schema.json v2) to Megatron-Bridge SFT JSONL.

Input record (from generate_data.py):
    {
      source_id, instruction,
      known_docs: List[List[{doc_id, context}]],
      new_doc:    List[{doc_id, context}],
      output:     {new[], conflict[{known_text, new_text, reason}]},
      _meta: {...}                           # 학습에는 사용 안 함
    }

Output schema (Megatron-Bridge FinetuningDatasetConfig):
    {input: str, output: str}

input 은 schema.json 구조를 그대로 살린 단일 JSON 문자열로 직렬화한다. source_id / _meta
는 학습 신호가 아니므로 input 에서 제외한다.

`--chat-template` 을 주면 HuggingFace tokenizer 의 `apply_chat_template` 을 적용한
텍스트로 input/output 을 split 한다. user content 는 JSON dump 대신 plain text 로
재구성 (prompt_text.format_prompt_text), assistant content 는 JSON string 유지.
non-thinking 모드로 통일하려고 `enable_thinking=False` kwarg 를 템플릿에 전달한다
(지원 안 하는 템플릿에서는 silently ignore 됨).

    user_text  = format_prompt_text(format_input(sample))     # 자연어 프롬프트
    assistant  = format_output(sample)                         # JSON dump (그대로)
    full       = tokenizer.apply_chat_template(
                     [user_text, assistant],
                     tokenize=False, enable_thinking=False)
    prefix     = full[: full.rfind(assistant)]
    suffix     = full[ full.rfind(assistant) + len(assistant) :]
    -> input   = prefix                         (generation prompt 포함)
    -> output  = assistant + suffix             (모델이 학습해야 할 영역)
Megatron-Bridge 가 `prompt_template="{input}{output}"` 로 concat 하면 `full` 과
bit-for-bit 동일해진다.

Layout written (FinetuningDatasetConfig 의 default path resolution `<root>/<split>.jsonl`):
    <out_dir>/training.jsonl
    <out_dir>/validation.jsonl
    <out_dir>/test.jsonl
"""

import argparse
import json
import random
from pathlib import Path

from prompt_text import format_prompt_text


def format_input(sample: dict) -> str:
    """모델에게 줄 입력 — instruction + known_docs + new_doc 을 단일 JSON 으로."""
    payload = {
        "instruction": sample["instruction"],
        "known_docs": sample["known_docs"],
        "new_doc": sample["new_doc"],
    }
    return json.dumps(payload, ensure_ascii=False)


CONFLICT_KEEP_KEYS = ("known_text", "new_text", "reason")


def format_output(sample: dict) -> str:
    out = sample["output"]
    conflicts = [
        {k: c[k] for k in CONFLICT_KEEP_KEYS if k in c}
        for c in out.get("conflict", [])
    ]
    cleaned = {"new": out.get("new", []), "conflict": conflicts}
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def _build_chat_splitter(hf_model: str):
    """tokenizer.apply_chat_template 을 이용해 (user_text, assistant_json) 를
    (prefix, assistant+suffix) 로 split 하는 함수를 돌려준다.

    user content 는 plain text (format_prompt_text 결과), assistant content 는
    JSON dump (format_output 결과) 그대로. non-thinking 모드로 통일.

    prefix 는 inference 시 `apply_chat_template(..., add_generation_prompt=True,
    enable_thinking=False)` 로 얻는 것과 동일해야 한다. bit-for-bit 일치 여부를
    첫 호출 때 한 번 검증한다.
    """
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(hf_model, trust_remote_code=True)

    validated = {"done": False}

    def split(user_text: str, assistant_json: str) -> tuple[str, str]:
        messages_full = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_json},
        ]
        full = tok.apply_chat_template(
            messages_full,
            tokenize=False,
            enable_thinking=False,
        )
        pos = full.rfind(assistant_json)
        if pos < 0:
            raise RuntimeError(
                "apply_chat_template 결과에서 assistant content 를 찾지 못했습니다. "
                "template 이 content 를 그대로 삽입하지 않는 경우(escape/rewrite) 에는 "
                "chat-template 학습 파이프라인을 그대로 쓸 수 없습니다."
            )
        prefix = full[:pos]
        suffix = full[pos + len(assistant_json):]

        if not validated["done"]:
            inference_prefix = tok.apply_chat_template(
                [{"role": "user", "content": user_text}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            if inference_prefix != prefix:
                # 일부 템플릿은 training / inference 에서 닫는 방식이 다를 수 있다.
                # 경고만 출력하고 training-side prefix 를 사용 (inference 쪽이 일관성
                # 깨지면 evaluate.py 에서도 동일 방식으로 맞춰야 함).
                print(
                    "[warn] training prefix != inference add_generation_prompt prefix. "
                    "evaluate.py 의 chat 모드와 분기할 가능성이 있는지 확인 필요."
                )
            validated["done"] = True

        return prefix, assistant_json + suffix

    return split, tok


def split_counts(n: int) -> tuple[int, int, int]:
    if n < 5:
        return n, min(1, n), min(1, n)
    val = max(1, n // 10)
    test = max(1, n // 10)
    return n - val - test, val, test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/sample_10.jsonl")
    parser.add_argument("--output-dir", default="data/sft")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-split", action="store_true",
                        help="Split 없이 input 전체를 <output_dir>/training.jsonl 로 변환")
    parser.add_argument("--chat-template", action="store_true",
                        help="HF tokenizer 의 apply_chat_template 을 적용해 "
                             "input=(user turn + assistant generation prompt), "
                             "output=(assistant content + template suffix) 로 분리.")
    parser.add_argument("--hf-model",
                        default="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
                        help="apply_chat_template 에 사용할 tokenizer 의 HF repo id. "
                             "--chat-template 이 있을 때만 의미.")
    args = parser.parse_args()

    samples: list[dict] = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    out_root = Path(args.output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.no_split:
        splits = {"training": samples}
    else:
        random.Random(args.seed).shuffle(samples)
        n_train, n_val, n_test = split_counts(len(samples))
        splits = {
            "training": samples[:n_train],
            "validation": samples[n_train : n_train + n_val],
            "test": samples[n_train + n_val : n_train + n_val + n_test],
        }

    chat_split = None
    if args.chat_template:
        print(f"[chat-template] loading tokenizer from {args.hf_model} ...", flush=True)
        chat_split, _tok = _build_chat_splitter(args.hf_model)

    for split_name, split_samples in splits.items():
        out_path = out_root / f"{split_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for s in split_samples:
                inp = format_input(s)
                outp = format_output(s)
                if chat_split is not None:
                    # user content 는 plain text 로 재구성 (JSON dump 대신).
                    user_text = format_prompt_text(inp)
                    inp, outp = chat_split(user_text, outp)
                row = {"input": inp, "output": outp}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{split_name}] {len(split_samples):4d} -> {out_path}")


if __name__ == "__main__":
    main()

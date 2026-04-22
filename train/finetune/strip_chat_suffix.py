#!/usr/bin/env python3
"""Strip trailing chat-template suffix from `output` field of SFT JSONL rows.

Why
---
`convert_data.py --chat-template` 은 output 필드에 `<|im_end|>\\n` 등 template
suffix 까지 포함시킨다 (학습 시 `prompt_template="{input}{output}"` 로 concat
하면 원본 `apply_chat_template` 결과와 bit-for-bit 일치하도록). 평가 시에는
gold JSON 만 필요하고, `json.loads(output)` 는 Extra data 로 실패한다.

이 스크립트는 output 을 균형 brace 로 첫 `{...}` 블록까지만 잘라내 덮어쓴다.
잘라내기 실패한 row 는 원본 그대로 두고 stderr 로 보고.

Usage:
    python3 finetune/strip_chat_suffix.py \\
        --input  data/sft-synthetic/test.filtered.jsonl \\
        --output data/sft-synthetic/test.filtered.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


def _json_slice(s: str) -> str | None:
    """첫 `{` 부터 균형 맞는 `}` 까지의 substring 을 반환. 못 찾으면 None."""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    total = stripped = unchanged = failed = 0
    out_lines: list[str] = []
    with open(in_path, encoding="utf-8") as f:
        for i, raw in enumerate(f):
            line = raw.rstrip("\n")
            if not line.strip():
                out_lines.append(line)
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[skip] row {i}: outer json failed — {e}", file=sys.stderr)
                out_lines.append(line)
                failed += 1
                continue
            out_field = row.get("output")
            if not isinstance(out_field, str):
                out_lines.append(line)
                unchanged += 1
                continue
            sliced = _json_slice(out_field)
            if sliced is None:
                print(f"[skip] row {i}: output 에 `{{...}}` 블록 없음", file=sys.stderr)
                out_lines.append(line)
                failed += 1
                continue
            # slice 가 실제로 valid JSON 인지 재확인
            try:
                json.loads(sliced)
            except json.JSONDecodeError as e:
                print(f"[skip] row {i}: sliced output re-parse 실패 — {e}", file=sys.stderr)
                out_lines.append(line)
                failed += 1
                continue
            if sliced == out_field:
                unchanged += 1
            else:
                stripped += 1
            row["output"] = sliced
            out_lines.append(json.dumps(row, ensure_ascii=False))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for line in out_lines:
            f.write(line + "\n")

    print(f"total={total}  stripped={stripped}  unchanged={unchanged}  failed={failed}")
    print(f"output -> {out_path}")


if __name__ == "__main__":
    main()

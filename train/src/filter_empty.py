#!/usr/bin/env python3
"""Filter out rows whose gold output is empty (new=[] AND conflict=[]).

Handles both record shapes:
  * schema v2 raw  : {"output": {"new": [...], "conflict": [...]}, ...}
  * SFT jsonl      : {"input": "...", "output": "<json string>"}
    (output 이 chat-template suffix 를 포함해도 첫 `{...}` 블록만 파싱)

Usage:
    python3 src/filter_empty.py --input data/sft/test.jsonl \\
        --output data/sft/test.filtered.jsonl
"""

import argparse
import json


def _extract_gold(row: dict) -> dict | None:
    """row 에서 gold {new, conflict} dict 를 뽑는다. 파싱 실패 시 None."""
    out = row.get("output")
    if isinstance(out, dict):
        return out
    if not isinstance(out, str) or not out:
        return None
    # SFT 포맷: output 이 JSON string. chat-template suffix (`<|im_end|>...`) 가
    # 뒤에 붙어있을 수 있으므로 첫 `{` 부터 균형 맞는 `}` 까지만 떼서 파싱.
    start = out.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(out)):
        ch = out[i]
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
                try:
                    parsed = json.loads(out[start : i + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _is_empty_gold(gold: dict | None) -> bool:
    if gold is None:
        return False  # 파싱 실패는 empty 로 취급하지 않음 (안전한 쪽: 유지)
    new = gold.get("new") or []
    conflict = gold.get("conflict") or []
    return len(new) == 0 and len(conflict) == 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report-unparseable", action="store_true",
                   help="output 파싱 실패한 row 도 별도 카운트해서 보고")
    args = p.parse_args()

    total = kept = dropped = unparseable = 0
    with open(args.input, encoding="utf-8") as fin, \
         open(args.output, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                unparseable += 1
                continue
            gold = _extract_gold(row)
            if gold is None:
                unparseable += 1
                # 안전하게 원본 그대로 유지
                fout.write(line + "\n")
                kept += 1
                continue
            if _is_empty_gold(gold):
                dropped += 1
                continue
            fout.write(line + "\n")
            kept += 1

    print(f"total={total}  kept={kept}  dropped_empty={dropped}"
          + (f"  unparseable={unparseable}" if args.report_unparseable or unparseable else ""))
    print(f"output -> {args.output}")


if __name__ == "__main__":
    main()

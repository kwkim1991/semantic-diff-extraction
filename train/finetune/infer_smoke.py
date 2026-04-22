#!/usr/bin/env python3
"""Single-sample smoke inference for the LoRA-merged diff-extraction model.

Assumes LoRA has already been merged back to HF format (see
Megatron-Bridge examples/peft/merge_lora.py).

Usage:
    python finetune/infer_smoke.py \
        --model-dir /path/to/merged_hf_dir \
        --sample data/sft/test.jsonl
"""

import argparse
import json


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", required=True, help="HF-format model dir (LoRA-merged)")
    p.add_argument("--sample", required=True, help="JSONL file; first line is used")
    p.add_argument("--max-new-tokens", type=int, default=512)
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    with open(args.sample, encoding="utf-8") as f:
        first = json.loads(f.readline())
    prompt, gold_raw = first["input"], first.get("output", "")

    tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    inputs = tok(prompt, return_tensors="pt").to(model.device)
    out_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
    gen = tok.decode(
        out_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
    ).strip()

    print("=== PROMPT (tail) ===")
    print(prompt[-300:])
    print("\n=== GENERATED ===")
    print(gen)
    print("\n=== GOLD ===")
    print(gold_raw)

    try:
        parsed = json.loads(gen)
        assert isinstance(parsed, dict), "top-level not dict"
        assert "new" in parsed and isinstance(parsed["new"], list), "missing/invalid 'new'"
        assert "conflict" in parsed and isinstance(parsed["conflict"], list), "missing/invalid 'conflict'"
        for i, c in enumerate(parsed["conflict"]):
            assert isinstance(c, dict), f"conflict[{i}] not dict"
            for key in ("known_text", "new_text", "reason"):
                assert key in c and isinstance(c[key], str), f"conflict[{i}].{key} missing or non-str"
        print("\n[OK] JSON parseable with {new, conflict[{known_text,new_text,reason}]} schema.")
    except Exception as e:
        print(f"\n[FAIL] JSON parse/shape check failed: {e}")


if __name__ == "__main__":
    main()

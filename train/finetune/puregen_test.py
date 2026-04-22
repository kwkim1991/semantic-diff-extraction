#!/usr/bin/env python3
"""Minimal HuggingFace generate() throughput test.

Loads the model, runs one warmup, then one timed generate, prints tok/s.

Usage:
    python finetune/puregen_test.py --model-dir <hf_dir>
    python finetune/puregen_test.py --model-dir <hf_dir> --prompt-file data/sft/test.jsonl
"""

import argparse
import json
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


TOY_PROMPT = "안녕하세요. 아래 JSON 스키마로 답해주세요: {\"new\": [], \"conflict\": []}"


def _gen(model, tok, prompt: str, max_new_tokens: int, label: str) -> None:
    inp = tok(prompt, return_tensors="pt").to(model.device)
    prompt_len = inp.input_ids.shape[-1]
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t0 = time.monotonic()
    out = model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False, use_cache=True)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    dt = time.monotonic() - t0
    new_tokens = out.shape[-1] - prompt_len
    tps = new_tokens / dt if dt > 0 else 0.0
    print(f"[{label}] prompt={prompt_len}tok gen={new_tokens}tok elapsed={dt:.2f}s throughput={tps:.2f} tok/s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", required=True)
    p.add_argument("--max-new-tokens", type=int, default=200)
    p.add_argument("--prompt-file", default=None,
                   help="Optional JSONL; first row's 'input' field is used")
    args = p.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        trust_remote_code=True,
    ).eval()

    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            prompt = json.loads(f.readline())["input"]
    else:
        prompt = TOY_PROMPT

    _gen(model, tok, prompt, 8, "warmup")
    _gen(model, tok, prompt, args.max_new_tokens, "timed")


if __name__ == "__main__":
    main()

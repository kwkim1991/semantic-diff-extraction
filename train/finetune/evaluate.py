#!/usr/bin/env python3
"""Evaluate diff-extraction with constrained generation + item-level judge.

Generation
----------
Target HF model is wrapped by `outlines` and driven against a Pydantic schema,
so every output is a structurally valid `{"new": [...], "conflict": [...]}`
document. No JSON-parse failures to worry about.

Scoring (item-level, not sample-level)
--------------------------------------
An LLM judge (OpenRouter) is asked to align each *predicted item* to the
ground-truth items and label the remaining ones. From those verdicts we
compute corpus-level (micro-averaged) precision / recall / F1:

  verdicts on pred.new[i]:
    match, duplicate, hallucination, not_novel, wrong_bucket
  verdicts on pred.conflict[i]:
    match, duplicate, hallucination_known, hallucination_new,
    not_a_conflict, wrong_bucket
  gold items that no pred item matched:
    reported as "missed"

Metrics
  new_precision        = #new_match / #pred_new
  new_recall           = #new_match / #gold_new   (gold matched == new_match for 1:1 alignment)
  new_f1               = harmonic mean
  conflict_precision/recall/f1 : analogous
  macro_f1             = (new_f1 + conflict_f1) / 2
  hallucination_rate   = #hallucinated_items / #pred_items        (both buckets combined)
  not_novel_rate       = #not_novel_items / #pred_new             (new bucket only)
  empty_both_rate      = samples where gold and pred are both fully empty / n

Usage
-----
    bash finetune/evaluate.sh exports/nemotron_3_nano_diff_hf
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from prompt_text import format_prompt_text as _format_prompt_text


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m{s:02d}s"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


JUDGE_SYSTEM = (
    "You are a strict evaluator aligning predicted diff items against ground-truth "
    "diff items for a Korean document comparison task. Respond with a single JSON "
    "object and nothing else."
)

JUDGE_USER_TEMPLATE = """The model is extracting a logical diff between KNOWN_DOCs and a NEW_DOC.
  - "new"      : claims in NEW_DOC not present in any KNOWN_DOC.
  - "conflict" : {{"known_text", "new_text", "reason"}} where "new_text" (from NEW_DOC)
                 contradicts "known_text" (from some KNOWN_DOC).
Paraphrases of existing KNOWN_DOC claims must NOT appear.

[ORIGINAL PROMPT TO MODEL]
{prompt}

[GOLD]
new:
{gold_new}
conflict:
{gold_conflict}

[PRED]
new:
{pred_new}
conflict:
{pred_conflict}

Align each PRED item to at most one GOLD item and assign a verdict.
Semantic match matters, not exact strings.

Return ONLY this JSON (no code fence, no prose before or after):

{{
  "new_alignment": [
    {{"pred_idx": 0, "matched_gold_idx": 0_or_null, "verdict": "<one of: match, duplicate, hallucination, not_novel, wrong_bucket>"}}
  ],
  "new_missed_gold_idxs": [/* GOLD.new indices not matched by any PRED item */],
  "conflict_alignment": [
    {{"pred_idx": 0, "matched_gold_idx": 0_or_null, "verdict": "<one of: match, duplicate, hallucination_known, hallucination_new, not_a_conflict, wrong_bucket>"}}
  ],
  "conflict_missed_gold_idxs": [/* GOLD.conflict indices not matched */],
  "notes": "<optional one-line explanation, can be empty>"
}}

Verdict definitions
  match                    : semantically matches the indicated GOLD item.
  duplicate                : semantically same as another PRED item already marked "match".
  hallucination            : (new) the claim is not found in NEW_DOC at all.
  hallucination_known      : (conflict) "known_text" substring does not exist in any KNOWN_DOC.
  hallucination_new        : (conflict) "new_text" substring does not exist in NEW_DOC.
  not_novel                : (new) the claim is actually present in some KNOWN_DOC (just paraphrased).
  not_a_conflict           : (conflict) both sides exist but they don't actually contradict.
  wrong_bucket             : the item should have been in the other bucket (new vs conflict)."""


# ---------- target-model schema --------------------------------------------

def _build_schema():
    from pydantic import BaseModel, Field

    class Conflict(BaseModel):
        known_text: str = Field(description="Substring of a KNOWN_DOC")
        new_text: str = Field(description="Substring of NEW_DOC that contradicts `known_text`")
        reason: str = Field(description="One-line reason")

    class DiffOutput(BaseModel):
        new: list[str] = Field(default_factory=list)
        conflict: list[Conflict] = Field(default_factory=list)

    return DiffOutput


# ---------- judge I/O -------------------------------------------------------

def _fmt_items(items: list, kind: str) -> str:
    if not items:
        return "  (empty)"
    lines = []
    for i, x in enumerate(items):
        if kind == "new":
            lines.append(f"  [{i}] {x}")
        else:
            k = (x.get("known_text", "") if isinstance(x, dict) else "").replace("\n", " ")
            nt = (x.get("new_text", "") if isinstance(x, dict) else "").replace("\n", " ")
            rsn = (x.get("reason", "") if isinstance(x, dict) else "").replace("\n", " ")
            lines.append(f"  [{i}] known_text=\"{k}\"  new_text=\"{nt}\"  reason=\"{rsn}\"")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict | None:
    """Judge 응답에서 최대한 JSON 을 뽑아낸다.

    (a) code fence (```json ... ```) 제거
    (b) 그대로 파싱 시도
    (c) 실패하면 첫 `{` 부터 균형 맞는 `}` 까지 추출해 재시도
    """
    if not raw:
        return None
    s = raw.strip()
    # (a) code fence
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    # (b) direct
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # (c) balanced braces scan
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
                try:
                    obj = json.loads(s[start : i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _call_judge(
    client,
    model: str,
    prompt: str,
    gold: dict,
    pred: dict,
    max_tokens: int = 2048,
    retries: int = 2,
) -> dict:
    """Judge 호출 + 강건한 JSON 파싱 + 재시도.

    invalid JSON 이 나오는 원인은 대부분 두 가지:
      (1) provider 기본 max_tokens 가 작아서 응답이 중간에 잘림
      (2) 판사 모델이 code fence / prose 감싸서 반환
    (1) 은 `max_tokens` 명시로, (2) 는 `_extract_json` 관용 파싱으로 커버.
    그래도 실패하면 수리 프롬프트로 1~2회 재시도.
    """
    user = JUDGE_USER_TEMPLATE.format(
        prompt=prompt,
        gold_new=_fmt_items(gold["new"], "new"),
        gold_conflict=_fmt_items(gold["conflict"], "conflict"),
        pred_new=_fmt_items(pred["new"], "new"),
        pred_conflict=_fmt_items(pred["conflict"], "conflict"),
    )
    messages: list[dict] = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]
    last_raw = ""
    last_err = ""
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=max_tokens,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            # API 호출 자체가 실패한 경우는 같은 메시지로 재시도
            continue
        last_raw = raw
        parsed = _extract_json(raw)
        if parsed is not None:
            return parsed
        # 재시도: 직전 응답을 보여주고 JSON 만 다시 내라고 요청
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": raw[:1000]},
            {
                "role": "user",
                "content": (
                    "Your previous response was not parseable JSON. "
                    "Return ONLY a single JSON object matching the schema. "
                    "No code fence, no prose before or after."
                ),
            },
        ]
    snippet = last_raw[:200] if last_raw else last_err
    return {"error": f"judge returned non-JSON after {retries + 1} attempts: {snippet}"}


def _empty_verdict(pred: dict, gold: dict) -> dict:
    """Trivial case: if a side has no pred or no gold items we can label without judge."""
    n_pred_new = len(pred["new"])
    n_gold_new = len(gold["new"])
    n_pred_conf = len(pred["conflict"])
    n_gold_conf = len(gold["conflict"])
    return {
        "new_alignment": [],
        "new_missed_gold_idxs": list(range(n_gold_new)) if n_pred_new == 0 else [],
        "conflict_alignment": [],
        "conflict_missed_gold_idxs": list(range(n_gold_conf)) if n_pred_conf == 0 else [],
        "notes": "both fully empty" if (n_pred_new + n_gold_new + n_pred_conf + n_gold_conf) == 0 else "trivial side(s)",
    }


# ---------- counting --------------------------------------------------------

NEW_VERDICTS = ("match", "duplicate", "hallucination", "not_novel", "wrong_bucket")
CONF_VERDICTS = ("match", "duplicate", "hallucination_known",
                 "hallucination_new", "not_a_conflict", "wrong_bucket")


def _count_sample(pred: dict, gold: dict, verdict: dict) -> dict:
    gold_new_len = len(gold["new"])
    gold_conf_len = len(gold["conflict"])

    cnt = {f"new_{v}": 0 for v in NEW_VERDICTS}
    cnt.update({f"conf_{v}": 0 for v in CONF_VERDICTS})
    cnt["pred_new_total"] = len(pred["new"])
    cnt["gold_new_total"] = gold_new_len
    cnt["pred_conf_total"] = len(pred["conflict"])
    cnt["gold_conf_total"] = gold_conf_len

    # TP (true positives) = 매칭된 **고유 gold index** 수.
    # judge 가 같은 gold 에 여러 pred 를 "match" 로 붙이거나 (duplicate 라벨 누락),
    # matched_gold_idx 를 out-of-range 로 내는 경우가 있어서, 단순히 verdict=="match"
    # 개수를 세면 TP 가 gold 개수를 넘어서 recall > 1 이 나온다. set + range-clamp.
    matched_new_idxs: set[int] = set()
    for a in verdict.get("new_alignment", []) or []:
        v = a.get("verdict", "")
        if v in NEW_VERDICTS:
            cnt[f"new_{v}"] += 1
        if v == "match":
            idx = a.get("matched_gold_idx")
            if isinstance(idx, int) and 0 <= idx < gold_new_len:
                matched_new_idxs.add(idx)
    cnt["new_gold_matched"] = len(matched_new_idxs)

    matched_conf_idxs: set[int] = set()
    for a in verdict.get("conflict_alignment", []) or []:
        v = a.get("verdict", "")
        if v in CONF_VERDICTS:
            cnt[f"conf_{v}"] += 1
        if v == "match":
            idx = a.get("matched_gold_idx")
            if isinstance(idx, int) and 0 <= idx < gold_conf_len:
                matched_conf_idxs.add(idx)
    cnt["conf_gold_matched"] = len(matched_conf_idxs)

    # missed idxs 도 dedupe + range-clamp (같은 이유로 missed_rate > 1 방지).
    missed_new = {i for i in (verdict.get("new_missed_gold_idxs") or [])
                  if isinstance(i, int) and 0 <= i < gold_new_len}
    cnt["new_missed"] = len(missed_new)
    missed_conf = {i for i in (verdict.get("conflict_missed_gold_idxs") or [])
                   if isinstance(i, int) and 0 <= i < gold_conf_len}
    cnt["conf_missed"] = len(missed_conf)

    return cnt


def _merge_counts(total: dict, cnt: dict) -> None:
    for k, v in cnt.items():
        total[k] = total.get(k, 0) + v


def _compute_metrics(total: dict, n_samples: int, n_empty_both: int) -> dict:
    def div(a, b): return a / b if b else 0.0
    def f1(p, r): return (2 * p * r / (p + r)) if (p + r) else 0.0

    # TP 는 "매칭된 고유 gold idx 수" (_count_sample 에서 dedupe 됨).
    # `new_match` / `conf_match` 는 pred 쪽 verdict=="match" 개수로, judge 가
    # duplicate 라벨 누락 시 실제 TP 보다 커질 수 있다. 메트릭 분자에는 사용 금지.
    new_tp = total.get("new_gold_matched", 0)
    conf_tp = total.get("conf_gold_matched", 0)
    pred_new = total.get("pred_new_total", 0)
    gold_new = total.get("gold_new_total", 0)
    pred_conf = total.get("pred_conf_total", 0)
    gold_conf = total.get("gold_conf_total", 0)

    new_halluc = total.get("new_hallucination", 0)
    conf_halluc = (total.get("conf_hallucination_known", 0)
                   + total.get("conf_hallucination_new", 0))
    not_novel = total.get("new_not_novel", 0)
    duplicates = total.get("new_duplicate", 0) + total.get("conf_duplicate", 0)
    wrong_bucket = total.get("new_wrong_bucket", 0) + total.get("conf_wrong_bucket", 0)
    not_a_conflict = total.get("conf_not_a_conflict", 0)
    total_pred_items = pred_new + pred_conf

    new_p = div(new_tp, pred_new)
    new_r = div(new_tp, gold_new)
    conf_p = div(conf_tp, pred_conf)
    conf_r = div(conf_tp, gold_conf)
    new_f = f1(new_p, new_r)
    conf_f = f1(conf_p, conf_r)

    return {
        "n_samples": n_samples,
        "n_empty_both": n_empty_both,
        "pred_new_total": pred_new,
        "gold_new_total": gold_new,
        "pred_conflict_total": pred_conf,
        "gold_conflict_total": gold_conf,
        "new_gold_matched": new_tp,
        "conflict_gold_matched": conf_tp,
        "new_match_verdicts": total.get("new_match", 0),
        "conflict_match_verdicts": total.get("conf_match", 0),
        "new_precision": new_p,
        "new_recall": new_r,
        "new_f1": new_f,
        "conflict_precision": conf_p,
        "conflict_recall": conf_r,
        "conflict_f1": conf_f,
        "macro_f1": (new_f + conf_f) / 2,
        "hallucination_rate": div(new_halluc + conf_halluc, total_pred_items),
        "not_novel_rate_new": div(not_novel, pred_new),
        "not_a_conflict_rate": div(not_a_conflict, pred_conf),
        "duplicate_rate": div(duplicates, total_pred_items),
        "wrong_bucket_rate": div(wrong_bucket, total_pred_items),
        "missed_rate_new": div(total.get("new_missed", 0), gold_new),
        "missed_rate_conflict": div(total.get("conf_missed", 0), gold_conf),
        "empty_both_rate": div(n_empty_both, n_samples),
    }


# ---------- visual ----------------------------------------------------------

def _pretty(obj: Any) -> str:
    try:
        if isinstance(obj, str):
            obj = json.loads(obj)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _fmt_alignments(pred_items: list, alignments: list, missed_idxs: list, bucket: str) -> str:
    out = []
    for i, a in enumerate(alignments or []):
        v = a.get("verdict", "?")
        g = a.get("matched_gold_idx")
        g_str = f"gold[{g}]" if isinstance(g, int) else "-"
        out.append(f"  pred[{i}] -> {g_str}  [{v}]")
    for g in missed_idxs or []:
        out.append(f"  gold[{g}] MISSED")
    if not out:
        out.append("  (no items)")
    return "\n".join(out)


def _print_block(done: int, total: int, prompt_tail: str,
                 pred_obj: dict, gold_obj: dict,
                 verdict: dict, sample_cnt: dict, running_m: dict,
                 timing: dict) -> None:
    bar = "=" * 78
    # TP (unique gold matched) 기준으로 표시 — pred 쪽 match 라벨 수는
    # duplicate 누락 시 부풀려질 수 있으므로 지양.
    new_tp = sample_cnt.get("new_gold_matched", 0)
    conf_tp = sample_cnt.get("conf_gold_matched", 0)
    hdr = (f"[{done}/{total}]  "
           f"new: TP={new_tp}/{sample_cnt['gold_new_total']} gold "
           f"({sample_cnt['pred_new_total']} pred)  |  "
           f"conflict: TP={conf_tp}/{sample_cnt['gold_conf_total']} gold "
           f"({sample_cnt['pred_conf_total']} pred)")
    print(f"\n{bar}\n{hdr}\n{'-' * 78}")
    print("PROMPT (tail):")
    print(prompt_tail)
    print("-" * 78)
    print("GENERATED:")
    print(_pretty(pred_obj))
    print("-" * 78)
    print("GOLD:")
    print(_pretty(gold_obj))
    print("-" * 78)
    print("new verdicts:")
    print(_fmt_alignments(pred_obj["new"],
                          verdict.get("new_alignment"),
                          verdict.get("new_missed_gold_idxs"), "new"))
    print("conflict verdicts:")
    print(_fmt_alignments(pred_obj["conflict"],
                          verdict.get("conflict_alignment"),
                          verdict.get("conflict_missed_gold_idxs"), "conflict"))
    notes = verdict.get("notes", "")
    if notes:
        print(f"notes: {notes}")
    print("-" * 78)
    print(f"TIMING  gen={_fmt_duration(timing['gen'])}  "
          f"judge={_fmt_duration(timing['judge'])}  "
          f"row={_fmt_duration(timing['row'])}  |  "
          f"elapsed={_fmt_duration(timing['elapsed'])}  "
          f"avg/row={_fmt_duration(timing['avg_row'])}  "
          f"ETA={_fmt_duration(timing['eta'])}")
    print(f"RUNNING corpus  "
          f"new P={running_m['new_precision']:.3f} R={running_m['new_recall']:.3f} "
          f"F1={running_m['new_f1']:.3f}  |  "
          f"conflict P={running_m['conflict_precision']:.3f} "
          f"R={running_m['conflict_recall']:.3f} F1={running_m['conflict_f1']:.3f}")
    print(f"              "
          f"macro_f1={running_m['macro_f1']:.3f}  "
          f"halluc_rate={running_m['hallucination_rate']:.3f}  "
          f"missed_new={running_m['missed_rate_new']:.3f}  "
          f"missed_conf={running_m['missed_rate_conflict']:.3f}")
    print(bar, flush=True)


# ---------- cli -------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", required=True, help="HF-format model dir")
    p.add_argument("--test", default="data/sft/test.jsonl")
    p.add_argument("--predictions", default="nemo_experiments/eval_predictions.jsonl")
    p.add_argument("--summary", default=None)
    p.add_argument("--judge-model", default="anthropic/claude-sonnet-4.5")
    p.add_argument("--judge-max-tokens", type=int, default=2048,
                   help="판사 응답 최대 토큰. invalid JSON 의 주원인이 응답 truncation 이라 여유있게 잡는다.")
    p.add_argument("--judge-retries", type=int, default=2,
                   help="판사 JSON 파싱 실패 시 repair prompt 로 재시도 횟수")
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--prompt-format", choices=["json", "text", "chat"], default="json",
                   help="json: 학습때와 동일한 raw JSON dump 입력. "
                        "text: 자연어 텍스트로 재포맷 (base model 진단 / task prior 강화용). "
                        "chat: tokenizer.apply_chat_template 을 적용해 user turn + "
                        "generation prompt 로 감싼다 (training 에서도 chat-template 로 "
                        "학습했을 때 일관된 입력 형태를 주기 위함).")
    p.add_argument("--do-sample", action="store_true",
                   help="greedy 대신 sampling 사용 (outlines schema-valid 최단 경로 collapse 완화).")
    p.add_argument("--temperature", type=float, default=0.7,
                   help="--do-sample 일 때만 사용")
    p.add_argument("--top-p", type=float, default=0.95,
                   help="--do-sample 일 때만 사용")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--prompt-tail", type=int, default=300)
    p.add_argument("--no-judge", action="store_true",
                   help="Skip LLM judge; counts become mostly zero (smoke test only)")
    # --- vLLM endpoint (HF + outlines 대체) ---
    p.add_argument("--vllm-endpoint", default=None,
                   help="OpenAI 호환 vLLM 엔드포인트 URL (예: http://localhost:9983/v1). "
                        "세팅 시 HF 모델 로드 대신 이 엔드포인트로 generation. "
                        "prompt 는 그대로 /v1/completions 에 보내며 `guided_json` 으로 "
                        "schema constrained decoding 을 적용.")
    p.add_argument("--vllm-model", default="vllmlora",
                   help="vLLM 에 등록된 모델 이름 (--vllm-endpoint 세팅 시 사용)")
    p.add_argument("--vllm-api-key", default="EMPTY",
                   help="vLLM 이 인증을 요구하지 않아도 OpenAI SDK 가 키를 요구 — placeholder.")
    return p.parse_args()


# ---------- generation backends ---------------------------------------------

def _build_hf_generator(model_dir: str, tokenizer, schema_cls):
    """Local HF + outlines constrained decoding.

    Returns `generate(prompt, gen_opts) -> dict` with the target schema keys.
    """
    import torch
    import outlines
    from transformers import AutoModelForCausalLM

    print(f"Loading HF model from {model_dir} ...", flush=True)
    hf_model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        trust_remote_code=True,
    )
    hf_model.eval()
    model = outlines.from_transformers(hf_model, tokenizer)

    def generate(prompt: str, gen_opts: dict) -> dict:
        kwargs: dict = {"max_new_tokens": gen_opts["max_new_tokens"]}
        if gen_opts.get("do_sample"):
            kwargs["do_sample"] = True
            kwargs["temperature"] = gen_opts["temperature"]
            kwargs["top_p"] = gen_opts["top_p"]
        raw_out = model(prompt, schema_cls, **kwargs)
        if hasattr(raw_out, "model_dump"):
            return raw_out.model_dump()
        if isinstance(raw_out, dict):
            return raw_out
        if isinstance(raw_out, str):
            return json.loads(raw_out)
        raise TypeError(
            f"outlines 가 예상치 못한 타입 반환: {type(raw_out).__name__}"
        )

    return generate


def _build_vllm_generator(endpoint: str, model_name: str, api_key: str, schema_cls):
    """vLLM OpenAI 호환 엔드포인트 + `guided_json` constrained decoding.

    - `/v1/completions` 로 raw prompt 를 보낸다 (chat template 은 이미 호출자 쪽에서
      씌워둔 상태). chat completions 대신 completions 를 쓰는 이유: HF 경로와
      prompt 형태를 동일하게 맞춰 apples-to-apples 비교 가능.
    - `extra_body={"guided_json": schema}` 는 vLLM 의 structured output 기능. 이
      모드에서 출력은 반드시 schema 를 만족하는 JSON string 이 된다.
    """
    from openai import OpenAI

    print(f"Using vLLM endpoint: {endpoint} (model={model_name})", flush=True)
    client = OpenAI(base_url=endpoint, api_key=api_key or "EMPTY")
    schema_dict = schema_cls.model_json_schema()

    def generate(prompt: str, gen_opts: dict) -> dict:
        temperature = gen_opts["temperature"] if gen_opts.get("do_sample") else 0.0
        top_p = gen_opts["top_p"] if gen_opts.get("do_sample") else 1.0
        resp = client.completions.create(
            model=model_name,
            prompt=prompt,
            max_tokens=gen_opts["max_new_tokens"],
            temperature=temperature,
            top_p=top_p,
            extra_body={"guided_json": schema_dict},
        )
        text = resp.choices[0].text or ""
        return json.loads(text)

    return generate


def main() -> None:
    args = parse_args()

    # judge client
    judge_client = None
    if not args.no_judge:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("ERROR: OPENROUTER_API_KEY not set. Use --no-judge to skip scoring.",
                  file=sys.stderr)
            sys.exit(2)
        from openai import OpenAI
        judge_client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    # samples
    samples: list[dict] = []
    with open(args.test, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    if args.limit:
        samples = samples[: args.limit]
    if not samples:
        raise SystemExit(f"No samples loaded from {args.test}")

    # target model / tokenizer. tokenizer 는 chat-template 포맷팅에 필요하므로
    # vLLM 모드에서도 항상 로드 (로컬 경로든 HF repo id 든 AutoTokenizer 가 처리).
    from transformers import AutoTokenizer

    DiffOutput = _build_schema()

    print(f"Loading tokenizer from {args.model_dir} ...", flush=True)
    hf_tokenizer = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)

    if args.vllm_endpoint:
        generate_fn = _build_vllm_generator(
            args.vllm_endpoint, args.vllm_model, args.vllm_api_key, DiffOutput,
        )
    else:
        generate_fn = _build_hf_generator(args.model_dir, hf_tokenizer, DiffOutput)

    def _format_prompt_chat(input_str: str) -> str:
        """Chat template 을 씌워 non-thinking generation prompt 형태로 반환.

        test.jsonl input 이 convert_data.py --chat-template 결과라 이미 chat-templated
        된 경우 (`<|im_start|>` 로 시작) 추가 포장하지 않고 그대로 사용한다 — 이미
        add_generation_prompt 가 포함되어 assistant turn 이 열린 상태이기 때문에
        한 번 더 감싸면 turn 이 중첩돼 `<|im_start|>assistant\\n<think></think>`
        가 두 번 찍힌다.
        """
        stripped = input_str.lstrip()
        if stripped.startswith("<|") and "<|im_start|>assistant" in input_str:
            return input_str

        user_text = _format_prompt_text(input_str)
        return hf_tokenizer.apply_chat_template(
            [{"role": "user", "content": user_text}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

    # 진단: 첫 샘플 prompt 머리/꼬리를 찍어 변환이 실제 먹고 있는지 확인
    if samples and args.prompt_format in ("text", "chat"):
        preview_raw = samples[0]["input"]
        if args.prompt_format == "text":
            preview_out = _format_prompt_text(preview_raw)
        else:
            preview_out = _format_prompt_chat(preview_raw)
        changed = preview_out != preview_raw
        print(f"[prompt] format={args.prompt_format}  transformed={changed}  "
              f"raw_len={len(preview_raw)} -> out_len={len(preview_out)}",
              flush=True)
        head = preview_out[:200].replace("\n", " ⏎ ")
        tail = preview_out[-200:].replace("\n", " ⏎ ")
        print(f"[prompt] head: {head}", flush=True)
        print(f"[prompt] tail: {tail}", flush=True)

    pred_path = Path(args.predictions)
    pred_path.parent.mkdir(parents=True, exist_ok=True)

    total_counts: dict = {}
    n_empty_both = 0
    n_judge_failures = 0
    n_skipped = 0
    skipped_idxs: list[int] = []
    loop_start = time.monotonic()
    total_gen_time = 0.0
    total_judge_time = 0.0

    with open(pred_path, "w", encoding="utf-8") as fout:
        for i, s in enumerate(samples):
            row_start = time.monotonic()
            raw_input = s["input"]
            if args.prompt_format == "text":
                prompt = _format_prompt_text(raw_input)
            elif args.prompt_format == "chat":
                prompt = _format_prompt_chat(raw_input)
            else:
                prompt = raw_input

            # --- gold 파싱 (generation 전에 먼저 — 실패 시 GPU 낭비 방지) ---
            # output 이 chat-template suffix (e.g. `<|im_end|>\n`) 를 달고 있어도
            # 첫 `{...}` 블록만 균형 파싱. 파싱 실패 / 형태 이상은 skip + 에러 출력.
            gold_raw = s.get("output", "")
            gold_err: str | None = None
            if not gold_raw:
                gold_err = "`output` 필드가 비어있음 (미리 필터링 권장)"
                gold_obj = None
            else:
                gold_obj = _extract_json(gold_raw)
                if not isinstance(gold_obj, dict):
                    gold_err = f"gold JSON 파싱 실패. 앞 200자: {gold_raw[:200]!r}"
                elif "new" not in gold_obj or "conflict" not in gold_obj:
                    gold_err = f"gold 에 `new`/`conflict` 키 없음. keys={list(gold_obj.keys())}"
            if gold_err is not None:
                print(f"[skip] sample idx={i}: {gold_err}", file=sys.stderr, flush=True)
                n_skipped += 1
                skipped_idxs.append(i)
                fout.write(json.dumps({
                    "idx": i, "skipped": True, "reason": gold_err, "stage": "gold",
                }, ensure_ascii=False) + "\n")
                fout.flush()
                continue

            # --- constrained generation ---
            # generate_fn 은 backend (HF+outlines / vLLM) 차이를 숨기고 dict 반환.
            # 네트워크/디코딩 실패는 예외로 전파 → skip + stderr 로그.
            gen_opts = {
                "max_new_tokens": args.max_new_tokens,
                "do_sample": args.do_sample,
                "temperature": args.temperature,
                "top_p": args.top_p,
            }
            gen_start = time.monotonic()
            pred_err: str | None = None
            pred_obj: dict | None = None
            try:
                pred_obj = generate_fn(prompt, gen_opts)
            except Exception as e:
                pred_err = f"generation 실패: {type(e).__name__}: {e}"
            gen_elapsed = time.monotonic() - gen_start
            total_gen_time += gen_elapsed

            if pred_err is None:
                if not isinstance(pred_obj, dict):
                    pred_err = f"generator 가 dict 아닌 값 반환 (type={type(pred_obj).__name__})"
                elif "new" not in pred_obj or "conflict" not in pred_obj:
                    pred_err = f"pred 에 `new`/`conflict` 키 없음. keys={list(pred_obj.keys())}"
            if pred_err is not None:
                print(f"[skip] sample idx={i}: {pred_err}", file=sys.stderr, flush=True)
                n_skipped += 1
                skipped_idxs.append(i)
                fout.write(json.dumps({
                    "idx": i, "skipped": True, "reason": pred_err, "stage": "pred",
                    "gen_sec": gen_elapsed,
                }, ensure_ascii=False) + "\n")
                fout.flush()
                continue

            empty_both = (not pred_obj["new"] and not pred_obj["conflict"]
                          and not gold_obj["new"] and not gold_obj["conflict"])
            judge_elapsed = 0.0
            if empty_both:
                n_empty_both += 1
                verdict = _empty_verdict(pred_obj, gold_obj)
            elif args.no_judge:
                verdict = _empty_verdict(pred_obj, gold_obj)  # trivial skeleton
            else:
                judge_start = time.monotonic()
                verdict = _call_judge(
                    judge_client, args.judge_model, prompt, gold_obj, pred_obj,
                    max_tokens=args.judge_max_tokens, retries=args.judge_retries,
                )
                judge_elapsed = time.monotonic() - judge_start
                total_judge_time += judge_elapsed
                if "error" in verdict:
                    n_judge_failures += 1
                    verdict = {**_empty_verdict(pred_obj, gold_obj),
                               "notes": "JUDGE ERROR: " + verdict["error"]}

            sample_cnt = _count_sample(pred_obj, gold_obj, verdict)
            _merge_counts(total_counts, sample_cnt)

            done = i + 1
            n_scored = done - n_skipped
            running_m = _compute_metrics(total_counts, n_scored, n_empty_both)

            row_elapsed = time.monotonic() - row_start
            elapsed_total = time.monotonic() - loop_start
            avg_row = elapsed_total / done
            eta = avg_row * (len(samples) - done)
            timing = {
                "gen": gen_elapsed,
                "judge": judge_elapsed,
                "row": row_elapsed,
                "elapsed": elapsed_total,
                "avg_row": avg_row,
                "eta": eta,
            }

            fout.write(json.dumps({
                "idx": i,
                "prompt_tail": prompt[-args.prompt_tail:],
                "generated": pred_obj,
                "gold": gold_obj,
                "verdict": verdict,
                "counts": sample_cnt,
                "timing": {
                    "gen_sec": gen_elapsed,
                    "judge_sec": judge_elapsed,
                    "row_sec": row_elapsed,
                },
            }, ensure_ascii=False) + "\n")
            fout.flush()

            if args.quiet:
                print(f"[{done}/{len(samples)}] "
                      f"new TP={sample_cnt.get('new_gold_matched', 0)}/"
                      f"{sample_cnt['gold_new_total']}g/{sample_cnt['pred_new_total']}p  "
                      f"conf TP={sample_cnt.get('conf_gold_matched', 0)}/"
                      f"{sample_cnt['gold_conf_total']}g/{sample_cnt['pred_conf_total']}p  "
                      f"| gen={_fmt_duration(gen_elapsed)} "
                      f"judge={_fmt_duration(judge_elapsed)} "
                      f"ETA={_fmt_duration(eta)} "
                      f"| macro_f1={running_m['macro_f1']:.3f} "
                      f"halluc={running_m['hallucination_rate']:.3f}")
            else:
                _print_block(done, len(samples), prompt[-args.prompt_tail:],
                             pred_obj, gold_obj, verdict, sample_cnt, running_m,
                             timing)

    n_scored = len(samples) - n_skipped
    summary = _compute_metrics(total_counts, n_scored, n_empty_both)
    summary["model_dir"] = args.model_dir
    summary["test"] = args.test
    summary["n_total"] = len(samples)
    summary["n_scored"] = n_scored
    summary["n_skipped"] = n_skipped
    summary["skipped_idxs"] = skipped_idxs
    summary["judge_model"] = None if args.no_judge else args.judge_model
    summary["judge_max_tokens"] = None if args.no_judge else args.judge_max_tokens
    summary["judge_failures"] = n_judge_failures
    summary["judge_failure_rate"] = (
        n_judge_failures / max(1, n_scored - n_empty_both)
        if not args.no_judge else 0.0
    )
    summary["raw_counts"] = total_counts
    total_elapsed = time.monotonic() - loop_start
    denom = max(1, n_scored)
    summary["timing"] = {
        "total_sec": total_elapsed,
        "total_human": _fmt_duration(total_elapsed),
        "total_gen_sec": total_gen_time,
        "total_judge_sec": total_judge_time,
        "avg_gen_sec": total_gen_time / denom,
        "avg_judge_sec": total_judge_time / denom,
        "avg_row_sec": total_elapsed / max(1, len(samples)),
    }

    summary_path = args.summary or str(pred_path) + ".summary.json"
    Path(summary_path).parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\npredictions -> {pred_path}")
    print(f"summary     -> {summary_path}")


if __name__ == "__main__":
    main()

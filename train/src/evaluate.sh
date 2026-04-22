#!/usr/bin/env bash
# Evaluate the diff-extraction model on data/sft/test.jsonl.
#
# Uses outlines for constrained JSON generation (output is always a valid
# {new[], conflict[]} document) and an OpenRouter judge model for scoring.
#
# Pre-req:
#   1) LoRA merged + exported to HF format (finetune/merge_and_export.sh).
#      Or point --model-dir at the original HF checkpoint for a baseline.
#   2) .env contains OPENROUTER_API_KEY (sourced below).
#   3) pip install outlines pydantic openai python-dotenv
#
# Usage:
#   bash finetune/evaluate.sh <HF_MODEL_DIR> [TEST_JSONL]
#
# Env overrides:
#   JUDGE_MODEL         OpenRouter judge model (default anthropic/claude-sonnet-4.5)
#   JUDGE_MAX_TOKENS    판사 응답 최대 토큰 (default 2048, invalid JSON 주원인 방어)
#   JUDGE_RETRIES       판사 JSON 파싱 실패 시 repair 재시도 횟수 (default 2)
#   PRED_OUT            per-sample predictions JSONL (default nemo_experiments/eval_predictions.jsonl)
#   MAX_NEW_TOKENS      target 모델 generation cap (default 512)
#   LIMIT               evaluate only first N rows
#   QUIET=1             suppress visual blocks (one line per sample)
#   NO_JUDGE=1          skip the LLM judge (smoke test without API key)
#   DO_SAMPLE=1         greedy 대신 sampling 사용 (empty collapse 완화)
#   TEMPERATURE         default 0.7 (DO_SAMPLE=1 일 때)
#   TOP_P               default 0.95 (DO_SAMPLE=1 일 때)
#   PROMPT_FORMAT       "json" (default) | "text" | "chat"
#                       - json: 학습때와 동일한 raw JSON dump 입력
#                       - text: 자연어 텍스트로 재포맷 (base model 진단용)
#                       - chat: tokenizer.apply_chat_template 적용
#                               (convert_data.py --chat-template 로 학습했을 때 일관)
#   VLLM_ENDPOINT       OpenAI-호환 vLLM URL (예: http://localhost:9983/v1).
#                       세팅 시 HF 모델 로드 대신 이 엔드포인트로 generation.
#                       MODEL_DIR 은 tokenizer 로드용으로 여전히 필요 (로컬 경로 또는 HF repo id).
#   VLLM_MODEL          vLLM 에 등록된 모델 이름 (default vllmlora)
#   VLLM_API_KEY        placeholder (default EMPTY)

set -euo pipefail

# Load .env for OPENROUTER_API_KEY (and anything else)
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

MODEL_DIR="${1:?Path to HF-format model dir required}"
TEST_JSONL="${2:-data/sft-eval/test.jsonl}"
PRED_OUT="${PRED_OUT:-nemo_experiments/eval_predictions.jsonl}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-2048}"
JUDGE_MODEL="${JUDGE_MODEL:-anthropic/claude-sonnet-4.5}"
JUDGE_MAX_TOKENS="${JUDGE_MAX_TOKENS:-2048}"
JUDGE_RETRIES="${JUDGE_RETRIES:-2}"

set -x

CMD=(python finetune/evaluate.py
    --model-dir "${MODEL_DIR}"
    --test "${TEST_JSONL}"
    --predictions "${PRED_OUT}"
    --max-new-tokens "${MAX_NEW_TOKENS}"
    --judge-model "${JUDGE_MODEL}"
    --judge-max-tokens "${JUDGE_MAX_TOKENS}"
    --judge-retries "${JUDGE_RETRIES}")

if [ -n "${LIMIT:-}" ]; then
    CMD+=(--limit "${LIMIT}")
fi
if [ -n "${QUIET:-}" ]; then
    CMD+=(--quiet)
fi
if [ -n "${NO_JUDGE:-}" ]; then
    CMD+=(--no-judge)
fi
if [ -n "${DO_SAMPLE:-}" ]; then
    CMD+=(--do-sample)
    CMD+=(--temperature "${TEMPERATURE:-0.7}")
    CMD+=(--top-p "${TOP_P:-0.95}")
fi
if [ -n "${PROMPT_FORMAT:-}" ]; then
    CMD+=(--prompt-format "${PROMPT_FORMAT}")
fi
if [ -n "${VLLM_ENDPOINT:-}" ]; then
    CMD+=(--vllm-endpoint "${VLLM_ENDPOINT}")
    CMD+=(--vllm-model "${VLLM_MODEL:-vllmlora}")
    CMD+=(--vllm-api-key "${VLLM_API_KEY:-EMPTY}")
fi

"${CMD[@]}"

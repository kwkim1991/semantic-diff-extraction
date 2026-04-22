#!/usr/bin/env bash
# Launch LoRA SFT for Nemotron 3 Nano 30B-A3B.
#
# Prereq (inside NeMo Framework container, CWD = project root):
#   1. HF -> Megatron checkpoint conversion (finetune/convert_hf_ckpt.py)
#   2. Dataset conversion (python finetune/convert_data.py)
#
# Usage:
#   bash finetune/run_sft.sh <MEGATRON_CKPT_DIR> [NGPU]
#
# GPU 0 가 vLLM 등에 물려있어 1,2,3 번만 쓰고 싶을 때:
#   CUDA_VISIBLE_DEVICES=1,2,3 bash finetune/run_sft.sh <ckpt>
#   (NGPU 는 CUDA_VISIBLE_DEVICES 개수로 자동 유도 → 3)
#
# Target env: 4x H200 single node. EP defaults to NGPU so expert parallel
# spans all GPUs (TP=1, PP=1, CP=1 from the recipe). Set EP env var to override.
#
# Env overrides:
#   EP                  expert parallel size (default NGPU)
#   DATASET_ROOT        SFT jsonl root (default data/sft)
#   SAVE_PATH           run dir (default nemo_experiments/hcdiff_nano3_lora)
#   EPOCHS              training epochs (default 3)
#   GLOBAL_BATCH_SIZE   global batch size (default 32)
#   HF_MODEL            HF repo id for AutoBridge + tokenizer
#   SEQ_LENGTH          context length (default 16384 — p95 커버. 낮추면
#                       overflow 샘플 증가해 output 잘림 위험 → truncation
#                       은 input left-trim 이므로 output 은 보존됨)
#   LORA_TARGETS        comma-separated LoRA target modules (optional)

set -euo pipefail

# Load .env (WANDB_API_KEY / WANDB_PROJECT / WANDB_ENTITY / WANDB_NAME etc.)
# so torchrun-spawned workers inherit them. Safe no-op if .env is missing.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PRETRAINED_CKPT="${1:?Path to converted Megatron checkpoint required}"

# CUDA_VISIBLE_DEVICES (e.g. "1,2,3" when GPU0 is taken by vLLM) 가 세팅되어 있고
# NGPU 가 positional 로 명시되지 않으면, 보이는 device 개수로 NGPU 를 자동 설정.
# 명시적으로 2번째 positional 이 주어지면 그 값을 우선.
if [ -n "${2:-}" ]; then
    NGPU="${2}"
elif [ -n "${CUDA_VISIBLE_DEVICES:-}" ]; then
    NGPU="$(awk -F, '{print NF}' <<< "${CUDA_VISIBLE_DEVICES}")"
else
    NGPU=4
fi
EP="${EP:-${NGPU}}"
DATASET_ROOT="${DATASET_ROOT:-data/sft}"
SAVE_PATH="${SAVE_PATH:-nemo_experiments/hcdiff_nano3_lora}"
EPOCHS="${EPOCHS:-3}"
GLOBAL_BATCH_SIZE="${GLOBAL_BATCH_SIZE:-32}"
HF_MODEL="${HF_MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
SEQ_LENGTH="${SEQ_LENGTH:-16384}"

CMD=(torchrun --nproc_per_node="${NGPU}" finetune/sft_nemotron_lora.py
    --pretrained-checkpoint "${PRETRAINED_CKPT}"
    --dataset-root "${DATASET_ROOT}"
    --save-path "${SAVE_PATH}"
    --hf-model "${HF_MODEL}"
    --epochs "${EPOCHS}"
    --global-batch-size "${GLOBAL_BATCH_SIZE}"
    --seq-length "${SEQ_LENGTH}"
    --expert-parallel-size "${EP}")

if [ -n "${LORA_TARGETS:-}" ]; then
    CMD+=(--lora-targets "${LORA_TARGETS}")
fi

set -x
"${CMD[@]}"

#!/usr/bin/env bash
# Convert a HuggingFace Nemotron checkpoint to Megatron format via AutoBridge.import_ckpt.
# No Megatron-Bridge repo clone needed; requires the `megatron-bridge` python package
# (present in NeMo Framework containers). Export HF_TOKEN if the HF repo is gated.
#
# Usage:
#   bash finetune/convert_hf_ckpt.sh [OUT_DIR] [HF_MODEL_ID]
#
# Defaults:
#   OUT_DIR       ./checkpoints/nemotron_3_nano_mcore
#   HF_MODEL_ID   nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16

set -euo pipefail

OUT_DIR="${1:-./checkpoints/nemotron_3_nano_mcore}"
HF_MODEL="${2:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"

python finetune/convert_hf_ckpt.py \
    --hf-model "${HF_MODEL}" \
    --megatron-path "${OUT_DIR}"

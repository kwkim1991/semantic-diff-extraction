#!/usr/bin/env bash
# Nemotron 3 Super — vLLM 서버 (별도 터미널에서 실행)
# 사용법: ./launch_nemotron_super.sh {bf16|fp8|nvfp4}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: launch_nemotron_super.sh {bf16|fp8|nvfp4}

  bf16   Option A — 4x H100 80GB (BF16)
  fp8    Option B — 2x H100 80GB (FP8)
  nvfp4  Option C — 1x B200 (NVFP4)

Reasoning parser와 작업 디렉터리는 이 스크립트가 있는 폴더(scripts/)에 둡니다.
EOF
  exit "${1:-0}"
}

case "${1:-}" in
  bf16|BF16|a|A)
    wget -nc "https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16/resolve/main/super_v3_reasoning_parser.py"
    exec vllm serve nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16 \
      --async-scheduling \
      --dtype auto \
      --kv-cache-dtype fp8 \
      --tensor-parallel-size 4 \
      --pipeline-parallel-size 1 \
      --data-parallel-size 1 \
      --swap-space 0 \
      --trust-remote-code \
      --gpu-memory-utilization 0.9 \
      --enable-chunked-prefill \
      --max-num-seqs 512 \
      --served-model-name nemotron \
      --host 0.0.0.0 \
      --port 5000 \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --reasoning-parser-plugin "./super_v3_reasoning_parser.py" \
      --reasoning-parser super_v3
    ;;
  fp8|FP8|b|B)
    wget -nc "https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8/resolve/main/super_v3_reasoning_parser.py"
    exec vllm serve nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8 \
      --async-scheduling \
      --dtype auto \
      --kv-cache-dtype fp8 \
      --tensor-parallel-size 2 \
      --attention-backend TRITON_ATTN \
      --gpu-memory-utilization 0.9 \
      --enable-chunked-prefill \
      --max-num-seqs 512 \
      --served-model-name nemotron \
      --host 0.0.0.0 \
      --port 5000 \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --reasoning-parser-plugin "./super_v3_reasoning_parser.py" \
      --reasoning-parser super_v3
    ;;
  nvfp4|NVFP4|c|C)
    wget -nc "https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4/resolve/main/super_v3_reasoning_parser.py"
    exec vllm serve nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 \
      --async-scheduling \
      --dtype auto \
      --kv-cache-dtype fp8 \
      --tensor-parallel-size 1 \
      --attention-backend TRITON_ATTN \
      --gpu-memory-utilization 0.9 \
      --enable-chunked-prefill \
      --max-num-seqs 512 \
      --served-model-name nemotron \
      --host 0.0.0.0 \
      --port 5000 \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --reasoning-parser-plugin "./super_v3_reasoning_parser.py" \
      --reasoning-parser super_v3
    ;;
  -h|--help|help) usage 0 ;;
  *)
    echo "Unknown option: ${1:-}" >&2
    usage 1
    ;;
esac

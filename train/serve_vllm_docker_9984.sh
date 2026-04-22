#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${IMAGE:-vllm/vllm-openai:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-vllm-server-9984}"

HOST_PORT="${HOST_PORT:-9984}"
CONTAINER_PORT="${CONTAINER_PORT:-8000}"

MODEL_BASE_DIR="${MODEL_BASE_DIR:-./hf_models}"
MODEL_SUBDIR="${MODEL_SUBDIR:-nvidia-nemotron-3-nano-4b-bf16}"
MODEL_PATH_IN_CONTAINER="/models/${MODEL_SUBDIR}"

HF_CACHE_DIR="${HF_CACHE_DIR:-$HOME/.cache/huggingface}"
HF_TOKEN="${HF_TOKEN:-}"

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-vllmlora}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"

TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-1}"
ENABLE_LORA="${ENABLE_LORA:-0}"
MAX_LORA_RANK="${MAX_LORA_RANK:-256}"

ENABLE_AUTO_TOOL_CHOICE="${ENABLE_AUTO_TOOL_CHOICE:-0}"
TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-hermes}"
TRUST_REQUEST_CHAT_TEMPLATE="${TRUST_REQUEST_CHAT_TEMPLATE:-0}"
STRUCTURED_OUTPUT_BACKEND="${STRUCTURED_OUTPUT_BACKEND:-outlines}"

ENABLE_LOG_REQUESTS="${ENABLE_LOG_REQUESTS:-0}"
ENABLE_LOG_OUTPUTS="${ENABLE_LOG_OUTPUTS:-0}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
ENABLE_PROMPT_TOKENS_DETAILS="${ENABLE_PROMPT_TOKENS_DETAILS:-0}"

QUANTIZATION="${QUANTIZATION:-}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-}"

EXTRA_ARGS=("$@")

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $1" >&2
    exit 1
  }
}

abs_path() {
  python3 - <<'PY' "$1"
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
}

need_cmd docker
need_cmd python3

MODEL_BASE_DIR_ABS="$(abs_path "$MODEL_BASE_DIR")"
HF_CACHE_DIR_ABS="$(abs_path "$HF_CACHE_DIR")"

if [[ ! -d "$MODEL_BASE_DIR_ABS" ]]; then
  echo "ERROR: MODEL_BASE_DIR does not exist: $MODEL_BASE_DIR_ABS" >&2
  exit 1
fi

if [[ ! -d "$MODEL_BASE_DIR_ABS/$MODEL_SUBDIR" ]]; then
  echo "ERROR: model directory does not exist: $MODEL_BASE_DIR_ABS/$MODEL_SUBDIR" >&2
  exit 1
fi

mkdir -p "$HF_CACHE_DIR_ABS"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Pulling image: $IMAGE"
  docker pull "$IMAGE"
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  echo "Removing existing container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

CMD_ARGS=(
  --model "$MODEL_PATH_IN_CONTAINER"
  --served-model-name "$SERVED_MODEL_NAME"
  --host "0.0.0.0"
  --port "$CONTAINER_PORT"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
)

if [[ "$TRUST_REMOTE_CODE" == "1" ]]; then
  CMD_ARGS+=(--trust-remote-code)
fi

if [[ "$ENABLE_LORA" == "1" ]]; then
  CMD_ARGS+=(--enable-lora --max-lora-rank "$MAX_LORA_RANK")
fi

if [[ "$ENABLE_AUTO_TOOL_CHOICE" == "1" ]]; then
  CMD_ARGS+=(--enable-auto-tool-choice --tool-call-parser "$TOOL_CALL_PARSER")
fi

if [[ "$TRUST_REQUEST_CHAT_TEMPLATE" == "1" ]]; then
  CMD_ARGS+=(--trust-request-chat-template)
fi

if [[ -n "$STRUCTURED_OUTPUT_BACKEND" ]]; then
  CMD_ARGS+=(--structured-outputs-config.backend "$STRUCTURED_OUTPUT_BACKEND")
fi

if [[ "$ENABLE_LOG_REQUESTS" == "1" ]]; then
  CMD_ARGS+=(--enable-log-requests)
fi

if [[ "$ENABLE_LOG_OUTPUTS" == "1" ]]; then
  CMD_ARGS+=(--enable-log-outputs)
fi

if [[ -n "$UVICORN_LOG_LEVEL" ]]; then
  CMD_ARGS+=(--uvicorn-log-level "$UVICORN_LOG_LEVEL")
fi

if [[ "$ENABLE_PROMPT_TOKENS_DETAILS" == "1" ]]; then
  CMD_ARGS+=(--enable-prompt-tokens-details)
fi

if [[ -n "$QUANTIZATION" ]]; then
  CMD_ARGS+=(--quantization "$QUANTIZATION")
fi

if [[ -n "$KV_CACHE_DTYPE" ]]; then
  CMD_ARGS+=(--kv-cache-dtype "$KV_CACHE_DTYPE")
fi

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD_ARGS+=("${EXTRA_ARGS[@]}")
fi

DOCKER_ARGS=(
  run -d
  --name "$CONTAINER_NAME"
  --restart unless-stopped
  --gpus device=1
  --ipc host
  -p "${HOST_PORT}:${CONTAINER_PORT}"
  -e NVIDIA_VISIBLE_DEVICES=all
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility
  -v "${MODEL_BASE_DIR_ABS}:/models"
  -v "${HF_CACHE_DIR_ABS}:/root/.cache/huggingface"
)

if [[ -n "$HF_TOKEN" ]]; then
  DOCKER_ARGS+=(-e "HF_TOKEN=${HF_TOKEN}")
fi

echo "Starting container: $CONTAINER_NAME"
echo "Image: $IMAGE"
echo "Model: $MODEL_BASE_DIR_ABS/$MODEL_SUBDIR"
echo "Port: ${HOST_PORT}->${CONTAINER_PORT}"

docker "${DOCKER_ARGS[@]}" "$IMAGE" "${CMD_ARGS[@]}"

echo
echo "Container started."
echo "Logs: docker logs -f $CONTAINER_NAME"
echo "OpenAI-compatible endpoint: http://localhost:${HOST_PORT}/v1"

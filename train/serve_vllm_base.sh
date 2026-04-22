#!/bin/bash

BASE_MODEL=$1

CHAT_TEMPLATE=
if [ ! -z $2 ] ; then
	CHAT_TEMPLATE=--chat-template $2
fi

export VLLM_LOG_LEVEL=DEBUG

set -x

vllm serve \
    --port 9983 \
	--served-model-name vllmlora \
	--model $BASE_MODEL \
	--trust-remote-code \
	--quantization fp8 \
	--kv-cache-dtype fp8 \
	--gpu-memory-utilization 0.85 \
	--enable-auto-tool-choice \
	--tool-call-parser hermes \
	--trust-request-chat-template $CHAT_TEMPLATE \
	--enable-lora \
	--max-lora-rank 256 \
	--structured-outputs-config.backend outlines \
	--enable-log-requests \
    --enable-log-outputs \
    --uvicorn-log-level=trace \
    --enable-prompt-tokens-details

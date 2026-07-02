#!/usr/bin/env bash
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="$NO_PROXY"
export OMP_NUM_THREADS=1

LOG_DIR="/root/autodl-tmp/text_to_sql_benchmarks/logs"
MODEL_PATH="/root/autodl-tmp/text_to_sql_benchmarks/models/Qwen3___5-4B"
VLLM_PY="/root/autodl-tmp/vllm-env/bin/python"

mkdir -p "$LOG_DIR"

exec "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" \
  --served-model-name "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --trust-remote-code \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.80

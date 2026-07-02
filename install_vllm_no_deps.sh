#!/usr/bin/env bash
set -euo pipefail

cd /root/autodl-tmp
LOG_DIR=/root/autodl-tmp/DeepEye-SQL/workspace/logs
mkdir -p "$LOG_DIR"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="$NO_PROXY"
export UV_HTTP_TIMEOUT=300
export PIP_DEFAULT_TIMEOUT=300

echo "[$(date -Is)] Starting vLLM no-deps install"
echo "Python: $(/root/autodl-tmp/vllm-env/bin/python --version)"

/root/autodl-tmp/vllm-env/bin/python -m ensurepip --upgrade || true
/root/autodl-tmp/vllm-env/bin/python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

if ! /root/autodl-tmp/vllm-env/bin/python -m pip install \
  --no-deps \
  --timeout 300 \
  --resume-retries 20 \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  vllm==0.10.2; then
  echo "[$(date -Is)] pip install failed, retrying with uv"
  uv pip install \
    --python /root/autodl-tmp/vllm-env/bin/python \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --no-deps \
    vllm==0.10.2
fi

/root/autodl-tmp/vllm-env/bin/python - <<'PY'
import vllm
print("VLLM_OK", vllm.__version__)
PY

echo "[$(date -Is)] vLLM install completed"

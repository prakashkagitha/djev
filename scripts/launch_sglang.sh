#!/usr/bin/env bash
# Usage: launch_sglang.sh MODEL_PATH DET(0|1) PORT [extra sglang args...]
# Serves one model on one GPU (default GPU 3) with SGLang 0.5.19 from ./.venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$1"; DET="$2"; PORT="$3"; shift 3
export PATH="$ROOT/.venv/bin:$PATH"
export CUDA_VISIBLE_DEVICES="${GPU:-3}"
export HF_HOME="${HF_HOME:-/local-ssd/hf_cache/}"
ARGS=(--model-path "$MODEL" --host 127.0.0.1 --port "$PORT" --dtype bfloat16 --tp 1
      --mem-fraction-static "${MEM:-0.80}" --attention-backend "${ATTN:-fa3}"
      --enable-cache-report --log-level "${LOGLEVEL:-warning}")
if [[ "$DET" == "1" ]]; then ARGS+=(--enable-deterministic-inference); fi
exec "$ROOT/.venv/bin/python" -m sglang.launch_server "${ARGS[@]}" "$@"

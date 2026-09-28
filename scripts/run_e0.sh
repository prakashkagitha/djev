#!/usr/bin/env bash
# E0: engine-level batch invariance, deterministic OFF vs ON, dense control and Nimble.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/
NIMBLE=$PWD/models/nimble-9b-merged
NIMBLE_ARGS=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
run() { # tag model det args...
  local tag=$1 model=$2 det=$3; shift 3
  scripts/serve_bg.sh "e0_$tag" "$model" "$det" 30010 "$@" || return 1
  .venv-api/bin/python replaykit/engine_probe.py --port 30010 --model "$model" \
     --out results/core/e0_$tag.json --targets 6 --trials 10 2>&1 | grep -v -i warn | tail -12
}
run qwen3_8b_det   Qwen/Qwen3-8B 1
run qwen3_8b_nodet Qwen/Qwen3-8B 0
run nimble_det     "$NIMBLE" 1 "${NIMBLE_ARGS[@]}"
run nimble_nodet   "$NIMBLE" 0 "${NIMBLE_ARGS[@]}"
echo E0_DONE

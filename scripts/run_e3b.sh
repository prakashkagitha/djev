#!/usr/bin/env bash
# E3b: patched SGLang (aligned fp32 mamba checkpoints + aligned splits), deterministic ON.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/
NIMBLE=$PWD/models/nimble-9b-merged
NIMBLE_ARGS=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh e3b_patched "$NIMBLE" 1 30010 "${NIMBLE_ARGS[@]}" || exit 1
(.venv-api/bin/python -m replaykit.pair_probe --port 30010 --model models/nimble-9b-merged --out results/core/e3b_pair_patched.json 2>&1 | grep -v -i warn | tail -12)
.venv-api/bin/python replaykit/engine_probe.py --port 30010 --model "$NIMBLE" --out results/core/e3b_nimble_det_patched.json --targets 6 --trials 10 2>&1 | grep -v -i warn | grep -E "^target"
echo E3B_DONE

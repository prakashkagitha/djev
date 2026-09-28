#!/usr/bin/env bash
# E3: fix batch-variance of hybrid (Gated DeltaNet) Nimble under deterministic mode.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/
NIMBLE=$PWD/models/nimble-9b-merged
NIMBLE_ARGS=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
probe() { .venv-api/bin/python replaykit/engine_probe.py --port 30010 --model "$NIMBLE" --out results/core/e3_$1.json --targets 6 --trials 10 2>&1 | grep -v -i warn | tail -3; }
ATTN=triton scripts/serve_bg.sh e3_triton "$NIMBLE" 1 30010 "${NIMBLE_ARGS[@]}" && probe nimble_det_triton
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh e3_fa3a64 "$NIMBLE" 1 30010 "${NIMBLE_ARGS[@]}" && probe nimble_det_fa3_align64
echo E3_DONE

#!/usr/bin/env bash
# E4 ablation: where does the deterministic throughput cost come from?
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
# (a) deterministic kernels, but stock mamba checkpointing and unaligned warm-up
SGLANG_DET_ALIGNED_MAMBA_CHECKPOINTS=0 scripts/serve_bg.sh c_det_stock "$NIMBLE" 1 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh c_det_stock
$PY replaykit/api_latency.py --api http://127.0.0.1:8020 --label det_on_stock_cache --out results/core/e4_det_on_stock_cache.json
# (b) non-deterministic kernels + our aligned warm-up (isolates the warm-up change)
scripts/serve_bg.sh c_off_aligned "$NIMBLE" 0 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=1 scripts/api_up.sh c_off_aligned
$PY replaykit/api_latency.py --api http://127.0.0.1:8020 --label det_off_aligned_warmup --out results/core/e4_det_off_aligned_warmup.json
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo COST_DONE

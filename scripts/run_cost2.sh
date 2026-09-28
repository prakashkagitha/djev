#!/usr/bin/env bash
# E4b: deterministic + aligned mamba checkpoints + aligned warm-up, WITHOUT fa3 split alignment.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
scripts/serve_bg.sh c_on_noalign "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh c_on_noalign
$PY replaykit/api_latency.py --api http://127.0.0.1:8020 --label det_on_noalign --out results/core/e4_det_on_noalign.json
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_on.json --label det_on_noalign --out results/core/e7_det_on_noalign.json
$PY replaykit/drift.py --api http://127.0.0.1:8020 --backend http://127.0.0.1:30020 --label det_on_noalign --loads 0,8,32 --targets 24 --repeats 10 --out results/core/e12_det_on_noalign.json
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo COST2_DONE

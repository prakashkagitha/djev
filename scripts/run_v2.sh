#!/usr/bin/env bash
# Deterministic Jev v2: skip the shared-prefix warm-up for single-question requests.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
scripts/serve_bg.sh v2 "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh det_on_v2
$PY replaykit/api_latency.py --api http://127.0.0.1:8020 --label det_on_v2 --out results/core/e4_det_on_v2.json
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_on.json --label det_on_v2 --out results/core/e7_det_on_v2.json
$PY replaykit/drift.py --api http://127.0.0.1:8020 --backend http://127.0.0.1:30020 --label det_on_v2 --loads 0,8,32 --targets 24 --repeats 10 --out results/core/e12_det_on_v2.json
$PY tasks/typesafe_consistency/legacy_cookbook.py --api http://127.0.0.1:8020 --label det_on_v2 --out results/core/e8_det_on_v2.json
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo V2_DONE

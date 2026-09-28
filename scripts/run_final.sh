#!/usr/bin/env bash
# Final config vs stock: determinism (drift, golden) and fair cost (cold + repeat passes).
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
B=http://127.0.0.1:30020; A=http://127.0.0.1:8020
# stock serving (upstream warm-up)
DETJEV_ALIGN_WARMUP=0 SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE= scripts/serve_bg.sh f_off "$NIMBLE" 0 30020 "${NA[@]}"
DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh f_off
$PY replaykit/api_latency.py --api $A --backend $B --repeat-pass --label off --out results/core/e4f_off.json
# final Deterministic Jev: patch + aligned splits + single-question fast path
export SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64
scripts/serve_bg.sh f_on "$NIMBLE" 1 30020 "${NA[@]}"
scripts/api_up.sh f_on
$PY replaykit/drift.py --api $A --backend $B --label final_on --loads 0,8,32 --targets 24 --repeats 10 --out results/core/e12_final_on.json
$PY replaykit/golden.py --api $A --verify results/core/golden_det_on.json --label final_on --out results/core/e7_final_on.json
$PY tasks/typesafe_consistency/legacy_cookbook.py --api $A --label final_on --out results/core/e8_final_on.json
$PY replaykit/api_latency.py --api $A --backend $B --repeat-pass --label on --out results/core/e4f_on.json
scripts/api_up.sh f_on_memo --memo 100000
$PY replaykit/api_latency.py --api $A --backend $B --repeat-pass --label on_memo --out results/core/e4f_on_memo.json
$PY replaykit/golden.py --api $A --verify results/core/golden_det_on.json --label final_on_memo --out results/core/e7_final_on_memo.json
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo FINAL_DONE

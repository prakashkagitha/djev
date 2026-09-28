#!/usr/bin/env bash
# E1 re-run (fixed flip metric), E7 golden/restart/second GPU, E6 invariance.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
until grep -q MAIN_DONE logs/run_main.out; do sleep 10; done
# E1 again: baseline drift with the corrected score-decision metric
DETJEV_ALIGN_WARMUP=0 SKIP_QUALITY=1 SKIP_COOKBOOK=1 SKIP_LATENCY=1 scripts/run_api.sh det_off 0 fa3
# E7: det_off golden across restart (contrast)
DETJEV_ALIGN_WARMUP=0 scripts/serve_bg.sh g_off1 "$NIMBLE" 0 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh g_off1
$PY replaykit/golden.py --api http://127.0.0.1:8020 --record results/core/golden_det_off.json
DETJEV_ALIGN_WARMUP=0 scripts/serve_bg.sh g_off2 "$NIMBLE" 0 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh g_off2
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_off.json --label det_off_restart --out results/core/e7_det_off_restart.json
# E7: det_on golden, restart, and invariance
export SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64
scripts/serve_bg.sh g_on1 "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh g_on1
$PY replaykit/golden.py --api http://127.0.0.1:8020 --record results/core/golden_det_on.json
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_on.json --label det_on_same_process --out results/core/e7_det_on_same.json
scripts/serve_bg.sh g_on2 "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh g_on2
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_on.json --label det_on_restart --out results/core/e7_det_on_restart.json
$PY replaykit/invariance.py --api http://127.0.0.1:8020 --label det_on --out results/core/e6_det_on.json
scripts/api_up.sh g_on2_canon --canonicalize
$PY replaykit/invariance.py --api http://127.0.0.1:8020 --label det_on_canonical --out results/core/e6_det_on_canonical.json
# E7: second GPU of the same SKU (GPU 4), brief and sequential
GPU=4 scripts/serve_bg.sh g_on_gpu4 "$NIMBLE" 1 30020 "${NA[@]}" && CUDA_VISIBLE_DEVICES=4 scripts/api_up.sh g_on_gpu4
$PY replaykit/golden.py --api http://127.0.0.1:8020 --verify results/core/golden_det_on.json --label det_on_gpu4 --out results/core/e7_det_on_gpu4.json
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
kill -- -"$(cat logs/api.pid)" 2>/dev/null
echo FOLLOW_DONE

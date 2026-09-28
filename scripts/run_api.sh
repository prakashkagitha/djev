#!/usr/bin/env bash
# Usage: run_api.sh TAG DET [ATTN] [extra sglang args]  -> results/core/e12_TAG.json, results/core/e5_TAG.json
# Starts Nimble-9B on SGLang (GPU ${GPU:-3}), the detjev API on :8020, then drift + quality.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
TAG=$1; DET=$2; export ATTN=${3:-fa3}; shift 3 || shift $#
NIMBLE=$PWD/models/nimble-9b-merged
ARGS=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193 "$@")
scripts/serve_bg.sh backend_$TAG "$NIMBLE" "$DET" 30020 "${ARGS[@]}" || exit 1
NIMBLE_MODEL_PATH=$NIMBLE setsid .venv-api/bin/python -m detjev.serve --backend http://127.0.0.1:30020 --port 8020 \
   ${CANON:+--canonicalize} > logs/api_$TAG.log 2>&1 < /dev/null &
API=$!
until curl -sf 127.0.0.1:8020/v1/fingerprint > /dev/null; do kill -0 $API || { tail logs/api_$TAG.log; exit 1; }; sleep 2; done
curl -s 127.0.0.1:8020/v1/fingerprint > results/core/fingerprint_$TAG.json
if [[ -z "${SKIP_DRIFT:-}" ]]; then
.venv-api/bin/python replaykit/drift.py --api http://127.0.0.1:8020 --backend http://127.0.0.1:30020 --label $TAG \
   --loads ${LOADS:-0,8,32} --targets ${TARGETS:-24} --repeats ${REPEATS:-10} --out results/core/e12_$TAG.json 2>&1 | grep -v -i warn
fi
if [[ -z "${SKIP_QUALITY:-}" ]]; then
.venv-api/bin/python tasks/nimble_holdout/quality.py --api http://127.0.0.1:8020 --label $TAG --out results/core/e5_$TAG.json 2>&1 | grep -v -i warn
fi
if [[ -z "${SKIP_COOKBOOK:-}" ]]; then
.venv-api/bin/python tasks/typesafe_consistency/legacy_cookbook.py --api http://127.0.0.1:8020 --label $TAG --out results/core/e8_$TAG.json 2>&1 | grep -v -i warn
fi
if [[ -z "${SKIP_LATENCY:-}" ]]; then
.venv-api/bin/python replaykit/api_latency.py --api http://127.0.0.1:8020 --label $TAG --out results/core/e4_$TAG.json 2>&1 | grep -v -i warn
fi
kill -- -$API 2>/dev/null
echo "RUN_DONE $TAG"

#!/usr/bin/env bash
# TypeSafe self-consistency cookbooks (their metrics) on djev and default serving.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh c_on "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh c_on
$PY -m tasks.typesafe_consistency.run --backend local --name djev
DETJEV_ALIGN_WARMUP=0 scripts/serve_bg.sh c_off "$NIMBLE" 0 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh c_off
$PY -m tasks.typesafe_consistency.run --backend local --name default-serving
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo CONS_DONE

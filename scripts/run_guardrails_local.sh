#!/usr/bin/env bash
# Guardrail suite on the local server: Deterministic Jev (final config) and the stock baseline.
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
NIMBLE=$PWD/models/nimble-9b-merged
NA=(--json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193)
PY=.venv-api/bin/python
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh gr_on "$NIMBLE" 1 30020 "${NA[@]}" && scripts/api_up.sh gr_on
$PY -m tasks.guardrails.run --backend local --name detjev --repeats 5 --concurrency 32
DETJEV_ALIGN_WARMUP=0 scripts/serve_bg.sh gr_off "$NIMBLE" 0 30020 "${NA[@]}" && DETJEV_ALIGN_WARMUP=0 scripts/api_up.sh gr_off
$PY -m tasks.guardrails.run --backend local --name stock-nimble --repeats 5 --concurrency 32
for f in logs/*.pid; do kill -- -"$(cat "$f")" 2>/dev/null; done
echo GR_LOCAL_DONE

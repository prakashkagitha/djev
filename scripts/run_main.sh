#!/usr/bin/env bash
# Main comparison: upstream-like non-deterministic serving vs Deterministic Jev.
cd "$(dirname "$0")/.."
DETJEV_ALIGN_WARMUP=0 scripts/run_api.sh det_off 0 fa3
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 DETJEV_ALIGN_WARMUP=1 scripts/run_api.sh det_on 1 fa3
echo MAIN_DONE

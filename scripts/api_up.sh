#!/usr/bin/env bash
# Usage: api_up.sh TAG [--canonicalize]   (backend must already listen on :30020)
cd "$(dirname "$0")/.."
export HF_HOME=/local-ssd/hf_cache/ PYTHONPATH=$PWD/nimble:$PWD:$PWD/server
[[ -f logs/api.pid ]] && kill -- -"$(cat logs/api.pid)" 2>/dev/null && sleep 2
NIMBLE_MODEL_PATH=$PWD/models/nimble-9b-merged setsid .venv-api/bin/python -m detjev.serve \
  --backend http://127.0.0.1:30020 --port 8020 "${@:2}" > logs/api_$1.log 2>&1 < /dev/null &
echo $! > logs/api.pid
until curl -sf 127.0.0.1:8020/v1/fingerprint > /dev/null; do sleep 2; done
curl -s 127.0.0.1:8020/v1/fingerprint > results/core/fingerprint_$1.json; echo "API up: $1"

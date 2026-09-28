#!/usr/bin/env bash
# Usage: serve_bg.sh NAME MODEL DET PORT [extra sglang args]
# Stops all servers recorded in logs/*.pid, launches detached, waits for /health.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$1"; MODEL="$2"; DET="$3"; PORT="$4"; shift 4
PIDF="$ROOT/logs/$NAME.pid"; LOG="$ROOT/logs/$NAME.log"
# One GPU: stop every server this project launched before starting a new one.
for f in "$ROOT"/logs/*.pid; do
  [[ -f "$f" ]] || continue
  kill -- -"$(cat "$f")" 2>/dev/null; sleep 5; kill -9 -- -"$(cat "$f")" 2>/dev/null; rm -f "$f" "$f.port"
done
setsid "$ROOT/scripts/launch_sglang.sh" "$MODEL" "$DET" "$PORT" "$@" > "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"; echo "$PORT" > "$PIDF.port"
until curl -sf "127.0.0.1:$PORT/health" > /dev/null; do
  if grep -q "Received sigquit\|^Traceback" "$LOG" || ! kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "FAILED: $NAME"; grep -E "^[A-Za-z]*Error" "$LOG" | tail -3; exit 1; fi
  sleep 3
done
echo "READY: $NAME on :$PORT (pid $(cat "$PIDF"))"

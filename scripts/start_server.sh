#!/usr/bin/env bash
# Start (or restart) Sorted in the background; logs go to data/server.log.
#   scripts/start_server.sh             start, keeping the current data
#   FT_RESET=1 scripts/start_server.sh  rebuild the demo data for today and start fresh
#   FT_PORT=8810 scripts/start_server.sh   use another port (default 8800)
# On Apple silicon the local model (Gemma 4 12B, about 7 GB, downloaded on first start) runs photos you upload;
# elsewhere, or with FT_CLASSIFIER=cache, only the demo's own photos are recognised.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${FT_PORT:-8800}"
EXTRA=""
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then EXTRA="--extra gemma"; else export FT_CLASSIFIER="${FT_CLASSIFIER:-cache}"; fi
pkill -f "uvicorn server:app --host 0.0.0.0 --port $PORT" 2>/dev/null || true
sleep 1
mkdir -p data
if [ "${FT_RESET:-0}" = "1" ] || [ ! -f seed/demo_incidents.json ]; then uv run $EXTRA python scripts/build_seed.py; fi
FT_CACHE_DELAY="${FT_CACHE_DELAY:-3}" nohup uv run $EXTRA uvicorn server:app --host 0.0.0.0 --port "$PORT" > data/server.log 2>&1 &
for _ in $(seq 1 60); do
  sleep 1
  if curl -s -m 2 "http://127.0.0.1:$PORT/api/config" | grep -q '"city"'; then
    echo "Sorted is running: public http://localhost:$PORT/   council http://localhost:$PORT/council"; exit 0
  fi
done
echo "The app did not start: see data/server.log"; exit 1

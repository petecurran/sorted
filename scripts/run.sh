#!/usr/bin/env bash
# Run Sorted in this terminal (Ctrl-C stops it).
#   scripts/run.sh             start as normal
#   FT_RESET=1 scripts/run.sh  rebuild the demo data for today and start fresh
#   FT_PORT=8810 scripts/run.sh   use another port (default 8800)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${FT_PORT:-8800}"
EXTRA=""
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then EXTRA="--extra gemma"; else export FT_CLASSIFIER="${FT_CLASSIFIER:-cache}"; fi
if [ "${FT_RESET:-0}" = "1" ] || [ ! -f seed/demo_incidents.json ]; then uv run $EXTRA python scripts/build_seed.py; fi
echo "Sorted: public http://localhost:$PORT/   council http://localhost:$PORT/council"
exec uv run $EXTRA uvicorn server:app --host 0.0.0.0 --port "$PORT"

#!/usr/bin/env sh
# The hosted copy's start command (Dockerfile): demo data for today, then the app on port 8800. The Worker in
# cloudflare/ starts a container like this for each visitor; see docs/HOSTING.md.
set -eu
cd "$(dirname "$0")/.."
python scripts/build_seed.py
exec uvicorn server:app --host 0.0.0.0 --port 8800 --no-access-log

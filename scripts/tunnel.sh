#!/usr/bin/env bash
# Share the running app with phones through a Cloudflare Quick Tunnel (no account needed).
# Start the app first with scripts/run.sh, then run this in a second terminal.
set -euo pipefail
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found; installing with Homebrew…"
  brew install cloudflared
fi
cat <<'TIP'

  Look below for a line like:   https://<random-words>.trycloudflare.com
  Open that on a phone (or turn it into a QR code). The council console is at /council.
  Quick Tunnels don't carry live streams, so the app polls. Press Ctrl-C to stop sharing.

TIP
exec cloudflared tunnel --url http://localhost:8800

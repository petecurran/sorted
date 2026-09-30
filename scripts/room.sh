#!/usr/bin/env bash
# The room's switches for the live demo. Each change applies at once, with no restart.
#   scripts/room.sh status          phones connected, requests a minute, the switches and the model's queue
#   scripts/room.sh off | on        off: every phone gets a thank-you and stops polling, which frees the wifi
#   scripts/room.sh close | open    close: phones can still watch the map but cannot report
#   scripts/room.sh pause | resume  pause: the room's photos wait for the model; yours still go straight through
#   scripts/room.sh kill            stop the Cloudflare tunnel, so nothing from phones reaches this laptop.
#                                   Run "off" first so open pages stop polling. A new tunnel has a new link.
#   scripts/room.sh tunnel          start a tunnel if none is running; print its link and make a QR code (data/tunnel-qr.png)
#   scripts/room.sh speed           test this laptop's connection (macOS networkQuality, about 20 seconds)
#   scripts/room.sh password [NEW]  show the council console's password for phones, or set a new one
set -euo pipefail
cd "$(dirname "$0")/.."

set_key() {  # set_key KEY VALUE: change one switch in content/config.json, keeping the file's layout
  python3 - "$1" "$2" <<'PY'
import json, re, sys
key, val = sys.argv[1], sys.argv[2]
p = "content/config.json"
s = open(p).read()
s2, n = re.subn(rf'("{key}"\s*:\s*)"[^"]*"', rf'\g<1>"{val}"', s, count=1)
if not n:
    sys.exit(f"{key} not found in {p}")
json.loads(s2)
open(p, "w").write(s2)
PY
  echo "$1 is now $2"
}

tunnel_url() { grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" data/tunnel.log 2>/dev/null | tail -1; }

case "${1:-status}" in
  status)
    curl -s -m 3 http://localhost:8800/api/room | python3 -c '
import json, sys
r = json.load(sys.stdin); m = r["model"]
p1, p10, req = r["phones_last_minute"], r["phones_last_10_minutes"], r["requests_last_minute"]
acc, up, ai = r["audience_access"], r["audience_uploads"], r["audience_ai"]
st, q, qa = m["status"], m["queue"], m.get("queue_audience", 0)
print(f"phones: {p1} in the last minute, {p10} in the last 10 minutes; {req} requests in the last minute")
print(f"room:   access {acc}, reporting {up}, their photos to the model {ai}")
print(f"model:  {st}, {q} in the queue ({qa} from the room)")' \
      || echo "app not answering on port 8800"
    if pgrep -f "cloudflared tunnel" >/dev/null; then
      url="$(tunnel_url)"
      # The process can be running while the wifi is down (phones then see Cloudflare error 1033), so test from outside.
      code="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$url/api/health" || true)"
      if [ "$code" = "200" ]; then echo "tunnel: running and reachable from outside, $url"
      else echo "tunnel: running but NOT reachable from outside ($code): wifi down? it reconnects by itself; see data/tunnel.log"; fi
    else echo "tunnel: not running (scripts/room.sh tunnel starts one)"; fi
    ;;
  off)    set_key audience_access off ;;
  on)     set_key audience_access on ;;
  close)  set_key audience_uploads off ;;
  open)   set_key audience_uploads on ;;
  pause)  set_key audience_ai paused ;;
  resume) set_key audience_ai on ;;
  kill)
    if pkill -f "cloudflared tunnel"; then echo "tunnel stopped: phones can no longer reach this laptop"; else echo "no tunnel was running"; fi
    ;;
  tunnel)
    if pgrep -f "cloudflared tunnel" >/dev/null; then
      echo "a tunnel is already running: $(tunnel_url)"
    else
      nohup cloudflared tunnel --url http://localhost:8800 --no-autoupdate > data/tunnel.log 2>&1 &
      for _ in $(seq 1 30); do sleep 1; [ -n "$(tunnel_url)" ] && break; done
      url="$(tunnel_url)"
      [ -n "$url" ] || { echo "no link yet: see data/tunnel.log"; exit 1; }
      uv run --quiet --with "qrcode[pil]" python -c "import qrcode; qrcode.make('$url').save('data/tunnel-qr.png')"
      echo "new tunnel: $url (QR code in data/tunnel-qr.png)"
    fi
    ;;
  speed)  networkQuality -s ;;
  password)
    if [ -n "${2:-}" ]; then printf '%s\n' "$2" > data/council_password.txt; echo "council password changed (phones must sign in again)"
    else cat data/council_password.txt 2>/dev/null || echo "not set yet: it is made the first time a phone signs in"; fi
    ;;
  *)      sed -n 2,12p "$0"; exit 1 ;;
esac

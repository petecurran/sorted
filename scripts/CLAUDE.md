# scripts/

Run everything from the repo root. Several of these start or stop servers, or rewrite data, so check the right-hand columns before running one.

| Script | What it does | Needs | Changes |
|---|---|---|---|
| `run.sh` | Runs the app in the foreground on `FT_PORT` (8800) | uv; the model only on Apple silicon | With `FT_RESET=1`, the database and the seed data |
| `start_server.sh` | The same in the background, logging to `data/server.log` | as above | Kills whatever is on the port first |
| `build_seed.py` | Makes the simulated reports, the cached readings and the phone-sized photos, dated from today | nothing | `seed/demo_incidents.json`, `history.json`, `model_cache.json`, `photos_web/` |
| `build_kit.py` | Writes GPS into the five demo-kit photos | nothing | `seed/live_demo/*.jpg`; run `build_seed.py` after it |
| `build_geo.py` | Rebuilds the map layers | raw extracts in `data/raw/land/`, not in git | `seed/*.geojson` |
| `demo_places.py` | The fixed places the seed and the kit share; a module, not a script | | |
| `brand_check.py` | Checks every page at desktop and phone sizes and makes a contact sheet | a running app (`--base`), Google Chrome, `uv run --with playwright` | `data/brand_check/` only |
| `screenshots.py` | Takes the README's screenshots | a throwaway app with fresh data on another port, Chrome, Playwright | That app's data, `content/brand.json` for a minute (it always puts it back), `docs/screenshots/` |
| `room.sh` | The live demo's switches: status, pause, close, off, tunnel, password | a running app on 8800 | `content/config.json`, `data/council_password.txt` |
| `tunnel.sh` | Shares the app through a Cloudflare Quick Tunnel | `cloudflared` (installs it with Homebrew) | Nothing, but it puts the app on the internet |
| `hosted_start.sh` | The hosted demo's start command, inside its container (`Dockerfile`, `docs/HOSTING.md`) | the container | The container's own seed data and database |

- **The model needs the laptop to itself.** Two copies of the 12B model don't fit in 16 GB. Before running `evals/run.py`, stop the app or restart it with `FT_CLASSIFIER=cache`.
- **`FT_RESET=1` wipes the database and uploads.** Don't use it on a running demo you want to keep.
- **`screenshots.py` changes the data it runs against.** Start a fresh copy for it (`/screenshots` does this) and never point it at the demo on 8800.
- **Don't run `tunnel.sh` or `room.sh tunnel` unless asked.** Either one makes the laptop reachable from the internet.

# Running and changing Sorted

The README shows what Sorted does. This page is for running it yourself and finding your way around the code.

## Running it

You need [uv](https://docs.astral.sh/uv/). It installs the right Python (3.13) for you.

```bash
git clone https://github.com/petecurran/sorted.git
cd sorted
FT_RESET=1 scripts/run.sh
```

The public site is at http://localhost:8800 and the council console at http://localhost:8800/council. On the machine running it, any password signs in.

`FT_RESET=1` wipes the database and rebuilds the demo data for today, so the newest reports are always from the last few hours. Leave it off to carry on where you left off. `scripts/start_server.sh` does the same in the background and logs to `data/server.log`.

### The model

On an Apple silicon Mac, the app downloads and runs Gemma 4 12B (the 4-bit MLX build `mlx-community/gemma-4-12B-it-4bit`, about 7 GB) the first time it starts. It needs 16 GB of memory and takes about 14 seconds a photo on an M2 Pro.

Anywhere else, or with `FT_CLASSIFIER=cache`, it runs without a model. The demo's own photos still work, because their readings are cached by the photo's fingerprint in `seed/model_cache.json`. A photo it hasn't seen is marked "Model offline. Check the photo." and goes to a person. To read new photos on other machines, `classifier.py` would need another backend, such as Ollama or a hosted vision API.

## How the pieces fit

| Step | Code |
|---|---|
| A resident reports a photo. The location comes from the photo's GPS, the phone or a pin. The photo is re-saved without its metadata. | `static/public/`, `photos.py`, `incidents.py` |
| The model reads the photo, one at a time, with the presenter's photos first. A photo it has seen is answered from the cache. | `classifier.py` |
| The rules decide the next step, in order: specialist for hazards, not fly-tipping if a bulky collection is booked there today, officer for bags and trade waste, otherwise a crew. If the model thinks it isn't fly-tipping, a person checks. | `triage.py`, `content/triage_rules.json` |
| Whose job it is: the council, a private landowner, Network Rail within 20 m of railway land, National Highways on its roads, or a neighbouring council over the boundary. | `content/whose_job.json`, `geo.py` |
| Priority: hazards, repeat sites, "still there" confirmations and reports growing week on week come first. | `priority.py` |
| Crew and officer routes from the depot, urgent stops first, with a Google Maps link and QR code. | `routes.py` |
| The WasteDataFlow return for the quarter, with a CSV laid out like the form. | `wdf_return.py` |
| Repeat hotspots, a 12-week trend and a prevention action for each. | `hotspots.py`, `content/reduce.json` |
| The API that ties it together, and the two front ends. | `server.py`, `static/` |

## The demo data

`scripts/build_seed.py` makes the demo data from the photos in `seed/photos` and their labels in `seed/cases/labels.json`. Everything is dated relative to the day it runs:

- `seed/history.json`: two years of simulated past reports on real Liverpool streets, with repeat hotspots, repeats near earlier reports, a June peak when students move out, and more reports after weekends;
- `seed/demo_incidents.json`: one case per photo, with a simulated place, date and resident's title. Fourteen need action, four are booked, and the rest were closed over the past five months;
- `seed/model_cache.json`: the reading of every photo, taken from its label.

The start scripts run it on `FT_RESET=1` or when those files don't exist yet. They're not in git, because they change every day. The fixed places the demo relies on (the hotspots, and where the demo kit photos land) are in `scripts/demo_places.py`. `scripts/build_kit.py` makes the demo kit photos in `seed/live_demo/`.

## Changing it

- **Rules, words and numbers** live in `content/*.json`. Edits show on the next page load, with no restart. `content/README.md` explains each file.
- **Rebranding** is `content/brand.json`: the council's name, colours, case prefix and an optional crest drawn in `static/shared/marks/`. `scripts/brand_check.py` then checks every page at desktop and phone sizes, and writes a contact sheet to http://localhost:8800/dev/brand-check/.
- **The model's prompt** is in `classifier.py`. `scripts/gemma_eval.py` runs a model over photos, and `scripts/gemma_score.py` scores its answers against the labels.
- **Screenshots** for the README come from `scripts/screenshots.py`, run against a copy with fresh data.

## Settings

| Setting | What it does |
|---|---|
| `FT_PORT` | The port for `scripts/run.sh` and `start_server.sh`. Default 8800. |
| `FT_RESET=1` | Wipe the data and rebuild it for today. |
| `FT_CLASSIFIER` | `gemma` (the default on Apple silicon), `cache` (cached readings only) or `off`. |
| `FT_MODEL` | Another model id for MLX. |
| `FT_TODAY` | Fix the date, as `YYYY-MM-DD`. The DEFRA quarter follows it. |
| `FT_OSRM_URL` | An OSRM server for the Routes tab. The default is the public demo server, which allows light use only. |
| `FT_DATA_DIR` | Where the database and uploads go. Default `data/`. |

## Phones and the room

The machine running Sorted is trusted: any password opens the council console there. Everyone else is remote, whether that's a phone through a tunnel or a visitor to a hosted copy. Remote users get the public site, and the console asks for a password, which is made the first time someone signs in and stored in `data/council_password.txt`. `scripts/room.sh` has the switches used at the demo. `seed/live_demo/LIVE_DEMO.md` explains them and gives a running order.

## Tests

```bash
uv run python tests/test_units.py
FT_CLASSIFIER=cache uv run python tests/smoke.py
```

The smoke test rebuilds the demo data, starts its own server on port 8810 with a throwaway database, and checks every endpoint.

## Before real use

- Real staff sign-in and roles, and a record of who changed what.
- Data protection: photos can show people and number plates, and reports carry locations and contact details. That means a data protection impact assessment, a privacy notice and retention rules.
- Production services: a paid map tile provider instead of OpenStreetMap's servers, your own OSRM routing server, and proper hosting instead of a Cloudflare Quick Tunnel. The fonts could be hosted locally instead of loading from Google.
- Testing the model on the council's own photos, with a person checking its decisions.

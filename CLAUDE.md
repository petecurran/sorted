# Sorted

Fly-tipping reporting and triage for councils. A resident photographs dumped rubbish, a vision model on the council's own laptop reads the photo, and the council's rules decide what happens next. It was built in a day at a policy hackathon for a demo, and it's finished: keep it working end to end on a fresh clone, and don't grow it into a product. It's good enough for a demo, not for real use; `docs/TECHNICAL.md` ("Before real use") lists the gaps.

## Commands

```bash
uv sync                                            # everything except the model
uv sync --extra gemma                              # plus the local model (Apple silicon only, about 7 GB)
FT_RESET=1 scripts/run.sh                          # the demo on http://localhost:8800, with fresh data for today
uv run python tests/test_units.py                  # seconds: no server, no model
FT_CLASSIFIER=cache uv run python tests/smoke.py   # its own server on 8810 and a throwaway database
uv run ruff check . && uv run ruff format --check .
```

Skills in `.claude/skills/`: `/check` runs all of the above, `/reset` restarts the demo with fresh data, `/rebrand` re-skins it for another council and checks every page, `/screenshots` retakes the README's images, and `/eval` measures a prompt with the model.

## How a report flows

`photos.py` strips the photo's metadata. `classifier.py` reads it (the cache first, then the model, one photo at a time) into DEFRA WasteDataFlow categories. `triage.py` applies `content/triage_rules.json` to decide the next step, and `content/whose_job.json` with `geo.py` to decide who must clear it. `priority.py` orders the queue, and `incidents.py` owns each report's state and timeline in SQLite (`db.py`). `server.py` is the API and the trust rule's gate (`trust.py`), and `static/` holds the two front ends. The Routes, Return and Reduce tabs come from `routes.py`, `wdf_return.py` and `hotspots.py`.

## Rules, and what checks each one

| # | Rule | Checked by |
|---|---|---|
| 1 | The model returns a reading and never a decision. Every decision comes from `triage.run` and names its rule ([decision 2](docs/decisions/0002-model-reads-rules-decide.md)). | `tests/test_units.py` triage cases |
| 2 | The model alone never closes a report: a "no" or "unsure" goes to a person. The only automatic close is a bulky collection booked there today. | unit: "model alone says no"; smoke: "model alone never auto-closes a report" |
| 3 | Only the laptop running the app is trusted without a password (`trust.py`, [decision 4](docs/decisions/0004-laptop-trust-rule.md)). Remote callers reach only what `server.py` allows through the tunnel; a new endpoint stays council-only unless added there. Never grant access because of a header. | unit and smoke: every "trust:" check |
| 4 | Residents never see cost, or that an officer is involved: the public API carries only `triage.decision`. Mersey Vale stands in for Liverpool City Council, which the app never names. | smoke: "no cost fields", "public triage hides…", "no Liverpool City Council in API" |
| 5 | DEFRA categories and ward names are spelt exactly as in `common.py` and `seed/wards.geojson`. The rules skip a misspelt one without complaint. | unit: "content names" |
| 6 | A prompt change is measured before it ships: a new `evals/prompts/vN.txt`, a run on the dev and holdout photos, and updated tables in `docs/EVALS.md`. | unit: "evals:" checks |
| 7 | Labels are ground truth. A person changes one by looking at the photo, never to move a score. | `.claude/hooks/protect_paths.py` |
| 8 | Generated and third-party files aren't edited by hand: the seed data, eval runs, past prompts, `data/`, `static/vendor/` and `uv.lock`. | `.claude/hooks/protect_paths.py` |
| 9 | Python is formatted and linted with ruff, and every edited JSON file parses. | `.claude/hooks/check_edit.py`, `/check` |

The hooks cover Claude's file tools only. They're a guardrail for the agent, not a security boundary: a shell command can still change those files.

## Traps

Nothing checks these, and each one fails quietly.

- **One server worker, one model thread.** MLX streams belong to the thread that made them, and two copies of the 12B model don't fit in 16 GB. Stop the app, or restart it with `FT_CLASSIFIER=cache`, before `evals/run.py`.
- **A broken content file keeps its last good copy**, so the edit looks as if it did nothing.
- **A photo's bytes are its identity.** The cache and the evals both key photos by SHA-256, so re-saving a photo breaks its cached reading and its measurement.
- **The demo kit moves as one.** The GPS in `seed/live_demo/` photos, the hotspots and the merge target all come from `scripts/demo_places.py`. After changing a place, run `scripts/build_kit.py`, then `scripts/build_seed.py`.
- **`FT_RESET=1` wipes the demo database.** The smoke test uses its own; `/screenshots` starts its own copy on 8811.
- **Use `localhost` or `127.0.0.1`.** Any other name for the laptop, such as its network address, counts as remote.
- **`scripts/tunnel.sh` and `scripts/room.sh tunnel` put the laptop on the internet.** Settings make Claude ask before running either.

## Where to look

Each of `content/`, `evals/`, `scripts/`, `seed/` and `static/` has its own `CLAUDE.md`, which loads when you work there. `docs/TECHNICAL.md` covers running it and the settings, `docs/EVALS.md` how good the model is, and `docs/decisions/` the calls that shaped it. `NOTICE.md` credits every data source and licence, so add a row for any new data. `seed/live_demo/LIVE_DEMO.md` is the running order for a live demo.

## Writing

- `README.md` is written by hand. Suggest changes to it; don't restructure or rewrite it.
- British English, and no em dashes, in the app's words and in the docs.
- Everything is fictional or credited. Mersey Vale City Council is made up, and there are no real reports, people or council branding.

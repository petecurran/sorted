# seed/

The demo's photos, labels, map layers and simulated data. Some of it is source and some is generated; never hand-edit the generated files.

| Path | What it is | Made by |
|---|---|---|
| `photos/case_NNN_before.jpg`, `_after.jpg` | AI-generated photos of each case, before and after clearing | Committed |
| `cases/labels.json` | What each photo shows, set by a person looking at it | Committed, by hand |
| `live_demo/` | The five demo-kit photos, with GPS written in, and `LIVE_DEMO.md` | `scripts/build_kit.py` |
| `*.geojson` | Streets, wards, boundaries and railway and National Highways land | `scripts/build_geo.py`, from sources in `NOTICE.md` |
| `demo_incidents.json`, `history.json`, `model_cache.json`, `photos_web/` | The simulated reports and cached readings, dated relative to today | `scripts/build_seed.py`, not in git |

- **`cases/labels.json` is ground truth twice over.** The seed builder turns it into each case's reading, and `evals/score.py` scores the model against it. Change a label only by looking at the photo, never to move a score. A label change moves the eval results, so re-score and say so in `docs/EVALS.md`. The edit hook blocks agents from changing it.
- **A photo's bytes are its identity.** The cache and the evals both key photos by SHA-256. Re-saving a photo, even losslessly, breaks its cached reading and means the shipped prompt is no longer measured on it (`tests/test_units.py` fails). Rebuild the seed and re-run the evals after changing any photo.
- **The kit photos and the simulated places move together.** The GPS in each `live_demo/` photo, the hotspots and the merge target all come from `scripts/demo_places.py`. After changing a place, run `build_kit.py`, then `build_seed.py`.
- **Everything here is fictional or credited.** No real report, no real person, and no real council's name or crest. The licence for each map layer is in `NOTICE.md`; add a row there for any new file.

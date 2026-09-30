# 5. Demo photos are answered from a cache, and the evaluation never uses it

Accepted for the demo.

## Context

The model needs an Apple silicon Mac, a 7 GB download and about 14 seconds a photo ([decision 1](0001-local-model.md)). Someone trying Sorted on another machine, the smoke test, and a presenter who can't wait 14 seconds on stage all need the demo photos to work without it.

## Decision

`seed/model_cache.json` maps the SHA-256 fingerprint of each demo photo to its reading, taken from its label. `classifier.py` checks the cache before the model. With `FT_CLASSIFIER=cache`, or on a machine without MLX, the model never loads: a photo that isn't in the cache is marked "Model offline. Check the photo." and goes to a person. On stage, the five demo-kit photos came from the cache, with a three-second pause (`FT_CACHE_DELAY`) so the "Checking…" step still showed; the audience's photos went to the model.

## Consequences

- The whole app, and every test, runs on any machine.
- Because the cache comes from the labels, a cached reading is right by construction and says nothing about the model. `evals/run.py` always calls the model and never reads the cache.
- The fingerprint covers the photo's exact bytes. If a phone re-saves or resizes a demo photo, it no longer matches and the model reads it live (`seed/live_demo/LIVE_DEMO.md`).
- The cache is rebuilt with the rest of the demo data by `scripts/build_seed.py`, so it's never edited by hand.
